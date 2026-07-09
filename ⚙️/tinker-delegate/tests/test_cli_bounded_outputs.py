import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tinker_delegate.main import _render_bounded_json


def _env(tmpdir: str, *, funding_mode: str = "manual_prefund") -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TINKER_FUNDING_MODE": funding_mode,
            "TINKER_FUNDING_RECEIPT_STORE_PATH": str(Path(tmpdir) / "funding_receipts.enc"),
            "TINKER_FUNDING_RECEIPT_STORE_KEY": "77" * 32,
        }
    )
    return env


class CliBoundedOutputsTest(unittest.TestCase):
    def test_preflight_can_write_bounded_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "preflight.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "funding-preflight",
                    "--amount",
                    "10",
                    "--api-url",
                    "http://localhost:8080",
                    "--allow-local-attestation",
                    "--output",
                    str(output_path),
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=_env(tmpdir, funding_mode="operator_capped_validation"),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            body = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(body["ready"])
            self.assertEqual(body["policy"]["mode"], "operator_capped_validation")

    def test_add_balance_can_write_policy_denied_receipt_file_without_card_material(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "add-balance-receipt.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "add-balance",
                    "5",
                    "--receipt-output",
                    str(receipt_path),
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=_env(tmpdir),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            rendered = json.dumps(receipt)
            self.assertEqual(receipt["surface"], "add_balance")
            self.assertEqual(receipt["outcome"], "policy_denied")
            self.assertFalse(receipt["raw_secret_egress"])
            self.assertNotIn("4242424242424242", rendered)
            self.assertNotIn("card_number", rendered)

    def test_bounded_renderer_rejects_secret_like_or_echoed_card_output(self):
        with self.assertRaisesRegex(ValueError, "secret-like material"):
            _render_bounded_json({"response": {"card_number": "4242424242424242"}})

        with self.assertRaisesRegex(ValueError, "submitted secret material"):
            _render_bounded_json(
                {"response": {"message": "Stripe Test User"}},
                forbidden_values=("Stripe Test User",),
            )

    def test_bounded_renderer_allows_explicit_public_chain_fields(self):
        rendered = _render_bounded_json(
            {
                "contract_address": "0x" + "12" * 20,
                "compose_hash": "0x" + "34" * 32,
                "amount_wei": "5000000000000000000",
                "max_amount_wei": "5000000000000000000",
                "raw_secret_egress": False,
            },
            public_hex_fields=("contract_address", "compose_hash"),
            public_decimal_fields=("amount_wei", "max_amount_wei"),
        )

        body = json.loads(rendered)
        self.assertEqual(body["amount_wei"], "5000000000000000000")
        self.assertFalse(body["raw_secret_egress"])

    def test_synthetic_private_reward_demo_cli_writes_bounded_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "synthetic-reward.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "synthetic-private-reward-demo",
                    "--candidate",
                    "alpha",
                    "--candidate",
                    "beta",
                    "--output",
                    str(output_path),
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=_env(tmpdir),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            body = json.loads(output_path.read_text(encoding="utf-8"))
            rendered = json.dumps(body)
            self.assertEqual(body["demo"], "synthetic_hidden_keyword")
            self.assertEqual(body["submitted_candidate_count"], 2)
            self.assertFalse(body["raw_secret_egress"])
            self.assertNotIn("alpha", rendered)
            self.assertNotIn("beta", rendered)
            self.assertNotIn("sealed alpha", rendered)


if __name__ == "__main__":
    unittest.main()
