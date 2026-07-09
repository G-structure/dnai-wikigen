"""Bounded receipts for source-modeled coordination consent decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from tinker_delegate.coordination import (
    CollabSession,
    ConsentDecision,
    ConsentGrant,
    CoordinationEnv,
    CoordinationState,
    Corpus,
    DelegationGrant,
    GateDecision,
    GatedQuery,
    GrantStatus,
    Participant,
    ParticipantRole,
    Turn,
    TurnRecord,
    TurnStatus,
    coordinate,
)


class ConsentReceiptError(ValueError):
    """Raised when a consent receipt input cannot be parsed safely."""


def build_consent_decision_receipt(
    state_payload: dict[str, Any],
    decision_payload: dict[str, Any],
    *,
    now: int = 0,
) -> dict[str, Any]:
    state = _state_from_payload(state_payload)
    decision = _decision_from_payload(decision_payload)
    before = state.turns.get(decision.turn_id)
    if before is None:
        raise ConsentReceiptError("unknown turn")

    updated = coordinate(state, decision, CoordinationEnv(now=now))
    after = updated.turns[decision.turn_id]
    normalized_decision = decision.decision.strip().lower()

    return {
        "surface": "coordination_consent_decision",
        "schema_version": 1,
        "applied": True,
        "event": "consent_decision",
        "action": _action_for_after(after),
        "turn": {
            "turn_id": decision.turn_id,
            "status_before": before.status.value,
            "status_after": after.status.value,
            "status_reason_after": after.status_reason,
            "corpus_count": len(after.turn.corpora),
            "requester_ref_hash": _stable_hash(after.turn.requester_ref, prefix="requester_ref"),
            "purpose_hash": _stable_hash(after.turn.purpose, prefix="purpose"),
            "pipeline_hash": _stable_hash(after.turn.pipeline, prefix="pipeline"),
        },
        "consent": {
            "corpus_ref": decision.corpus_ref,
            "owner_ref_hash": _stable_hash(decision.owner_ref, prefix="owner_ref"),
            "decision": normalized_decision,
            "decision_hash": _stable_hash(normalized_decision, prefix="consent_decision"),
            "expires_at_set": decision.expires_at is not None,
        },
        "quorum": {
            "consent_quorum": state.session.consent_quorum,
            "grant_count_before": len(state.session.consent_grants),
            "grant_count_after": len(updated.session.consent_grants),
            "settled": after.status == TurnStatus.SETTLED,
        },
        "state_input_hash": _stable_hash(state_payload, prefix="coordination_state_input"),
        "state_output_hash": _stable_hash(_state_to_payload(updated), prefix="coordination_state_output"),
        "raw_artifact_egress": False,
        "raw_policy_egress": False,
        "raw_private_data_egress": False,
        "raw_secret_egress": False,
    }


def _state_from_payload(payload: dict[str, Any]) -> CoordinationState:
    allowed = {"session", "turns", "revoked_corpora"}
    _reject_unknown(payload, allowed, "coordination state")
    session = _session_from_payload(_require_dict(payload, "session"))
    turns_payload = _require_dict(payload, "turns")
    turns = {
        str(turn_id): _turn_record_from_payload(record_payload)
        for turn_id, record_payload in turns_payload.items()
    }
    revoked = payload.get("revoked_corpora", [])
    if not isinstance(revoked, list | tuple) or not all(isinstance(item, str) for item in revoked):
        raise ConsentReceiptError("invalid revoked corpora")
    return CoordinationState(session=session, turns=turns, revoked_corpora=frozenset(revoked))


def _session_from_payload(payload: dict[str, Any]) -> CollabSession:
    allowed = {"participants", "corpora", "consent_grants", "delegation_grants", "consent_quorum"}
    _reject_unknown(payload, allowed, "session")
    return CollabSession(
        participants=tuple(_participant_from_payload(item) for item in _require_list(payload, "participants")),
        corpora=tuple(_corpus_from_payload(item) for item in _require_list(payload, "corpora")),
        consent_grants=tuple(_consent_grant_from_payload(item) for item in payload.get("consent_grants", [])),
        delegation_grants=tuple(_delegation_grant_from_payload(item) for item in payload.get("delegation_grants", [])),
        consent_quorum=_optional_string(payload, "consent_quorum", "unanimous"),
    )


def _participant_from_payload(payload: Any) -> Participant:
    item = _as_dict(payload, "participant")
    _reject_unknown(item, {"ref", "role", "owner_ref"}, "participant")
    try:
        role = ParticipantRole(_require_string(item, "role"))
    except ValueError as exc:
        raise ConsentReceiptError("invalid participant role") from exc
    return Participant(
        ref=_require_string(item, "ref"),
        role=role,
        owner_ref=_optional_string(item, "owner_ref", ""),
    )


def _corpus_from_payload(payload: Any) -> Corpus:
    item = _as_dict(payload, "corpus")
    _reject_unknown(item, {"ref", "owner_ref", "policy_hash", "royalty_per_query"}, "corpus")
    return Corpus(
        ref=_require_string(item, "ref"),
        owner_ref=_require_string(item, "owner_ref"),
        policy_hash=_require_string(item, "policy_hash"),
        royalty_per_query=int(item.get("royalty_per_query", 0)),
    )


def _consent_grant_from_payload(payload: Any) -> ConsentGrant:
    item = _as_dict(payload, "consent grant")
    _reject_unknown(item, {"corpus_ref", "owner_ref", "requester_ref", "purpose", "pipeline", "status", "expires_at"}, "consent grant")
    return ConsentGrant(
        corpus_ref=_require_string(item, "corpus_ref"),
        owner_ref=_require_string(item, "owner_ref"),
        requester_ref=_require_string(item, "requester_ref"),
        purpose=_require_string(item, "purpose"),
        pipeline=_require_string(item, "pipeline"),
        status=_grant_status(item.get("status", GrantStatus.ACTIVE.value)),
        expires_at=_optional_int(item, "expires_at"),
    )


def _delegation_grant_from_payload(payload: Any) -> DelegationGrant:
    item = _as_dict(payload, "delegation grant")
    _reject_unknown(item, {"agent_ref", "grantor_ref", "corpora", "purposes", "pipelines", "status", "expires_at"}, "delegation grant")
    return DelegationGrant(
        agent_ref=_require_string(item, "agent_ref"),
        grantor_ref=_require_string(item, "grantor_ref"),
        corpora=tuple(_string_list(item, "corpora")),
        purposes=tuple(_string_list(item, "purposes")),
        pipelines=tuple(_string_list(item, "pipelines")),
        status=_grant_status(item.get("status", GrantStatus.ACTIVE.value)),
        expires_at=_optional_int(item, "expires_at"),
    )


def _turn_record_from_payload(payload: Any) -> TurnRecord:
    item = _as_dict(payload, "turn record")
    _reject_unknown(item, {"turn", "status", "queries", "status_reason"}, "turn record")
    try:
        status = TurnStatus(_require_string(item, "status"))
    except ValueError as exc:
        raise ConsentReceiptError("invalid turn status") from exc
    return TurnRecord(
        turn=_turn_from_payload(_require_dict(item, "turn")),
        status=status,
        queries=tuple(_query_from_payload(query) for query in item.get("queries", [])),
        status_reason=_optional_string(item, "status_reason", ""),
    )


def _turn_from_payload(payload: dict[str, Any]) -> Turn:
    _reject_unknown(payload, {"turn_id", "by", "requester_ref", "purpose", "pipeline", "corpora", "requests"}, "turn")
    requests = _require_dict(payload, "requests")
    return Turn(
        turn_id=_require_string(payload, "turn_id"),
        by=_require_string(payload, "by"),
        requester_ref=_require_string(payload, "requester_ref"),
        purpose=_require_string(payload, "purpose"),
        pipeline=_require_string(payload, "pipeline"),
        corpora=tuple(_string_list(payload, "corpora")),
        requests={str(key): _as_dict(value, "turn request") for key, value in requests.items()},
    )


def _query_from_payload(payload: Any) -> GatedQuery:
    item = _as_dict(payload, "query")
    _reject_unknown(item, {"corpus_ref", "decision", "stage", "reason", "routed_role"}, "query")
    try:
        decision = GateDecision(_require_string(item, "decision"))
    except ValueError as exc:
        raise ConsentReceiptError("invalid gate decision") from exc
    return GatedQuery(
        corpus_ref=_require_string(item, "corpus_ref"),
        decision=decision,
        stage=int(item.get("stage", 0)),
        reason=_optional_string(item, "reason", ""),
        routed_role=_optional_string(item, "routed_role", ""),
    )


def _decision_from_payload(payload: dict[str, Any]) -> ConsentDecision:
    _reject_unknown(payload, {"turn_id", "corpus_ref", "owner_ref", "decision", "expires_at"}, "consent decision")
    return ConsentDecision(
        turn_id=_require_string(payload, "turn_id"),
        corpus_ref=_require_string(payload, "corpus_ref"),
        owner_ref=_require_string(payload, "owner_ref"),
        decision=_require_string(payload, "decision"),
        expires_at=_optional_int(payload, "expires_at"),
    )


def _state_to_payload(state: CoordinationState) -> dict[str, Any]:
    return {
        "session": {
            "participants": [
                {"ref": participant.ref, "role": participant.role.value, "owner_ref": participant.owner_ref}
                for participant in state.session.participants
            ],
            "corpora": [
                {
                    "ref": corpus.ref,
                    "owner_ref": corpus.owner_ref,
                    "policy_hash": corpus.policy_hash,
                    "royalty_per_query": corpus.royalty_per_query,
                }
                for corpus in state.session.corpora
            ],
            "consent_grants": [
                {
                    "corpus_ref": grant.corpus_ref,
                    "owner_ref": grant.owner_ref,
                    "requester_ref": grant.requester_ref,
                    "purpose": grant.purpose,
                    "pipeline": grant.pipeline,
                    "status": grant.status.value,
                    "expires_at": grant.expires_at,
                }
                for grant in state.session.consent_grants
            ],
            "delegation_grants": [
                {
                    "agent_ref": grant.agent_ref,
                    "grantor_ref": grant.grantor_ref,
                    "corpora": list(grant.corpora),
                    "purposes": list(grant.purposes),
                    "pipelines": list(grant.pipelines),
                    "status": grant.status.value,
                    "expires_at": grant.expires_at,
                }
                for grant in state.session.delegation_grants
            ],
            "consent_quorum": state.session.consent_quorum,
        },
        "turns": {
            turn_id: {
                "turn": {
                    "turn_id": record.turn.turn_id,
                    "by": record.turn.by,
                    "requester_ref": record.turn.requester_ref,
                    "purpose": record.turn.purpose,
                    "pipeline": record.turn.pipeline,
                    "corpora": list(record.turn.corpora),
                    "requests": record.turn.requests,
                },
                "status": record.status.value,
                "queries": [
                    {
                        "corpus_ref": query.corpus_ref,
                        "decision": query.decision.value,
                        "stage": query.stage,
                        "reason": query.reason,
                        "routed_role": query.routed_role,
                    }
                    for query in record.queries
                ],
                "status_reason": record.status_reason,
            }
            for turn_id, record in sorted(state.turns.items())
        },
        "revoked_corpora": sorted(state.revoked_corpora),
    }


def _action_for_after(record: TurnRecord) -> str:
    if record.status == TurnStatus.SETTLED:
        return "settle_bounded_result"
    if record.status == TurnStatus.DENIED:
        return "deny"
    return "await_more_consent"


def _grant_status(value: Any) -> GrantStatus:
    try:
        return GrantStatus(str(value))
    except ValueError as exc:
        raise ConsentReceiptError("invalid grant status") from exc


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _as_dict(payload.get(key), key)


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ConsentReceiptError(f"missing or invalid {key}")
    return value


def _string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) and item for item in value):
        raise ConsentReceiptError(f"missing or invalid {key}")
    return list(value)


def _as_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConsentReceiptError(f"invalid {label}")
    return value


def _reject_unknown(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ConsentReceiptError(f"unknown {label} field")


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ConsentReceiptError(f"missing or invalid {key}")
    return value


def _optional_string(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ConsentReceiptError(f"invalid {key}")
    return value


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConsentReceiptError(f"invalid {key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConsentReceiptError(f"invalid {key}") from exc


def _stable_hash(value: Any, *, prefix: str) -> str:
    if isinstance(value, str):
        payload = value
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(prefix.encode("utf-8") + b"\0" + payload.encode("utf-8")).hexdigest()
