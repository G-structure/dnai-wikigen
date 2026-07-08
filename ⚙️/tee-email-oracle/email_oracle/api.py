"""FastAPI service for the email oracle.

Endpoints:
  POST /pin          — extract a verification pin from inbox
  GET  /health       — service health + credential status
  GET  /inbox        — list recent emails (debug)
  GET  /attestation  — TDX quote (no-op locally, real in TEE)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from email_oracle.config import Settings
from email_oracle.cred_store import CredentialStore, EmailCredentials
from email_oracle.dstack_utils import derive_storage_key, get_attestation
from email_oracle.imap_client import IMAPClient


# --- Request / Response models ---

class PinRequest(BaseModel):
    target_service: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_.:-]+$",
        description="Service requesting the OTP, e.g. tinker",
    )
    expected_sender: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Expected sender substring/address",
    )
    expected_subject_contains: str = Field(
        "",
        max_length=255,
        description="Expected subject substring, empty only when the live subject is not stable",
    )
    max_age_seconds: int = Field(300, ge=1, le=900, description="Max email age in seconds")
    extract_pattern: str = Field(
        r"\b\d{6}\b",
        min_length=1,
        max_length=128,
        description="Regex to extract a bounded OTP/confirmation code",
    )
    nonce: str = Field(
        ...,
        min_length=8,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_.:-]+$",
        description="Caller-generated one-time request nonce",
    )
    caller_identity: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Bounded caller identity such as app id, compose hash, or service name",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Human-readable bounded purpose for audit logs",
    )
    delete_after: bool = Field(False, description="Delete email after extraction")

    @field_validator("extract_pattern")
    @classmethod
    def validate_extract_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid extract_pattern: {exc}") from exc
        return value


class PinResponse(BaseModel):
    pin: str
    email_id: str
    subject: str
    sender: str
    received_at: str
    oracle_email: str
    timestamp: str
    request_hash: str
    otp_use_hash: str
    tdx_quote: str = ""  # populated in TEE mode


class HealthResponse(BaseModel):
    status: str
    oracle_email: str
    imap_connected: bool
    dstack_enabled: bool
    timestamp: str


class AttestationResponse(BaseModel):
    tdx_quote: str
    app_id: str
    compose_hash: str
    oracle_email: str
    timestamp: str


# --- App state ---

class OracleState:
    def __init__(self):
        self.settings: Settings | None = None
        self.store: CredentialStore | None = None
        self.creds: EmailCredentials | None = None
        self.imap: IMAPClient | None = None
        self.used_otp_hashes: set[str] = set()


state = OracleState()


def _runtime_auth_enabled() -> bool:
    settings = state.settings
    if not settings:
        return False
    return settings.runtime_auth_required or bool(settings.runtime_auth_token)


def _runtime_auth_token() -> str:
    settings = state.settings
    if not settings:
        return ""
    if settings.runtime_auth_token:
        return settings.runtime_auth_token
    if settings.dstack_enabled:
        key = derive_storage_key(settings.runtime_auth_key_path)
        return hashlib.sha256(b"email-oracle-runtime-auth:" + key).hexdigest()
    return ""


def require_runtime_auth(authorization: str = Header(default="")) -> None:
    """Protect OTP and inbox egress with same-CVM bearer auth."""
    if not _runtime_auth_enabled():
        return

    expected = _runtime_auth_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Oracle runtime auth is required but no token is configured",
        )

    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token",
        )


def _hash_json(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _pin_request_hash(req: PinRequest) -> str:
    return _hash_json(
        {
            "target_service": req.target_service,
            "expected_sender": req.expected_sender,
            "expected_subject_contains": req.expected_subject_contains,
            "max_age_seconds": req.max_age_seconds,
            "extract_pattern": req.extract_pattern,
            "nonce": req.nonce,
            "caller_identity": req.caller_identity,
            "reason": req.reason,
            "delete_after": req.delete_after,
        }
    )


def _otp_use_hash(req: PinRequest, result, oracle_email: str) -> str:
    return _hash_json(
        {
            "target_service": req.target_service,
            "caller_identity": req.caller_identity,
            "oracle_email": oracle_email,
            "email_id": result.email_id,
            "pin_hash": hashlib.sha256(result.pin.encode()).hexdigest(),
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize oracle on startup."""
    settings = Settings()
    state.settings = settings
    state.store = CredentialStore(
        settings.cred_store_path,
        settings.cred_store_key,
        dstack_enabled=settings.dstack_enabled,
        dstack_key_path=settings.dstack_key_path,
    )

    # Load existing credentials
    if state.store.exists():
        try:
            state.creds = state.store.load()
            print(f"[api] loaded credentials for {state.creds.email}")
        except Exception as e:
            print(f"[api] failed to decrypt credentials (wrong key?): {e}")
            print("[api] delete the credential file or use the same dstack key path / ORACLE_CRED_STORE_KEY")
            state.creds = None
    else:
        print("[api] no credentials found — run genesis first")

    # Connect IMAP if we have creds
    if state.creds:
        state.imap = IMAPClient(state.creds, settings)
        try:
            state.imap.connect()
        except Exception as e:
            print(f"[api] IMAP connection failed (will retry on request): {e}")

    yield

    # Cleanup
    if state.imap:
        state.imap.disconnect()


