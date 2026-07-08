import asyncio
import unittest

from tinker_delegate.main import _render_bounded_json
from tinker_delegate.redaction import redact_text
from tinker_delegate.selector_map import build_selector_map, probe_selector_map_context, selector_map_hash


class FakeLocator:
    def __init__(self, count: int):
        self._count = count

    async def count(self):
        return self._count


class FakeScope:
    def __init__(self, *, url: str = "", name: str = "", counts: dict[str, int] | None = None):
        self.url = url
        self.name = name
        self._counts = counts or {}

    def locator(self, selector: str):
        return FakeLocator(self._counts.get(selector, 0))


class FakePage(FakeScope):
    def __init__(self, *, url: str, counts: dict[str, int], frames: list[FakeScope] | None = None):
        super().__init__(url=url, counts=counts)
        self.frames = frames or []


class FakeContext:
    def __init__(self, pages: list[FakePage]):
        self.pages = pages


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

    def test_probe_reports_count_bands_without_raw_urls(self):
        async def run_probe():
            return await probe_selector_map_context(FakeContext([page]), issued_at=123)

        page = FakePage(
            url="https://tinker-console.thinkingmachines.ai/keys?session=secret",
            counts={
                '[data-testid="create-api-key"]': 1,
                'button:has-text("Generate key")': 1,
                'button:has-text("Done")': 3,
            },
            frames=[
                FakeScope(
                    url="https://js.stripe.com/elements-inner-card.html#private",
                    name="__privateStripeFrame123",
                    counts={
                        'input[name="cardnumber"]': 1,
                        'input[data-elements-stable-field-name="cardExpiry"]': 1,
                        'input[name="cvc"]': 1,
                    },
                )
            ],
        )

        result = asyncio.run(run_probe())
        rendered = _render_bounded_json(result)

        self.assertNotIn("session=secret", rendered)
        self.assertNotIn("elements-inner-card.html#private", rendered)
        self.assertEqual(redact_text(rendered), rendered)
        self.assertTrue(result["success"])
        self.assertEqual(result["page_count_band"], "1")
        self.assertEqual(result["pages"][0]["url_class"], "tinker_console_keys")
        self.assertEqual(result["pages"][0]["frame_observations"][0]["kind"], "stripe_card")
        api_flow = next(
            flow for flow in result["pages"][0]["flow_observations"] if flow["name"] == "api_keys"
        )
        create_family = next(
            family for family in api_flow["family_observations"] if family["name"] == "create_key"
        )
        close_family = next(
            family for family in api_flow["family_observations"] if family["name"] == "close_key_dialog"
        )
        self.assertEqual(create_family["match_band"], "1")
        self.assertEqual(close_family["match_band"], "2+")


if __name__ == "__main__":
    unittest.main()
