"""FastAPI server for tinker-delegate.

Endpoints:
  GET  /health                    — service health + oracle email
  GET  /attestation               — TDX attestation quote + encryption public key
  GET  /billing/balance           — current Tinker balance
  POST /billing/card              — add payment method (plaintext — local dev only)
  POST /billing/card/encrypted    — add payment method (encrypted to TEE — production)
  POST /billing/add-balance       — add credit balance
"""
from fastapi import FastAPI

from tinker_delegate.config import Settings
from tinker_delegate.oracle_client import OracleClient
from tinker_delegate.card_channel import (
    CardPayload,
    EncryptedCardPayload,
    BalancePayload,
    BillingResponse,
    get_attestation,
    handle_card_update,
    handle_encrypted_card_update,
    handle_add_balance,
    handle_get_balance,
)

app = FastAPI(
    title="Tinker Delegate",
    description="TEE-hosted Tinker account management. Card details are ephemeral.",
)

settings = Settings()


@app.get("/health")
async def health():
    oracle = OracleClient(settings)
    try:
        oracle_health = oracle.health()
    except Exception as e:
        oracle_health = {"error": str(e)}

    return {
        "status": "ok",
        "oracle": oracle_health,
        "cdp_url": settings.cdp_url,
    }


@app.get("/attestation")
async def attestation():
    """Get TDX attestation quote + TEE encryption public key.

    Developer MUST:
    1. Verify the TDX quote (code measurements match expected values)
    2. Extract encryption_public_key from the response
    3. Encrypt card details to this key before sending to /billing/card/encrypted
    """
    return get_attestation()


@app.get("/billing/balance")
async def billing_balance():
    """Get current Tinker account balance."""
    result = await handle_get_balance(settings)
    return result.model_dump()


@app.post("/billing/card", response_model=BillingResponse)
async def billing_card(payload: CardPayload):
    """Add a payment method (plaintext — local dev only).

    In production, use POST /billing/card/encrypted instead.
    """
    result = await handle_card_update(payload, settings)
    return result


@app.post("/billing/card/encrypted", response_model=BillingResponse)
async def billing_card_encrypted(payload: EncryptedCardPayload):
    """Add a payment method (encrypted to TEE — production).

    The payload must be encrypted using X25519 + AES-256-GCM to the
    TEE's public key from GET /attestation.

    Protocol:
    1. GET /attestation → verify TDX quote → extract encryption_public_key
    2. Generate ephemeral X25519 keypair
    3. ECDH(ephemeral_private, tee_public) → shared_secret
    4. HKDF-SHA256(shared_secret, info="tinker-delegate-card") → AES key
    5. AES-256-GCM encrypt CardPayload JSON → {ephemeral_public_key, nonce, ciphertext}
    6. POST this endpoint with the encrypted payload

    See tinker_delegate.crypto.encrypt_card_payload() for a reference implementation.
    """
    result = await handle_encrypted_card_update(payload, settings)
    return result


@app.post("/billing/add-balance", response_model=BillingResponse)
async def billing_add_balance(payload: BalancePayload):
    """Add credit balance to the Tinker account.

    Requires a payment method to already be on file.
    """
    result = await handle_add_balance(payload, settings)
    return result
