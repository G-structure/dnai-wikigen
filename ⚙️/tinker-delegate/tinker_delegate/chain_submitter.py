"""TEE-held DiligenceRoom result submission.

This module signs ``submitResult`` transactions with an Ethereum key derived
inside dstack. It intentionally has no raw-private-key configuration path.
Tests may inject a signer object, but production construction goes through
``DstackEthereumSigner.from_settings`` and fails closed outside dstack mode.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from eth_account import Account
from eth_hash.auto import keccak

from tinker_delegate.config import Settings
from tinker_delegate.dstack_utils import derive_storage_key, is_dstack_enabled
from tinker_delegate.run_metadata_store import value_band


SECP256K1_N = int(
    "fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141",
    16,
)

SUBMIT_RESULT_SELECTOR = keccak(
    b"submitResult(uint256,uint8,uint256,bytes32)"
)[:4]
DEALS_SELECTOR = keccak(b"deals(uint256)")[:4]

SCORE_BAND_TO_CONTRACT = {
    "negligible": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "exceptional": 4,
}
CONTRACT_SCORE_BANDS = {
    value: key for key, value in SCORE_BAND_TO_CONTRACT.items()
}


class ChainSubmitterError(ValueError):
    """Raised when result submission cannot proceed safely."""


class SignerUnavailable(ChainSubmitterError):
    """Raised when no TEE-held signer is available."""


class EthereumSigner(Protocol):
    """Minimal signer interface for production dstack and test signers."""

    address: str
    custody: str

    def sign_transaction(self, transaction: dict[str, Any]):
        """Return an eth-account signed transaction object."""


@dataclass(frozen=True)
class DealRead:
    """Public subset of ``DiligenceRoom.deals(dealId)`` used for guardrails."""

    seller: str
    buyer: str
    reserve_price: int
    budget_cap: int
    expiry: int
    state: int
    artifact_hash: str
    tee_identity: str
    score_band: int
    compute_cost: int
    fee: int
    result_hash: str


@dataclass(frozen=True)
class SubmitResultReceipt:
    """Bounded receipt for a signed result submission."""

    submitted: bool
    tx_hash: str
    deal_id: int
    score_band: str
    score_band_value: int
    compute_cost_band: str
    result_hash: str
    signer_address: str
    contract_address: str
    chain_id: int
    nonce: int
    gas_limit: int
    custody: str
    raw_secret_egress: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "submitted": self.submitted,
            "tx_hash": self.tx_hash,
            "deal_id": self.deal_id,
            "score_band": self.score_band,
            "score_band_value": self.score_band_value,
            "compute_cost_band": self.compute_cost_band,
            "result_hash": self.result_hash,
            "signer_address": self.signer_address,
            "contract_address": self.contract_address,
            "chain_id": self.chain_id,
            "nonce": self.nonce,
            "gas_limit": self.gas_limit,
            "custody": self.custody,
            "raw_secret_egress": self.raw_secret_egress,
        }


class DstackEthereumSigner:
    """Ethereum signer derived from dstack-held key material."""

    custody = "dstack_derived"

    def __init__(self, private_key: bytes):
        self._account = Account.from_key(private_key)
        self.address = self._account.address

    @classmethod
    def from_settings(cls, settings: Settings) -> "DstackEthereumSigner":
        if not is_dstack_enabled():
            raise SignerUnavailable("dstack mode is required for TEE chain signing")
        key_material = derive_storage_key(settings.chain_signer_key_path)
        return cls(derive_ethereum_private_key(key_material, settings.chain_signer_key_path))

    def sign_transaction(self, transaction: dict[str, Any]):
        return self._account.sign_transaction(transaction)


def derive_ethereum_private_key(key_material: bytes, path: str) -> bytes:
    """Map dstack key material to a valid secp256k1 private key."""

    if not key_material:
        raise SignerUnavailable("empty dstack key material")
    seed = hashlib.sha256(
        b"dnai-wikigen/dstack/ethereum-signer/v1" + path.encode() + key_material
    ).digest()
    value = (int.from_bytes(seed, "big") % (SECP256K1_N - 1)) + 1
    return value.to_bytes(32, "big")


def normalize_address(address: str) -> str:
    raw = address.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) != 40:
        raise ChainSubmitterError("expected 20-byte Ethereum address")
    int(raw, 16)
    return "0x" + raw


def normalize_bytes32(value: str) -> str:
    raw = value.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) != 64:
        raise ChainSubmitterError("expected bytes32 hex value")
    int(raw, 16)
    if int(raw, 16) == 0:
        raise ChainSubmitterError("result hash must be non-zero")
    return "0x" + raw


def encode_uint256(value: int) -> bytes:
    if value < 0:
        raise ChainSubmitterError("uint256 value cannot be negative")
    return value.to_bytes(32, "big")


def score_band_to_contract_value(score_band: str | int) -> tuple[int, str]:
    if isinstance(score_band, int):
        if score_band not in CONTRACT_SCORE_BANDS:
            raise ChainSubmitterError("unknown score band value")
        return score_band, CONTRACT_SCORE_BANDS[score_band]
    key = str(score_band).strip().lower()
    if key not in SCORE_BAND_TO_CONTRACT:
        raise ChainSubmitterError("unknown score band")
    return SCORE_BAND_TO_CONTRACT[key], key


def encode_submit_result_calldata(
    *,
    deal_id: int,
    score_band: str | int,
    compute_cost_wei: int,
    result_hash: str,
) -> str:
    band_value, _ = score_band_to_contract_value(score_band)
    result_hash_hex = normalize_bytes32(result_hash)[2:]
    payload = b"".join(
        [
            SUBMIT_RESULT_SELECTOR,
            encode_uint256(deal_id),
            encode_uint256(band_value),
            encode_uint256(compute_cost_wei),
            bytes.fromhex(result_hash_hex),
        ]
    )
    return "0x" + payload.hex()


def encode_deals_calldata(deal_id: int) -> str:
    return "0x" + (DEALS_SELECTOR + encode_uint256(deal_id)).hex()


def _quantity(value: int) -> str:
    return hex(value)


def _parse_quantity(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ChainSubmitterError("JSON-RPC quantity must be hex")
    return int(value, 16)


def _word_to_address(word: str) -> str:
    return "0x" + word[-40:].lower()


def _word_to_bytes32(word: str) -> str:
    return "0x" + word.lower()


def decode_deal_call_result(raw: str) -> DealRead:
    if not isinstance(raw, str) or not raw.startswith("0x"):
        raise ChainSubmitterError("invalid deals() response")
    body = raw[2:]
    words = [body[index:index + 64] for index in range(0, len(body), 64)]
    if len(words) < 12 or any(len(word) != 64 for word in words[:12]):
        raise ChainSubmitterError("short deals() response")
    return DealRead(
        seller=_word_to_address(words[0]),
        buyer=_word_to_address(words[1]),
        reserve_price=int(words[2], 16),
        budget_cap=int(words[3], 16),
        expiry=int(words[4], 16),
        state=int(words[5], 16),
        artifact_hash=_word_to_bytes32(words[6]),
        tee_identity=_word_to_address(words[7]),
        score_band=int(words[8], 16),
        compute_cost=int(words[9], 16),
        fee=int(words[10], 16),
        result_hash=_word_to_bytes32(words[11]),
    )


class JsonRpcClient:
    """Small synchronous JSON-RPC client for chain submission."""

    def __init__(self, rpc_url: str, *, timeout: float = 20.0):
        if not rpc_url:
            raise ChainSubmitterError("chain RPC URL is required")
        self.rpc_url = rpc_url
        self._client = httpx.Client(timeout=timeout)
        self._next_id = 1

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, params: list[Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        response = self._client.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            message = payload["error"].get("message", "JSON-RPC error")
            raise ChainSubmitterError(str(message))
        return payload.get("result")

    def chain_id(self) -> int:
        return _parse_quantity(self.call("eth_chainId", []))

    def nonce(self, address: str) -> int:
        return _parse_quantity(self.call("eth_getTransactionCount", [address, "latest"]))

    def gas_price(self) -> int:
        return _parse_quantity(self.call("eth_gasPrice", []))

    def estimate_gas(self, tx: dict[str, Any]) -> int:
        return _parse_quantity(self.call("eth_estimateGas", [tx]))

    def eth_call(self, tx: dict[str, Any]) -> str:
        return str(self.call("eth_call", [tx, "latest"]))

    def send_raw_transaction(self, raw_transaction: bytes) -> str:
        return str(self.call("eth_sendRawTransaction", ["0x" + raw_transaction.hex()]))


class DiligenceRoomSubmitter:
    """Broadcast bounded evaluation results from a TEE-held signer."""

    def __init__(
        self,
        rpc: JsonRpcClient,
        contract_address: str,
        signer: EthereumSigner,
        *,
        gas_limit: int = 0,
    ):
        self.rpc = rpc
        self.contract_address = normalize_address(contract_address)
        self.signer = signer
        self.gas_limit = gas_limit

    def read_deal(self, deal_id: int) -> DealRead:
        raw = self.rpc.eth_call(
            {
                "to": self.contract_address,
                "data": encode_deals_calldata(deal_id),
            }
        )
        return decode_deal_call_result(raw)

    def submit_result(
        self,
        *,
        deal_id: int,
        score_band: str | int,
        compute_cost_wei: int,
        result_hash: str,
    ) -> SubmitResultReceipt:
        if deal_id < 0:
            raise ChainSubmitterError("deal ID cannot be negative")
        if compute_cost_wei < 0:
            raise ChainSubmitterError("compute cost cannot be negative")

        band_value, band_label = score_band_to_contract_value(score_band)
        normalized_result_hash = normalize_bytes32(result_hash)
        signer_address = normalize_address(self.signer.address)
        deal = self.read_deal(deal_id)
        if deal.state != 1:
            raise ChainSubmitterError("deal is not in Funded state")
        if normalize_address(deal.tee_identity) != signer_address:
            raise ChainSubmitterError("TEE signer does not match deal teeIdentity")
        fee = (compute_cost_wei * 100) // 10000
        if compute_cost_wei + fee > deal.budget_cap:
            raise ChainSubmitterError("compute cost exceeds deal budget cap")

        calldata = encode_submit_result_calldata(
            deal_id=deal_id,
            score_band=band_value,
            compute_cost_wei=compute_cost_wei,
            result_hash=normalized_result_hash,
        )
        chain_id = self.rpc.chain_id()
        nonce = self.rpc.nonce(signer_address)
        gas_price = self.rpc.gas_price()
        base_tx = {
            "from": signer_address,
            "to": self.contract_address,
            "value": "0x0",
            "data": calldata,
        }
        gas_limit = self.gas_limit or self.rpc.estimate_gas(base_tx)
        tx = {
            "chainId": chain_id,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "to": self.contract_address,
            "value": 0,
            "data": calldata,
        }
        signed = self.signer.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:
            raw = getattr(signed, "rawTransaction", None)
        if raw is None:
            raise ChainSubmitterError("signer did not return a raw transaction")
        tx_hash = self.rpc.send_raw_transaction(bytes(raw))
        return SubmitResultReceipt(
            submitted=True,
            tx_hash=tx_hash,
            deal_id=deal_id,
            score_band=band_label,
            score_band_value=band_value,
            compute_cost_band=value_band(compute_cost_wei),
            result_hash=normalized_result_hash,
            signer_address=signer_address,
            contract_address=self.contract_address,
            chain_id=chain_id,
            nonce=nonce,
            gas_limit=gas_limit,
            custody=getattr(self.signer, "custody", "unknown"),
        )


def build_dstack_submitter(settings: Settings, *, rpc_url: str = "", contract_address: str = "") -> DiligenceRoomSubmitter:
    """Build the production submitter from dstack-held key material."""

    signer = DstackEthereumSigner.from_settings(settings)
    rpc = JsonRpcClient(rpc_url or settings.chain_rpc_url)
    return DiligenceRoomSubmitter(
        rpc,
        contract_address or settings.chain_contract_address,
        signer,
        gas_limit=settings.chain_submit_gas_limit,
    )
