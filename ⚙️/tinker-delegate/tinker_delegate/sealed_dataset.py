"""Envelope encryption for portable, TEE-sealed datasets.

This is the load-bearing primitive for "Sealed Data At Rest" (see PROJECT.md /
ARCHITECTURE.md): a reward dataset can live on untrusted public storage
(Hugging Face Hub, S3, IPFS) while plaintext exists only inside the attested
boundary. The construction reuses the existing X25519 + AES-256-GCM channel
(`crypto.encrypt_for_tee` / `TEEKeyPair`), it is not a new scheme:

    DEK   = fresh random AES-256 key (per dataset)
    blob  = chunked AES-256-GCM(plaintext, DEK)   # large, storage-agnostic
    wrap  = encrypt_for_tee(DEK, recipient CVM pubkey)  # one per measurement
    manifest = bounded { dataset_id, hashes, wrapped-DEK per recipient,
                         data_sensitivity, storage ref, optional signature }

Bounded-output rule: every public function here returns only hashes, sizes,
counts, labels, and ciphertext. The DEK and plaintext never appear in a
manifest or receipt. Storage backends (local/HF/S3/https) are intentionally out
of scope for this module — it produces/consumes the ciphertext blob + manifest;
where those bytes are published is a separate adapter.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tinker_delegate.crypto import NONCE_SIZE, EncryptedPayload, TEEKeyPair, encrypt_for_tee

SCHEMA_VERSION = "sealed-dataset-manifest-v1"
DEK_HKDF_INFO_PREFIX = b"tinker-delegate-dataset-dek"
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB


class DataSensitivity(str, Enum):
    PUBLIC_BENCHMARK = "public_benchmark"
    PRIVATE = "private"
    PHI = "phi"


class SealedDatasetError(ValueError):
    """Raised when a sealed-dataset operation cannot be performed safely."""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_prefixed(value: str, *, prefix: str) -> str:
    return f"{prefix}_{hashlib.sha256(f'{prefix}:{value}'.encode()).hexdigest()[:48]}"


def generate_dek() -> bytes:
    """Fresh 256-bit data-encryption key. Never logged or placed in a manifest."""

    return AESGCM.generate_key(bit_length=256)


def _dek_info(dataset_id: str) -> bytes:
    return DEK_HKDF_INFO_PREFIX + b"|" + dataset_id.encode()


def _chunk_aad(dataset_id: str, index: int, total: int) -> bytes:
    return b"|".join((b"dataset-chunk", dataset_id.encode(), str(index).encode(), str(total).encode()))


@dataclass(frozen=True)
class EncryptedBlob:
    """Chunked AES-GCM ciphertext for a dataset, plus bounded chunk metadata."""

    dataset_id: str
    blob: bytes
    plaintext_sha256: str
    ciphertext_sha256: str
    plaintext_size: int
    chunk_size: int
    chunk_count: int
    chunk_nonces: tuple[str, ...]

    def chunk_metadata(self) -> dict[str, Any]:
        return {
            "chunk_size": self.chunk_size,
            "chunk_count": self.chunk_count,
            "chunk_nonces": list(self.chunk_nonces),
        }


def encrypt_dataset(
    plaintext: bytes,
    dek: bytes,
    *,
    dataset_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> EncryptedBlob:
    """Chunked AES-256-GCM encryption of `plaintext` under `dek`.

    Each chunk gets a fresh nonce and AAD binding dataset_id|index|total, so a
    truncated or reordered blob fails authentication. The wire blob is a length-
    prefixed concatenation of per-chunk ciphertexts.
    """

    if len(dek) != 32:
        raise SealedDatasetError("dek must be 32 bytes")
    if chunk_size <= 0:
        raise SealedDatasetError("chunk_size must be positive")
    aesgcm = AESGCM(dek)
    chunks = [plaintext[i : i + chunk_size] for i in range(0, len(plaintext), chunk_size)] or [b""]
    total = len(chunks)
    nonces: list[str] = []
    parts: list[bytes] = []
    for index, chunk in enumerate(chunks):
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = aesgcm.encrypt(nonce, chunk, _chunk_aad(dataset_id, index, total))
        nonces.append(nonce.hex())
        parts.append(len(ciphertext).to_bytes(8, "big") + ciphertext)
    blob = b"".join(parts)
    return EncryptedBlob(
        dataset_id=dataset_id,
        blob=blob,
        plaintext_sha256=_sha256_hex(plaintext),
        ciphertext_sha256=_sha256_hex(blob),
        plaintext_size=len(plaintext),
        chunk_size=chunk_size,
        chunk_count=total,
        chunk_nonces=tuple(nonces),
    )


def decrypt_dataset(
    blob: bytes,
    dek: bytes,
    *,
    dataset_id: str,
    chunk_nonces: list[str] | tuple[str, ...],
    expected_plaintext_sha256: str | None = None,
) -> bytearray:
    """Decrypt a chunked blob inside the boundary into a mutable buffer."""

    if len(dek) != 32:
        raise SealedDatasetError("dek must be 32 bytes")
    aesgcm = AESGCM(dek)
    total = len(chunk_nonces)
    out = bytearray()
    offset = 0
    for index in range(total):
        if offset + 8 > len(blob):
            raise SealedDatasetError("truncated blob header")
        length = int.from_bytes(blob[offset : offset + 8], "big")
        offset += 8
        ciphertext = blob[offset : offset + length]
        if len(ciphertext) != length:
            raise SealedDatasetError("truncated blob chunk")
        offset += length
        nonce = bytes.fromhex(chunk_nonces[index])
        plaintext = aesgcm.decrypt(nonce, ciphertext, _chunk_aad(dataset_id, index, total))
        out.extend(plaintext)
    if offset != len(blob):
        raise SealedDatasetError("trailing bytes after final chunk")
    if expected_plaintext_sha256 is not None and _sha256_hex(bytes(out)) != expected_plaintext_sha256:
        raise SealedDatasetError("plaintext hash mismatch after decrypt")
    return out


def wrap_dek(dek: bytes, recipient_public_key_hex: str, *, dataset_id: str) -> dict[str, str]:
    """Wrap the DEK to a recipient CVM's attestation-bound X25519 public key."""

    payload = encrypt_for_tee(
        dek,
        bytes.fromhex(recipient_public_key_hex),
        info=_dek_info(dataset_id),
    )
    envelope = payload.to_hex()
    envelope["recipient_key_hash"] = _hash_prefixed(recipient_public_key_hex, prefix="recipient")
    return envelope


