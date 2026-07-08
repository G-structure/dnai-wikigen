"""Bounded Tinker browser selector and frame contract.

The map is safe to print in logs or attach to deployment evidence: it records
declared selectors, expected frame matchers, and evidence status, but never live
page text, account identifiers, OTPs, cards, API keys, cookies, or browser URLs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from tinker_delegate.browser_ready import connect_chromium, get_browser_context
from tinker_delegate.billing import (
    ADD_BALANCE_AMOUNT_SELECTORS,
    ADD_BALANCE_CONFIRM_SELECTORS,
    ADD_BALANCE_DIALOG_SELECTORS,
    ADD_PAYMENT_METHOD_SELECTORS,
    ADD_TO_BALANCE_SELECTORS,
    ADDRESS_FIELD_SELECTORS,
    AUTO_RELOAD_AMOUNT_SELECTORS,
    AUTO_RELOAD_SAVE_SELECTORS,
    AUTO_RELOAD_THRESHOLD_SELECTORS,
    AUTO_RELOAD_TOGGLE_SELECTORS,
    BILLING_BALANCE_URL,
    CARDHOLDER_NAME_SELECTORS,
    PAYMENT_METHODS_SELECTORS,
    STRIPE_CARD_CVC_SELECTORS,
    STRIPE_CARD_EXPIRY_SELECTORS,
    STRIPE_CARD_NUMBER_SELECTORS,
    STRIPE_FRAME_MATCHERS,
)
from tinker_delegate.config import Settings
from tinker_delegate.signup import (
    API_KEY_CLOSE_SELECTORS,
    API_KEY_CONFIRM_SELECTORS,
    API_KEY_CREATE_SELECTORS,
    AUTH_EMAIL_SELECTORS,
    AUTH_FIRST_NAME_SELECTORS,
    AUTH_LAST_NAME_SELECTORS,
    AUTH_SIGNUP_LINK_SELECTORS,
    AUTH_SUBMIT_SELECTORS,
    ONBOARDING_CONTINUE_SELECTORS,
    ONBOARDING_FULL_NAME_SELECTORS,
    ONBOARDING_TOS_SELECTORS,
    OTP_INPUT_SELECTORS,
)

SELECTOR_MAP_VERSION = "2026-07-08.1"
DEPLOYED_SELECTOR_EVIDENCE_STATUS = "pending_deployed_cvm_capture"
PROBE_VERSION = "2026-07-08.1"
COUNT_BAND_CAP = 2


def _family(name: str, selectors: tuple[str, ...], *, required: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "required": required,
        "selector_count": len(selectors),
        "selectors": list(selectors),
    }


def _flow(name: str, *, evidence: str, families: list[dict[str, Any]], notes: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "evidence": evidence,
        "families": families,
        "notes": notes or [],
    }


def build_selector_map(*, include_selectors: bool = True) -> dict[str, Any]:
    """Return the bounded selector/frame map for current Tinker automation."""

    address_families = [
        _family(f"billing_{field}", selectors, required=field != "address_country")
        for field, selectors in ADDRESS_FIELD_SELECTORS
    ]
    flows = [
        _flow(
            "email_auth",
            evidence="local_neko_validated_phala_bounded_failure",
            families=[
                _family("email_input", AUTH_EMAIL_SELECTORS),
                _family("submit_email", AUTH_SUBMIT_SELECTORS),
                _family("signup_link", AUTH_SIGNUP_LINK_SELECTORS, required=False),
                _family("signup_first_name", AUTH_FIRST_NAME_SELECTORS, required=False),
                _family("signup_last_name", AUTH_LAST_NAME_SELECTORS, required=False),
            ],
            notes=[
                "Local Neko/CDP reached Tinker OTP auth.",
                "Latest Phala one-shot reached bounded tinker_auth failure without raw page evidence.",
            ],
        ),
        _flow(
            "magic_code_otp",
            evidence="local_neko_validated_oracle_otp",
            families=[
                _family("otp_inputs", OTP_INPUT_SELECTORS),
            ],
            notes=["OTP values are consumed through the email oracle and are not exposed by this map."],
        ),
        _flow(
            "onboarding",
            evidence="local_neko_validated",
            families=[
                _family("full_name", ONBOARDING_FULL_NAME_SELECTORS),
                _family("tos_label", ONBOARDING_TOS_SELECTORS, required=False),
                _family("continue", ONBOARDING_CONTINUE_SELECTORS),
            ],
        ),
        _flow(
            "api_keys",
            evidence="local_neko_validated_mock_replay_tested",
            families=[
                _family("create_key", API_KEY_CREATE_SELECTORS),
                _family("confirm_key_generation", API_KEY_CONFIRM_SELECTORS, required=False),
                _family("close_key_dialog", API_KEY_CLOSE_SELECTORS, required=False),
            ],
            notes=["Raw API keys are sealed by the signup path and represented only by hashes/status metadata."],
        ),
        _flow(
            "billing_payment_method",
            evidence="local_test_card_reached_stripe_submission_mock_replay_tested",
            families=[
                _family("open_add_balance", ADD_TO_BALANCE_SELECTORS, required=False),
                _family("payment_methods_tab", PAYMENT_METHODS_SELECTORS, required=False),
                _family("add_payment_method", ADD_PAYMENT_METHOD_SELECTORS),
                _family("cardholder_name", CARDHOLDER_NAME_SELECTORS),
                *address_families,
            ],
            notes=["Card details are intentionally absent; payment-method receipts are bounded."],
        ),
        _flow(
            "stripe_card_iframe",
            evidence="local_test_card_reached_stripe_submission_mock_replay_tested",
            families=[
                _family("stripe_frame_matchers", STRIPE_FRAME_MATCHERS),
                _family("stripe_card_number", STRIPE_CARD_NUMBER_SELECTORS),
                _family("stripe_card_expiry", STRIPE_CARD_EXPIRY_SELECTORS),
                _family("stripe_card_cvc", STRIPE_CARD_CVC_SELECTORS),
            ],
            notes=["Stripe iframe selectors are shape-only and contain no card data."],
        ),
        _flow(
            "balance_top_up",
            evidence="local_add_balance_policy_and_selector_mock_replay_tested",
            families=[
                _family("open_add_balance", ADD_TO_BALANCE_SELECTORS),
                _family("add_balance_dialog", ADD_BALANCE_DIALOG_SELECTORS, required=False),
                _family("add_balance_amount", ADD_BALANCE_AMOUNT_SELECTORS),
                _family("confirm_add_balance", ADD_BALANCE_CONFIRM_SELECTORS),
            ],
        ),
        _flow(
            "auto_reload",
            evidence="selector_declared_not_live_validated",
            families=[
                _family("auto_reload_toggle", AUTO_RELOAD_TOGGLE_SELECTORS),
                _family("auto_reload_threshold", AUTO_RELOAD_THRESHOLD_SELECTORS, required=False),
                _family("auto_reload_amount", AUTO_RELOAD_AMOUNT_SELECTORS, required=False),
                _family("auto_reload_save", AUTO_RELOAD_SAVE_SELECTORS, required=False),
            ],
            notes=["Auto-reload remains a declared selector surface; it has not been promoted to production funding."],
        ),
    ]
    payload: dict[str, Any] = {
        "version": SELECTOR_MAP_VERSION,
        "surface": "tinker_console_and_stripe_billing",
        "raw_secret_egress": False,
        "bounded_output": True,
        "deployed_cvm_selector_evidence": DEPLOYED_SELECTOR_EVIDENCE_STATUS,
        "urls": {
            "billing_balance": BILLING_BALANCE_URL,
            "auth": "https://auth.thinkingmachines.ai/",
            "console": "https://tinker-console.thinkingmachines.ai/",
            "api_keys": "https://tinker-console.thinkingmachines.ai/keys",
        },
        "flows": flows,
    }
    if not include_selectors:
        for flow in payload["flows"]:
            for family in flow["families"]:
                family.pop("selectors", None)
    payload["selector_map_hash"] = selector_map_hash(payload)
    return payload


def selector_map_hash(payload: dict[str, Any]) -> str:
    """Hash the map while excluding the self-referential hash field."""

    clone = {key: value for key, value in payload.items() if key != "selector_map_hash"}
    encoded = json.dumps(clone, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _count_band(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    return f"{COUNT_BAND_CAP}+"


def _classify_url(url: str) -> str:
    """Return a coarse public route class without emitting the raw URL."""

    try:
        parsed = urlparse(url or "")
    except Exception:
        return "unknown"
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "auth.thinkingmachines.ai" in host:
        return "tinker_auth_magic_code" if "magic-code" in path else "tinker_auth"
    if "tinker-console.thinkingmachines.ai" in host:
        if "billing" in path:
            return "tinker_console_billing"
        if "keys" in path:
            return "tinker_console_keys"
        if "onboarding" in path:
            return "tinker_console_onboarding"
        return "tinker_console"
    if "stripe" in host:
        return "stripe"
    if not url:
        return "empty"
    return "other"


def _frame_kind(frame: Any) -> str:
    url = str(getattr(frame, "url", "") or "")
    name = str(getattr(frame, "name", "") or "")
    if "elements-inner-card" in url or "StripeFrame" in name:
        return "stripe_card"
    return _classify_url(url)


async def _selector_count_band(scope: Any, selectors: list[str]) -> str:
    total = 0
    for selector in selectors:
        try:
            locator = scope.locator(selector)
            total += int(await locator.count())
        except Exception:
            return "probe_error"
        if total >= COUNT_BAND_CAP:
            return f"{COUNT_BAND_CAP}+"
    return _count_band(total)


async def probe_selector_map_context(context: Any, *, issued_at: int | None = None) -> dict[str, Any]:
    """Inspect current browser pages/frames without navigation or raw content egress."""

    selector_map = build_selector_map(include_selectors=True)
    pages = list(getattr(context, "pages", []) or [])
    page_results = []
    for page_index, page in enumerate(pages[:5]):
        page_url = str(getattr(page, "url", "") or "")
        page_result: dict[str, Any] = {
            "page_index": page_index,
            "url_class": _classify_url(page_url),
            "url_hash": _hash_text(page_url) if page_url else "",
            "flow_observations": [],
            "frame_observations": [],
        }
        for flow in selector_map["flows"]:
            family_observations = []
            for family in flow["families"]:
                if family["name"] == "stripe_frame_matchers":
                    continue
                family_observations.append(
                    {
                        "name": family["name"],
                        "required": family["required"],
                        "match_band": await _selector_count_band(page, family.get("selectors", [])),
                    }
                )
            present_required = sum(
                1
                for item in family_observations
                if item["required"] and item["match_band"] not in {"0", "probe_error"}
            )
            page_result["flow_observations"].append(
                {
                    "name": flow["name"],
                    "present_required_families": present_required,
                    "family_observations": family_observations,
                }
            )

        frames = list(getattr(page, "frames", []) or [])
        for frame_index, frame in enumerate(frames[:10]):
            frame_observation: dict[str, Any] = {
                "frame_index": frame_index,
                "kind": _frame_kind(frame),
                "url_class": _classify_url(str(getattr(frame, "url", "") or "")),
            }
            if frame_observation["kind"] == "stripe_card":
                frame_observation["stripe_field_observations"] = [
                    {
                        "name": "stripe_card_number",
                        "match_band": await _selector_count_band(frame, list(STRIPE_CARD_NUMBER_SELECTORS)),
                    },
                    {
                        "name": "stripe_card_expiry",
                        "match_band": await _selector_count_band(frame, list(STRIPE_CARD_EXPIRY_SELECTORS)),
                    },
                    {
                        "name": "stripe_card_cvc",
                        "match_band": await _selector_count_band(frame, list(STRIPE_CARD_CVC_SELECTORS)),
                    },
                ]
            page_result["frame_observations"].append(frame_observation)
        page_results.append(page_result)

    return {
        "version": PROBE_VERSION,
        "selector_map_hash": selector_map["selector_map_hash"],
        "surface": selector_map["surface"],
        "issued_at": int(issued_at if issued_at is not None else time.time()),
        "raw_secret_egress": False,
        "bounded_output": True,
        "read_only": True,
        "success": True,
        "page_count_band": _count_band(len(pages)),
        "pages_observed": len(page_results),
        "pages": page_results,
    }


async def probe_live_selector_map(settings: Settings | None = None) -> dict[str, Any]:
    """Connect to the configured browser and run a read-only bounded probe."""

    if settings is None:
        settings = Settings()
    async with async_playwright() as playwright:
        browser = await connect_chromium(playwright, settings)
        context = await get_browser_context(browser)
        return await probe_selector_map_context(context)


def run_live_selector_map_probe(settings: Settings | None = None) -> dict[str, Any]:
    return asyncio.run(probe_live_selector_map(settings))
