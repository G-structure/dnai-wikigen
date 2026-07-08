"""DiligenceRoom chain-event watcher and TEE control-plane dispatcher."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx
from eth_hash.auto import keccak


EVENT_SIGNATURES = {
    "DealCreated": "DealCreated(uint256,address,uint256,uint256,bytes32,address)",
    "DealFunded": "DealFunded(uint256,address,uint256)",
    "EvaluationSubmitted": "EvaluationSubmitted(uint256,uint8,uint256,bytes32)",
    "DealAccepted": "DealAccepted(uint256,uint256,uint256,uint256)",
    "DealRejected": "DealRejected(uint256,uint256,uint256)",
    "DealExpired": "DealExpired(uint256,uint256)",
}

EVENT_TOPICS = {
    name: "0x" + keccak(signature.encode("ascii")).hex()
    for name, signature in EVENT_SIGNATURES.items()
}

TOPIC_EVENTS = {topic: name for name, topic in EVENT_TOPICS.items()}
SCORE_BANDS = ("negligible", "low", "medium", "high", "exceptional")
RESOLUTION_EVENTS = {"DealAccepted", "DealRejected", "DealExpired"}


class ChainWatcherError(RuntimeError):
    """Raised when chain watcher input or JSON-RPC output is invalid."""


@dataclass(frozen=True)
class DiligenceRoomEvent:
    """Decoded public DiligenceRoom event."""

    name: str
    deal_id: str
    block_number: int
    tx_hash: str
    log_index: int
    fields: dict[str, Any] = field(default_factory=dict)

    def to_control_plane_payload(self) -> dict[str, Any]:
        return {
            "event_name": self.name,
            "deal_id": self.deal_id,
            "block_number": self.block_number,
            "tx_hash": self.tx_hash,
            "log_index": self.log_index,
            "fields": self.fields,
        }


@dataclass(frozen=True)
class DispatchSummary:
    """Bounded summary of a watcher dispatch batch."""

    event_count: int = 0
    chain_event_posts: int = 0
    funded_notifications: int = 0
    resolved_notifications: int = 0
    missing_created_context: int = 0

    def to_public_dict(self) -> dict[str, int]:
        return {
            "event_count": self.event_count,
            "chain_event_posts": self.chain_event_posts,
            "funded_notifications": self.funded_notifications,
            "resolved_notifications": self.resolved_notifications,
            "missing_created_context": self.missing_created_context,
        }


def event_topic(name: str) -> str:
    """Return the topic0 hash for a supported DiligenceRoom event."""
    return EVENT_TOPICS[name]


def decode_diligence_room_log(log: dict[str, Any]) -> DiligenceRoomEvent | None:
    """Decode one DiligenceRoom event log, ignoring unsupported events."""
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if not topics:
        return None
    name = TOPIC_EVENTS.get(topics[0])
    if name is None:
        return None
    if len(topics) < 2:
        raise ChainWatcherError(f"{name} log missing indexed deal ID")

    deal_id = str(_topic_uint(topics[1]))
    words = _data_words(log.get("data", "0x"))
    block_number = _hex_int(log.get("blockNumber", "0x0"))
    log_index = _hex_int(log.get("logIndex", "0x0"))
    tx_hash = str(log.get("transactionHash", ""))

    fields: dict[str, Any]
    if name == "DealCreated":
        _require_topics(name, topics, 3)
        _require_words(name, words, 4)
        fields = {
            "seller": _topic_address(topics[2]),
            "reserve_price": _word_uint(words[0]),
            "expiry": _word_uint(words[1]),
            "artifact_hash": _word_bytes32(words[2]),
            "tee_identity": _word_address(words[3]),
        }
    elif name == "DealFunded":
        _require_topics(name, topics, 3)
        _require_words(name, words, 1)
        fields = {
            "buyer": _topic_address(topics[2]),
            "budget_cap": _word_uint(words[0]),
        }
    elif name == "EvaluationSubmitted":
        _require_words(name, words, 3)
        score_value = _word_uint(words[0])
        fields = {
            "score_band": SCORE_BANDS[score_value] if score_value < len(SCORE_BANDS) else str(score_value),
            "compute_cost": _word_uint(words[1]),
            "result_hash": _word_bytes32(words[2]),
        }
    elif name == "DealAccepted":
        _require_words(name, words, 3)
        fields = {
            "seller_payment": _word_uint(words[0]),
            "dev_payment": _word_uint(words[1]),
            "buyer_refund": _word_uint(words[2]),
        }
    elif name == "DealRejected":
        _require_words(name, words, 2)
        fields = {
            "dev_payment": _word_uint(words[0]),
            "buyer_refund": _word_uint(words[1]),
        }
    elif name == "DealExpired":
        _require_words(name, words, 1)
        fields = {"refund": _word_uint(words[0])}
    else:
        return None

    return DiligenceRoomEvent(
        name=name,
        deal_id=deal_id,
        block_number=block_number,
        tx_hash=tx_hash,
        log_index=log_index,
        fields=fields,
    )


class JsonRpcLogSource:
    """Minimal JSON-RPC log source for DiligenceRoom events."""

    def __init__(self, rpc_url: str, contract_address: str, *, client: httpx.Client | None = None):
        if not rpc_url:
            raise ChainWatcherError("chain RPC URL is required")
        if not contract_address:
            raise ChainWatcherError("DiligenceRoom contract address is required")
        self.rpc_url = rpc_url
        self.contract_address = _normalize_address(contract_address)
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def latest_block(self) -> int:
        return _hex_int(self._rpc("eth_blockNumber", []))

    def get_events(self, from_block: int, to_block: int) -> list[DiligenceRoomEvent]:
        if to_block < from_block:
            return []
        logs = self._rpc(
            "eth_getLogs",
            [
                {
                    "address": self.contract_address,
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    "topics": [list(EVENT_TOPICS.values())],
                }
            ],
        )
        events = [decode_diligence_room_log(log) for log in logs]
        return sorted(
            [event for event in events if event is not None],
            key=lambda event: (event.block_number, event.log_index),
        )

    def _rpc(self, method: str, params: list[Any]) -> Any:
        response = self._client.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise ChainWatcherError(str(payload["error"]))
        if "result" not in payload:
            raise ChainWatcherError(f"JSON-RPC response missing result for {method}")
        return payload["result"]


class ChainEventDispatcher:
    """Dispatch decoded DiligenceRoom events to the TEE control-plane API."""

    def __init__(self, control_plane_url: str, *, client: httpx.Client | None = None):
        if not control_plane_url:
            raise ChainWatcherError("control-plane API URL is required")
        self.control_plane_url = control_plane_url
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._created: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def dispatch(self, events: list[DiligenceRoomEvent]) -> DispatchSummary:
        chain_event_posts = 0
        funded_notifications = 0
        resolved_notifications = 0
        missing_created_context = 0

        for event in sorted(events, key=lambda item: (item.block_number, item.log_index)):
            self._post("/deal/chain-event", event.to_control_plane_payload())
            chain_event_posts += 1

            if event.name == "DealCreated":
                self._created[event.deal_id] = event.fields
                continue

            if event.name == "DealFunded":
                created = self._created.get(event.deal_id)
                if not created:
                    missing_created_context += 1
                    continue
                self._post(
                    "/deal/notify-funded",
                    {
                        "deal_id": event.deal_id,
                        "buyer": event.fields["buyer"],
                        "seller": created["seller"],
                        "budget_cap": event.fields["budget_cap"],
                        "reserve_price": created["reserve_price"],
                    },
                )
                funded_notifications += 1
                continue

            if event.name in RESOLUTION_EVENTS:
                self._post(f"/deal/{event.deal_id}/resolve", {"deal_id": event.deal_id})
                resolved_notifications += 1

        return DispatchSummary(
            event_count=len(events),
            chain_event_posts=chain_event_posts,
            funded_notifications=funded_notifications,
            resolved_notifications=resolved_notifications,
            missing_created_context=missing_created_context,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._client.post(_endpoint(self.control_plane_url, path), json=payload)
        response.raise_for_status()
        return response.json()


class ChainWatcher:
    """Poll a JSON-RPC endpoint and dispatch DiligenceRoom events."""

    def __init__(self, source: JsonRpcLogSource, dispatcher: ChainEventDispatcher):
        self.source = source
        self.dispatcher = dispatcher

    def poll_once(self, from_block: int, to_block: int) -> DispatchSummary:
        return self.dispatcher.dispatch(self.source.get_events(from_block, to_block))

    def run(
        self,
        *,
        start_block: int | None = None,
        poll_interval: float = 5.0,
        confirmations: int = 2,
        once: bool = False,
    ):
        next_block = start_block
        while True:
            latest = self.source.latest_block()
            safe_tip = latest - max(0, confirmations)
            if safe_tip < 0:
                safe_tip = 0
            if next_block is None:
                next_block = safe_tip
            summary = self.poll_once(next_block, safe_tip)
            yield {"from_block": next_block, "to_block": safe_tip, **summary.to_public_dict()}
            next_block = safe_tip + 1
            if once:
                return
            time.sleep(poll_interval)


def parse_start_block(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return _hex_int(value) if value.startswith("0x") else int(value)


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _normalize_address(value: str) -> str:
    raw = _strip_0x(value).lower()
    if len(raw) != 40:
        raise ChainWatcherError("address must be 20 bytes")
    int(raw, 16)
    return "0x" + raw


def _strip_0x(value: str) -> str:
    return value[2:] if value.startswith(("0x", "0X")) else value


def _hex_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value, 16)


def _data_words(data: str) -> list[str]:
    raw = _strip_0x(data)
    if raw == "":
        return []
    if len(raw) % 64 != 0:
        raise ChainWatcherError("event data is not 32-byte aligned")
    return [raw[index : index + 64] for index in range(0, len(raw), 64)]


def _topic_uint(topic: str) -> int:
    return int(_strip_0x(topic), 16)


def _topic_address(topic: str) -> str:
    raw = _strip_0x(topic)
    if len(raw) != 64:
        raise ChainWatcherError("address topic must be 32 bytes")
    return "0x" + raw[-40:].lower()


def _word_uint(word: str) -> int:
    return int(word, 16)


def _word_bytes32(word: str) -> str:
    if len(word) != 64:
        raise ChainWatcherError("bytes32 word must be 32 bytes")
    return "0x" + word.lower()


def _word_address(word: str) -> str:
    if len(word) != 64:
        raise ChainWatcherError("address word must be 32 bytes")
    return "0x" + word[-40:].lower()


def _require_topics(event_name: str, topics: list[str], count: int) -> None:
    if len(topics) < count:
        raise ChainWatcherError(f"{event_name} log missing indexed topics")


def _require_words(event_name: str, words: list[str], count: int) -> None:
    if len(words) < count:
        raise ChainWatcherError(f"{event_name} log missing data words")
