import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from tinker_delegate.automation_receipts import AutomationStage
from tinker_delegate.billing import (
    CardDetails,
    add_payment_method,
    _debug_screenshot,
    _add_balance_result,
    _billing_error_message,
    _format_expiry,
    _payment_method_result,
)
from tinker_delegate.config import Settings


class FakeScreenshotPage:
    def __init__(self):
        self.paths = []

    async def screenshot(self, *, path: str):
        self.paths.append(path)


class BillingHelpersTest(unittest.TestCase):
    def test_format_expiry_accepts_four_digit_year(self):
        card = CardDetails("4242424242424242", "12", "2030", "123", "Test User")

        self.assertEqual(_format_expiry(card), "1230")

    def test_format_expiry_accepts_two_digit_year(self):
        card = CardDetails("4242424242424242", "9", "30", "123", "Test User")

        self.assertEqual(_format_expiry(card), "0930")

    def test_billing_error_message_extracts_card_error(self):
        text = "Add payment method Your card number is invalid. Cancel"

        self.assertEqual(_billing_error_message(text), "Your card number is invalid.")

    def test_payment_method_result_returns_bounded_decline_receipt(self):
        result = _payment_method_result(
            False,
            "Your card was declined.",
            AutomationStage.PAYMENT_SUBMITTED,
            "page text",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["attempt_record"]["surface"], "payment_method")
        self.assertEqual(result["attempt_record"]["outcome"], "card_declined")
        self.assertEqual(result["attempt_record"]["furthest_stage"], "payment_submitted")
        self.assertTrue(result["attempt_record"]["card_payload_destroyed"])

    def test_add_balance_result_bands_amount_without_card_data(self):
        result = _add_balance_result(
            False,
            "Payment method required before adding balance",
            3.0,
            AutomationStage.ADD_BALANCE_MODAL_OPENED,
            "page text",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["attempt_record"]["surface"], "add_balance")
        self.assertEqual(result["attempt_record"]["outcome"], "payment_method_required")
        self.assertEqual(result["attempt_record"]["amount_band"], "lt_5_usd")

    def test_debug_screenshot_writes_non_secret_artifact_when_enabled(self):
        page = FakeScreenshotPage()

        wrote = asyncio.run(
            _debug_screenshot(
                page,
                Settings(debug_screenshots=True),
                "screenshot_no_stripe.png",
            )
        )

        self.assertTrue(wrote)
        self.assertEqual(page.paths, ["screenshot_no_stripe.png"])

    def test_debug_screenshot_suppresses_secret_bearing_artifact_even_when_enabled(self):
        page = FakeScreenshotPage()

        wrote = asyncio.run(
            _debug_screenshot(
                page,
                Settings(debug_screenshots=True),
                "screenshot_billing_filled.png",
                contains_secrets=True,
            )
        )

        self.assertFalse(wrote)
        self.assertEqual(page.paths, [])

    def test_debug_screenshot_disabled_by_default(self):
        page = FakeScreenshotPage()

        wrote = asyncio.run(
            _debug_screenshot(
                page,
                Settings(debug_screenshots=False),
                "screenshot_add_balance.png",
            )
        )

        self.assertFalse(wrote)
        self.assertEqual(page.paths, [])

    def test_add_payment_method_purges_configured_secret_debug_artifacts(self):
        card = CardDetails("4242424242424242", "12", "2030", "123", "Test User")
        settings = Settings(debug_artifact_dir="/tmp/tinker-debug-artifacts")

        with (
            patch(
                "tinker_delegate.billing._do_add_payment_method",
                new=AsyncMock(return_value={"success": False, "error": "stubbed"}),
            ),
            patch("tinker_delegate.billing.purge_secret_debug_artifacts", return_value=2) as purge,
        ):
            result = asyncio.run(add_payment_method(card, settings))

        self.assertEqual(result["error"], "stubbed")
        purge.assert_called_once_with("/tmp/tinker-debug-artifacts")
        self.assertEqual(card.number, "")
        self.assertEqual(card.cvc, "")


if __name__ == "__main__":
    unittest.main()
