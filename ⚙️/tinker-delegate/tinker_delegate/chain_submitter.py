"""TEE-held DiligenceRoom result submission.

This module signs ``submitResult`` transactions with an Ethereum key derived
inside dstack. It intentionally has no raw-private-key configuration path.
Tests may inject a signer object, but production construction goes through
``DstackEthereumSigner.from_settings`` and fails closed outside dstack mode.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from eth_account import Account
from eth_hash.auto import keccak
from eth_utils import to_checksum_address

from tinker_delegate.config import Settings
from tinker_delegate.dstack_utils import (
    derive_storage_key,
    get_attestation_details,
    is_dstack_enabled,
)
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
    payload_result_hash: str
    compose_hash: str
    expiry: int
    signer_address: str
    contract_address: str
    chain_id: int
    nonce: int
    gas_limit: int
    custody: str
    signer_attestation_hash: str
    signer_attestation_report_data: str
    signer_attestation_quote_size: int
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
            "payload_result_hash": self.payload_result_hash,
            "compose_hash": self.compose_hash,
            "expiry": self.expiry,
            "signer_address": self.signer_address,
            "contract_address": self.contract_address,
            "chain_id": self.chain_id,
            "nonce": self.nonce,
            "gas_limit": self.gas_limit,
            "custody": self.custody,
            "signer_attestation_hash": self.signer_attestation_hash,
            "signer_attestation_report_data": self.signer_attestation_report_data,
            "signer_attestation_quote_size": self.signer_attestation_quote_size,
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


@dataclass(frozen=True)
class SignerAttestationEvidence:
    """Bounded signer attestation evidence for off-chain verification."""

    mode: str
    signer_address: str
    chain_id: int
    contract_address: str
    report_data: str
    quote_report_data: str
    quote_hash: str
    quote_size: int
    compose_hash: str
    app_id: str = ""
    os_image_hash: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "signer_address": normalize_address(self.signer_address),
            "chain_id": self.chain_id,
            "contract_address": normalize_address(self.contract_address),
            "report_data": normalize_bytes32(self.report_data),
            "quote_report_data": normalize_bytes32(self.quote_report_data),
            "quote_hash": normalize_bytes32(self.quote_hash),
            "quote_size": self.quote_size,
            "compose_hash": normalize_bytes32(self.compose_hash),
            "app_id": self.app_id,
            "os_image_hash": self.os_image_hash,
            "raw_secret_egress": False,
        }


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


def normalize_optional_bytes32(value: str) -> str:
    if not value:
        raise ChainSubmitterError("compose hash is required for result commitment")
    return normalize_bytes32(value)


def _hex_bytes(value: str, *, field: str) -> bytes:
    raw = value.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    try:
        decoded = bytes.fromhex(raw)
    except ValueError as exc:
        raise ChainSubmitterError(f"{field} must be hex") from exc
    if not decoded:
        raise ChainSubmitterError(f"{field} must be non-empty")
    return decoded


def _normalize_quote_report_data(value: str, *, expected_report_data: str) -> str:
    """Return the 32-byte binding from a TDX quote report-data field.

    TDX report data is 64 bytes. dstack may expose our 32-byte report binding
    padded with zero bytes, while local bounded receipts keep only the binding.
    """

    raw = _hex_bytes(value, field="quote_report_data")
    expected = bytes.fromhex(normalize_bytes32(expected_report_data)[2:])
    if len(raw) == 32 and raw == expected:
        return "0x" + raw.hex()
    if len(raw) == 64 and raw[:32] == expected and raw[32:] == b"\x00" * 32:
        return "0x" + raw[:32].hex()
    raise ChainSubmitterError("signer quote report data mismatch")


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


def signer_attestation_report_data(
    *,
    signer_address: str,
    chain_id: int,
    contract_address: str,
) -> bytes:
    """Report data binding dstack quote evidence to a result signer context."""

    payload = json.dumps(
        {
            "service": "dnai-wikigen",
            "context": "diligence-room-submit-result",
            "signer_address": normalize_address(signer_address),
            "chain_id": chain_id,
            "contract_address": normalize_address(contract_address),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()


def get_dstack_signer_attestation(
    *,
    signer_address: str,
    chain_id: int,
    contract_address: str,
) -> SignerAttestationEvidence:
    """Fetch quote evidence binding the current CVM to the result signer."""

    if not is_dstack_enabled():
        raise SignerUnavailable("dstack mode is required for signer attestation")
    report_data = signer_attestation_report_data(
        signer_address=signer_address,
        chain_id=chain_id,
        contract_address=contract_address,
    )
    details = get_attestation_details(report_data)
    quote = _hex_bytes(str(details.get("quote") or ""), field="quote")
    quote_hash = "0x" + hashlib.sha256(quote).hexdigest()
    expected_report_data = "0x" + report_data.hex()
    quote_report_data = _normalize_quote_report_data(
        str(details.get("quote_report_data") or ""),
        expected_report_data=expected_report_data,
    )
    return SignerAttestationEvidence(
        mode="tdx",
        signer_address=signer_address,
        chain_id=chain_id,
        contract_address=contract_address,
        report_data=expected_report_data,
        quote_report_data=quote_report_data,
        quote_hash=quote_hash,
        quote_size=len(quote),
        compose_hash=normalize_bytes32(str(details.get("compose_hash") or "")),
        app_id=str(details.get("app_id") or ""),
        os_image_hash=str(details.get("os_image_hash") or ""),
    )


def verify_signer_attestation_evidence(
    evidence: SignerAttestationEvidence,
    *,
    signer_address: str,
    chain_id: int,
    contract_address: str,
    expected_compose_hash: str = "",
) -> None:
    """Fail closed unless signer attestation matches the submission context."""

    if evidence.mode != "tdx":
        raise ChainSubmitterError("signer attestation mode must be tdx")
    if normalize_address(evidence.signer_address) != normalize_address(signer_address):
        raise ChainSubmitterError("signer attestation address mismatch")
    if int(evidence.chain_id) != int(chain_id):
        raise ChainSubmitterError("signer attestation chain id mismatch")
    if normalize_address(evidence.contract_address) != normalize_address(contract_address):
        raise ChainSubmitterError("signer attestation contract mismatch")
    expected_report_data = "0x" + signer_attestation_report_data(
        signer_address=signer_address,
        chain_id=chain_id,
        contract_address=contract_address,
    ).hex()
    if normalize_bytes32(evidence.report_data) != expected_report_data:
        raise ChainSubmitterError("signer attestation report data mismatch")
    if normalize_bytes32(evidence.quote_report_data) != expected_report_data:
        raise ChainSubmitterError("signer quote report data mismatch")
    if (
        expected_compose_hash
        and normalize_bytes32(evidence.compose_hash) != normalize_bytes32(expected_compose_hash)
    ):
        raise ChainSubmitterError("signer attestation compose hash mismatch")
    if evidence.quote_size <= 0:
        raise ChainSubmitterError("signer attestation quote is missing")


@dataclass(frozen=True)
class ResultCommitment:
    """Anti-replay commitment submitted as DiligenceRoom.resultHash."""

    chain_id: int
    contract_address: str
    deal_id: int
    nonce: int
    compose_hash: str
    payload_result_hash: str
    score_band_value: int
    compute_cost_wei: int
    expiry: int

    def digest(self) -> str:
        payload = b"".join(
            [
                keccak(b"dnai-wikigen:DiligenceRoomResult:v1"),
                encode_uint256(self.chain_id),
                bytes.fromhex(normalize_address(self.contract_address)[2:]).rjust(32, b"\x00"),
                encode_uint256(self.deal_id),
                encode_uint256(self.nonce),
                bytes.fromhex(normalize_bytes32(self.compose_hash)[2:]),
                bytes.fromhex(normalize_bytes32(self.payload_result_hash)[2:]),
                encode_uint256(self.score_band_value),
                encode_uint256(self.compute_cost_wei),
                encode_uint256(self.expiry),
            ]
        )
        return "0x" + keccak(payload).hex()

    def public_fields(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "contract_address": normalize_address(self.contract_address),
            "deal_id": self.deal_id,
            "nonce": self.nonce,
            "compose_hash": normalize_bytes32(self.compose_hash),
            "payload_result_hash": normalize_bytes32(self.payload_result_hash),
            "score_band_value": self.score_band_value,
            "compute_cost_band": value_band(self.compute_cost_wei),
            "expiry": self.expiry,
        }


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
        compose_hash: str = "",
        signer_attestation: SignerAttestationEvidence | None = None,
    ) -> SubmitResultReceipt:
        if deal_id < 0:
            raise ChainSubmitterError("deal ID cannot be negative")
        if compute_cost_wei < 0:
            raise ChainSubmitterError("compute cost cannot be negative")

        band_value, band_label = score_band_to_contract_value(score_band)
        payload_result_hash = normalize_bytes32(result_hash)
        signer_address = normalize_address(self.signer.address)
        deal = self.read_deal(deal_id)
        if deal.state != 1:
            raise ChainSubmitterError("deal is not in Funded state")
        if normalize_address(deal.tee_identity) != signer_address:
            raise ChainSubmitterError("TEE signer does not match deal teeIdentity")
        fee = (compute_cost_wei * 100) // 10000
        if compute_cost_wei + fee > deal.budget_cap:
            raise ChainSubmitterError("compute cost exceeds deal budget cap")

        chain_id = self.rpc.chain_id()
        nonce = self.rpc.nonce(signer_address)
        if signer_attestation is not None:
            verify_signer_attestation_evidence(
                signer_attestation,
                signer_address=signer_address,
                chain_id=chain_id,
                contract_address=self.contract_address,
                expected_compose_hash=compose_hash,
            )
            normalized_compose_hash = normalize_optional_bytes32(signer_attestation.compose_hash)
        elif compose_hash:
            normalized_compose_hash = normalize_optional_bytes32(compose_hash)
        else:
            raise ChainSubmitterError("signer attestation or compose hash is required")
        commitment = ResultCommitment(
            chain_id=chain_id,
            contract_address=self.contract_address,
            deal_id=deal_id,
            nonce=nonce,
            compose_hash=normalized_compose_hash,
            payload_result_hash=payload_result_hash,
            score_band_value=band_value,
            compute_cost_wei=compute_cost_wei,
            expiry=deal.expiry,
        )
        submission_result_hash = commitment.digest()
        calldata = encode_submit_result_calldata(
            deal_id=deal_id,
            score_band=band_value,
            compute_cost_wei=compute_cost_wei,
            result_hash=submission_result_hash,
        )
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
            "to": to_checksum_address(self.contract_address),
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
            result_hash=submission_result_hash,
            payload_result_hash=payload_result_hash,
            compose_hash=normalized_compose_hash,
            expiry=deal.expiry,
            signer_address=signer_address,
            contract_address=self.contract_address,
            chain_id=chain_id,
            nonce=nonce,
            gas_limit=gas_limit,
            custody=getattr(self.signer, "custody", "unknown"),
            signer_attestation_hash=(
                signer_attestation.quote_hash if signer_attestation is not None else ""
            ),
            signer_attestation_report_data=(
                signer_attestation.report_data if signer_attestation is not None else ""
            ),
            signer_attestation_quote_size=(
                signer_attestation.quote_size if signer_attestation is not None else 0
            ),
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
