import unittest

from fastapi.testclient import TestClient

from email_oracle.api import app, state
from email_oracle.config import Settings


def _reset_state(settings: Settings) -> None:
    state.settings = settings
    state.store = None
    state.creds = None
    state.imap = None


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
            json={},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Oracle not initialized", response.json()["detail"])

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

        response = self.client.post("/pin", json={})

        self.assertEqual(response.status_code, 503)
        self.assertIn("Oracle not initialized", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
