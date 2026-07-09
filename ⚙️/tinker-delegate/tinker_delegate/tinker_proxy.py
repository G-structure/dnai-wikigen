"""Bounded Tinker proxy credentials and status helpers.

The Tinker proxy is the intended public surface for Tinker operations. The CVM
keeps the upstream Tinker API key, project id, base URL, browser session, and
payment state sealed; approved users receive only scoped delegate tokens and
bounded operation receipts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tinker_delegate.api_key_store import resolve_api_key
from tinker_delegate.crypto import _derive_aes_key, encrypt_for_tee
from tinker_delegate.dstack_utils import derive_storage_key, is_dstack_enabled
from tinker_delegate.run_metadata_store import stable_hash
from tinker_delegate.tinker_proxy_store import (
    build_proxy_token_store,
    make_proxy_token_issue_record,
)


PROXY_TOKEN_HKDF_INFO = b"tinker-delegate-proxy-token"
SUPPORTED_PROXY_SCOPES = {
    "proxy:status",
    "tinker:smoke",
    "billing:payment-method-status",
    "billing:add-balance",
}


def generate_proxy_recipient_keypair() -> tuple[str, str]:
    """Generate a recipient X25519 keypair for encrypted proxy-token delivery."""

    private_key = X25519PrivateKey.generate()
    private_key_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_key_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private_key_hex, public_key_hex


def decrypt_encrypted_proxy_token(payload: dict[str, Any], recipient_private_key_hex: str) -> str:
    """Decrypt an encrypted proxy-token issuance response with the recipient key."""

    private_key = X25519PrivateKey.from_private_bytes(bytes.fromhex(recipient_private_key_hex))
    encrypted = payload["encrypted_token"]
    sender_public = X25519PublicKey.from_public_bytes(bytes.fromhex(encrypted["ephemeral_public_key"]))
    shared_secret = private_key.exchange(sender_public)
    aes_key = _derive_aes_key(shared_secret, info=PROXY_TOKEN_HKDF_INFO)
    plaintext = AESGCM(aes_key).decrypt(
        bytes.fromhex(encrypted["nonce"]),
        bytes.fromhex(encrypted["ciphertext"]),
        bytes.fromhex(payload["associated_data"]),
    )
    return plaintext.decode("utf-8")


@dataclass(frozen=True)
class ProxyTokenClaims:
    subject: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    jwt_id: str
    issuer: str
    audience: str

    def to_jwt_payload(self) -> dict[str, Any]:
        return {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": self.subject,
            "scope": " ".join(self.scopes),
            "iat": self.issued_at,
            "nbf": self.issued_at,
            "exp": self.expires_at,
            "jti": self.jwt_id,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "subject_hash": stable_hash(self.subject, prefix="proxy_subject"),
            "scopes": list(self.scopes),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "ttl_seconds": max(0, self.expires_at - self.issued_at),
            "jwt_id_hash": stable_hash(self.jwt_id, prefix="proxy_jti"),
        }


def build_tinker_proxy_status(settings) -> dict[str, Any]:
    """Return bounded evidence about the sealed Tinker proxy configuration."""

    api_key_configured = bool(resolve_api_key(settings))
    project_id = getattr(settings, "project_id", "")
    base_url = getattr(settings, "base_url", "")
    return {
        "surface": "tinker_proxy",
        "schema_version": 1,
        "success": api_key_configured,
        "proxy_boundary": {
            "mode": "tee_cvm_delegate" if is_dstack_enabled() else "local_or_unattested_delegate",
            "sdk_client_created_inside_delegate": True,
            "jwt_signing_key_source": _signing_key_source(settings),
            "raw_credentials_returned": False,
            "raw_project_id_returned": False,
            "raw_secret_egress": False,
        },
        "sealed_client_config": {
            "api_key_configured": api_key_configured,
            "api_key_returned": False,
            "project_id_configured": bool(project_id),
            "project_id_hash": stable_hash(project_id, prefix="tinker_project") if project_id else "",
            "project_id_returned": False,
            "base_url_configured": bool(base_url),
            "base_url_host_family": _base_url_host_family(base_url),
            "base_url_hash": stable_hash(base_url, prefix="tinker_base_url") if base_url else "",
            "base_url_returned": False,
        },
        "token_issuer": {
            "enabled": bool(getattr(settings, "allow_tinker_proxy_token_issuance", False)),
            "format": "jwt_hs256",
            "delivery": "x25519_aes_256_gcm_envelope",
            "audit_store": "sealed",
            "issue_policy_required": bool(getattr(settings, "proxy_require_issue_policy", False)),
            "issue_policy_configured": bool(getattr(settings, "proxy_issue_policy_path", "")),
            "plaintext_token_returned": False,
            "supported_scopes": sorted(SUPPORTED_PROXY_SCOPES),
        },
        "allowed_proxy_operations": [
            {
                "operation": "status",
                "enabled": True,
                "bounded_output": True,
                "raw_secret_egress": False,
            },
            {
                "operation": "tinker_sdk_smoke",
                "enabled": bool(getattr(settings, "allow_tinker_smoke_endpoint", False)),
                "bounded_output": True,
                "raw_secret_egress": False,
            },
            {
                "operation": "add_balance",
                "enabled": bool(getattr(settings, "allow_add_balance_endpoint", False)),
                "bounded_output": True,
                "raw_secret_egress": False,
            },
        ],
        "next_required_configuration": _next_required_configuration(
            api_key_configured=api_key_configured,
            project_id_configured=bool(project_id),
        ),
        "raw_secret_egress": False,
    }


def issue_encrypted_proxy_token(
    settings,
    *,
    subject: str,
    scopes: list[str] | tuple[str, ...],
    recipient_public_key_hex: str,
    ttl_seconds: int | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Issue a scoped JWT and encrypt it to the approved recipient public key."""

    subject = _normalize_subject(subject)
    normalized_scopes = _normalize_scopes(scopes)
    normalized_ttl = _normalize_ttl(settings, ttl_seconds)
    _validate_approved_subject(settings, subject)
    recipient_public_key = _decode_x25519_public_key(recipient_public_key_hex)
    recipient_public_key_hash = stable_hash(
        recipient_public_key_hex.lower(),
        prefix="proxy_recipient_public_key",
    )
    policy_binding = _validate_proxy_issue_policy(
        settings,
        subject=subject,
        scopes=normalized_scopes,
        recipient_public_key_hash=recipient_public_key_hash,
        ttl_seconds=normalized_ttl,
    )
    claims, token = issue_proxy_token(
        settings,
        subject=subject,
        scopes=normalized_scopes,
        ttl_seconds=normalized_ttl,
        now=now,
    )
    associated_data = _proxy_token_associated_data(claims)
    envelope = encrypt_for_tee(
        token.encode("utf-8"),
        recipient_public_key,
        info=PROXY_TOKEN_HKDF_INFO,
        associated_data=associated_data,
    )
    audit_record = build_proxy_token_store(settings).append(
        make_proxy_token_issue_record(
            subject_hash=claims.to_public_dict()["subject_hash"],
            jwt_id_hash=claims.to_public_dict()["jwt_id_hash"],
            recipient_public_key_hash=recipient_public_key_hash,
            scopes=list(claims.scopes),
            issued_at=claims.issued_at,
            expires_at=claims.expires_at,
        )
    )
    return {
        "surface": "tinker_proxy_token",
        "schema_version": 1,
        "success": True,
        "delivery": "x25519_aes_256_gcm_envelope",
        "encrypted_token": envelope.to_hex(),
        "associated_data": associated_data.hex(),
        "token": claims.to_public_dict(),
        "recipient_public_key_hash": recipient_public_key_hash,
        "policy_binding": policy_binding,
        "associated_data_hash": stable_hash(
            associated_data.hex(),
            prefix="proxy_token_aad",
        ),
        "audit_record": audit_record,
        "plaintext_token_returned": False,
        "raw_secret_egress": False,
    }


