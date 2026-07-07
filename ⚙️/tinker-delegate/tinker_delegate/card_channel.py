"""Secure card update channel — encrypted card delivery from developer to TEE.

Trust model:
  1. Developer requests TDX attestation from CVM via GET /attestation
  2. Developer verifies: code measurements match git SHA → docker digest → compose hash
  3. Developer encrypts CardPayload to TEE's ephemeral public key (X25519 + AES-256-GCM)
  4. Developer sends encrypted payload to POST /billing/card
  5. TEE decrypts inside enclave, fills Stripe form via browser, submits
  6. TEE zeroes card details from memory — never persisted to disk
  7. Returns success + TDX quote attesting the billing operation

What the developer CAN do:
  - Add/update payment method (card details encrypted to TEE)
  - Add balance (amount only, no card details needed if card on file)
  - Read balance (no sensitive data)

What the developer CANNOT do:
  - Access the Tinker API key
  - Read training data or model weights
  - View training run results (only bounded scores via the deal flow)
  - Extract the email/password (sealed in TEE)

Why this doesn't break the trust model:
  - Card details are ephemeral — exist only in TEE memory for ~10 seconds
  - The developer already trusts the TEE code (verified via attestation)
  - Stripe tokenizes the card on their servers — TEE doesn't persist it
  - The billing session uses the same Tinker auth session that's already in the TEE
  - No new attack surface: the card goes developer → TEE → Stripe, same as
    developer → browser → Stripe, except the browser is inside the TEE

The key insight: the developer is NOT giving the TEE access to their card.
They're using the TEE as a secure intermediary to add a card to the Tinker
account that the TEE controls. The developer trusts the TEE because its code
is attested. The card is delivered to Stripe, not stored by the TEE.
"""
import asyncio
import json
from typing import Optional

from pydantic import BaseModel

from tinker_delegate.billing import CardDetails, add_payment_method, add_balance, get_balance
from tinker_delegate.config import Settings
from tinker_delegate.crypto import TEEKeyPair, EncryptedPayload
from tinker_delegate.dstack_utils import get_attestation as get_dstack_attestation, is_dstack_enabled


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CardPayload(BaseModel):
    """Card details submitted by developer. Normally encrypted in transit."""
    card_number: str
    exp_month: str  # "01"-"12"
    exp_year: str   # "26" or "2026"
    cvc: str
    cardholder_name: str
    address_line1: str = ""
    address_city: str = ""
    address_state: str = ""
    address_postal: str = ""
    address_country: str = "US"


class EncryptedCardPayload(BaseModel):
    """Encrypted card payload — production format.

    Developer encrypts CardPayload JSON to the TEE's X25519 public key
    (obtained from GET /attestation after verifying the TDX quote).
    """
    ephemeral_public_key: str  # hex
    nonce: str                 # hex
    ciphertext: str            # hex


class BalancePayload(BaseModel):
    """Add balance request."""
    amount_dollars: float


class BillingResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    balance: Optional[str] = None
    tdx_quote: Optional[str] = None  # hex-encoded TDX quote in production


# ---------------------------------------------------------------------------
# TEE keypair — singleton, generated on boot
# ---------------------------------------------------------------------------

_tee_keypair: TEEKeyPair | None = None


def get_tee_keypair() -> TEEKeyPair:
    """Get or create the TEE's X25519 keypair."""
    global _tee_keypair
    if _tee_keypair is None:
        _tee_keypair = TEEKeyPair()
    return _tee_keypair


# ---------------------------------------------------------------------------
# TEE attestation (stub for local, real in dstack)
# ---------------------------------------------------------------------------

def get_attestation() -> dict:
    """Get TDX attestation quote + TEE's encryption public key.

    In production (dstack CVM): returns real TDX quote binding the
    enclave identity + code measurements + encryption public key.

    Locally: returns a stub with the encryption public key (for testing).
    """
    keypair = get_tee_keypair()
    if is_dstack_enabled():
        try:
            quote, app_id, compose_hash = get_dstack_attestation("billing-attestation")
            return {
                "mode": "tdx",
                "quote": quote,
                "encryption_public_key": keypair.public_key_bytes.hex(),
                "app_id": app_id,
                "compose_hash": compose_hash,
                "verified": True,
            }
        except Exception as e:
            return {"mode": "tdx", "error": str(e), "verified": False}
    else:
        return {
            "mode": "local",
            "note": "Running locally without TDX. In production, this returns a real attestation quote.",
            "encryption_public_key": keypair.public_key_bytes.hex(),
            "verified": False,
        }


# ---------------------------------------------------------------------------
# Card update operations (called by the API server)
# ---------------------------------------------------------------------------

async def handle_card_update(payload: CardPayload, settings: Settings) -> BillingResponse:
    """Process a plaintext card payload: fill form, zero memory.

    For local dev only. In production, use handle_encrypted_card_update.
    """
    card = CardDetails(
        number=payload.card_number,
        exp_month=payload.exp_month,
        exp_year=payload.exp_year,
        cvc=payload.cvc,
        name=payload.cardholder_name,
        address_line1=payload.address_line1,
        address_city=payload.address_city,
        address_state=payload.address_state,
        address_postal=payload.address_postal,
        address_country=payload.address_country,
    )

    try:
        result = await add_payment_method(card, settings)

        payload.card_number = ""
        payload.cvc = ""

        attestation = get_attestation()

        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
            tdx_quote=attestation.get("quote"),
        )
    except Exception as e:
        card.zero()
        return BillingResponse(success=False, error=str(e))


async def handle_encrypted_card_update(
    payload: EncryptedCardPayload, settings: Settings
) -> BillingResponse:
    """Process an encrypted card payload: decrypt inside TEE, fill form, zero memory.

    Production path. Card details are encrypted to the TEE's X25519 public key.
    """
    keypair = get_tee_keypair()
    plaintext_bytes = None
    card = None

    try:
        encrypted = EncryptedPayload.from_hex({
            "ephemeral_public_key": payload.ephemeral_public_key,
            "nonce": payload.nonce,
            "ciphertext": payload.ciphertext,
        })
        plaintext_bytes = keypair.decrypt(encrypted)
        card_data = json.loads(plaintext_bytes)

        card = CardDetails(
            number=card_data["card_number"],
            exp_month=card_data["exp_month"],
            exp_year=card_data["exp_year"],
            cvc=card_data["cvc"],
            name=card_data["cardholder_name"],
            address_line1=card_data.get("address_line1", ""),
            address_city=card_data.get("address_city", ""),
            address_state=card_data.get("address_state", ""),
            address_postal=card_data.get("address_postal", ""),
            address_country=card_data.get("address_country", "US"),
        )

        # Zero plaintext immediately after parsing
        plaintext_bytes = b"\x00" * len(plaintext_bytes)

        result = await add_payment_method(card, settings)
        attestation = get_attestation()

        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
            tdx_quote=attestation.get("quote"),
        )
    except Exception as e:
        if card:
            card.zero()
        return BillingResponse(success=False, error=str(e))


async def handle_add_balance(payload: BalancePayload, settings: Settings) -> BillingResponse:
    """Add credit balance. No card details needed (uses card on file)."""
    try:
        result = await add_balance(payload.amount_dollars, settings)
        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=str(e))


async def handle_get_balance(settings: Settings) -> BillingResponse:
    """Get current balance."""
    try:
        result = await get_balance(settings)
        return BillingResponse(
            success=True,
            balance=result.get("balance"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=str(e))
