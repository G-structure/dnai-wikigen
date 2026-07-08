"""Email Oracle entrypoint.

Lifecycle:
  1. GENESIS: Create email account (if no credentials exist)
  2. OPERATION: Start FastAPI server for pin extraction

Commands:
  email-oracle genesis   — create account only
  email-oracle serve     — start API server (auto-genesis if needed)
  email-oracle check     — verify IMAP connectivity
"""

import argparse
import asyncio
import sys

from email_oracle.config import Settings
from email_oracle.cred_store import CredentialStore
from email_oracle.redaction import redact_text


async def cmd_genesis(settings: Settings, store: CredentialStore) -> None:
    """Create a new email account."""
    if store.exists():
        creds = store.load()
        print(f"[genesis] credentials already exist for {creds.email}")
        print("[genesis] delete the credential file to re-create")
        return

    from email_oracle.account_creator import create_account
    creds = await create_account(settings, store)
    print(f"[genesis] complete: {creds.email}")


def cmd_serve(settings: Settings, store: CredentialStore) -> None:
    """Start the API server."""
    import uvicorn

    # Auto-genesis is useful for local demos but brittle in production: account
    # creation failures must not prevent bounded health/attestation endpoints
    # from serving.
    if not store.exists() and settings.auto_genesis:
        print("[serve] no credentials found, running genesis first...")
        asyncio.run(cmd_genesis(settings, store))

    if not store.exists() and settings.auto_genesis:
        print("[serve] genesis failed, cannot start server")
        sys.exit(1)
    if not store.exists():
        print("[serve] no credentials found, starting API in degraded mode")

    print(f"[serve] starting API on {settings.api_host}:{settings.api_port}")
    uvicorn.run(
        "email_oracle.api:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


def cmd_check(settings: Settings, store: CredentialStore) -> None:
    """Verify IMAP connectivity."""
    if not store.exists():
        print("[check] no credentials found")
        sys.exit(1)

    creds = store.load()
    print(f"[check] testing IMAP for {creds.email}")

    from email_oracle.imap_client import IMAPClient
    client = IMAPClient(creds, settings)
    try:
        client.connect()
        emails = client.list_recent(max_age_seconds=86400, limit=5)
        print(f"[check] IMAP OK — {len(emails)} recent emails")
        for e in emails:
            print(f"  {e['date']}  {e['from']}  {e['subject']}")
    except Exception as e:
        print(f"[check] IMAP FAILED: {redact_text(e)}")
        sys.exit(1)
    finally:
        client.disconnect()


def cli():
    parser = argparse.ArgumentParser(
        prog="email-oracle",
        description="TEE Email Oracle — account creation + pin extraction",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("genesis", help="Create a new email account")
    sub.add_parser("serve", help="Start the API server")
    sub.add_parser("check", help="Verify IMAP connectivity")

    args = parser.parse_args()

    settings = Settings()
    store = CredentialStore(
        settings.cred_store_path,
        settings.cred_store_key,
        dstack_enabled=settings.dstack_enabled,
        dstack_key_path=settings.dstack_key_path,
    )

    if args.command == "genesis":
        asyncio.run(cmd_genesis(settings, store))
    elif args.command == "serve":
        cmd_serve(settings, store)
    elif args.command == "check":
        cmd_check(settings, store)


if __name__ == "__main__":
    cli()
