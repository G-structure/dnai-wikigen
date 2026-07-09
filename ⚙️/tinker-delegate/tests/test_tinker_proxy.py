import os
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tinker_delegate.config import Settings
from tinker_delegate.crypto import _derive_aes_key
from tinker_delegate.tinker_proxy import (
    PROXY_TOKEN_HKDF_INFO,
    build_tinker_proxy_status,
    issue_encrypted_proxy_token,
    verify_proxy_token,
)
from tinker_delegate.tinker_proxy_store import build_proxy_token_store


UPSTREAM_KEY = "tml-secretsecretsecretsecretsecret"
PROJECT_ID = "proj-sensitive"
BASE_URL = "https://api.thinkingmachines.ai"
SIGNING_KEY_HEX = "11" * 32
STORE_KEY_HEX = "66" * 32


def _recipient_keypair():
    private_key = X25519PrivateKey.generate()
    public_key_hex = private_key.public_key().public_bytes_raw().hex()
    return private_key, public_key_hex


def _decrypt_token(private_key, payload: dict) -> str:
    encrypted = payload["encrypted_token"]
    sender_public = X25519PublicKey.from_public_bytes(bytes.fromhex(encrypted["ephemeral_public_key"]))
    shared_secret = private_key.exchange(sender_public)
    aes_key = _derive_aes_key(shared_secret, info=PROXY_TOKEN_HKDF_INFO)
    return AESGCM(aes_key).decrypt(
        bytes.fromhex(encrypted["nonce"]),
        bytes.fromhex(encrypted["ciphertext"]),
        bytes.fromhex(payload["associated_data"]),
    ).decode("utf-8")


class TinkerProxyTest(unittest.TestCase):
    def _settings(self, tmpdir: str, **overrides) -> Settings:
        values = {
            "proxy_jwt_key": SIGNING_KEY_HEX,
            "proxy_token_store_path": os.path.join(tmpdir, "proxy_tokens.enc"),
            "proxy_token_store_key": STORE_KEY_HEX,
        }
        values.update(overrides)
        return Settings(**values)

    def test_status_is_bounded_and_does_not_return_upstream_config(self):
        settings = Settings(
            project_id=PROJECT_ID,
            base_url=BASE_URL,
            proxy_jwt_key=SIGNING_KEY_HEX,
        )

        with patch.dict(os.environ, {"TINKER_API_KEY": UPSTREAM_KEY}, clear=False):
            status = build_tinker_proxy_status(settings)

        rendered = repr(status)
        self.assertTrue(status["success"])
        self.assertEqual(status["sealed_client_config"]["api_key_configured"], True)
        self.assertEqual(status["sealed_client_config"]["project_id_configured"], True)
        self.assertEqual(status["sealed_client_config"]["base_url_host_family"], "thinkingmachines")
        self.assertFalse(status["raw_secret_egress"])
        self.assertNotIn(UPSTREAM_KEY, rendered)
        self.assertNotIn(PROJECT_ID, rendered)
        self.assertNotIn(BASE_URL, rendered)

    def test_issue_encrypted_proxy_token_and_verify_decrypted_jwt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            private_key, public_key_hex = _recipient_keypair()
            settings = self._settings(
                tmpdir,
                proxy_approved_subjects="buyer-agent-1",
                proxy_jwt_default_ttl_seconds=60,
                proxy_jwt_max_ttl_seconds=120,
            )

            issued = issue_encrypted_proxy_token(
                settings,
                subject="buyer-agent-1",
                scopes=["proxy:status", "tinker:smoke"],
                recipient_public_key_hex=public_key_hex,
                ttl_seconds=90,
                now=1000,
            )
            token = _decrypt_token(private_key, issued)
            verification = verify_proxy_token(settings, token, required_scope="proxy:status", now=1010)
            records = build_proxy_token_store(settings).load()

        rendered = repr(issued)
        self.assertTrue(issued["success"])
        self.assertEqual(issued["token"]["ttl_seconds"], 90)
        self.assertEqual(verification["scopes"], ["proxy:status", "tinker:smoke"])
        self.assertEqual(records[0]["event"], "issued")
        self.assertEqual(records[0]["jwt_id_hash"], issued["token"]["jwt_id_hash"])
        self.assertEqual(issued["audit_record"], records[0])
        self.assertFalse(issued["plaintext_token_returned"])
        self.assertFalse(issued["raw_secret_egress"])
        self.assertNotIn(token, rendered)
        self.assertNotIn("buyer-agent-1", rendered)

    def test_issuer_rejects_unapproved_subject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _, public_key_hex = _recipient_keypair()
            settings = self._settings(tmpdir, proxy_approved_subjects="approved-agent")

            with self.assertRaises(ValueError):
                issue_encrypted_proxy_token(
                    settings,
                    subject="other-agent",
                    scopes=["proxy:status"],
                    recipient_public_key_hex=public_key_hex,
                )

    def test_verifier_rejects_missing_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            private_key, public_key_hex = _recipient_keypair()
            settings = self._settings(tmpdir)
            issued = issue_encrypted_proxy_token(
                settings,
                subject="buyer-agent-1",
                scopes=["proxy:status"],
                recipient_public_key_hex=public_key_hex,
                ttl_seconds=60,
                now=1000,
            )
            token = _decrypt_token(private_key, issued)

            with self.assertRaises(ValueError):
                verify_proxy_token(settings, token, required_scope="billing:add-balance", now=1001)

    def test_verifier_rejects_revoked_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            private_key, public_key_hex = _recipient_keypair()
            settings = self._settings(tmpdir)
            issued = issue_encrypted_proxy_token(
                settings,
                subject="buyer-agent-1",
                scopes=["proxy:status"],
                recipient_public_key_hex=public_key_hex,
                ttl_seconds=60,
                now=1000,
            )
            token = _decrypt_token(private_key, issued)
            store = build_proxy_token_store(settings)
            store.revoke(issued["token"]["jwt_id_hash"], reason="operator_requested", revoked_at=1001)

            with self.assertRaises(ValueError):
                verify_proxy_token(settings, token, required_scope="proxy:status", now=1002)


if __name__ == "__main__":
    unittest.main()
