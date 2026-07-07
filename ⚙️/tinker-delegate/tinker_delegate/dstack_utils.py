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


def is_dstack_enabled() -> bool:
    raw = os.environ.get("DSTACK_ENABLED") or os.environ.get("TINKER_DSTACK_ENABLED") or "false"
    return raw.lower() == "true"


def _normalize_report_data(report_data: str | bytes) -> bytes:
    raw = report_data.encode() if isinstance(report_data, str) else report_data
    if len(raw) <= 64:
        return raw
    return hashlib.sha256(raw).digest()


def derive_storage_key(path: str) -> bytes:
    client = _client()
    result = client.get_key(path, "encryption")
    return result.decode_key()[:32]


def get_attestation(report_data: str | bytes) -> tuple[str, str, str]:
    client = _client()
    info = client.info()
    quote = client.get_quote(_normalize_report_data(report_data))
    return quote.quote, info.app_id, info.compose_hash
