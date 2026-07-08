"""Client-side attestation-gated artifact uploader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from tinker_delegate.artifacts import artifact_keccak256, encrypt_artifact_payload, zero_buffer
from tinker_delegate.card_channel import attestation_report_data


class AttestationVerificationError(RuntimeError):
    """Raised when the attestation response does not satisfy upload policy."""


@dataclass(frozen=True)
class ArtifactUploadPolicy:
    """Client-side policy for accepting a TEE artifact-ingress key."""

    expected_compose_hash: str = ""
    expected_app_id: str = ""
    context: str = "artifact"
    allow_local: bool = False


@dataclass(frozen=True)
class ArtifactUploadResult:
    """Bounded result from an encrypted artifact upload attempt."""

    deal_id: str
    artifact_hash: str
    size: int
    status_code: int
    response: dict[str, Any]


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _hex_bytes(value: object, field: str, *, expected_len: int | None = None) -> bytes:
    if not isinstance(value, str) or not value:
        raise AttestationVerificationError(f"{field} is missing")
    raw = value[2:] if value.startswith(("0x", "0X")) else value
    try:
        decoded = bytes.fromhex(raw)
    except ValueError as exc:
        raise AttestationVerificationError(f"{field} must be hex") from exc
    if expected_len is not None and len(decoded) != expected_len:
        raise AttestationVerificationError(f"{field} must be {expected_len} bytes")
    if expected_len is None and not decoded:
        raise AttestationVerificationError(f"{field} must be non-empty")
    return decoded


def verify_artifact_attestation(
    attestation: dict[str, Any],
    policy: ArtifactUploadPolicy,
) -> str:
    """Verify the attestation envelope before using its encryption key.

    This fail-closed gate checks the evidence fields the service exposes today:
    dstack mode, non-empty quote bytes, compose/app identity, operation context,
    32-byte encryption key, and report_data recomputed from that key. It does
    not parse Intel TDX quote internals; that remains a separate verifier task.
    """
    mode = attestation.get("mode")
    if mode == "local":
        if not policy.allow_local:
            raise AttestationVerificationError("local attestation is not allowed")
    elif mode == "tdx":
        if attestation.get("verified") is False:
            raise AttestationVerificationError("attestation endpoint reported verification failure")
        _hex_bytes(attestation.get("quote"), "quote")
        if not policy.expected_compose_hash:
            raise AttestationVerificationError("expected compose hash is required for tdx mode")
        if attestation.get("compose_hash") != policy.expected_compose_hash:
            raise AttestationVerificationError("compose hash mismatch")
        if policy.expected_app_id and attestation.get("app_id") != policy.expected_app_id:
            raise AttestationVerificationError("app id mismatch")
    else:
        raise AttestationVerificationError("attestation mode must be tdx")

    if attestation.get("report_context") != policy.context:
        raise AttestationVerificationError("report context mismatch")

    public_key = _hex_bytes(
        attestation.get("encryption_public_key"),
        "encryption_public_key",
        expected_len=32,
    )
    report_data = _hex_bytes(attestation.get("report_data"), "report_data", expected_len=32)
    expected_report_data = attestation_report_data(policy.context, public_key)
    if report_data != expected_report_data:
        raise AttestationVerificationError("report data does not bind the encryption key")

    return public_key.hex()


def upload_artifact_bytes(
    base_url: str,
    deal_id: str,
    artifact: bytes | bytearray,
    policy: ArtifactUploadPolicy,
    *,
    client: httpx.Client | None = None,
) -> ArtifactUploadResult:
    """Fetch attestation, verify it, encrypt artifact bytes, and upload."""
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        attestation_response = http.get(_endpoint(base_url, "/attestation"))
        attestation_response.raise_for_status()
        tee_public_key = verify_artifact_attestation(attestation_response.json(), policy)

        artifact_hash = artifact_keccak256(artifact)
        encrypted = encrypt_artifact_payload(
            artifact,
            tee_public_key,
            deal_id=deal_id,
            artifact_hash=artifact_hash,
        )

        upload_response = http.post(
            _endpoint(base_url, f"/deal/{deal_id}/artifact/encrypted"),
            json=encrypted,
        )
        upload_response.raise_for_status()
        return ArtifactUploadResult(
            deal_id=deal_id,
            artifact_hash=artifact_hash,
            size=len(artifact),
            status_code=upload_response.status_code,
            response=upload_response.json(),
        )
    finally:
        if owns_client:
            http.close()


def upload_artifact_file(
    base_url: str,
    deal_id: str,
    artifact_path: str | Path,
    policy: ArtifactUploadPolicy,
) -> ArtifactUploadResult:
    """Read an artifact file into memory, upload it encrypted, then zero it."""
    artifact = bytearray(Path(artifact_path).read_bytes())
    try:
        return upload_artifact_bytes(base_url, deal_id, artifact, policy)
    finally:
        zero_buffer(artifact)
