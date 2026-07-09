import unittest

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from tinker_delegate import api
from tinker_delegate.config import Settings
from tinker_delegate.tinker_proxy import issue_proxy_token


SIGNING_KEY_HEX = "22" * 32


class TinkerProxyApiTest(unittest.TestCase):
    def setUp(self):
        self.original_settings = api.settings

    def tearDown(self):
        api.settings = self.original_settings

    def test_proxy_status_disabled_by_default(self):
        api.settings = Settings(allow_tinker_proxy_endpoint=False)
        client = TestClient(api.app)

        response = client.get("/tinker/proxy/status")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Tinker proxy endpoint is disabled", response.json()["detail"])

    def test_proxy_token_issuance_disabled_by_default(self):
        api.settings = Settings(runtime_auth_required=True, runtime_auth_token="operator-secret")
        client = TestClient(api.app)
        recipient_public_key = X25519PrivateKey.generate().public_key().public_bytes_raw().hex()

        response = client.post(
            "/tinker/proxy/token",
            headers={"Authorization": "Bearer operator-secret"},
            json={
                "subject": "buyer-agent-1",
                "scopes": ["proxy:status"],
                "recipient_public_key": recipient_public_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Tinker proxy token issuance is disabled", response.json()["detail"])

    def test_proxy_token_issuance_requires_configured_runtime_auth(self):
        api.settings = Settings(allow_tinker_proxy_token_issuance=True, proxy_jwt_key=SIGNING_KEY_HEX)
        client = TestClient(api.app)
        recipient_public_key = X25519PrivateKey.generate().public_key().public_bytes_raw().hex()

        response = client.post(
            "/tinker/proxy/token",
            json={
                "subject": "buyer-agent-1",
                "scopes": ["proxy:status"],
                "recipient_public_key": recipient_public_key,
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Runtime bearer auth must be configured", response.json()["detail"])

    def test_proxy_token_issuance_returns_encrypted_bounded_envelope(self):
        api.settings = Settings(
            allow_tinker_proxy_token_issuance=True,
            runtime_auth_required=True,
            runtime_auth_token="operator-secret",
            proxy_jwt_key=SIGNING_KEY_HEX,
            proxy_approved_subjects="buyer-agent-1",
        )
        client = TestClient(api.app)
        recipient_public_key = X25519PrivateKey.generate().public_key().public_bytes_raw().hex()

        response = client.post(
            "/tinker/proxy/token",
            headers={"Authorization": "Bearer operator-secret"},
            json={
                "subject": "buyer-agent-1",
                "scopes": ["proxy:status"],
                "recipient_public_key": recipient_public_key,
                "ttl_seconds": 30,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        rendered = repr(body)
        self.assertTrue(body["success"])
        self.assertEqual(body["delivery"], "x25519_aes_256_gcm_envelope")
        self.assertIn("encrypted_token", body)
        self.assertIn("associated_data", body)
        self.assertFalse(body["plaintext_token_returned"])
        self.assertFalse(body["raw_secret_egress"])
        self.assertNotIn("operator-secret", rendered)
        self.assertNotIn("buyer-agent-1", rendered)

    def test_proxy_status_accepts_scoped_proxy_jwt(self):
        api.settings = Settings(
            allow_tinker_proxy_endpoint=True,
            proxy_jwt_key=SIGNING_KEY_HEX,
        )
        claims, token = issue_proxy_token(
            api.settings,
            subject="buyer-agent-1",
            scopes=["proxy:status"],
            ttl_seconds=60,
        )
        del claims
        client = TestClient(api.app)

        response = client.get(
            "/tinker/proxy/status",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["surface"], "tinker_proxy")
        self.assertFalse(body["raw_secret_egress"])


if __name__ == "__main__":
    unittest.main()
