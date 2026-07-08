import unittest
from unittest.mock import AsyncMock, patch

from tinker_delegate.card_channel import CardPayload, handle_card_update
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
