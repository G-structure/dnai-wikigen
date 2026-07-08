import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tinker_delegate.funding_manifest import (
    MANIFEST_VERSION,
    assert_no_secret_material,
    build_funding_validation_manifest,
)


def _preflight():
    return {
        "ready": True,
        "policy": {
            "mode": "operator_capped_validation",
            "max_add_balance_usd": 5.0,
            "raw_card_scope": "operator-owned capped validation only",
        },
        "checks": [
            {"name": "funding_mode", "ok": True, "status": "operator_capped_validation"},
            {"name": "billing_attestation_policy", "ok": True, "status": "configured"},
        ],
    }


def _receipt():
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


class FundingManifestTest(unittest.TestCase):
    def test_manifest_hashes_bounded_inputs_without_raw_card_fields(self):
        manifest = build_funding_validation_manifest(
            preflight=_preflight(),
            receipt=_receipt(),
            validation_id="operator-run-1",
            attestation_policy={"compose_hash": "c" * 64, "app_id": "app-ok"},
        ).to_public_dict()

        rendered = repr(manifest)
        self.assertEqual(manifest["version"], MANIFEST_VERSION)
        self.assertEqual(manifest["funding_mode"], "operator_capped_validation")
        self.assertEqual(manifest["receipt_outcome"], "card_declined")
        self.assertTrue(manifest["card_payload_destroyed"])
        self.assertTrue(manifest["no_raw_secret_egress"])
        self.assertTrue(manifest["no_raw_card_retained"])
        self.assertEqual(len(manifest["preflight_hash"]), 64)
        self.assertEqual(len(manifest["receipt_hash"]), 64)
        self.assertEqual(len(manifest["attestation_policy_hash"]), 64)
        self.assertEqual(len(manifest["manifest_hash"]), 64)
        self.assertNotIn("operator-run-1", rendered)
        self.assertNotIn("4242424242424242", rendered)

    def test_rejects_secret_like_values_and_forbidden_keys(self):
        with self.assertRaisesRegex(ValueError, "secret-like material"):
            assert_no_secret_material({"bounded_message": "card_number=4242424242424242"})

        with self.assertRaisesRegex(ValueError, "forbidden key"):
            assert_no_secret_material({"card_number": "<redacted>"})

    def test_no_raw_card_retained_requires_destroyed_and_no_egress(self):
        receipt = _receipt()
        receipt["card_payload_destroyed"] = False

        manifest = build_funding_validation_manifest(
            preflight=_preflight(),
            receipt=receipt,
        ).to_public_dict()

        self.assertFalse(manifest["no_raw_card_retained"])

    def test_cli_builds_manifest_from_json_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            preflight_path = Path(tmpdir) / "preflight.json"
            receipt_path = Path(tmpdir) / "receipt.json"
            output_path = Path(tmpdir) / "manifest.json"
            preflight_path.write_text(json.dumps(_preflight()), encoding="utf-8")
            receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tinker_delegate.main",
                    "funding-manifest",
                    "--preflight-json",
                    str(preflight_path),
                    "--receipt-json",
                    str(receipt_path),
                    "--validation-id",
                    "operator-run-1",
                    "--compose-hash",
                    "c" * 64,
                    "--output",
                    str(output_path),
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["receipt_outcome"], "card_declined")
            self.assertTrue(manifest["no_raw_card_retained"])


if __name__ == "__main__":
    unittest.main()