def unwrap_dek(envelope: dict[str, str], tee_keypair: TEEKeyPair, *, dataset_id: str) -> bytes:
    """Unwrap the DEK inside the CVM using its attestation-bound private key."""

    payload = EncryptedPayload.from_hex(envelope)
    return tee_keypair.decrypt(payload, info=_dek_info(dataset_id))


def build_manifest(
    encrypted: EncryptedBlob,
    *,
    task: str,
    data_sensitivity: DataSensitivity,
    recipients: list[dict[str, str]],
    storage_ref: str | None = None,
) -> dict[str, Any]:
    """Assemble the bounded, egress-safe dataset manifest.

    Contains only hashes, sizes, chunk metadata, per-recipient wrapped-DEK
    envelopes, a sensitivity label, and an optional storage reference. Never the
    DEK or plaintext.
    """

    if not recipients:
        raise SealedDatasetError("at least one recipient is required")
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": encrypted.dataset_id,
        "task": task,
        "data_sensitivity": DataSensitivity(data_sensitivity).value,
        "ciphertext_sha256": encrypted.ciphertext_sha256,
        "plaintext_sha256": encrypted.plaintext_sha256,
        "plaintext_size": encrypted.plaintext_size,
        "chunk": encrypted.chunk_metadata(),
        "recipients": [
            {
                "recipient_key_hash": r["recipient_key_hash"],
                "ephemeral_public_key": r["ephemeral_public_key"],
                "nonce": r["nonce"],
                "ciphertext": r["ciphertext"],
            }
            for r in recipients
        ],
        "storage_ref": storage_ref,
        "raw_secret_egress": False,
    }