def issue_proxy_token(
    settings,
    *,
    subject: str,
    scopes: list[str] | tuple[str, ...],
    ttl_seconds: int | None = None,
    now: int | None = None,
) -> tuple[ProxyTokenClaims, str]:
    """Issue a scoped JWT signed by CVM-derived or explicit local key material."""

    subject = _normalize_subject(subject)
    normalized_scopes = _normalize_scopes(scopes)
    issued_at = int(time.time() if now is None else now)
    ttl = _normalize_ttl(settings, ttl_seconds)
    claims = ProxyTokenClaims(
        subject=subject,
        scopes=normalized_scopes,
        issued_at=issued_at,
        expires_at=issued_at + ttl,
        jwt_id=str(uuid.uuid4()),
        issuer=getattr(settings, "proxy_jwt_issuer", "") or "dnai-wikigen:tinker-proxy",
        audience=getattr(settings, "proxy_jwt_audience", "") or "dnai-wikigen:tinker-delegate",
    )
    token = _encode_jwt(claims.to_jwt_payload(), _proxy_signing_key(settings))
    return claims, token


def verify_proxy_token(
    settings,
    token: str,
    *,
    required_scope: str = "",
    now: int | None = None,
) -> dict[str, Any]:
    """Verify a scoped proxy JWT without returning the raw subject or token."""

    payload = _decode_jwt(token, _proxy_signing_key(settings))
    current = int(time.time() if now is None else now)
    issuer = getattr(settings, "proxy_jwt_issuer", "") or "dnai-wikigen:tinker-proxy"
    audience = getattr(settings, "proxy_jwt_audience", "") or "dnai-wikigen:tinker-delegate"
    if payload.get("iss") != issuer:
        raise ValueError("proxy token issuer mismatch")
    if payload.get("aud") != audience:
        raise ValueError("proxy token audience mismatch")
    if current < int(payload.get("nbf", 0)):
        raise ValueError("proxy token not yet valid")
    if current >= int(payload.get("exp", 0)):
        raise ValueError("proxy token expired")
    scopes = tuple(str(payload.get("scope", "")).split())
    if required_scope and required_scope not in scopes:
        raise ValueError("proxy token missing required scope")
    subject = str(payload.get("sub", ""))
    jwt_id = str(payload.get("jti", ""))
    jwt_id_hash = stable_hash(jwt_id, prefix="proxy_jti")
    if jwt_id_hash in build_proxy_token_store(settings).revoked_token_hashes():
        raise ValueError("proxy token revoked")
    return {
        "valid": True,
        "subject_hash": stable_hash(subject, prefix="proxy_subject"),
        "jwt_id_hash": jwt_id_hash,
        "scopes": list(scopes),
        "expires_at": int(payload["exp"]),
        "raw_secret_egress": False,
    }


