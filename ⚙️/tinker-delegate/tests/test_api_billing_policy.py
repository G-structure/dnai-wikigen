import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tinker_delegate import api
from tinker_delegate.config import Settings


CARD_PAYLOAD = {
    "card_number": "4242424242424242",
    "exp_month": "12",
    "exp_year": "2030",
    "cvc": "123",
    "cardholder_name": "Test User",
}


class BillingApiPolicyTest(unittest.TestCase):
    def setUp(self):
        self.original_settings = api.settings

    def tearDown(self):
        api.settings = self.original_settings

    def test_plaintext_card_endpoint_disabled_by_default(self):
        api.settings = Settings(allow_plaintext_card_endpoint=False)
        client = TestClient(api.app)

        response = client.post("/billing/card", json=CARD_PAYLOAD)

        self.assertEqual(response.status_code, 403)
        self.assertIn("Plaintext card endpoint is disabled", response.json()["detail"])

    def test_plaintext_card_endpoint_requires_non_dstack_local_flag(self):
        api.settings = Settings(allow_plaintext_card_endpoint=True)
        client = TestClient(api.app)

        with (
            patch("tinker_delegate.api.is_dstack_enabled", return_value=True),
            patch("tinker_delegate.api.handle_card_update", new=AsyncMock()) as handle_card_update,
        ):
            response = client.post("/billing/card", json=CARD_PAYLOAD)

        self.assertEqual(response.status_code, 403)
        handle_card_update.assert_not_called()

    def test_plaintext_card_endpoint_can_be_enabled_for_local_dev(self):
        api.settings = Settings(allow_plaintext_card_endpoint=True)
        client = TestClient(api.app)

        with (
            patch("tinker_delegate.api.is_dstack_enabled", return_value=False),
            patch(
                "tinker_delegate.api.handle_card_update",
                new=AsyncMock(return_value={"success": False, "error": "stubbed"}),
            ) as handle_card_update,
        ):
            response = client.post("/billing/card", json=CARD_PAYLOAD)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "stubbed")
        handle_card_update.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
