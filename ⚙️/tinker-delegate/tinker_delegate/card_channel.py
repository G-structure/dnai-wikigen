"""Secure card update channel — encrypted card delivery from developer to TEE.

Trust model:
  1. Developer requests TDX attestation from CVM via GET /attestation
  2. Developer verifies: code measurements match git SHA → docker digest → compose hash
     and report_data binds the returned encryption_public_key
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
import hashlib
import json
from typing import Optional

from pydantic import BaseModel

from tinker_delegate.billing import CardDetails, add_payment_method, add_balance, get_balance
from tinker_delegate.config import Settings
from tinker_delegate.crypto import TEEKeyPair, EncryptedPayload
from tinker_delegate.dstack_utils import get_attestation_details, is_dstack_enabled
from tinker_delegate.redaction import redact_text


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

    def zero(self) -> None:
        self.card_number = ""
        self.exp_month = ""
        self.exp_year = ""
        self.cvc = ""
        self.cardholder_name = ""
        self.address_line1 = ""
        self.address_city = ""
        self.address_state = ""
        self.address_postal = ""
        self.address_country = ""


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


def attestation_report_data(context: str, public_key: bytes) -> bytes:
    """Report data binding an operation context to the TEE encryption key."""
    payload = json.dumps(
        {
            "service": "tinker-delegate",
            "context": context,
            "encryption_public_key": public_key.hex(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).digest()


# ---------------------------------------------------------------------------
# TEE attestation (stub for local, real in dstack)
# ---------------------------------------------------------------------------

def get_attestation(context: str = "ingress") -> dict:
    """Get TDX attestation quote + TEE's encryption public key.

    In production (dstack CVM): returns real TDX quote binding the
    enclave identity + code measurements + encryption public key.

    Locally: returns a stub with the encryption public key (for testing).
    """
    keypair = get_tee_keypair()
    report_data = attestation_report_data(context, keypair.public_key_bytes)
    if is_dstack_enabled():
        try:
            details = get_attestation_details(report_data)
            return {
                "mode": "tdx",
                "quote": details["quote"],
                "encryption_public_key": keypair.public_key_bytes.hex(),
                "report_context": context,
                "report_data": report_data.hex(),
                "quote_report_data": details.get("quote_report_data", ""),
                "event_log": details.get("event_log", ""),
                "vm_config": details.get("vm_config", ""),
                "app_id": details["app_id"],
                "instance_id": details.get("instance_id", ""),
                "app_name": details.get("app_name", ""),
                "device_id": details.get("device_id", ""),
                "mr_aggregated": details.get("mr_aggregated", ""),
                "os_image_hash": details.get("os_image_hash", ""),
                "compose_hash": details["compose_hash"],
                "tcb_info": details.get("tcb_info", {}),
                "verified": True,
            }
        except Exception as e:
            return {"mode": "tdx", "error": redact_text(e), "verified": False}
    else:
        return {
            "mode": "local",
            "note": "Running locally without TDX. In production, this returns a real attestation quote.",
            "encryption_public_key": keypair.public_key_bytes.hex(),
            "report_context": context,
            "report_data": report_data.hex(),
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

        attestation = get_attestation("billing")

        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
            tdx_quote=attestation.get("quote"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=redact_text(e))
    finally:
        card.zero()
        payload.zero()


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
        plaintext_bytes = bytearray(keypair.decrypt(encrypted))
        card_data = json.loads(plaintext_bytes.decode())

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

        # Zero plaintext immediately after parsing.
        for i in range(len(plaintext_bytes)):
            plaintext_bytes[i] = 0
        plaintext_bytes = None

        result = await add_payment_method(card, settings)
        attestation = get_attestation("billing")

        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
            tdx_quote=attestation.get("quote"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=redact_text(e))
    finally:
        if plaintext_bytes is not None:
            for i in range(len(plaintext_bytes)):
                plaintext_bytes[i] = 0
        if card:
            card.zero()


async def handle_add_balance(payload: BalancePayload, settings: Settings) -> BillingResponse:
    """Add credit balance. No card details needed (uses card on file)."""
    try:
        result = await add_balance(payload.amount_dollars, settings)
        return BillingResponse(
            success=result.get("success", False),
            error=result.get("error"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=redact_text(e))


async def handle_get_balance(settings: Settings) -> BillingResponse:
    """Get current balance."""
    try:
        result = await get_balance(settings)
        return BillingResponse(
            success=True,
            balance=result.get("balance"),
        )
    except Exception as e:
        return BillingResponse(success=False, error=redact_text(e))