app = FastAPI(
    title="TEE Email Oracle",
    description="Verification pin extraction from TEE-sealed email account",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/pin", response_model=PinResponse, dependencies=[Depends(require_runtime_auth)])
async def extract_pin(req: PinRequest):
    """Extract a verification pin from the oracle's inbox."""
    if not state.creds or not state.imap:
        raise HTTPException(503, "Oracle not initialized — no credentials")

    result = state.imap.search_and_extract(
        from_filter=req.expected_sender,
        subject_contains=req.expected_subject_contains,
        max_age_seconds=req.max_age_seconds,
        extract_pattern=req.extract_pattern,
    )

    if not result:
        raise HTTPException(404, "No matching pin found in inbox")

    if len(result.pin) > state.settings.pin_max_length:
        raise HTTPException(400, "Extracted value exceeds OTP length cap")

    request_hash = _pin_request_hash(req)
    otp_use_hash = _otp_use_hash(req, result, state.creds.email)
    if otp_use_hash in state.used_otp_hashes:
        raise HTTPException(409, "OTP has already been released")
    state.used_otp_hashes.add(otp_use_hash)

    if req.delete_after:
        try:
            state.imap.delete_email(result.email_id)
        except Exception as e:
            print(f"[api] failed to delete email {result.email_id}: {e}")

    tdx_quote = ""
    if state.settings.dstack_enabled:
        tdx_quote, _, _ = get_attestation(f"pin:{request_hash}:{otp_use_hash}")

    return PinResponse(
        pin=result.pin,
        email_id=result.email_id,
        subject=result.subject,
        sender=result.sender,
        received_at=result.received_at,
        oracle_email=state.creds.email,
        timestamp=datetime.now(timezone.utc).isoformat(),
        request_hash=request_hash,
        otp_use_hash=otp_use_hash,
        tdx_quote=tdx_quote,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Service health check."""
    imap_ok = False
    if state.imap:
        try:
            state.imap._ensure_connected()
            imap_ok = True
        except Exception:
            pass

    return HealthResponse(
        status="ok" if state.creds and imap_ok else "degraded",
        oracle_email=state.creds.email if state.creds else "",
        imap_connected=imap_ok,
        dstack_enabled=state.settings.dstack_enabled if state.settings else False,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/inbox", dependencies=[Depends(require_runtime_auth)])
async def list_inbox(max_age: int = 3600, limit: int = 20):
    """List recent emails (debug endpoint)."""
    if not state.imap:
        raise HTTPException(503, "IMAP not connected")
    return state.imap.list_recent(max_age_seconds=max_age, limit=limit)


@app.get("/attestation", response_model=AttestationResponse)
async def attestation():
    """Get TDX attestation quote (no-op locally)."""
    if not state.settings.dstack_enabled:
        return AttestationResponse(
            tdx_quote="local-mode-no-attestation",
            app_id="local-dev",
            compose_hash="local-dev",
            oracle_email=state.creds.email if state.creds else "",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    quote, app_id, compose_hash = get_attestation("attestation")
    return AttestationResponse(
        tdx_quote=quote,
        app_id=app_id,
        compose_hash=compose_hash,
        oracle_email=state.creds.email if state.creds else "",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
