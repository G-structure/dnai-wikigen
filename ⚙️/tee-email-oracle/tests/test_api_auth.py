import unittest

from fastapi.testclient import TestClient

from email_oracle.api import app, state
from email_oracle.config import Settings
from email_oracle.cred_store import EmailCredentials
from email_oracle.imap_client import ExtractedPin


def _reset_state(settings: Settings) -> None:
    state.settings = settings
    state.store = None
    state.creds = None
    state.imap = None
    state.used_otp_hashes = set()


def _scoped_pin_payload(**overrides):
    payload = {
        "target_service": "tinker",
        "expected_sender": "no-reply@thinkingmachines.ai",
        "expected_subject_contains": "",
        "max_age_seconds": 300,
        "extract_pattern": r"\b\d{6}\b",
        "nonce": "nonce-123456",
        "caller_identity": "tinker-delegate.test",
        "reason": "tinker-auth-test",
        "delete_after": False,
    }
    payload.update(overrides)
    return payload


class FakeIMAP:
    def __init__(self, pin: str = "123456"):
        self.pin = pin
        self.search_calls = []
        self.deleted = []

    def search_and_extract(self, **kwargs):
        self.search_calls.append(kwargs)
        return ExtractedPin(
            pin=self.pin,
            email_id="42",
            subject="Your Thinking Machines code",
            sender="Thinking Machines Lab <no-reply@thinkingmachines.ai>",
            received_at="Wed, 08 Jul 2026 12:00:00 +0000",
            body_snippet="redacted",
        )

    def delete_email(self, email_id: str) -> None:
        self.deleted.append(email_id)


class ApiAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_pin_requires_bearer_token_when_runtime_auth_is_enabled(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.post("/pin", json={})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_pin_rejects_wrong_bearer_token(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer wrong-secret"},
            json={},
        )

        self.assertEqual(response.status_code, 403)

    def test_pin_accepts_correct_bearer_token_before_oracle_state_check(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer shared-secret"},
            json=_scoped_pin_payload(),
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Oracle not initialized", response.json()["detail"])

    def test_pin_requires_scoped_request_metadata(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer shared-secret"},
            json={},
        )

        self.assertEqual(response.status_code, 422)

    def test_pin_releases_scoped_otp_once(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))
        state.creds = EmailCredentials("oracle", "example.com", "pw")
        state.imap = FakeIMAP()

        response = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer shared-secret"},
            json=_scoped_pin_payload(delete_after=True),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pin"], "123456")
        self.assertEqual(body["oracle_email"], "oracle@example.com")
        self.assertEqual(len(body["request_hash"]), 64)
        self.assertEqual(len(body["otp_use_hash"]), 64)
        self.assertEqual(state.imap.search_calls[0]["from_filter"], "no-reply@thinkingmachines.ai")
        self.assertEqual(state.imap.deleted, ["42"])

        replay = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer shared-secret"},
            json=_scoped_pin_payload(nonce="nonce-abcdef"),
        )
        self.assertEqual(replay.status_code, 409)
        self.assertIn("already been released", replay.json()["detail"])

    def test_pin_rejects_overlong_extraction(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret", pin_max_length=6))
        state.creds = EmailCredentials("oracle", "example.com", "pw")
        state.imap = FakeIMAP(pin="123456789")

        response = self.client.post(
            "/pin",
            headers={"Authorization": "Bearer shared-secret"},
            json=_scoped_pin_payload(extract_pattern=r"\d+"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("length cap", response.json()["detail"])

    def test_inbox_requires_bearer_token_when_runtime_auth_is_enabled(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.get("/inbox")

        self.assertEqual(response.status_code, 401)

    def test_inbox_accepts_correct_bearer_token_before_imap_check(self):
        _reset_state(Settings(runtime_auth_required=True, runtime_auth_token="shared-secret"))

        response = self.client.get("/inbox", headers={"Authorization": "Bearer shared-secret"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("IMAP not connected", response.json()["detail"])

    def test_local_dev_can_leave_runtime_auth_disabled(self):
        _reset_state(Settings(runtime_auth_required=False, runtime_auth_token=""))

        response = self.client.post("/pin", json=_scoped_pin_payload())

        self.assertEqual(response.status_code, 503)
        self.assertIn("Oracle not initialized", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
