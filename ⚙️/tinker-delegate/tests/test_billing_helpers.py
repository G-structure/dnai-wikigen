import unittest

from tinker_delegate.automation_receipts import AutomationStage
from tinker_delegate.billing import (
    CardDetails,
    _add_balance_result,
    _billing_error_message,
    _format_expiry,
    _payment_method_result,
)


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


if __name__ == "__main__":
    unittest.main()
