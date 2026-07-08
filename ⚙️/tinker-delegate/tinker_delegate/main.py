"""CLI entrypoint for tinker-delegate automation."""
import argparse
import asyncio
import json
import os
import time
import sys

from tinker_delegate.api_key_store import build_api_key_store
from tinker_delegate.config import Settings
from tinker_delegate.oracle_client import OracleClient
from tinker_delegate.redaction import redact_text
from tinker_delegate.runtime_state import reset_runtime_state, update_runtime_state
from tinker_delegate.signup import AuthAccessBlockedError


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
    parser = argparse.ArgumentParser(description="Tinker delegate — automated account management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check oracle health and email readiness")
    sub.add_parser("signup", help="Full signup: auth → onboarding → API key")
    sub.add_parser("signin", help="Sign in to existing account")

    # Billing commands
    sub.add_parser("balance", help="Get current Tinker account balance")

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

    add_bal_p = sub.add_parser("add-balance", help="Add credit balance to Tinker account")
    add_bal_p.add_argument("amount", type=float, help="Amount in USD to add")

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

    elif args.command == "balance":
        from tinker_delegate.billing import get_balance
        result = asyncio.run(get_balance(settings))
        print(json.dumps(result, indent=2))

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
        print(result.model_dump_json(indent=2))
        sys.exit(0 if result.success else 1)

    elif args.command == "add-balance":
        from tinker_delegate.card_channel import BalancePayload, handle_add_balance
        payload = BalancePayload(amount_dollars=args.amount)
        result = asyncio.run(handle_add_balance(payload, settings))
        print(result.model_dump_json(indent=2))
        sys.exit(0 if result.success else 1)

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
