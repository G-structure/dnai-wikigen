import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from eth_account import Account

from tinker_delegate.chain_submitter import (
    ChainSubmitterError,
    DiligenceRoomSubmitter,
    DstackEthereumSigner,
    SignerUnavailable,
    encode_submit_result_calldata,
)
from tinker_delegate.config import Settings


def _word_int(value: int) -> str:
    return value.to_bytes(32, "big").hex()


def _word_address(address: str) -> str:
    raw = address.lower().removeprefix("0x")
    return ("0" * 24) + raw


def _deal_response(*, tee_identity: str, state: int = 1, budget_cap: int = 10**18) -> str:
    words = [
        _word_address("0x" + "11" * 20),  # seller
        _word_address("0x" + "22" * 20),  # buyer
        _word_int(10**15),  # reservePrice
        _word_int(budget_cap),
        _word_int(9999999999),  # expiry
        _word_int(state),
        "33" * 32,  # artifactHash
        _word_address(tee_identity),
        _word_int(0),  # scoreBand
        _word_int(0),  # computeCost
        _word_int(0),  # fee
        "00" * 32,  # resultHash
    ]
    return "0x" + "".join(words)


class InjectedTestSigner:
    custody = "injected_test_signer"

    def __init__(self):
        self._account = Account.create("dnai-wikigen-chain-submit-test")
        self.address = self._account.address

    def sign_transaction(self, transaction):
        return self._account.sign_transaction(transaction)


class FakeRpc:
    def __init__(self, deal_response: str):
        self.deal_response = deal_response
        self.sent_raw_transactions: list[bytes] = []
        self.estimate_calls: list[dict] = []

    def eth_call(self, tx):
        self.last_eth_call = tx
        return self.deal_response

    def chain_id(self):
        return 31337

    def nonce(self, address):
        self.nonce_address = address
        return 7

    def gas_price(self):
        return 1_000_000_000

    def estimate_gas(self, tx):
        self.estimate_calls.append(tx)
        return 123456

    def send_raw_transaction(self, raw_transaction: bytes):
        self.sent_raw_transactions.append(raw_transaction)
        return "0x" + "ab" * 32


class ChainSubmitterTest(unittest.TestCase):
    def test_submit_result_encodes_bounded_contract_call(self):
        result_hash = "0x" + "44" * 32
        calldata = encode_submit_result_calldata(
            deal_id=5,
            score_band="high",
            compute_cost_wei=123,
            result_hash=result_hash,
        )

        self.assertTrue(calldata.startswith("0x"))
        self.assertEqual(len(bytes.fromhex(calldata[2:])), 4 + (4 * 32))
        self.assertIn(_word_int(5), calldata)
        self.assertIn(_word_int(3), calldata)
        self.assertTrue(calldata.endswith("44" * 32))

    def test_submit_result_broadcasts_from_matching_tee_signer(self):
        signer = InjectedTestSigner()
        rpc = FakeRpc(_deal_response(tee_identity=signer.address))
        submitter = DiligenceRoomSubmitter(
            rpc,
            "0x" + "55" * 20,
            signer,
        )

        receipt = submitter.submit_result(
            deal_id=1,
            score_band="medium",
            compute_cost_wei=10**15,
            result_hash="0x" + "66" * 32,
        )

        self.assertTrue(receipt.submitted)
        self.assertEqual(receipt.tx_hash, "0x" + "ab" * 32)
        self.assertEqual(receipt.score_band, "medium")
        self.assertEqual(receipt.score_band_value, 2)
        self.assertEqual(receipt.chain_id, 31337)
        self.assertEqual(receipt.nonce, 7)
        self.assertEqual(receipt.gas_limit, 123456)
        self.assertEqual(receipt.custody, "injected_test_signer")
        self.assertFalse(receipt.raw_secret_egress)
        self.assertEqual(len(rpc.sent_raw_transactions), 1)
        recovered = Account.recover_transaction(rpc.sent_raw_transactions[0])
        self.assertEqual(recovered.lower(), signer.address.lower())

    def test_submit_result_rejects_wrong_deal_state_or_signer(self):
        signer = InjectedTestSigner()
        wrong_tee = "0x" + "77" * 20
        submitter = DiligenceRoomSubmitter(
            FakeRpc(_deal_response(tee_identity=wrong_tee)),
            "0x" + "55" * 20,
            signer,
        )
        with self.assertRaisesRegex(ChainSubmitterError, "teeIdentity"):
            submitter.submit_result(
                deal_id=1,
                score_band="low",
                compute_cost_wei=1,
                result_hash="0x" + "66" * 32,
            )

        submitter = DiligenceRoomSubmitter(
            FakeRpc(_deal_response(tee_identity=signer.address, state=0)),
            "0x" + "55" * 20,
            signer,
        )
        with self.assertRaisesRegex(ChainSubmitterError, "Funded"):
            submitter.submit_result(
                deal_id=1,
                score_band="low",
                compute_cost_wei=1,
                result_hash="0x" + "66" * 32,
            )

    def test_submit_result_rejects_over_budget_compute_cost(self):
        signer = InjectedTestSigner()
        submitter = DiligenceRoomSubmitter(
            FakeRpc(_deal_response(tee_identity=signer.address, budget_cap=100)),
            "0x" + "55" * 20,
            signer,
        )
        with self.assertRaisesRegex(ChainSubmitterError, "budget"):
            submitter.submit_result(
                deal_id=1,
                score_band="low",
                compute_cost_wei=100,
                result_hash="0x" + "66" * 32,
            )

    def test_dstack_signer_fails_closed_outside_dstack_mode(self):
        with patch("tinker_delegate.chain_submitter.is_dstack_enabled", return_value=False):
            with self.assertRaisesRegex(SignerUnavailable, "dstack mode"):
                DstackEthereumSigner.from_settings(Settings())

    def test_cli_submit_result_has_no_private_key_flag(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tinker_delegate.main",
                "submit-result",
                "--help",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
        )
        help_body = result.stdout.lower()
        self.assertIn("submit-result", help_body)
        self.assertNotIn("private-key", help_body)
        self.assertNotIn("seed", help_body)
        self.assertNotIn("mnemonic", help_body)

    def test_bounded_receipt_json_contains_no_secret_shaped_fields(self):
        signer = InjectedTestSigner()
        rpc = FakeRpc(_deal_response(tee_identity=signer.address))
        receipt = DiligenceRoomSubmitter(
            rpc,
            "0x" + "55" * 20,
            signer,
            gas_limit=200000,
        ).submit_result(
            deal_id=1,
            score_band="medium",
            compute_cost_wei=10**15,
            result_hash="0x" + "66" * 32,
        )

        body = json.dumps(receipt.to_public_dict())
        self.assertIn('"raw_secret_egress": false', body)
        self.assertNotIn("private", body.lower())
        self.assertNotIn("card", body.lower())
        self.assertNotIn("api_key", body.lower())


if __name__ == "__main__":
    unittest.main()
