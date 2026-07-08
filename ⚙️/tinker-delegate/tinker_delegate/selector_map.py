"""Bounded Tinker browser selector and frame contract.

The map is safe to print in logs or attach to deployment evidence: it records
declared selectors, expected frame matchers, and evidence status, but never live
page text, account identifiers, OTPs, cards, API keys, cookies, or browser URLs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

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
