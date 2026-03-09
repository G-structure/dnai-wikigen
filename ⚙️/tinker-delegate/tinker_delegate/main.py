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


if __name__ == "__main__":
    cli()
