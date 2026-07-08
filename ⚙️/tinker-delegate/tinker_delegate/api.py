"""FastAPI server for tinker-delegate.

Endpoints:
  GET  /health                    — service health + oracle email
  GET  /attestation               — TDX attestation quote + encryption public key
  GET  /billing/balance           — current Tinker balance
  POST /billing/card              — add payment method (plaintext — local dev only)
  POST /billing/card/encrypted    — add payment method (encrypted to TEE — production)
  POST /billing/add-balance       — add credit balance
  POST /deal/{deal_id}/artifact   — upload seller's encrypted artifact
  GET  /deal/{deal_id}/result     — get bounded evaluation result
  GET  /deals                     — list active deals
  POST /deal/{deal_id}/evaluate   — trigger evaluation (internal)
  POST /deal/{deal_id}/resolve    — notify deal resolution (internal)
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from tinker_delegate.api_key_store import resolve_api_key
from tinker_delegate.artifacts import decode_artifact_hex, zero_buffer
from tinker_delegate.config import Settings
from tinker_delegate.dstack_utils import is_dstack_enabled
from tinker_delegate.oracle_client import OracleClient
from tinker_delegate.redaction import redact_text
from tinker_delegate.runtime_state import get_runtime_state
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
    description="TEE-hosted Tinker account management and NDAI deal orchestration.",
)

settings = Settings()

# ---------------------------------------------------------------------------
# Control plane (lazy init — only when Tinker API key is available)
# ---------------------------------------------------------------------------
_control_plane = None


def _agent_stack_available() -> bool:
    try:
        import tinker  # noqa: F401
        return True
    except Exception:
        return False


def _plaintext_card_endpoint_allowed() -> bool:
    """Plaintext card delivery is a local-dev escape hatch, never a TEE path."""
    return settings.allow_plaintext_card_endpoint and not is_dstack_enabled()


def _get_control_plane():
    global _control_plane
    if _control_plane is None:
        api_key = resolve_api_key(settings)
        if not api_key:
            raise HTTPException(503, "TINKER_API_KEY not configured — control plane unavailable")
        try:
            from tinker_delegate.control_plane import ControlPlane
        except ModuleNotFoundError as exc:
            if exc.name == "tinker":
                raise HTTPException(
                    503,
                    "Tinker agent stack is not installed in this deployment",
                ) from exc
            raise
        _control_plane = ControlPlane(api_key)
    return _control_plane


# ---------------------------------------------------------------------------
# Deal API models
# ---------------------------------------------------------------------------

class ArtifactUpload(BaseModel):
    artifact_hex: str        # hex-encoded artifact payload
    artifact_hash: str       # keccak256 of the artifact

class DealFundedNotification(BaseModel):
    deal_id: str
    buyer: str
    seller: str
    budget_cap: int          # wei
    reserve_price: int       # wei

class DealResolvedNotification(BaseModel):
    deal_id: str

class EvaluationResultResponse(BaseModel):
    deal_id: str
    score_band: str
    quality_delta: str
    offer_price: int
    recommendation: str
    confidence: str
    methodology_summary: str
    compute_cost_wei: int
    fee_wei: int


@app.get("/health")
async def health():
    oracle = OracleClient(settings)
    try:
        oracle_health = oracle.health()
    except Exception as e:
        oracle_health = {"error": redact_text(e)}

    return {
        "status": "ok",
        "oracle": oracle_health,
        "cdp_url": settings.cdp_url,
        "browser_ws_endpoint": settings.browser_ws_endpoint,
        "api_key_configured": bool(resolve_api_key(settings)),
        "agent_stack_available": _agent_stack_available(),
        "runtime": get_runtime_state(),
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
    if not _plaintext_card_endpoint_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                "Plaintext card endpoint is disabled; use "
                "POST /billing/card/encrypted after verifying attestation"
            ),
        )
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


# ═══════════════════════════════════════════════════════════════════════════
# Deal lifecycle endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/deal/notify-funded")
async def deal_notify_funded(notification: DealFundedNotification):
    """Called by the on-chain watcher when a deal is funded.

    Creates an IsolatedTinkerSession for this deal.
    """
    cp = _get_control_plane()
    ctx = cp.on_deal_funded(
        deal_id=notification.deal_id,
        buyer=notification.buyer,
        seller=notification.seller,
        budget_cap=notification.budget_cap,
        reserve_price=notification.reserve_price,
    )
    return {"deal_id": ctx.deal_id, "state": ctx.state.value}


@app.post("/deal/{deal_id}/artifact")
async def deal_upload_artifact(deal_id: str, upload: ArtifactUpload):
    """Seller uploads artifact payload. Held in memory only."""
    artifact_buffer = None
    try:
        artifact_buffer = decode_artifact_hex(upload.artifact_hex)
        cp = _get_control_plane()
        cp.receive_artifact(deal_id, artifact_buffer, upload.artifact_hash)
        return {"deal_id": deal_id, "received": True, "size": len(artifact_buffer)}
    except KeyError:
        raise HTTPException(404, f"Deal {deal_id} not found")
    except (AssertionError, ValueError) as e:
        raise HTTPException(400, redact_text(e))
    finally:
        zero_buffer(artifact_buffer)


@app.post("/deal/{deal_id}/evaluate")
async def deal_evaluate(deal_id: str):
    """Trigger evaluation for a deal that has received its artifact.

    Uses the stub evaluator. In production, the evaluator is pluggable.
    """
    cp = _get_control_plane()

    try:
        from tinker_delegate.evaluator import stub_evaluate
        result = await cp.evaluate(deal_id, stub_evaluate)
        return EvaluationResultResponse(
            deal_id=result.deal_id,
            score_band=result.score_band.value,
            quality_delta=result.quality_delta,
            offer_price=result.offer_price,
            recommendation=result.recommendation,
            confidence=result.confidence,
            methodology_summary=result.methodology_summary,
            compute_cost_wei=result.compute_cost_wei,
            fee_wei=result.fee_wei,
        )
    except KeyError:
        raise HTTPException(404, f"Deal {deal_id} not found")
    except AssertionError as e:
        raise HTTPException(400, redact_text(e))


@app.get("/deal/{deal_id}/result", response_model=EvaluationResultResponse)
async def deal_get_result(deal_id: str):
    """Get bounded evaluation result for a completed deal."""
    cp = _get_control_plane()
    result = cp.get_result(deal_id)
    if result is None:
        raise HTTPException(404, f"No result for deal {deal_id}")
    return EvaluationResultResponse(
        deal_id=result.deal_id,
        score_band=result.score_band.value,
        quality_delta=result.quality_delta,
        offer_price=result.offer_price,
        recommendation=result.recommendation,
        confidence=result.confidence,
        methodology_summary=result.methodology_summary,
        compute_cost_wei=result.compute_cost_wei,
        fee_wei=result.fee_wei,
    )


@app.post("/deal/{deal_id}/resolve")
async def deal_resolve(deal_id: str):
    """Notify that a deal has been resolved on-chain.

    Triggers cleanup: session destroyed, artifact zeroed.
    """
    cp = _get_control_plane()
    cp.on_deal_resolved(deal_id)
    return {"deal_id": deal_id, "resolved": True}


@app.get("/deals")
async def list_deals():
    """List active deals."""
    cp = _get_control_plane()
    return {"active_deals": cp.active_deals}
