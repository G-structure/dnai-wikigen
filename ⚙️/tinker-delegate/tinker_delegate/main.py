"""CLI entrypoint for tinker-delegate automation."""
import argparse
import asyncio
import getpass
import json
import os
import time
import sys
from pathlib import Path
from typing import Any

from tinker_delegate.api_key_store import build_api_key_store
from tinker_delegate.config import Settings
from tinker_delegate.oracle_client import OracleClient
from tinker_delegate.redaction import redact_text
from tinker_delegate.runtime_hardening import disable_core_dumps
from tinker_delegate.runtime_state import reset_runtime_state, update_runtime_state
from tinker_delegate.signup import AuthAccessBlockedError


def _render_bounded_json(
    payload: Any,
    *,
    forbidden_values: tuple[str, ...] = (),
    public_hex_fields: tuple[str, ...] = (),
    public_decimal_fields: tuple[str, ...] = (),
) -> str:
    """Render JSON only if it does not contain obvious secret-shaped material."""
    rendered = json.dumps(payload, indent=2, default=str)
    redaction_payload = _mask_public_fields(
        payload,
        public_hex_fields=public_hex_fields,
        public_decimal_fields=public_decimal_fields,
    )
    redaction_rendered = json.dumps(redaction_payload, indent=2, default=str)
    if redact_text(redaction_rendered) != redaction_rendered:
        raise ValueError("bounded CLI output contains secret-like material")
    for value in forbidden_values:
        if value and len(value) >= 4 and value in rendered:
            raise ValueError("bounded CLI output contains submitted secret material")
    return rendered


