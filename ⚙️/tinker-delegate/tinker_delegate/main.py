"""CLI entrypoint for tinker-delegate automation."""
import argparse
import asyncio
import json
import sys

from tinker_delegate.config import Settings


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

    elif args.command == "serve":
        import uvicorn
        uvicorn.run(
            "tinker_delegate.api:app",
            host=args.host,
            port=args.port,
            log_level="info",
        )


if __name__ == "__main__":
    cli()
