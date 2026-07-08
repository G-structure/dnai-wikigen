import unittest
from unittest.mock import AsyncMock, patch

from tinker_delegate.card_channel import (
    CardPayload,
    attestation_report_data,
    get_attestation,
    get_tee_keypair,
    handle_card_update,
)
from tinker_delegate.config import Settings


def _payload() -> CardPayload:
    return CardPayload(
        card_number="4242424242424242",
        exp_month="12",
        exp_year="2030",
        cvc="123",
        cardholder_name="Test User",
        address_line1="123 Main St",
        address_city="SF",
        address_state="CA",
        address_postal="94105",
    )


class CardChannelTest(unittest.IsolatedAsyncioTestCase):
    def test_attestation_report_data_binds_context_and_public_key(self):
        keypair = get_tee_keypair()
        billing = attestation_report_data("billing", keypair.public_key_bytes)
        artifact = attestation_report_data("artifact", keypair.public_key_bytes)
        other_key = bytes([keypair.public_key_bytes[0] ^ 1]) + keypair.public_key_bytes[1:]

        self.assertEqual(len(billing), 32)
        self.assertNotEqual(billing, artifact)
        self.assertNotEqual(billing, attestation_report_data("billing", other_key))

        attestation = get_attestation("artifact")
        self.assertEqual(attestation["report_context"], "artifact")
        self.assertEqual(
            attestation["report_data"],
            attestation_report_data("artifact", keypair.public_key_bytes).hex(),
        )
        self.assertEqual(attestation["encryption_public_key"], keypair.public_key_bytes.hex())

    async def test_plaintext_payload_is_wiped_after_success(self):
        payload = _payload()

        with (
            patch(
                "tinker_delegate.card_channel.add_payment_method",
                new=AsyncMock(return_value={"success": False, "error": "stubbed"}),
            ),
            patch("tinker_delegate.card_channel.get_attestation", return_value={}),
        ):
            result = await handle_card_update(payload, Settings())

        self.assertFalse(result.success)
        self.assertEqual(result.error, "stubbed")
        self.assertEqual(payload.card_number, "")
        self.assertEqual(payload.exp_month, "")
        self.assertEqual(payload.exp_year, "")
        self.assertEqual(payload.cvc, "")
        self.assertEqual(payload.cardholder_name, "")
        self.assertEqual(payload.address_line1, "")

    async def test_plaintext_payload_is_wiped_after_exception(self):
        payload = _payload()

        with patch(
            "tinker_delegate.card_channel.add_payment_method",
            new=AsyncMock(side_effect=RuntimeError("browser failed")),
        ):
            result = await handle_card_update(payload, Settings())

        self.assertFalse(result.success)
        self.assertEqual(result.error, "browser failed")
        self.assertEqual(payload.card_number, "")
        self.assertEqual(payload.exp_month, "")
        self.assertEqual(payload.exp_year, "")
        self.assertEqual(payload.cvc, "")
        self.assertEqual(payload.cardholder_name, "")
        self.assertEqual(payload.address_line1, "")


if __name__ == "__main__":
    unittest.main()
