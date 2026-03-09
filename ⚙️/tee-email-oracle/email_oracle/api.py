"""FastAPI service for the email oracle.

Endpoints:
  POST /pin          — extract a verification pin from inbox
  GET  /health       — service health + credential status
  GET  /inbox        — list recent emails (debug)
  GET  /attestation  — TDX quote (no-op locally, real in TEE)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from email_oracle.config import Settings
from email_oracle.cred_store import CredentialStore, EmailCredentials
from email_oracle.imap_client import IMAPClient


# --- Request / Response models ---

class PinRequest(BaseModel):
    from_filter: str = Field("", description="Filter by sender address")
    subject_contains: str = Field("", description="Filter by subject substring")
    max_age_seconds: int = Field(300, description="Max email age in seconds")
    extract_pattern: str = Field(r"\b\d{6}\b", description="Regex to extract pin")
    delete_after: bool = Field(False, description="Delete email after extraction")


class PinResponse(BaseModel):
    pin: str
    email_id: str
    subject: str
    sender: str
    received_at: str
    oracle_email: str
    timestamp: str
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


state = OracleState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize oracle on startup."""
    settings = Settings()
    state.settings = settings
    state.store = CredentialStore(settings.cred_store_path, settings.cred_store_key)

    # Load existing credentials
    if state.store.exists():
        try:
            state.creds = state.store.load()
            print(f"[api] loaded credentials for {state.creds.email}")
        except Exception as e:
            print(f"[api] failed to decrypt credentials (wrong key?): {e}")
            print("[api] delete the credential file or set the correct ORACLE_CRED_STORE_KEY")
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


@app.post("/pin", response_model=PinResponse)
async def extract_pin(req: PinRequest):
    """Extract a verification pin from the oracle's inbox."""
    if not state.creds or not state.imap:
        raise HTTPException(503, "Oracle not initialized — no credentials")

    result = state.imap.search_and_extract(
        from_filter=req.from_filter,
        subject_contains=req.subject_contains,
        max_age_seconds=req.max_age_seconds,
        extract_pattern=req.extract_pattern,
    )

    if not result:
        raise HTTPException(404, "No matching pin found in inbox")

    if req.delete_after:
        try:
            state.imap.delete_email(result.email_id)
        except Exception as e:
            print(f"[api] failed to delete email {result.email_id}: {e}")

    tdx_quote = ""
    if state.settings.dstack_enabled:
        tdx_quote = _get_tdx_quote(f"pin:{result.pin}")

    return PinResponse(
        pin=result.pin,
        email_id=result.email_id,
        subject=result.subject,
        sender=result.sender,
        received_at=result.received_at,
        oracle_email=state.creds.email,
        timestamp=datetime.now(timezone.utc).isoformat(),
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


@app.get("/inbox")
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

    # In dstack TEE, this would call TappdClient
    quote = _get_tdx_quote("attestation")
    return AttestationResponse(
        tdx_quote=quote,
        app_id=_get_app_id(),
        compose_hash=_get_compose_hash(),
        oracle_email=state.creds.email if state.creds else "",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _get_tdx_quote(report_data: str) -> str:
    """Get TDX quote — stub for local, real in dstack."""
    # In TEE: from dstack_sdk import DstackClient
    # client = DstackClient()
    # quote = client.get_quote(report_data=report_data.encode())
    # return quote.quote.hex()
    return "stub-tdx-quote"


def _get_app_id() -> str:
    # In TEE: client.info().app_id
    return "local-dev"


def _get_compose_hash() -> str:
    # In TEE: client.info().tcb_info.compose_hash
    return "local-dev"
