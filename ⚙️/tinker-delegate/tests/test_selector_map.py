import unittest

from tinker_delegate.main import _render_bounded_json
from tinker_delegate.redaction import redact_text
from tinker_delegate.selector_map import build_selector_map, selector_map_hash


class SelectorMapTest(unittest.TestCase):
    def test_selector_map_covers_required_tinker_and_billing_flows(self):
        selector_map = build_selector_map()
        flow_names = {flow["name"] for flow in selector_map["flows"]}

        self.assertEqual(selector_map["surface"], "tinker_console_and_stripe_billing")
        self.assertFalse(selector_map["raw_secret_egress"])
        self.assertEqual(selector_map["deployed_cvm_selector_evidence"], "pending_deployed_cvm_capture")
        self.assertTrue(
            {
                "email_auth",
                "magic_code_otp",
                "onboarding",
                "api_keys",
                "billing_payment_method",
                "stripe_card_iframe",
                "balance_top_up",
                "auto_reload",
            }.issubset(flow_names)
        )

    def test_selector_map_contains_no_secret_shaped_material(self):
        selector_map = build_selector_map()
        rendered = _render_bounded_json(selector_map)

        self.assertEqual(redact_text(rendered), rendered)
        self.assertNotIn("tml-", rendered)
        self.assertNotIn("one-time-code value", rendered)
        self.assertNotIn("card number", rendered.lower())

    def test_summary_mode_preserves_counts_without_selectors(self):
        selector_map = build_selector_map(include_selectors=False)

        for flow in selector_map["flows"]:
            for family in flow["families"]:
                self.assertIn("selector_count", family)
                self.assertNotIn("selectors", family)

    def test_selector_map_hash_is_recomputable(self):
        selector_map = build_selector_map()

        self.assertRegex(selector_map["selector_map_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(selector_map["selector_map_hash"], selector_map_hash(selector_map))


if __name__ == "__main__":
    unittest.main()
