"""Helpers for dstack-backed storage and attestation."""

from __future__ import annotations

import hashlib
import os

from dstack_sdk import DstackClient


def _client() -> DstackClient:
    endpoint = os.environ.get("DSTACK_SIMULATOR_ENDPOINT", "").strip()
    if endpoint:
        return DstackClient(endpoint)
    return DstackClient()


def _normalize_report_data(report_data: str | bytes) -> bytes:
    raw = report_data.encode() if isinstance(report_data, str) else report_data
    if len(raw) <= 64:
        return raw
    return hashlib.sha256(raw).digest()


def derive_storage_key(path: str) -> bytes:
    """Derive a deterministic 32-byte secret bound to this CVM identity."""
    client = _client()
    result = client.get_key(path, "encryption")
    return result.decode_key()[:32]


def get_attestation(report_data: str | bytes) -> tuple[str, str, str]:
    """Return quote hex, app id, and compose hash for the running CVM."""
    client = _client()
    info = client.info()
    quote = client.get_quote(_normalize_report_data(report_data))
    return quote.quote, info.app_id, info.compose_hash
