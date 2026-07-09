import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    def test_balance_can_query_deployed_delegate_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "balance.json"
            seen_headers: list[str] = []

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != "/billing/balance":
                        self.send_response(404)
                        self.end_headers()
                        return
                    seen_headers.append(self.headers.get("Authorization", ""))
                    body = json.dumps(
                        {
                            "success": True,
                            "attempt_record": {
                                "surface": "balance",
                                "outcome": "success",
                                "amount_band": "",
                                "balance_band": "0_25_usd",
                                "raw_secret_egress": False,
                            },
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format, *args):
                    return

            server = HTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = _env(tmpdir)
                env["TINKER_RUNTIME_AUTH_TOKEN"] = "operator-secret"
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tinker_delegate.main",
                        "balance",
                        "--api-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--auth-token-env",
                        "TINKER_RUNTIME_AUTH_TOKEN",
                        "--output",
                        str(output_path),
                    ],
                    check=False,
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    text=True,
                    capture_output=True,
                )
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(seen_headers, ["Bearer operator-secret"])
            body = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(body["success"])
            self.assertEqual(body["attempt_record"]["balance_band"], "0_25_usd")
            self.assertFalse(body["attempt_record"]["raw_secret_egress"])

    def test_tinker_smoke_can_query_deployed_delegate_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "smoke.json"
            seen_headers: list[str] = []
            seen_body: list[dict] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    if self.path != "/tinker/smoke":
                        self.send_response(404)
                        self.end_headers()
                        return
                    seen_headers.append(self.headers.get("Authorization", ""))
                    length = int(self.headers.get("Content-Length", "0"))
                    seen_body.append(json.loads(self.rfile.read(length).decode("utf-8")))
                    body = json.dumps(
                        {
                            "surface": "tinker_sdk_smoke",
                            "success": True,
                            "outcome": "success",
                            "furthest_stage": "cleanup_completed",
                            "training_run_id_hash": "a" * 64,
                            "checkpoint_path_hash": "b" * 64,
                            "sample_observed": True,
                            "sample_output_returned": False,
                            "raw_secret_egress": False,
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format, *args):
                    return

            server = HTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = _env(tmpdir)
                env["TINKER_RUNTIME_AUTH_TOKEN"] = "operator-secret"
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tinker_delegate.main",
                        "tinker-smoke",
                        "--api-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--auth-token-env",
                        "TINKER_RUNTIME_AUTH_TOKEN",
                        "--max-usd",
                        "0.05",
                        "--model",
                        "meta-llama/Llama-3.2-1B",
                        "--rank",
                        "4",
                        "--output",
                        str(output_path),
                    ],
                    check=False,
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    text=True,
                    capture_output=True,
                )
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(seen_headers, ["Bearer operator-secret"])
            self.assertEqual(seen_body[0]["max_usd"], 0.05)
            self.assertEqual(seen_body[0]["rank"], 4)
            body = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(body["success"])
            self.assertTrue(body["sample_observed"])
            self.assertFalse(body["sample_output_returned"])
            self.assertFalse(body["raw_secret_egress"])

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