def _mask_public_fields(
    payload: Any,
    *,
    public_hex_fields: tuple[str, ...],
    public_decimal_fields: tuple[str, ...],
) -> Any:
    """Mask explicitly public fields before generic secret-shape checks."""

    if not public_hex_fields and not public_decimal_fields:
        return payload
    hex_allowed = set(public_hex_fields)
    decimal_allowed = set(public_decimal_fields)
    if isinstance(payload, dict):
        return {
            key: (
                f"__public_hex_{key}__"
                if key in hex_allowed and isinstance(value, str) and value.startswith("0x")
                else (
                    f"__public_decimal_{key}__"
                    if key in decimal_allowed and isinstance(value, int)
                    else _mask_public_fields(
                        value,
                        public_hex_fields=public_hex_fields,
                        public_decimal_fields=public_decimal_fields,
                    )
                )
            )
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [
            _mask_public_fields(
                item,
                public_hex_fields=public_hex_fields,
                public_decimal_fields=public_decimal_fields,
            )
            for item in payload
        ]
    return payload


def _emit_bounded_json(
    payload: Any,
    *,
    output_path: str = "",
    forbidden_values: tuple[str, ...] = (),
    public_hex_fields: tuple[str, ...] = (),
    public_decimal_fields: tuple[str, ...] = (),
) -> None:
    rendered = _render_bounded_json(
        payload,
        forbidden_values=forbidden_values,
        public_hex_fields=public_hex_fields,
        public_decimal_fields=public_decimal_fields,
    )
    if output_path:
        Path(output_path).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def _receipt_or_raise(response: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        response = response.model_dump(mode="json")
    receipt = response.get("attempt_record") if isinstance(response, dict) else None
    if not isinstance(receipt, dict):
        raise ValueError("bounded receipt output requested, but response has no attempt_record")
    return receipt


def _prompt_billing_card_payload(prompt_fn=getpass.getpass) -> dict[str, str]:
    """Read card fields without placing them in shell history or argv."""
    fields = (
        ("card_number", "Card number", ""),
        ("exp_month", "Expiration month", ""),
        ("exp_year", "Expiration year", ""),
        ("cvc", "CVC", ""),
        ("cardholder_name", "Cardholder name", ""),
        ("address_line1", "Billing address line 1 (optional)", ""),
        ("address_city", "Billing city (optional)", ""),
        ("address_state", "Billing state/region (optional)", ""),
        ("address_postal", "Billing postal code (optional)", ""),
        ("address_country", "Billing country", "US"),
    )
    payload = {}
    for key, label, default in fields:
        suffix = f" [{default}]" if default else ""
        value = prompt_fn(f"{label}{suffix}: ").strip()
        payload[key] = value or default
    return payload


def _validate_prompt_billing_policy(args) -> None:
    """Require a concrete deployed attestation policy for prompt-based card entry."""
    if args.allow_local_attestation:
        return
    missing = [
        flag
        for flag, attr in (
            ("--compose-hash", "compose_hash"),
            ("--app-id", "app_id"),
            ("--os-image-hash", "os_image_hash"),
        )
        if not getattr(args, attr, "")
    ]
    if missing:
        joined = ", ".join(missing)
        command = getattr(args, "command", "prompt billing")
        raise ValueError(
            f"{command} requires deployed billing attestation expectations "
            f"({joined}) unless --allow-local-attestation is set for local development"
        )


def _wait_for_oracle(settings: Settings) -> None:
    """Wait until the email oracle reports a healthy inbox."""
    oracle = OracleClient(settings)
    deadline = time.time() + settings.bootstrap_oracle_timeout

    while time.time() < deadline:
        try:
            health = oracle.health()
            if health.get("imap_connected") and health.get("oracle_email"):
                print(f"[serve] oracle ready: {health['oracle_email']}")
                return
            print(f"[serve] oracle not ready yet: {health}")
        except Exception as exc:
            print(f"[serve] oracle check failed: {redact_text(exc)}")

        time.sleep(settings.bootstrap_oracle_poll_interval)

    raise RuntimeError(
        f"oracle did not become ready within {settings.bootstrap_oracle_timeout}s"
    )


async def _ensure_api_key(settings: Settings) -> None:
    """Load or bootstrap the Tinker API key before serving."""
    if os.environ.get("TINKER_API_KEY"):
        print("[serve] using TINKER_API_KEY from environment")
        update_runtime_state(
            api_key_available=True,
            api_key_source="environment",
            bootstrap_attempted=False,
            bootstrap_success=False,
            bootstrap_error="",
            bootstrap_error_kind="",
        )
        return

    store = build_api_key_store(settings)
    if store.exists():
        try:
            api_key = store.load()
        except Exception as exc:
            raise RuntimeError(f"failed to load stored API key: {redact_text(exc)}") from exc
        if api_key:
            print(f"[serve] loaded stored API key from {settings.api_key_store_path}")
            update_runtime_state(
                api_key_available=True,
                api_key_source="encrypted_store",
                bootstrap_attempted=False,
                bootstrap_success=False,
                bootstrap_error="",
                bootstrap_error_kind="",
            )
            return

    if not settings.bootstrap_signup:
        print("[serve] no Tinker API key configured or stored")
        update_runtime_state(
            api_key_available=False,
            api_key_source="none",
            bootstrap_attempted=False,
            bootstrap_success=False,
            bootstrap_error="",
            bootstrap_error_kind="",
        )
        return

    _wait_for_oracle(settings)
    print("[serve] no API key found, running signup bootstrap...")
    from tinker_delegate.signup import signup

    update_runtime_state(
        api_key_available=False,
        api_key_source="bootstrap",
        bootstrap_attempted=True,
        bootstrap_success=False,
        bootstrap_error="",
        bootstrap_error_kind="",
    )

    result = await signup(settings)
    if not result.get("stored"):
        raise RuntimeError("signup bootstrap did not store an API key")

    print(f"[serve] bootstrap complete, API key stored at {settings.api_key_store_path}")
    update_runtime_state(
        api_key_available=True,
        api_key_source="bootstrap",
        bootstrap_attempted=True,
        bootstrap_success=True,
        bootstrap_error="",
        bootstrap_error_kind="",
    )


def cli():
    disable_core_dumps()
    parser = argparse.ArgumentParser(description="Tinker delegate — automated account management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check oracle health and email readiness")
    sub.add_parser("signup", help="Full signup: auth → onboarding → API key")
    sub.add_parser("signin", help="Sign in to existing account")
    sub.add_parser("reauth", help="Refresh Tinker auth through OTP and return bounded receipt")
    synthetic_reward_p = sub.add_parser(
        "synthetic-private-reward-demo",
        help="Run a bounded synthetic hidden-dataset private reward demo",
    )
    synthetic_reward_p.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Candidate keyword to query; repeat for multiple candidates",
    )
    synthetic_reward_p.add_argument("--output", default="", help="Optional output path for bounded JSON")

    # Billing commands
    sub.add_parser("balance", help="Get current Tinker account balance")
    sub.add_parser("funding-policy", help="Print bounded Tinker funding-mode policy")

    funding_preflight_p = sub.add_parser(
        "funding-preflight",
        help="Check operator funding validation readiness without card material",
    )
    funding_preflight_p.add_argument(
        "--amount",
        type=float,
        default=None,
        help="Planned add-balance amount in USD to check against the configured cap",
    )
    funding_preflight_p.add_argument(
        "--require-add-balance-endpoint",
        action="store_true",
        help="Require POST /billing/add-balance to be explicitly enabled",
    )
    funding_preflight_p.add_argument(
        "--api-url",
        default="",
        help="Tinker delegate API base URL for billing attestation preflight",
    )
    funding_preflight_p.add_argument(
        "--compose-hash",
        default="",
        help="Expected dstack compose hash for billing attestation",
    )
    funding_preflight_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    funding_preflight_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash",
    )
    funding_preflight_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development preflight only",
    )
    funding_preflight_p.add_argument(
        "--fetch-attestation",
        action="store_true",
        help="Live-fetch and verify /attestation?context=billing",
    )
    funding_preflight_p.add_argument("--output", default="", help="Optional output path for preflight JSON")

    encumbrance_preflight_p = sub.add_parser(
        "tinker-encumbrance-preflight",
        help="Check TinkerAccountEncumbrance policy without card material or browser launch",
    )
    encumbrance_preflight_p.add_argument(
        "--operation",
        required=True,
        choices=("add-payment-method", "add-balance", "spend-tinker-compute", "manual-prefund"),
        help="Tinker account operation to check",
    )
    encumbrance_preflight_p.add_argument(
        "--amount",
        type=float,
        default=None,
        help="USD amount to map into policy units for add-balance checks",
    )
    encumbrance_preflight_p.add_argument(
        "--amount-wei",
        type=int,
        default=None,
        help="Explicit policy amount in wei-style units; overrides --amount",
    )
    encumbrance_preflight_p.add_argument(
        "--compose-hash",
        default="",
        help="Compose hash to check; defaults to TINKER_ENCUMBRANCE_COMPOSE_HASH",
    )
    encumbrance_preflight_p.add_argument(
        "--contract-address",
        default="",
        help="TinkerAccountEncumbrance address; defaults to TINKER_ENCUMBRANCE_CONTRACT_ADDRESS",
    )
    encumbrance_preflight_p.add_argument(
        "--rpc-url",
        default="",
        help="JSON-RPC URL; defaults to TINKER_ENCUMBRANCE_RPC_URL or TINKER_CHAIN_RPC_URL",
    )
    encumbrance_preflight_p.add_argument(
        "--required",
        action="store_true",
        help="Fail closed if no encumbrance contract is configured",
    )
    encumbrance_preflight_p.add_argument("--output", default="", help="Optional output path for preflight JSON")

    funding_manifest_p = sub.add_parser(
        "funding-manifest",
        help="Build a bounded funding validation manifest from preflight and receipt JSON",
    )
    funding_manifest_p.add_argument("--preflight-json", required=True, help="Path to saved funding-preflight JSON")
    funding_manifest_p.add_argument("--receipt-json", required=True, help="Path to bounded funding receipt JSON")
    funding_manifest_p.add_argument("--validation-id", default="", help="Operator-local validation run ID to hash")
    funding_manifest_p.add_argument("--compose-hash", default="", help="Expected compose hash to bind by hash")
    funding_manifest_p.add_argument("--app-id", default="", help="Expected app ID to bind by hash")
    funding_manifest_p.add_argument("--os-image-hash", default="", help="Expected OS image hash to bind by hash")
    funding_manifest_p.add_argument("--output", default="", help="Optional output path for manifest JSON")

    verify_funding_manifest_p = sub.add_parser(
        "verify-funding-manifest",
        help="Verify a bounded funding manifest against saved preflight and receipt JSON",
    )
    verify_funding_manifest_p.add_argument("--preflight-json", required=True, help="Path to saved funding-preflight JSON")
    verify_funding_manifest_p.add_argument("--receipt-json", required=True, help="Path to bounded funding receipt JSON")
    verify_funding_manifest_p.add_argument("--manifest-json", required=True, help="Path to saved funding manifest JSON")
    verify_funding_manifest_p.add_argument("--validation-id", default="", help="Operator-local validation run ID to hash")
    verify_funding_manifest_p.add_argument("--compose-hash", default="", help="Expected compose hash bound by hash")
    verify_funding_manifest_p.add_argument("--app-id", default="", help="Expected app ID bound by hash")
    verify_funding_manifest_p.add_argument("--os-image-hash", default="", help="Expected OS image hash bound by hash")
    verify_funding_manifest_p.add_argument(
        "--require-ready",
        action="store_true",
        help="Require the saved preflight to be ready",
    )
    verify_funding_manifest_p.add_argument(
        "--allow-card-retention-flag",
        action="store_true",
        help="Do not require no_raw_card_retained=true; development/debug only",
    )
    verify_funding_manifest_p.add_argument("--output", default="", help="Optional output path for verification JSON")

    validation_packet_p = sub.add_parser(
        "funding-validation-packet",
        help="Create a bounded preflight/receipt/manifest/verification packet",
    )
    validation_packet_p.add_argument("--output-dir", required=True, help="Directory for bounded packet JSON artifacts")
    validation_packet_p.add_argument("--api-url", required=True, help="Tinker delegate API base URL")
    validation_packet_p.add_argument("--amount", type=float, default=None, help="Planned add-balance amount in USD")
    validation_packet_p.add_argument("--compose-hash", default="", help="Expected dstack compose hash")
    validation_packet_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    validation_packet_p.add_argument("--os-image-hash", default="", help="Expected dstack OS image hash")
    validation_packet_p.add_argument("--validation-id", default="", help="Operator-local validation run ID to hash")
    validation_packet_p.add_argument("--receipt-json", default="", help="Existing bounded receipt JSON to bind")
    validation_packet_p.add_argument(
        "--add-balance-receipt-json",
        default="",
        help="Existing bounded add-balance receipt JSON to bind",
    )
    validation_packet_p.add_argument(
        "--require-add-balance-endpoint",
        action="store_true",
        help="Require POST /billing/add-balance to be explicitly enabled",
    )
    validation_packet_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode billing attestation for development only",
    )
    validation_packet_p.add_argument(
        "--fetch-attestation",
        action="store_true",
        help="Live-fetch and verify /attestation?context=billing during preflight",
    )
    validation_packet_p.add_argument(
        "--run-card-attempt",
        action="store_true",
        help="Explicitly run encrypted card submission; requires card fields",
    )
    validation_packet_p.add_argument(
        "--prompt-card",
        action="store_true",
        help="Prompt interactively for card fields instead of reading card fields from argv",
    )
    validation_packet_p.add_argument(
        "--run-add-balance-attempt",
        action="store_true",
        help="Explicitly POST amount to /billing/add-balance and bind the bounded receipt",
    )
    validation_packet_p.add_argument("--number", default="", help="Test-card number; requires --run-card-attempt")
    validation_packet_p.add_argument("--exp-month", default="", help="Test-card expiration month; requires --run-card-attempt")
    validation_packet_p.add_argument("--exp-year", default="", help="Test-card expiration year; requires --run-card-attempt")
    validation_packet_p.add_argument("--cvc", default="", help="Test-card CVC/CVV; requires --run-card-attempt")
    validation_packet_p.add_argument("--name", default="", help="Test-card cardholder name; requires --run-card-attempt")
    validation_packet_p.add_argument("--address-line1", default="", help="Address line 1")
    validation_packet_p.add_argument("--address-city", default="", help="City")
    validation_packet_p.add_argument("--address-state", default="", help="State")
    validation_packet_p.add_argument("--address-postal", default="", help="Postal code")
    validation_packet_p.add_argument("--address-country", default="US", help="Country (default: US)")

    packet_check_p = sub.add_parser(
        "check-funding-validation-packet",
        help="Replay-check a bounded funding validation packet directory",
    )
    packet_check_p.add_argument("--packet-dir", required=True, help="Funding validation packet directory")
    packet_check_p.add_argument("--validation-id", default="", help="Operator-local validation run ID to hash")
    packet_check_p.add_argument("--compose-hash", default="", help="Expected compose hash bound by hash")
    packet_check_p.add_argument("--app-id", default="", help="Expected app ID bound by hash")
    packet_check_p.add_argument("--os-image-hash", default="", help="Expected OS image hash bound by hash")
    packet_check_p.add_argument(
        "--require-add-balance",
        action="store_true",
        help="Require add-balance receipt, manifest, and verification files",
    )
    packet_check_p.add_argument(
        "--require-deployed-attestation",
        action="store_true",
        help="Require preflight evidence that billing attestation was live-verified as TDX",
    )
    packet_check_p.add_argument("--output", default="", help="Optional output path for checker JSON")

    add_card_p = sub.add_parser("add-card", help="Add payment method (card) to Tinker account")
    add_card_p.add_argument("--number", required=True, help="Card number")
    add_card_p.add_argument("--exp-month", required=True, help="Expiration month (01-12)")
    add_card_p.add_argument("--exp-year", required=True, help="Expiration year (26 or 2026)")
    add_card_p.add_argument("--cvc", required=True, help="CVC/CVV code")
    add_card_p.add_argument("--name", required=True, help="Cardholder name")
    add_card_p.add_argument("--address-line1", default="", help="Address line 1")
    add_card_p.add_argument("--address-city", default="", help="City")
    add_card_p.add_argument("--address-state", default="", help="State")
    add_card_p.add_argument("--address-postal", default="", help="Postal code")
    add_card_p.add_argument("--address-country", default="US", help="Country (default: US)")
    add_card_p.add_argument("--receipt-output", default="", help="Optional output path for bounded receipt JSON")

    add_bal_p = sub.add_parser("add-balance", help="Add credit balance to Tinker account")
    add_bal_p.add_argument("amount", type=float, help="Amount in USD to add")
    add_bal_p.add_argument("--receipt-output", default="", help="Optional output path for bounded receipt JSON")

    add_card_encrypted_p = sub.add_parser(
        "add-card-encrypted",
        help="Verify attestation, encrypt card details, and POST /billing/card/encrypted",
    )
    add_card_encrypted_p.add_argument("api_url", help="Tinker delegate API base URL")
    add_card_encrypted_p.add_argument("--number", required=True, help="Card number")
    add_card_encrypted_p.add_argument("--exp-month", required=True, help="Expiration month (01-12)")
    add_card_encrypted_p.add_argument("--exp-year", required=True, help="Expiration year (26 or 2026)")
    add_card_encrypted_p.add_argument("--cvc", required=True, help="CVC/CVV code")
    add_card_encrypted_p.add_argument("--name", required=True, help="Cardholder name")
    add_card_encrypted_p.add_argument("--address-line1", default="", help="Address line 1")
    add_card_encrypted_p.add_argument("--address-city", default="", help="City")
    add_card_encrypted_p.add_argument("--address-state", default="", help="State")
    add_card_encrypted_p.add_argument("--address-postal", default="", help="Postal code")
    add_card_encrypted_p.add_argument("--address-country", default="US", help="Country (default: US)")
    add_card_encrypted_p.add_argument(
        "--compose-hash",
        default="",
        help="Expected dstack compose hash; required unless --allow-local-attestation is set",
    )
    add_card_encrypted_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    add_card_encrypted_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash",
    )
    add_card_encrypted_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development only",
    )
    add_card_encrypted_p.add_argument("--receipt-output", default="", help="Optional output path for bounded receipt JSON")

    add_card_encrypted_prompt_p = sub.add_parser(
        "add-card-encrypted-prompt",
        help="Prompt for card details, verify attestation, encrypt, and POST /billing/card/encrypted",
    )
    add_card_encrypted_prompt_p.add_argument("api_url", help="Tinker delegate API base URL")
    add_card_encrypted_prompt_p.add_argument(
        "--compose-hash",
        default="",
        help="Expected dstack compose hash; required unless --allow-local-attestation is set",
    )
    add_card_encrypted_prompt_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    add_card_encrypted_prompt_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash; required unless --allow-local-attestation is set",
    )
    add_card_encrypted_prompt_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development only; do not use for real cards",
    )
    add_card_encrypted_prompt_p.add_argument(
        "--receipt-output",
        default="",
        help="Optional output path for bounded receipt JSON",
    )

    upload_artifact_p = sub.add_parser(
        "upload-artifact",
        help="Verify attestation, encrypt an artifact, and upload it to a deal",
    )
    upload_artifact_p.add_argument("api_url", help="Tinker delegate API base URL")
    upload_artifact_p.add_argument("deal_id", help="Deal ID to receive the artifact")
    upload_artifact_p.add_argument("artifact_path", help="Path to artifact file")
    upload_artifact_p.add_argument(
        "--compose-hash",
        default="",
        help="Expected dstack compose hash; required unless --allow-local-attestation is set",
    )
    upload_artifact_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    upload_artifact_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash",
    )
    upload_artifact_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development only",
    )

    verify_attestation_p = sub.add_parser(
        "verify-attestation",
        help="Fetch /attestation and verify public TEE evidence against policy",
    )
    verify_attestation_p.add_argument("api_url", help="Tinker delegate API base URL")
    verify_attestation_p.add_argument(
        "--compose-hash",
        default="",
        help="Expected dstack compose hash; required unless --allow-local-attestation is set",
    )
    verify_attestation_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    verify_attestation_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash",
    )
    verify_attestation_p.add_argument("--context", default="artifact", help="Expected report context")
    verify_attestation_p.add_argument(
        "--max-age-seconds",
        type=float,
        default=60.0,
        help="Maximum client-side age for fetched evidence",
    )
    verify_attestation_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development only",
    )

    verify_cvm_attestation_p = sub.add_parser(
        "verify-cvm-attestation",
        help="Verify digest-pinned compose input against a live CVM attestation",
    )
    verify_cvm_attestation_p.add_argument("api_url", help="Tinker delegate API base URL")
    verify_cvm_attestation_p.add_argument("--compose", required=True, help="Docker Compose file")
    verify_cvm_attestation_p.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Environment file used by docker compose config; repeatable",
    )
    verify_cvm_attestation_p.add_argument(
        "--allowed-env-file",
        default="",
        help="Runtime env file whose keys should be included as allowed_envs",
    )
    verify_cvm_attestation_p.add_argument(
        "--allowed-env",
        action="append",
        default=[],
        help="Runtime env key included as an encrypted Phala allowed_env; repeatable",
    )
    verify_cvm_attestation_p.add_argument(
        "--phala-raw-compose",
        action="store_true",
        help="Hash raw compose source plus allowed_envs, matching Phala deploy",
    )
    verify_cvm_attestation_p.add_argument(
        "--expected-compose-hash",
        default="",
        help="Expected Phala compose hash before checking live attestation",
    )
    verify_cvm_attestation_p.add_argument(
        "--attested-compose-hash",
        default="",
        help="Expected live attestation compose hash when Phala's full app-compose hash differs from local image-policy hash",
    )
    verify_cvm_attestation_p.add_argument("--app-id", default="", help="Expected dstack app ID")
    verify_cvm_attestation_p.add_argument(
        "--os-image-hash",
        default="",
        help="Expected dstack OS image hash",
    )
    verify_cvm_attestation_p.add_argument(
        "--require-image",
        action="append",
        default=[],
        help="Exact digest-pinned image reference required in rendered compose; repeatable",
    )
    verify_cvm_attestation_p.add_argument(
        "--require-image-digest",
        action="append",
        default=[],
        help="Required sha256 image digest in rendered compose; repeatable",
    )
    verify_cvm_attestation_p.add_argument(
        "--context",
        default="artifact",
        help="Expected attestation report context",
    )
    verify_cvm_attestation_p.add_argument(
        "--max-age-seconds",
        type=float,
        default=60.0,
        help="Maximum client-side age for fetched evidence",
    )
    verify_cvm_attestation_p.add_argument(
        "--allow-local-attestation",
        action="store_true",
        help="Allow local-mode attestation for development only",
    )
    verify_cvm_attestation_p.add_argument(
        "--allow-tags",
        action="store_true",
        help="Allow mutable tag images in compose verification; development only",
    )

    verify_compose_p = sub.add_parser(
        "verify-compose-hash",
        help="Render a registry-image compose file and compute its Phala compose hash",
    )
    verify_compose_p.add_argument("--compose", required=True, help="Docker Compose file to render")
    verify_compose_p.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Environment file used by docker compose config; repeatable",
    )
    verify_compose_p.add_argument(
        "--allowed-env-file",
        default="",
        help="Runtime env file whose keys should be included as allowed_envs",
    )
    verify_compose_p.add_argument(
        "--allowed-env",
        action="append",
        default=[],
        help="Runtime env key included as an encrypted Phala allowed_env; repeatable",
    )
    verify_compose_p.add_argument(
        "--phala-raw-compose",
        action="store_true",
        help="Hash raw compose source plus allowed_envs, matching Phala deploy",
    )
    verify_compose_p.add_argument("--expected-hash", default="", help="Expected Phala compose hash")
    verify_compose_p.add_argument(
        "--allow-tags",
        action="store_true",
        help="Allow mutable tag images; development only",
    )

    watch_chain_p = sub.add_parser(
        "watch-chain",
        help="Watch DiligenceRoom events and notify the TEE control-plane API",
    )
    watch_chain_p.add_argument("--rpc-url", default="", help="JSON-RPC URL, or TINKER_CHAIN_RPC_URL")
    watch_chain_p.add_argument(
        "--contract-address",
        default="",
        help="DiligenceRoom address, or TINKER_CHAIN_CONTRACT_ADDRESS",
    )
    watch_chain_p.add_argument(
        "--api-url",
        default="",
        help="TEE control-plane API URL, or TINKER_CHAIN_CONTROL_PLANE_URL",
    )
    watch_chain_p.add_argument(
        "--from-block",
        default="",
        help="First block to scan; omit to start at the current safe tip",
    )
    watch_chain_p.add_argument("--poll-interval", type=float, default=None, help="Polling interval in seconds")
    watch_chain_p.add_argument("--confirmations", type=int, default=None, help="Confirmation depth")
    watch_chain_p.add_argument(
        "--cursor-store",
        default="",
        help="Durable cursor JSON path, or TINKER_CHAIN_CURSOR_STORE_PATH",
    )
    watch_chain_p.add_argument(
        "--no-cursor",
        action="store_true",
        help="Disable durable cursor storage for one-off local probes",
    )
    watch_chain_p.add_argument(
        "--cursor-summary",
        action="store_true",
        help="Print bounded cursor summary and exit without polling",
    )
    watch_chain_p.add_argument("--once", action="store_true", help="Poll one range and exit")

    submit_result_p = sub.add_parser(
        "submit-result",
        help="Broadcast DiligenceRoom.submitResult from the dstack-derived TEE signer",
    )
    submit_result_p.add_argument("deal_id", type=int, help="DiligenceRoom deal ID")
    submit_result_p.add_argument(
        "score_band",
        help="Bounded score band: negligible, low, medium, high, or exceptional",
    )
    submit_result_p.add_argument("compute_cost_wei", type=int, help="Bounded compute cost in wei")
    submit_result_p.add_argument(
        "result_hash",
        help="bytes32 hash of the bounded result payload; the CLI submits an anti-replay commitment",
    )
    submit_result_p.add_argument(
        "--authorization-expiry",
        type=int,
        required=True,
        help="Unix timestamp after which the verifier authorization is invalid",
    )
    submit_result_p.add_argument(
        "--verifier-signature",
        required=True,
        help="65-byte verifier signature over the DiligenceRoom result authorization digest",
    )
    submit_result_p.add_argument("--rpc-url", default="", help="JSON-RPC URL, or TINKER_CHAIN_RPC_URL")
    submit_result_p.add_argument(
        "--contract-address",
        default="",
        help="DiligenceRoom address, or TINKER_CHAIN_CONTRACT_ADDRESS",
    )
    submit_result_p.add_argument(
        "--gas-limit",
        type=int,
        default=None,
        help="Optional gas limit override; defaults to TINKER_CHAIN_SUBMIT_GAS_LIMIT or eth_estimateGas",
    )

    verifier_address_p = sub.add_parser(
        "result-verifier-address",
        help="Print the dstack-derived DiligenceRoom result verifier address",
    )
    verifier_address_p.add_argument("--output", default="", help="Optional JSON output path")

    authorize_result_p = sub.add_parser(
        "authorize-result",
        help="Issue a bounded verifier authorization for DiligenceRoom.submitResult",
    )
    authorize_result_p.add_argument("deal_id", type=int, help="DiligenceRoom deal ID")
    authorize_result_p.add_argument(
        "score_band",
        help="Bounded score band: negligible, low, medium, high, or exceptional",
    )
    authorize_result_p.add_argument("compute_cost_wei", type=int, help="Bounded compute cost in wei")
    authorize_result_p.add_argument("result_hash", help="Replay-bound result commitment bytes32")
    authorize_result_p.add_argument("--chain-id", type=int, required=True, help="Target chain ID")
    authorize_result_p.add_argument("--contract-address", required=True, help="DiligenceRoom address")
    authorize_result_p.add_argument("--tee-identity", required=True, help="TEE signer address for the deal")
    authorize_result_p.add_argument("--compose-hash", required=True, help="Approved compose hash for this result")
    authorize_result_p.add_argument(
        "--signer-attestation-json",
        required=True,
        help="Path to bounded signer-attestation JSON, not raw quote material",
    )
    authorize_result_p.add_argument(
        "--allow-compose-hash",
        action="append",
        default=[],
        help="Allowed compose hash; repeat for multiple approved measurements",
    )
    authorize_result_p.add_argument(
        "--allow-app-id",
        action="append",
        default=[],
        help="Allowed Phala app ID; repeat for multiple approved apps",
    )
    authorize_result_p.add_argument(
        "--allow-os-image-hash",
        action="append",
        default=[],
        help="Optional allowed OS image hash; repeat for multiple approved images",
    )
    authorize_result_p.add_argument(
        "--revoke-quote-hash",
        action="append",
        default=[],
        help="Revoked signer quote hash; repeat for multiple revoked quotes",
    )
    authorize_result_p.add_argument(
        "--revoke-signer-address",
        action="append",
        default=[],
        help="Revoked TEE signer address; repeat for multiple revoked signers",
    )
    authorize_result_p.add_argument(
        "--ttl-seconds",
        type=int,
        default=None,
        help="Authorization TTL; defaults to TINKER_CHAIN_RESULT_AUTHORIZATION_TTL_SECONDS",
    )
    authorize_result_p.add_argument("--output", default="", help="Optional JSON output path")

    # API server
    serve_p = sub.add_parser("serve", help="Start the FastAPI server")
    serve_p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_p.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")

    args = parser.parse_args()
    settings = Settings()

    if args.command == "check":
        from tinker_delegate.oracle_client import OracleClient
        oracle = OracleClient(settings)
        health = oracle.health()
        print(json.dumps(health, indent=2))

    elif args.command == "signup":
        from tinker_delegate.signup import signup
        result = asyncio.run(signup(settings))
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("success") else 1)

    elif args.command == "signin":
        from tinker_delegate.signup import signin
        result = asyncio.run(signin(settings))
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("success") else 1)

    elif args.command == "reauth":
        from tinker_delegate.signup import reauth
        result = asyncio.run(reauth(settings))
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("success") else 1)

    elif args.command == "synthetic-private-reward-demo":
        from tinker_delegate.private_reward_envs.synthetic_demo import (
            hidden_demo_forbidden_values,
            run_synthetic_hidden_keyword_demo,
        )

        candidates = tuple(args.candidate)
        result = run_synthetic_hidden_keyword_demo(candidates or None)
        _emit_bounded_json(
            result,
            output_path=args.output,
            forbidden_values=hidden_demo_forbidden_values(candidates or None),
        )

    elif args.command == "balance":
        from tinker_delegate.billing import get_balance
        result = asyncio.run(get_balance(settings))
        print(json.dumps(result, indent=2))

    elif args.command == "funding-policy":
        from tinker_delegate.funding_policy import funding_policy_status
        print(json.dumps(funding_policy_status(settings).to_public_dict(), indent=2))

    elif args.command == "funding-preflight":
        from tinker_delegate.funding_policy import funding_validation_preflight
        result = funding_validation_preflight(
            settings,
            amount_dollars=args.amount,
            require_add_balance_endpoint=args.require_add_balance_endpoint,
            api_url=args.api_url,
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            allow_local_attestation=args.allow_local_attestation,
            fetch_attestation=args.fetch_attestation,
        )
        _emit_bounded_json(result.to_public_dict(), output_path=args.output)
        sys.exit(0 if result.ready else 1)

    elif args.command == "tinker-encumbrance-preflight":
        from tinker_delegate.tinker_encumbrance import (
            TinkerOperationKind,
            preflight_tinker_operation,
        )

        operation_kinds = {
            "add-payment-method": TinkerOperationKind.ADD_PAYMENT_METHOD,
            "add-balance": TinkerOperationKind.ADD_BALANCE,
            "spend-tinker-compute": TinkerOperationKind.SPEND_TINKER_COMPUTE,
            "manual-prefund": TinkerOperationKind.MANUAL_PREFUND,
        }
        result = preflight_tinker_operation(
            settings,
            operation_kind=operation_kinds[args.operation],
            amount_dollars=args.amount,
            amount_wei=args.amount_wei,
            compose_hash=args.compose_hash,
            contract_address=args.contract_address,
            rpc_url=args.rpc_url,
            required=args.required or None,
        )
        _emit_bounded_json(result.to_public_dict(), output_path=args.output)
        sys.exit(0 if result.allowed else 1)

    elif args.command == "funding-manifest":
        from tinker_delegate.funding_manifest import build_funding_validation_manifest

        preflight = json.loads(Path(args.preflight_json).read_text(encoding="utf-8"))
        receipt = json.loads(Path(args.receipt_json).read_text(encoding="utf-8"))
        manifest = build_funding_validation_manifest(
            preflight=preflight,
            receipt=receipt,
            validation_id=args.validation_id,
            attestation_policy={
                "compose_hash": args.compose_hash,
                "app_id": args.app_id,
                "os_image_hash": args.os_image_hash,
            },
        ).to_public_dict()
        rendered = json.dumps(manifest, indent=2)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        sys.exit(0 if manifest["no_raw_card_retained"] else 1)

    elif args.command == "verify-funding-manifest":
        from tinker_delegate.funding_manifest import verify_funding_validation_manifest

        preflight = json.loads(Path(args.preflight_json).read_text(encoding="utf-8"))
        receipt = json.loads(Path(args.receipt_json).read_text(encoding="utf-8"))
        manifest = json.loads(Path(args.manifest_json).read_text(encoding="utf-8"))
        result = verify_funding_validation_manifest(
            preflight=preflight,
            receipt=receipt,
            manifest=manifest,
            validation_id=args.validation_id,
            attestation_policy={
                "compose_hash": args.compose_hash,
                "app_id": args.app_id,
                "os_image_hash": args.os_image_hash,
            },
            require_ready=args.require_ready,
            require_no_raw_card_retained=not args.allow_card_retention_flag,
        )
        _emit_bounded_json(result.to_public_dict(), output_path=args.output)
        sys.exit(0 if result.ok else 1)

    elif args.command == "funding-validation-packet":
        from tinker_delegate.funding_validation_packet import run_funding_validation_packet

        card_fields = {
            "card_number": args.number,
            "exp_month": args.exp_month,
            "exp_year": args.exp_year,
            "cvc": args.cvc,
            "cardholder_name": args.name,
            "address_line1": args.address_line1,
            "address_city": args.address_city,
            "address_state": args.address_state,
            "address_postal": args.address_postal,
            "address_country": args.address_country,
        }
        provided_card_fields = [
            value
            for key, value in card_fields.items()
            if key != "address_country" and value
        ]
        if provided_card_fields and not args.run_card_attempt:
            print("[funding-validation-packet] card fields require --run-card-attempt")
            sys.exit(1)
        if args.prompt_card and provided_card_fields:
            print("[funding-validation-packet] use either --prompt-card or test-card fields, not both")
            sys.exit(1)
        if args.prompt_card and not args.run_card_attempt:
            print("[funding-validation-packet] --prompt-card requires --run-card-attempt")
            sys.exit(1)
        required_card_fields = ("card_number", "exp_month", "exp_year", "cvc", "cardholder_name")
        if args.run_card_attempt and args.prompt_card:
            try:
                _validate_prompt_billing_policy(args)
            except ValueError as exc:
                print(f"[funding-validation-packet] policy rejected: {redact_text(exc)}")
                sys.exit(1)
            card_fields = _prompt_billing_card_payload()
        if args.run_card_attempt and any(not card_fields[field] for field in required_card_fields):
            print("[funding-validation-packet] --run-card-attempt requires card number, expiration, CVC, and name")
            for key in list(card_fields):
                card_fields[key] = ""
            sys.exit(1)
        if args.run_add_balance_attempt and args.amount is None:
            print("[funding-validation-packet] --run-add-balance-attempt requires --amount")
            sys.exit(1)

        result = run_funding_validation_packet(
            settings,
            output_dir=Path(args.output_dir),
            api_url=args.api_url,
            amount_dollars=args.amount,
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            allow_local_attestation=args.allow_local_attestation,
            fetch_attestation=args.fetch_attestation,
            require_add_balance_endpoint=args.require_add_balance_endpoint,
            validation_id=args.validation_id,
            receipt_json=Path(args.receipt_json) if args.receipt_json else None,
            add_balance_receipt_json=(
                Path(args.add_balance_receipt_json) if args.add_balance_receipt_json else None
            ),
            run_card_attempt=args.run_card_attempt,
            run_add_balance_attempt=args.run_add_balance_attempt,
            card_data=card_fields if args.run_card_attempt else None,
        )
        _emit_bounded_json(result.to_public_dict())
        sys.exit(0 if result.ok else 1)

    elif args.command == "check-funding-validation-packet":
        from tinker_delegate.funding_validation_packet import check_funding_validation_packet

        result = check_funding_validation_packet(
            packet_dir=Path(args.packet_dir),
            validation_id=args.validation_id,
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            require_add_balance=args.require_add_balance,
            require_deployed_attestation=args.require_deployed_attestation,
        )
        _emit_bounded_json(result.to_public_dict(), output_path=args.output)
        sys.exit(0 if result.ok else 1)

    elif args.command == "add-card":
        from tinker_delegate.card_channel import CardPayload, handle_card_update
        payload = CardPayload(
            card_number=args.number,
            exp_month=args.exp_month,
            exp_year=args.exp_year,
            cvc=args.cvc,
            cardholder_name=args.name,
            address_line1=args.address_line1,
            address_city=args.address_city,
            address_state=args.address_state,
            address_postal=args.address_postal,
            address_country=args.address_country,
        )
        result = asyncio.run(handle_card_update(payload, settings))
        body = result.model_dump(mode="json")
        if args.receipt_output:
            _emit_bounded_json(_receipt_or_raise(body), output_path=args.receipt_output)
        _emit_bounded_json(body)
        sys.exit(0 if result.success else 1)

    elif args.command == "add-balance":
        from tinker_delegate.card_channel import BalancePayload, handle_add_balance
        payload = BalancePayload(amount_dollars=args.amount)
        result = asyncio.run(handle_add_balance(payload, settings))
        body = result.model_dump(mode="json")
        if args.receipt_output:
            _emit_bounded_json(_receipt_or_raise(body), output_path=args.receipt_output)
        _emit_bounded_json(body)
        sys.exit(0 if result.success else 1)

    elif args.command == "add-card-encrypted":
        from tinker_delegate.attestation_verifier import AttestationVerificationError
        from tinker_delegate.billing_uploader import (
            BillingCardUploadPolicy,
            upload_billing_card_payload,
        )

        card = {
            "card_number": args.number,
            "exp_month": args.exp_month,
            "exp_year": args.exp_year,
            "cvc": args.cvc,
            "cardholder_name": args.name,
            "address_line1": args.address_line1,
            "address_city": args.address_city,
            "address_state": args.address_state,
            "address_postal": args.address_postal,
            "address_country": args.address_country,
        }
        policy = BillingCardUploadPolicy(
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            allow_local=args.allow_local_attestation,
        )
        try:
            result = upload_billing_card_payload(args.api_url, card, policy)
        except AttestationVerificationError as exc:
            print(f"[add-card-encrypted] attestation rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[add-card-encrypted] update failed: {redact_text(exc)}")
            sys.exit(1)
        finally:
            for key in list(card):
                card[key] = ""

        body = {
            "status_code": result.status_code,
            "response": result.response,
        }
        forbidden_values = (
            args.number,
            args.name,
            args.address_line1,
            args.address_postal,
        )
        if args.receipt_output:
            _emit_bounded_json(
                _receipt_or_raise(result.response),
                output_path=args.receipt_output,
                forbidden_values=forbidden_values,
            )
        _emit_bounded_json(body, forbidden_values=forbidden_values)
        sys.exit(0 if result.response.get("success") else 1)

    elif args.command == "add-card-encrypted-prompt":
        from tinker_delegate.attestation_verifier import AttestationVerificationError
        from tinker_delegate.billing_uploader import (
            BillingCardUploadPolicy,
            upload_billing_card_payload,
        )

        try:
            _validate_prompt_billing_policy(args)
        except ValueError as exc:
            print(f"[add-card-encrypted-prompt] policy rejected: {redact_text(exc)}")
            sys.exit(1)

        card = _prompt_billing_card_payload()
        policy = BillingCardUploadPolicy(
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            allow_local=args.allow_local_attestation,
        )
        forbidden_values = tuple(card.values())
        try:
            result = upload_billing_card_payload(args.api_url, card, policy)
        except AttestationVerificationError as exc:
            print(f"[add-card-encrypted-prompt] attestation rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[add-card-encrypted-prompt] update failed: {redact_text(exc)}")
            sys.exit(1)
        finally:
            for key in list(card):
                card[key] = ""

        body = {
            "status_code": result.status_code,
            "response": result.response,
        }
        if args.receipt_output:
            _emit_bounded_json(
                _receipt_or_raise(result.response),
                output_path=args.receipt_output,
                forbidden_values=forbidden_values,
            )
        _emit_bounded_json(body, forbidden_values=forbidden_values)
        sys.exit(0 if result.response.get("success") else 1)

    elif args.command == "upload-artifact":
        from tinker_delegate.artifact_uploader import (
            ArtifactUploadPolicy,
            AttestationVerificationError,
            upload_artifact_file,
        )

        policy = ArtifactUploadPolicy(
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            allow_local=args.allow_local_attestation,
        )
        try:
            result = upload_artifact_file(
                args.api_url,
                args.deal_id,
                args.artifact_path,
                policy,
            )
        except AttestationVerificationError as exc:
            print(f"[upload-artifact] attestation rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[upload-artifact] upload failed: {redact_text(exc)}")
            sys.exit(1)

        print(json.dumps({
            "deal_id": result.deal_id,
            "artifact_hash": result.artifact_hash,
            "size": result.size,
            "status_code": result.status_code,
            "response": result.response,
        }, indent=2))

    elif args.command == "verify-attestation":
        from tinker_delegate.attestation_verifier import (
            AttestationPolicy,
            AttestationVerificationError,
            fetch_and_verify_attestation,
        )

        policy = AttestationPolicy(
            expected_compose_hash=args.compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            context=args.context,
            allow_local=args.allow_local_attestation,
            max_age_seconds=args.max_age_seconds,
        )
        try:
            result = fetch_and_verify_attestation(args.api_url, policy)
        except AttestationVerificationError as exc:
            print(f"[verify-attestation] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[verify-attestation] failed: {redact_text(exc)}")
            sys.exit(1)

        print(json.dumps({
            "mode": result.mode,
            "report_context": result.report_context,
            "report_data": result.report_data,
            "encryption_public_key": result.encryption_public_key,
            "quote_size": result.quote_size,
            "compose_hash": result.compose_hash,
            "app_id": result.app_id,
            "os_image_hash": result.os_image_hash,
            "fetched_at": result.fetched_at,
        }, indent=2))

    elif args.command == "verify-cvm-attestation":
        from tinker_delegate.cvm_attestation import (
            CvmAttestationError,
            CvmAttestationPolicy,
            bundle_to_json,
            verify_cvm_attestation,
        )

        policy = CvmAttestationPolicy(
            api_url=args.api_url,
            compose_path=Path(args.compose),
            env_files=tuple(Path(path) for path in args.env_file),
            allowed_env_file=Path(args.allowed_env_file) if args.allowed_env_file else None,
            allowed_envs=tuple(args.allowed_env),
            context=args.context,
            expected_compose_hash=args.expected_compose_hash,
            expected_attested_compose_hash=args.attested_compose_hash,
            expected_app_id=args.app_id,
            expected_os_image_hash=args.os_image_hash,
            required_images=tuple(args.require_image),
            required_image_digests=tuple(args.require_image_digest),
            allow_local=args.allow_local_attestation,
            allow_tags=args.allow_tags,
            phala_raw_compose=args.phala_raw_compose,
            max_age_seconds=args.max_age_seconds,
        )
        try:
            bundle = verify_cvm_attestation(policy)
        except CvmAttestationError as exc:
            print(f"[verify-cvm-attestation] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[verify-cvm-attestation] failed: {redact_text(exc)}")
            sys.exit(1)

        print(bundle_to_json(bundle))

    elif args.command == "verify-compose-hash":
        from tinker_delegate.compose_hash import ComposeHashError, verify_compose_hash

        try:
            result = verify_compose_hash(
                Path(args.compose),
                env_files=[Path(path) for path in args.env_file],
                allowed_env_file=Path(args.allowed_env_file) if args.allowed_env_file else None,
                expected_hash=args.expected_hash,
                allowed_envs=list(args.allowed_env),
                phala_raw_compose=args.phala_raw_compose,
                allow_tags=args.allow_tags,
            )
        except ComposeHashError as exc:
            print(f"[verify-compose-hash] rejected: {redact_text(exc)}")
            sys.exit(1)

        print(json.dumps(result.to_public_dict(), indent=2))

    elif args.command == "watch-chain":
        from tinker_delegate.chain_watcher import (
            ChainEventDispatcher,
            ChainCursorStore,
            ChainWatcher,
            ChainWatcherError,
            JsonRpcLogSource,
            parse_start_block,
        )

        rpc_url = args.rpc_url or settings.chain_rpc_url
        contract_address = args.contract_address or settings.chain_contract_address
        api_url = args.api_url or settings.chain_control_plane_url
        poll_interval = (
            args.poll_interval
            if args.poll_interval is not None
            else settings.chain_poll_interval
        )
        confirmations = (
            args.confirmations
            if args.confirmations is not None
            else settings.chain_confirmations
        )
        from_block = args.from_block or settings.chain_start_block
        cursor_path = args.cursor_store or settings.chain_cursor_store_path
        cursor_store = None if args.no_cursor else ChainCursorStore(cursor_path)

        if args.cursor_summary:
            if cursor_store is None:
                _emit_bounded_json({"cursor_enabled": False, "raw_secret_egress": False})
            else:
                _emit_bounded_json({"cursor_enabled": True, **cursor_store.public_summary()})
            sys.exit(0)

        source = None
        dispatcher = None
        try:
            source = JsonRpcLogSource(rpc_url, contract_address)
            created_context = cursor_store.load().created_deals if cursor_store is not None else None
            dispatcher = ChainEventDispatcher(api_url, created_context=created_context)
            watcher = ChainWatcher(source, dispatcher)
            for summary in watcher.run(
                start_block=parse_start_block(from_block),
                poll_interval=poll_interval,
                confirmations=confirmations,
                once=args.once,
                cursor_store=cursor_store,
            ):
                _emit_bounded_json(summary)
        except ChainWatcherError as exc:
            print(f"[watch-chain] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[watch-chain] failed: {redact_text(exc)}")
            sys.exit(1)
        finally:
            if dispatcher is not None:
                dispatcher.close()
            if source is not None:
                source.close()

    elif args.command == "result-verifier-address":
        from tinker_delegate.result_verifier import (
            DstackResultVerifierSigner,
            ResultVerifierError,
            VerifierSignerUnavailable,
        )

        try:
            signer = DstackResultVerifierSigner.from_settings(settings)
            _emit_bounded_json(
                {
                    "verifier_address": signer.address,
                    "custody": signer.custody,
                    "raw_secret_egress": False,
                },
                output_path=args.output,
            )
        except VerifierSignerUnavailable as exc:
            print(f"[result-verifier-address] signer unavailable: {redact_text(exc)}")
            sys.exit(1)
        except ResultVerifierError as exc:
            print(f"[result-verifier-address] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[result-verifier-address] failed: {redact_text(exc)}")
            sys.exit(1)

    elif args.command == "authorize-result":
        from tinker_delegate.result_verifier import (
            DstackResultVerifierSigner,
            ResultAuthorizationRequest,
            ResultVerifierError,
            ResultVerifierPolicy,
            VerifierSignerUnavailable,
            authorize_result_submission,
            signer_attestation_from_public_dict,
        )

        try:
            attestation_payload = json.loads(
                Path(args.signer_attestation_json).read_text(encoding="utf-8")
            )
            signer_attestation = signer_attestation_from_public_dict(attestation_payload)
            policy = ResultVerifierPolicy(
                allowed_compose_hashes=tuple(args.allow_compose_hash),
                allowed_app_ids=tuple(args.allow_app_id),
                allowed_os_image_hashes=tuple(args.allow_os_image_hash),
                revoked_quote_hashes=tuple(args.revoke_quote_hash),
                revoked_signer_addresses=tuple(args.revoke_signer_address),
                authorization_ttl_seconds=(
                    args.ttl_seconds
                    if args.ttl_seconds is not None
                    else settings.chain_result_authorization_ttl_seconds
                ),
            )
            request = ResultAuthorizationRequest(
                chain_id=args.chain_id,
                contract_address=args.contract_address,
                deal_id=args.deal_id,
                tee_identity=args.tee_identity,
                compose_hash=args.compose_hash,
                score_band=args.score_band,
                compute_cost_wei=args.compute_cost_wei,
                result_hash=args.result_hash,
            )
            authorization = authorize_result_submission(
                request,
                signer_attestation=signer_attestation,
                policy=policy,
                verifier_signer=DstackResultVerifierSigner.from_settings(settings),
            )
            _emit_bounded_json(
                authorization.to_public_dict(),
                output_path=args.output,
                public_hex_fields=("verifier_signature",),
                public_decimal_fields=("compute_cost_wei",),
            )
        except VerifierSignerUnavailable as exc:
            print(f"[authorize-result] signer unavailable: {redact_text(exc)}")
            sys.exit(1)
        except ResultVerifierError as exc:
            print(f"[authorize-result] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[authorize-result] failed: {redact_text(exc)}")
            sys.exit(1)

    elif args.command == "submit-result":
        from tinker_delegate.chain_submitter import (
            ChainSubmitterError,
            DiligenceRoomSubmitter,
            DstackEthereumSigner,
            JsonRpcClient,
            SignerUnavailable,
            get_dstack_signer_attestation,
        )

        rpc_url = args.rpc_url or settings.chain_rpc_url
        contract_address = args.contract_address or settings.chain_contract_address
        gas_limit = (
            args.gas_limit
            if args.gas_limit is not None
            else settings.chain_submit_gas_limit
        )
        rpc = None
        try:
            rpc = JsonRpcClient(rpc_url)
            signer = DstackEthereumSigner.from_settings(settings)
            submitter = DiligenceRoomSubmitter(
                rpc,
                contract_address,
                signer,
                gas_limit=gas_limit,
            )
            signer_attestation = get_dstack_signer_attestation(
                signer_address=signer.address,
                chain_id=rpc.chain_id(),
                contract_address=contract_address,
            )
            receipt = submitter.submit_result(
                deal_id=args.deal_id,
                score_band=args.score_band,
                compute_cost_wei=args.compute_cost_wei,
                result_hash=args.result_hash,
                authorization_expiry=args.authorization_expiry,
                verifier_signature=args.verifier_signature,
                signer_attestation=signer_attestation,
            )
            _emit_bounded_json(receipt.to_public_dict())
        except SignerUnavailable as exc:
            print(f"[submit-result] signer unavailable: {redact_text(exc)}")
            sys.exit(1)
        except ChainSubmitterError as exc:
            print(f"[submit-result] rejected: {redact_text(exc)}")
            sys.exit(1)
        except Exception as exc:
            print(f"[submit-result] failed: {redact_text(exc)}")
            sys.exit(1)
        finally:
            if rpc is not None:
                rpc.close()

    elif args.command == "serve":
        import uvicorn
        reset_runtime_state()
        try:
            asyncio.run(_ensure_api_key(settings))
        except Exception as exc:
            print(f"[serve] bootstrap failed: {redact_text(exc)}")
            update_runtime_state(
                api_key_available=False,
                api_key_source="bootstrap" if settings.bootstrap_signup else "none",
                bootstrap_attempted=settings.bootstrap_signup,
                bootstrap_success=False,
                bootstrap_error=redact_text(exc),
                bootstrap_error_kind=(
                    "auth_access_blocked"
                    if isinstance(exc, AuthAccessBlockedError)
                    else "bootstrap_error"
                ),
            )
            if not settings.bootstrap_fail_open:
                sys.exit(1)
        uvicorn.run(
            "tinker_delegate.api:app",
            host=args.host,
            port=args.port,
            log_level="info",
        )


if __name__ == "__main__":
    cli()
