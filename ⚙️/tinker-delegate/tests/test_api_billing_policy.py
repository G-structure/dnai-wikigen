import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tinker_delegate import api
from tinker_delegate.automation_receipts import (
    AutomationOutcome,
    AutomationStage,
    AutomationSurface,
    make_receipt,
)
from tinker_delegate.billing_uploader import encrypt_billing_card_payload
from tinker_delegate.card_channel import attestation_report_data, get_tee_keypair
from tinker_delegate.config import Settings
from tinker_delegate.funding_receipt_store import FundingReceiptStore


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

    def test_attestation_endpoint_binds_requested_billing_context(self):
        client = TestClient(api.app)

        response = client.get("/attestation", params={"context": "billing"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        keypair = get_tee_keypair()
        self.assertEqual(body["report_context"], "billing")
        self.assertEqual(
            body["report_data"],
            attestation_report_data("billing", keypair.public_key_bytes).hex(),
        )

    def test_attestation_endpoint_rejects_unknown_context(self):
        client = TestClient(api.app)

        response = client.get("/attestation", params={"context": "raw-card-dump"})

        self.assertEqual(response.status_code, 400)

    def test_encrypted_card_endpoint_decrypts_and_persists_bounded_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "funding_receipts.enc"
            key = "aa" * 32
            api.settings = Settings(
                funding_receipt_store_path=str(receipt_path),
                funding_receipt_store_key=key,
            )
            client = TestClient(api.app)
            attestation = client.get("/attestation", params={"context": "billing"}).json()
            encrypted = encrypt_billing_card_payload(
                CARD_PAYLOAD,
                attestation["encryption_public_key"],
            )

            with patch(
                "tinker_delegate.card_channel.add_payment_method",
                new=AsyncMock(return_value={"success": False, "error": "Your card was declined."}),
            ):
                response = client.post("/billing/card/encrypted", json=encrypted)

            stored = FundingReceiptStore(str(receipt_path), key_hex=key).load()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["attempt_record"]["outcome"], "card_declined")
        self.assertEqual(stored, [body["attempt_record"]])
        self.assertNotIn("4242424242424242", repr(body))

    def test_funding_receipts_endpoint_returns_bounded_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "funding_receipts.enc"
            key = "88" * 32
            api.settings = Settings(
                funding_receipt_store_path=str(receipt_path),
                funding_receipt_store_key=key,
            )
            receipt = make_receipt(
                surface=AutomationSurface.PAYMENT_METHOD,
                outcome=AutomationOutcome.CARD_DECLINED,
                furthest_stage=AutomationStage.PAYMENT_SUBMITTED,
                evidence="card_number=4242424242424242",
                bounded_message="Your card was declined.",
                card_payload_destroyed=True,
            ).to_public_dict()
            FundingReceiptStore(str(receipt_path), key_hex=key).append(receipt)
            client = TestClient(api.app)

            response = client.get("/billing/funding-receipts")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["receipts"][0]["outcome"], "card_declined")
        self.assertNotIn("4242424242424242", repr(body))


if __name__ == "__main__":
    unittest.main()
