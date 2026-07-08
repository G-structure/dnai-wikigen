"""Artifact ingress helpers for bounded, hash-checked uploads."""

from __future__ import annotations

from eth_hash.auto import keccak


def decode_artifact_hex(artifact_hex: str) -> bytearray:
    """Decode a hex artifact payload into a mutable buffer."""
    raw = artifact_hex[2:] if artifact_hex.startswith(("0x", "0X")) else artifact_hex
    if len(raw) % 2 != 0:
        raise ValueError("artifact_hex must contain an even number of hex characters")
    try:
        return bytearray.fromhex(raw)
    except ValueError as exc:
        raise ValueError("artifact_hex must be valid hex") from exc


def zero_buffer(buffer: bytearray | None) -> None:
    """Best-effort in-place zeroing for mutable artifact buffers."""
    if buffer is None:
        return
    for i in range(len(buffer)):
        buffer[i] = 0


def normalize_artifact_hash(artifact_hash: str) -> str:
    """Normalize a bytes32 hash string to 0x-prefixed lowercase hex."""
    raw = artifact_hash[2:] if artifact_hash.startswith(("0x", "0X")) else artifact_hash
    if len(raw) != 64:
        raise ValueError("artifact_hash must be a 32-byte hex string")
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError("artifact_hash must be valid hex") from exc
    return f"0x{raw.lower()}"


def artifact_keccak256(artifact: bytes | bytearray) -> str:
    """Return Ethereum keccak256 hash for artifact bytes."""
    return f"0x{keccak(bytes(artifact)).hex()}"


def verify_artifact_hash(artifact: bytes | bytearray, artifact_hash: str) -> str:
    """Verify artifact bytes against the expected on-chain keccak256 hash."""
    expected = normalize_artifact_hash(artifact_hash)
    actual = artifact_keccak256(artifact)
    if actual != expected:
        raise ValueError("artifact_hash does not match uploaded artifact")
    return expected
