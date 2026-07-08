import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tinker_delegate.billing_uploader import BillingCardUploadResult
from tinker_delegate.config import Settings
from tinker_delegate.funding_validation_packet import run_funding_validation_packet


def _receipt() -> dict:
    return {
        "surface": "payment_method",
        "outcome": "card_declined",
        "furthest_stage": "payment_submitted",
        "bounded_message": "Your card was declined.",
        "evidence_hash": "a" * 64,
        "account_hash": "",
        "amount_band": "",
        "balance_band": "",
        "tdx_quote_hash": "b" * 64,
        "card_payload_destroyed": True,
        "raw_secret_egress": False,
        "issued_at": 123,
    }


def _env(tmpdir: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TINKER_FUNDING_MODE": "operator_capped_validation",
            "TINKER_FUNDING_RECEIPT_STORE_PATH": str(Path(tmpdir) / "funding_receipts.enc"),
            "TINKER_FUNDING_RECEIPT_STORE_KEY": "88" * 32,
        }
    )
    return env


class FundingValidationPacketTest(unittest.TestCase):
    def test_runner_builds_and_verifies_packet_from_existing_bounded_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "existing-receipt.json"
            output_dir = Path(tmpdir) / "packet"
            receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")
            settings = Settings(
                funding_mode="operator_capped_validation",
                funding_receipt_store_path=str(Path(tmpdir) / "funding_receipts.enc"),
                funding_receipt_store_key="88" * 32,
            )

            result = run_funding_validation_packet(
                settings,
                output_dir=output_dir,
                api_url="http://localhost:8080",
                amount_dollars=5.0,
                expected_compose_hash="c" * 64,
                allow_local_attestation=True,
                validation_id="operator-run-1",
                receipt_json=receipt_path,
            ).to_public_dict()

            self.assertTrue(result["ok"])
            self.assertTrue(result["preflight_ready"])
            self.assertFalse(result["card_attempt_run"])
            self.assertEqual(result["receipt_outcome"], "card_declined")
            for name in (
                "preflight.json",
                "payment-method-receipt.json",
                "funding-manifest.json",
                "funding-verification.json",
                "funding-validation-summary.json",
            ):
                self.assertTrue((output_dir / name).exists(), name)
            summary = json.loads((output_dir / "funding-validation-summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertNotIn("4242424242424242", json.dumps(summary))

    def test_cli_packet_rejects_card_fields_without_explicit_run_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "funding-validation-packet",
                    "--output-dir",
                    str(Path(tmpdir) / "packet"),
                    "--api-url",
                    "http://localhost:8080",
                    "--amount",
                    "5",
                    "--allow-local-attestation",
                    "--number",
                    "4242424242424242",
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=_env(tmpdir),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("--run-card-attempt", result.stdout)
            self.assertNotIn("4242424242424242", result.stdout)
            self.assertNotIn("4242424242424242", result.stderr)

    def test_runner_card_attempt_uses_fake_uploader_and_zeroes_card_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "packet"
            card_data = {
                "card_number": "4242424242424242",
                "exp_month": "12",
                "exp_year": "2030",
                "cvc": "123",
                "cardholder_name": "Stripe Test User",
                "address_postal": "94105",
            }
            settings = Settings(
                funding_mode="operator_capped_validation",
                funding_receipt_store_path=str(Path(tmpdir) / "funding_receipts.enc"),
                funding_receipt_store_key="99" * 32,
            )

            def fake_upload(api_url, submitted_card, policy):
                self.assertEqual(api_url, "http://localhost:8080")
                self.assertEqual(submitted_card["card_number"], "4242424242424242")
                self.assertTrue(policy.allow_local)
                return BillingCardUploadResult(
                    status_code=200,
                    response={
                        "success": False,
                        "error": "Your card was declined.",
                        "attempt_record": _receipt(),
                    },
                )

            result = run_funding_validation_packet(
                settings,
                output_dir=output_dir,
                api_url="http://localhost:8080",
                amount_dollars=5.0,
                allow_local_attestation=True,
                validation_id="operator-run-1",
                run_card_attempt=True,
                card_data=card_data,
                upload_fn=fake_upload,
            ).to_public_dict()

            self.assertTrue(result["ok"])
            self.assertTrue(result["card_attempt_run"])
            self.assertTrue(all(value == "" for value in card_data.values()))
            rendered_packet = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.iterdir())
            self.assertNotIn("4242424242424242", rendered_packet)
            self.assertNotIn("Stripe Test User", rendered_packet)

    def test_cli_packet_writes_bounded_packet_from_existing_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "receipt.json"
            output_dir = Path(tmpdir) / "packet"
            receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "funding-validation-packet",
                    "--output-dir",
                    str(output_dir),
                    "--api-url",
                    "http://localhost:8080",
                    "--amount",
                    "5",
                    "--compose-hash",
                    "c" * 64,
                    "--allow-local-attestation",
                    "--validation-id",
                    "operator-run-1",
                    "--receipt-json",
                    str(receipt_path),
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=_env(tmpdir),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            body = json.loads(result.stdout)
            self.assertTrue(body["ok"])
            self.assertEqual(body["receipt_outcome"], "card_declined")
            verification = json.loads((output_dir / "funding-verification.json").read_text(encoding="utf-8"))
            self.assertTrue(verification["ok"])


if __name__ == "__main__":
    unittest.main()
