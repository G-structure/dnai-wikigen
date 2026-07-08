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
) -> str:
    """Render JSON only if it does not contain obvious secret-shaped material."""
    rendered = json.dumps(payload, indent=2, default=str)
    if redact_text(rendered) != rendered:
        raise ValueError("bounded CLI output contains secret-like material")
    for value in forbidden_values:
        if value and len(value) >= 4 and value in rendered:
            raise ValueError("bounded CLI output contains submitted secret material")
    return rendered


def _emit_bounded_json(
    payload: Any,
    *,
    output_path: str = "",
    forbidden_values: tuple[str, ...] = (),
) -> None:
    rendered = _render_bounded_json(payload, forbidden_values=forbidden_values)
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
    verify_compose_p.add_argument("--expected-hash", default="", help="Expected Phala compose hash")
    verify_compose_p.add_argument(
        "--allow-tags",
        action="store_true",
        help="Allow mutable tag images; development only",
    )

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

    elif args.command == "verify-compose-hash":
        from tinker_delegate.compose_hash import ComposeHashError, verify_compose_hash

        try:
            result = verify_compose_hash(
                Path(args.compose),
                env_files=[Path(path) for path in args.env_file],
                allowed_env_file=Path(args.allowed_env_file) if args.allowed_env_file else None,
                expected_hash=args.expected_hash,
                allow_tags=args.allow_tags,
            )
        except ComposeHashError as exc:
            print(f"[verify-compose-hash] rejected: {redact_text(exc)}")
            sys.exit(1)

        print(json.dumps(result.to_public_dict(), indent=2))

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