def seal_receipt(encrypted: EncryptedBlob, manifest: dict[str, Any]) -> dict[str, Any]:
    """Bounded, egress-safe receipt for a seal operation. No DEK/plaintext."""

    return {
        "dataset_id": encrypted.dataset_id,
        "task": manifest.get("task"),
        "data_sensitivity": manifest.get("data_sensitivity"),
        "ciphertext_sha256": encrypted.ciphertext_sha256,
        "plaintext_size": encrypted.plaintext_size,
        "chunk_count": encrypted.chunk_count,
        "recipient_count": len(manifest.get("recipients", [])),
        "recipient_key_hashes": [r["recipient_key_hash"] for r in manifest.get("recipients", [])],
        "manifest_hash": manifest_hash(manifest),
        "storage_ref": manifest.get("storage_ref"),
        "raw_secret_egress": False,
    }


def seal_dataset(
    plaintext: bytes,
    *,
    dataset_id: str,
    task: str,
    data_sensitivity: DataSensitivity | str,
    recipient_public_keys: list[str],
    storage_ref: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    """Envelope-encrypt a dataset for one or more attested CVM recipients.

    Returns `(ciphertext_blob, manifest, bounded_receipt)`. The DEK is generated,
    used, and dropped here; it never appears in the manifest or receipt.
    """

    if not recipient_public_keys:
        raise SealedDatasetError("at least one recipient public key is required")
    dek = generate_dek()
    encrypted = encrypt_dataset(plaintext, dek, dataset_id=dataset_id, chunk_size=chunk_size)
    recipients = [wrap_dek(dek, pk, dataset_id=dataset_id) for pk in recipient_public_keys]
    manifest = build_manifest(
        encrypted,
        task=task,
        data_sensitivity=DataSensitivity(data_sensitivity),
        recipients=recipients,
        storage_ref=storage_ref,
    )
    return encrypted.blob, manifest, seal_receipt(encrypted, manifest)


def _canonical(manifest: dict[str, Any]) -> str:
    egress_safe = {k: v for k, v in manifest.items() if k not in {"owner_signature", "signer_hash"}}
    return json.dumps(egress_safe, sort_keys=True, separators=(",", ":"))


def manifest_hash(manifest: dict[str, Any]) -> str:
    return _sha256_hex(_canonical(manifest).encode())


def verify_manifest(manifest: dict[str, Any], *, blob: bytes | None = None) -> dict[str, Any]:
    """Verify manifest schema/integrity without any plaintext access.

    Checks schema version, sensitivity label, recipient envelope shape, and — if
    the ciphertext blob is supplied — that its sha256 matches. Returns a bounded
    verification receipt.
    """

    problems: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append("bad_schema_version")
    try:
        DataSensitivity(manifest.get("data_sensitivity"))
    except ValueError:
        problems.append("bad_data_sensitivity")
    recipients = manifest.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        problems.append("no_recipients")
    else:
        for r in recipients:
            if not all(k in r for k in ("recipient_key_hash", "ephemeral_public_key", "nonce", "ciphertext")):
                problems.append("malformed_recipient")
                break
    chunk = manifest.get("chunk", {})
    if not isinstance(chunk, dict) or "chunk_nonces" not in chunk:
        problems.append("missing_chunk_metadata")
    ciphertext_ok = None
    if blob is not None:
        ciphertext_ok = _sha256_hex(blob) == manifest.get("ciphertext_sha256")
        if not ciphertext_ok:
            problems.append("ciphertext_hash_mismatch")
    return {
        "ok": not problems,
        "problems": problems,
        "dataset_id": manifest.get("dataset_id"),
        "data_sensitivity": manifest.get("data_sensitivity"),
        "recipient_count": len(recipients) if isinstance(recipients, list) else 0,
        "manifest_hash": manifest_hash(manifest),
        "ciphertext_verified": ciphertext_ok,
        "raw_secret_egress": False,
    }