def _encode_jwt(payload: dict[str, Any], key: bytes) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = b".".join(
        [
            _b64url_json(header),
            _b64url_json(payload),
        ]
    )
    signature = hmac.new(key, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(signature)).decode("ascii")


def _decode_jwt(token: str, key: bytes) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid proxy token format")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    supplied = _b64url_decode(parts[2])
    expected = hmac.new(key, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("invalid proxy token signature")
    header = json.loads(_b64url_decode(parts[0]))
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise ValueError("unsupported proxy token header")
    payload = json.loads(_b64url_decode(parts[1]))
    if not isinstance(payload, dict):
        raise ValueError("invalid proxy token payload")
    return payload


def _proxy_signing_key(settings) -> bytes:
    explicit = getattr(settings, "proxy_jwt_key", "")
    if explicit:
        return hashlib.sha256(bytes.fromhex(explicit)).digest()
    if is_dstack_enabled():
        return hashlib.sha256(
            b"tinker-proxy-jwt:" + derive_storage_key(getattr(settings, "proxy_jwt_key_path", "tinker/proxy_jwt"))
        ).digest()
    env_key = os.environ.get("TINKER_PROXY_JWT_KEY", "")
    if env_key:
        return hashlib.sha256(bytes.fromhex(env_key)).digest()
    raise ValueError("proxy JWT signing key unavailable outside dstack")


def _validate_approved_subject(settings, subject: str) -> None:
    approved = [
        item.strip()
        for item in str(getattr(settings, "proxy_approved_subjects", "") or "").split(",")
        if item.strip()
    ]
    if approved and subject.strip() not in approved:
        raise ValueError("proxy token subject is not approved")


def _validate_proxy_issue_policy(
    settings,
    *,
    subject: str,
    scopes: tuple[str, ...],
    recipient_public_key_hash: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    policy_path = str(getattr(settings, "proxy_issue_policy_path", "") or "").strip()
    require_policy = bool(getattr(settings, "proxy_require_issue_policy", False))
    if not policy_path:
        if require_policy:
            raise ValueError("proxy issue policy is required")
        return {
            "required": False,
            "configured": False,
            "raw_secret_egress": False,
        }

    policy = _load_proxy_issue_policy(policy_path)
    grants = policy.get("grants")
    if not isinstance(grants, list):
        raise ValueError("proxy issue policy grants must be a list")
    subject_hash = stable_hash(subject, prefix="proxy_subject")
    requested_scopes = set(scopes)
    policy_hash = stable_hash(_canonical_json(policy), prefix="proxy_issue_policy")
    ttl_cap_fail = False

    for grant in grants:
        if not isinstance(grant, dict):
            raise ValueError("proxy issue policy grant must be an object")
        grant_subject_hash = str(grant.get("subject_hash", "")).lower()
        grant_recipient_hash = str(grant.get("recipient_public_key_hash", "")).lower()
        grant_scopes = grant.get("scopes", [])
        if not isinstance(grant_scopes, list) or not all(isinstance(scope, str) for scope in grant_scopes):
            raise ValueError("proxy issue policy grant scopes must be strings")
        normalized_grant_scopes = set(_normalize_scopes(tuple(grant_scopes)))
        if grant_subject_hash != subject_hash or grant_recipient_hash != recipient_public_key_hash:
            continue
        if not requested_scopes.issubset(normalized_grant_scopes):
            continue
        max_ttl = int(grant.get("max_ttl_seconds", 0) or 0)
        if max_ttl <= 0:
            raise ValueError("proxy issue policy grant ttl cap is required")
        if ttl_seconds > max_ttl:
            ttl_cap_fail = True
            continue
        return {
            "required": True,
            "configured": True,
            "policy_hash": policy_hash,
            "grant_hash": stable_hash(_canonical_json(grant), prefix="proxy_issue_grant"),
            "subject_hash": subject_hash,
            "recipient_public_key_hash": recipient_public_key_hash,
            "requested_scopes": list(scopes),
            "granted_scopes": sorted(normalized_grant_scopes),
            "max_ttl_seconds": max_ttl,
            "ttl_seconds": ttl_seconds,
            "raw_secret_egress": False,
        }
    if ttl_cap_fail:
        raise ValueError("proxy token ttl exceeds policy cap")
    raise ValueError("proxy token issuance is not allowed by policy")


def _load_proxy_issue_policy(policy_path: str) -> dict[str, Any]:
    path = Path(policy_path)
    try:
        policy = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("proxy issue policy is unavailable") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("proxy issue policy is invalid JSON") from exc
    if not isinstance(policy, dict):
        raise ValueError("proxy issue policy must be an object")
    if policy.get("schema_version") != 1:
        raise ValueError("proxy issue policy schema_version must be 1")
    return policy


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _signing_key_source(settings) -> str:
    if getattr(settings, "proxy_jwt_key", ""):
        return "explicit_env_or_settings"
    if is_dstack_enabled():
        return "dstack_derived"
    if os.environ.get("TINKER_PROXY_JWT_KEY", ""):
        return "explicit_env_or_settings"
    return "unavailable"


def _normalize_subject(subject: str) -> str:
    normalized = subject.strip()
    if not normalized:
        raise ValueError("proxy token subject is required")
    if len(normalized) > 128:
        raise ValueError("proxy token subject is too long")
    return normalized


def _normalize_scopes(scopes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({scope.strip() for scope in scopes if scope.strip()}))
    if not normalized:
        raise ValueError("at least one proxy token scope is required")
    unsupported = [scope for scope in normalized if scope not in SUPPORTED_PROXY_SCOPES]
    if unsupported:
        raise ValueError("unsupported proxy token scope")
    return normalized


def _normalize_ttl(settings, ttl_seconds: int | None) -> int:
    default_ttl = int(getattr(settings, "proxy_jwt_default_ttl_seconds", 900) or 900)
    max_ttl = int(getattr(settings, "proxy_jwt_max_ttl_seconds", 3600) or 3600)
    ttl = int(ttl_seconds if ttl_seconds is not None else default_ttl)
    if ttl <= 0:
        raise ValueError("proxy token ttl must be positive")
    return min(ttl, max_ttl)


def _decode_x25519_public_key(value: str) -> bytes:
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("recipient public key must be hex") from exc
    if len(raw) != 32:
        raise ValueError("recipient public key must be 32 bytes")
    return raw


def _proxy_token_associated_data(claims: ProxyTokenClaims) -> bytes:
    return json.dumps(
        {
            "surface": "tinker_proxy_token",
            "subject_hash": stable_hash(claims.subject, prefix="proxy_subject"),
            "jwt_id_hash": stable_hash(claims.jwt_id, prefix="proxy_jti"),
            "scopes": list(claims.scopes),
            "expires_at": claims.expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _b64url_json(value: dict[str, Any]) -> bytes:
    return _b64url(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _b64url(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _next_required_configuration(*, api_key_configured: bool, project_id_configured: bool) -> list[str]:
    missing: list[str] = []
    if not api_key_configured:
        missing.append("seal_tinker_api_key_in_delegate")
    if not project_id_configured:
        missing.append("seal_tinker_project_id_in_delegate_if_provider_requires_it")
    return missing


def _base_url_host_family(base_url: str) -> str:
    if not base_url:
        return "sdk_default"
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return "invalid"
    if not host:
        return "invalid"
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "localhost"
    if (
        host.startswith("10.")
        or host.startswith("192.168.")
        or host.startswith("172.16.")
        or host.startswith("172.17.")
        or host.startswith("172.18.")
        or host.startswith("172.19.")
        or host.startswith("172.2")
        or host.startswith("172.30.")
        or host.startswith("172.31.")
    ):
        return "private_network"
    if host.endswith("thinkingmachines.ai"):
        return "thinkingmachines"
    return "external"
