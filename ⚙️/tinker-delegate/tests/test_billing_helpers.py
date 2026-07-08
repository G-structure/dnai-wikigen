import unittest

from tinker_delegate.billing import CardDetails, _billing_error_message, _format_expiry


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


if __name__ == "__main__":
    unittest.main()
