import types
import unittest

from tinker_delegate.main import (
    _prompt_billing_card_payload,
    _validate_prompt_billing_policy,
)


class PromptBillingCliTest(unittest.TestCase):
    def test_prompt_card_payload_reads_fields_without_argv(self):
        prompts = []
        values = iter([
            "4242424242424242",
            "07",
            "2031",
            "123",
            "Test User",
            "",
            "",
            "",
            "94105",
            "",
        ])

        def fake_prompt(label: str) -> str:
            prompts.append(label)
            return next(values)

        payload = _prompt_billing_card_payload(prompt_fn=fake_prompt)

        self.assertEqual(payload["card_number"], "4242424242424242")
        self.assertEqual(payload["exp_month"], "07")
        self.assertEqual(payload["exp_year"], "2031")
        self.assertEqual(payload["cvc"], "123")
        self.assertEqual(payload["cardholder_name"], "Test User")
        self.assertEqual(payload["address_postal"], "94105")
        self.assertEqual(payload["address_country"], "US")
        self.assertEqual(len(prompts), 10)

    def test_prompt_policy_requires_deployed_attestation_expectations(self):
        args = types.SimpleNamespace(
            command="add-card-encrypted-prompt",
            allow_local_attestation=False,
            compose_hash="compose-ok",
            app_id="",
            os_image_hash="os-ok",
        )

        with self.assertRaisesRegex(ValueError, "--app-id"):
            _validate_prompt_billing_policy(args)

    def test_prompt_policy_allows_local_only_when_explicit(self):
        args = types.SimpleNamespace(
            command="add-card-encrypted-prompt",
            allow_local_attestation=True,
            compose_hash="",
            app_id="",
            os_image_hash="",
        )

        _validate_prompt_billing_policy(args)


if __name__ == "__main__":
    unittest.main()
