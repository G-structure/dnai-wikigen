"""FastAPI server for tinker-delegate.

Endpoints:
  GET  /health                    — service health + oracle email
  GET  /attestation               — TDX attestation quote + context-bound encryption public key
  POST /auth/reauth               — bounded Tinker OTP re-auth, disabled unless explicitly enabled
  GET  /billing/balance           — current Tinker balance
  GET  /billing/funding-policy    — bounded active funding mode
  GET  /billing/funding-preflight — bounded operator validation readiness
  GET  /billing/funding-receipts  — bounded funding attempt audit records
  POST /billing/card              — add payment method (plaintext — local dev only)
  POST /billing/card/encrypted    — add payment method (encrypted to TEE — production)
  POST /billing/add-balance       — add credit balance
  POST /deal/{deal_id}/artifact/encrypted — upload seller's encrypted artifact
  POST /deal/{deal_id}/artifact   — plaintext local-dev artifact hook
  GET  /deal/{deal_id}/result     — get bounded evaluation result
  GET  /deals                     — list active deals
  POST /deal/{deal_id}/evaluate   — trigger evaluation (internal)
  POST /deal/{deal_id}/resolve    — notify deal resolution (internal)
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from cryptography.exceptions import InvalidTag
from pydantic import BaseModel

from tinker_delegate.api_key_store import resolve_api_key
from tinker_delegate.artifacts import (
    decode_artifact_hex,
    decrypt_artifact_payload,
    zero_buffer,
)
from tinker_delegate.config import Settings
from tinker_delegate.crypto import EncryptedPayload
from tinker_delegate.dstack_utils import is_dstack_enabled
from tinker_delegate.funding_receipt_store import build_funding_receipt_store
from tinker_delegate.funding_policy import (
    FundingPolicyError,
    funding_policy_status,
    funding_validation_preflight,
)
from tinker_delegate.oracle_client import OracleClient
from tinker_delegate.redaction import redact_text
from tinker_delegate.run_metadata_store import build_run_metadata_store
from tinker_delegate.runtime_hardening import disable_core_dumps
from tinker_delegate.runtime_state import get_runtime_state, update_runtime_state
from tinker_delegate.card_channel import (
    CardPayload,
    EncryptedCardPayload,
    BalancePayload,
    BillingResponse,
    get_tee_keypair,
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
disable_core_dumps()

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


def _plaintext_artifact_endpoint_allowed() -> bool:
    """Plaintext artifacts are a local-dev escape hatch, never a TEE path."""
    return settings.allow_plaintext_artifact_endpoint and not is_dstack_enabled()


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
        _control_plane = ControlPlane(api_key, run_metadata_store=build_run_metadata_store(settings))
    return _control_plane


# ---------------------------------------------------------------------------
# Deal API models
# ---------------------------------------------------------------------------

class ArtifactUpload(BaseModel):
    artifact_hex: str        # hex-encoded artifact payload
    artifact_hash: str       # keccak256 of the artifact

class EncryptedArtifactUpload(BaseModel):
    ephemeral_public_key: str  # hex
    nonce: str                 # hex
    ciphertext: str            # hex
    artifact_hash: str         # keccak256 of the decrypted artifact

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


ATTESTATION_CONTEXTS = {"ingress", "artifact", "billing"}


@app.get("/attestation")
async def attestation(context: str = "ingress"):
    """Get TDX attestation quote + context-bound TEE encryption public key.

    Developer MUST:
    1. Verify the TDX quote (code measurements match expected values)
    2. Verify report_data binds context + encryption_public_key
    3. Extract encryption_public_key from the response
    4. Encrypt card details or artifacts to this key before sending them to an encrypted endpoint
    """
    if context not in ATTESTATION_CONTEXTS:
        raise HTTPException(400, "unsupported attestation context")
    return get_attestation(context)


@app.post("/auth/reauth")
async def auth_reauth():
    """Refresh Tinker browser auth through the OTP path.

    This endpoint is disabled by default because it can trigger account auth
    emails. Enable only for an internal/deployed control plane that already
    restricts who can invoke account operations.
    """
    if not settings.allow_auth_automation_endpoint:
        raise HTTPException(403, "auth automation endpoint is disabled")

    from tinker_delegate.signup import reauth

    result = await reauth(settings)
    update_runtime_state(
        reauth_attempted=True,
        reauth_success=bool(result.get("success")),
        reauth_error_kind=result.get("error_kind", ""),
        last_reauth_attempt_record=result.get("attempt_record"),
    )
    return result


@app.get("/billing/balance")
async def billing_balance():
    """Get current Tinker account balance."""
    result = await handle_get_balance(settings)
    return result.model_dump()


@app.get("/billing/funding-policy")
async def billing_funding_policy():
    """Return the bounded funding-mode policy for this delegate."""
    try:
        return funding_policy_status(settings).to_public_dict()
    except FundingPolicyError as e:
        raise HTTPException(503, redact_text(e)) from e


@app.get("/billing/funding-preflight")
async def billing_funding_preflight(
    amount_dollars: Optional[float] = None,
    require_add_balance_endpoint: bool = False,
    api_url: str = "",
    expected_compose_hash: str = "",
    expected_app_id: str = "",
    expected_os_image_hash: str = "",
    allow_local_attestation: bool = False,
    fetch_attestation: bool = False,
):
    """Return bounded readiness checks for an operator funding validation."""
    try:
        return funding_validation_preflight(
            settings,
            amount_dollars=amount_dollars,
            require_add_balance_endpoint=require_add_balance_endpoint,
            api_url=api_url,
            expected_compose_hash=expected_compose_hash,
            expected_app_id=expected_app_id,
            expected_os_image_hash=expected_os_image_hash,
            allow_local_attestation=allow_local_attestation,
            fetch_attestation=fetch_attestation,
        ).to_public_dict()
    except FundingPolicyError as e:
        raise HTTPException(503, redact_text(e)) from e


@app.get("/billing/funding-receipts")
async def billing_funding_receipts():
    """Return bounded funding attempt records from sealed storage."""
    try:
        receipts = build_funding_receipt_store(settings).load()
    except Exception as e:
        raise HTTPException(503, f"funding receipt store unavailable: {redact_text(e)}") from e
    return {"count": len(receipts), "receipts": receipts}


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
    TEE's public key from GET /attestation?context=billing.

    Protocol:
    1. GET /attestation?context=billing → verify TDX quote → extract encryption_public_key
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
    if not settings.allow_add_balance_endpoint:
        raise HTTPException(
            status_code=403,
            detail=(
                "Add-balance endpoint is disabled; use the capped operator "
                "CLI path or explicitly enable TINKER_ALLOW_ADD_BALANCE_ENDPOINT"
            ),
        )
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
    """Seller uploads artifact payload. Local dev only; held in memory only."""
    if not _plaintext_artifact_endpoint_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                "Plaintext artifact endpoint is disabled; use "
                "POST /deal/{deal_id}/artifact/encrypted after verifying attestation"
            ),
        )
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
    except InvalidTag:
        raise HTTPException(400, "encrypted artifact could not be decrypted or verified")
    finally:
        zero_buffer(artifact_buffer)


@app.post("/deal/{deal_id}/artifact/encrypted")
async def deal_upload_artifact_encrypted(deal_id: str, upload: EncryptedArtifactUpload):
    """Seller uploads artifact encrypted to the quote-bound TEE public key."""
    artifact_buffer = None
    try:
        encrypted = EncryptedPayload.from_hex({
            "ephemeral_public_key": upload.ephemeral_public_key,
            "nonce": upload.nonce,
            "ciphertext": upload.ciphertext,
        })
        artifact_buffer = decrypt_artifact_payload(
            encrypted,
            get_tee_keypair(),
            deal_id=deal_id,
            artifact_hash=upload.artifact_hash,
        )
        cp = _get_control_plane()
        cp.receive_artifact(deal_id, artifact_buffer, upload.artifact_hash)
        return {"deal_id": deal_id, "received": True, "size": len(artifact_buffer)}
    except KeyError:
        raise HTTPException(404, f"Deal {deal_id} not found")
    except (AssertionError, ValueError) as e:
        raise HTTPException(400, redact_text(e))
    except InvalidTag:
        raise HTTPException(400, "encrypted artifact could not be decrypted or verified")
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
