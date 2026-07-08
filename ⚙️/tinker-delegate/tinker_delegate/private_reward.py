"""Private verified-reward environment interface.

This module is the code-level counterpart of the private reward model in
PROJECT.md. Exact rewards and sealed data stay inside the environment; callers
receive only bounded feedback, hashes, attestable transcript metadata, and final
bounded results.
"""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeedbackMode(str, Enum):
    """How much reward-derived feedback may leave the environment."""
    NONE = "none"
    PASS_HOLD_DENY = "pass_hold_deny"
    BAND = "band"


class RewardBand(str, Enum):
    EXCEPTIONAL = "exceptional"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"
    WITHHELD = "withheld"


class Decision(str, Enum):
    PASS = "pass"
    HOLD = "hold"
    DENY = "deny"
    BUDGET_EXHAUSTED = "budget_exhausted"
    POLICY_REJECTED = "policy_rejected"


class SecurityTier(str, Enum):
    """Where reward-derived state may live."""
    INTERNAL_TEE = "internal_tee"
    ATTESTED_REMOTE = "attested_remote"
    EXTERNAL_BOUNDED = "external_bounded"


@dataclass(frozen=True)
class PublicProblem:
    title: str
    statement: str
    public_metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "statement": self.statement,
            "public_metadata": _stable_public(self.public_metadata),
        }


@dataclass(frozen=True)
class CandidateSchema:
    kind: str
    json_schema: dict[str, Any]
    max_bytes: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "json_schema": _stable_public(self.json_schema),
            "max_bytes": self.max_bytes,
        }


@dataclass(frozen=True)
class Candidate:
    payload: bytes
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_hash(self) -> str:
        return _sha256_hex(self.payload)

    @property
    def size_bytes(self) -> int:
        return len(self.payload)


@dataclass(frozen=True)
class InternalReward:
    """Exact reward value. This must never be returned to external callers."""
    value: float
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeakageBudget:
    max_queries: int
    feedback_mode: FeedbackMode = FeedbackMode.BAND
    reward_precision_bits: int = 0
    release_candidate_payloads: bool = False
    timing_band_seconds: int = 60
    cost_band_units: int = 1

    def __post_init__(self) -> None:
        if self.max_queries < 0:
            raise ValueError("max_queries must be non-negative")
        if self.reward_precision_bits < 0:
            raise ValueError("reward_precision_bits must be non-negative")
        if self.feedback_mode != FeedbackMode.NONE and self.reward_precision_bits > 0:
            raise ValueError("public reward precision must be zero unless feedback is withheld")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "max_queries": self.max_queries,
            "feedback_mode": self.feedback_mode.value,
            "reward_precision_bits": self.reward_precision_bits,
            "release_candidate_payloads": self.release_candidate_payloads,
            "timing_band_seconds": self.timing_band_seconds,
            "cost_band_units": self.cost_band_units,
        }


@dataclass(frozen=True)
class QueryLeakageRecord:
    candidate_hash: str
    accepted: bool
    decision: Decision
    feedback_mode: FeedbackMode
    reward_band: RewardBand = RewardBand.WITHHELD
    public_message: str = ""
    elapsed_band_seconds: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "candidate_hash": self.candidate_hash,
            "accepted": self.accepted,
            "decision": self.decision.value,
            "feedback_mode": self.feedback_mode.value,
            "reward_band": self.reward_band.value,
            "public_message": self.public_message,
            "elapsed_band_seconds": self.elapsed_band_seconds,
        }


@dataclass(frozen=True)
class BoundedFeedback:
    """Reward-derived output safe to return outside the private boundary."""
    candidate_hash: str
    decision: Decision
    feedback_mode: FeedbackMode
    reward_band: RewardBand = RewardBand.WITHHELD
    public_message: str = ""
    transcript_hash: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "candidate_hash": self.candidate_hash,
            "decision": self.decision.value,
            "feedback_mode": self.feedback_mode.value,
            "reward_band": self.reward_band.value,
            "public_message": self.public_message,
            "transcript_hash": self.transcript_hash,
        }


@dataclass(frozen=True)
class BoundedResult:
    decision: Decision
    result_band: RewardBand
    accepted_count: int
    rejected_count: int
    transcript_hash: str
    leakage_hash: str
    attestation: dict[str, Any]
    public_message: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "result_band": self.result_band.value,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "transcript_hash": self.transcript_hash,
            "leakage_hash": self.leakage_hash,
            "attestation": _stable_public(self.attestation),
            "public_message": self.public_message,
        }


@dataclass(frozen=True)
class EnvironmentAttestation:
    environment_hash: str
    transcript_hash: str
    leakage_hash: str
    security_tier: SecurityTier
    query_budget: int
    accepted_count: int
    rejected_count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "environment_hash": self.environment_hash,
            "transcript_hash": self.transcript_hash,
            "leakage_hash": self.leakage_hash,
            "security_tier": self.security_tier.value,
            "query_budget": self.query_budget,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
        }


class PrivateRewardEnvironment(ABC):
    """Base class for sealed-data reward environments.

    Subclasses provide the problem, candidate schema, exact internal reward, and
    reducer. Callers should use evaluate() and finalize(); direct reward() calls
    are internal TEE-only.
    """

    def __init__(self) -> None:
        self._records: list[QueryLeakageRecord] = []
        self._internal_rewards: list[InternalReward] = []

    @abstractmethod
    def problem(self) -> PublicProblem:
        """Public problem statement safe to show optimizers."""

    @property
    @abstractmethod
    def candidate_schema(self) -> CandidateSchema:
        """Allowed candidate format."""

    @property
    @abstractmethod
    def query_budget(self) -> LeakageBudget:
        """Leakage and query budget for the environment."""

    @property
    def security_tier(self) -> SecurityTier:
        return SecurityTier.EXTERNAL_BOUNDED

    def acceptance_policy(self, candidate: Candidate) -> Decision:
        if candidate.size_bytes > self.candidate_schema.max_bytes:
            return Decision.POLICY_REJECTED
        return Decision.PASS

    @abstractmethod
    def reward(self, candidate: Candidate) -> InternalReward:
        """Exact reward over sealed data. Internal-only."""

    @abstractmethod
    def output_reducer(self, reward: InternalReward) -> BoundedFeedback:
        """Convert exact reward to approved public feedback."""

    def evaluate(self, candidate: Candidate) -> BoundedFeedback:
        """Apply policy and budget, compute private reward, return bounded output."""
        started_at = time.time()
        if self.accepted_count >= self.query_budget.max_queries:
            return self._record_rejection(
                candidate,
                Decision.BUDGET_EXHAUSTED,
                "query budget exhausted",
                started_at,
            )

        decision = self.acceptance_policy(candidate)
        if decision != Decision.PASS:
            return self._record_rejection(candidate, decision, "candidate rejected by policy", started_at)

        internal = self.reward(candidate)
        self._internal_rewards.append(internal)
        bounded = self._sanitize_feedback(candidate, self.output_reducer(internal))
        record = QueryLeakageRecord(
            candidate_hash=candidate.candidate_hash,
            accepted=True,
            decision=bounded.decision,
            feedback_mode=bounded.feedback_mode,
            reward_band=bounded.reward_band,
            public_message=bounded.public_message,
            elapsed_band_seconds=self._elapsed_band(started_at),
        )
        self._records.append(record)
        return BoundedFeedback(
            candidate_hash=bounded.candidate_hash,
            decision=bounded.decision,
            feedback_mode=bounded.feedback_mode,
            reward_band=bounded.reward_band,
            public_message=bounded.public_message,
            transcript_hash=self.transcript_hash,
        )

    def leakage_records(self) -> tuple[QueryLeakageRecord, ...]:
        return tuple(self._records)

    @property
    def accepted_count(self) -> int:
        return sum(1 for record in self._records if record.accepted)

    @property
    def rejected_count(self) -> int:
        return sum(1 for record in self._records if not record.accepted)

    @property
    def transcript_hash(self) -> str:
        return _hash_public_dicts(record.to_public_dict() for record in self._records)

    @property
    def leakage_hash(self) -> str:
        leakage = {
            "problem": self.problem().to_public_dict(),
            "candidate_schema": self.candidate_schema.to_public_dict(),
            "query_budget": self.query_budget.to_public_dict(),
            "records": [record.to_public_dict() for record in self._records],
        }
        return _sha256_json(leakage)

    @property
    def environment_hash(self) -> str:
        return _sha256_json({
            "problem": self.problem().to_public_dict(),
            "candidate_schema": self.candidate_schema.to_public_dict(),
            "query_budget": self.query_budget.to_public_dict(),
            "security_tier": self.security_tier.value,
        })

    def attest(self) -> EnvironmentAttestation:
        return EnvironmentAttestation(
            environment_hash=self.environment_hash,
            transcript_hash=self.transcript_hash,
            leakage_hash=self.leakage_hash,
            security_tier=self.security_tier,
            query_budget=self.query_budget.max_queries,
            accepted_count=self.accepted_count,
            rejected_count=self.rejected_count,
        )

    def finalize(self) -> BoundedResult:
        final_band = RewardBand.WITHHELD
        if self._records:
            final_band = self._records[-1].reward_band
        decision = Decision.PASS if self.accepted_count else Decision.DENY
        return BoundedResult(
            decision=decision,
            result_band=final_band,
            accepted_count=self.accepted_count,
            rejected_count=self.rejected_count,
            transcript_hash=self.transcript_hash,
            leakage_hash=self.leakage_hash,
            attestation=self.attest().to_public_dict(),
            public_message="bounded private reward result",
        )

    def _record_rejection(
        self,
        candidate: Candidate,
        decision: Decision,
        message: str,
        started_at: float,
    ) -> BoundedFeedback:
        record = QueryLeakageRecord(
            candidate_hash=candidate.candidate_hash,
            accepted=False,
            decision=decision,
            feedback_mode=self.query_budget.feedback_mode,
            reward_band=RewardBand.WITHHELD,
            public_message=message,
            elapsed_band_seconds=self._elapsed_band(started_at),
        )
        self._records.append(record)
        return BoundedFeedback(
            candidate_hash=candidate.candidate_hash,
            decision=decision,
            feedback_mode=self.query_budget.feedback_mode,
            reward_band=RewardBand.WITHHELD,
            public_message=message,
            transcript_hash=self.transcript_hash,
        )

    def _sanitize_feedback(
        self,
        candidate: Candidate,
        feedback: BoundedFeedback,
    ) -> BoundedFeedback:
        if feedback.candidate_hash and feedback.candidate_hash != candidate.candidate_hash:
            raise ValueError("bounded feedback candidate_hash mismatch")
        if self.query_budget.feedback_mode == FeedbackMode.NONE:
            return BoundedFeedback(
                candidate_hash=candidate.candidate_hash,
                decision=feedback.decision,
                feedback_mode=FeedbackMode.NONE,
                reward_band=RewardBand.WITHHELD,
                public_message=feedback.public_message,
            )
        if self.query_budget.feedback_mode == FeedbackMode.PASS_HOLD_DENY:
            return BoundedFeedback(
                candidate_hash=candidate.candidate_hash,
                decision=feedback.decision,
                feedback_mode=FeedbackMode.PASS_HOLD_DENY,
                reward_band=RewardBand.WITHHELD,
                public_message=feedback.public_message,
            )
        return BoundedFeedback(
            candidate_hash=candidate.candidate_hash,
            decision=feedback.decision,
            feedback_mode=FeedbackMode.BAND,
            reward_band=feedback.reward_band,
            public_message=feedback.public_message,
        )

    def _elapsed_band(self, started_at: float) -> int:
        granularity = max(1, self.query_budget.timing_band_seconds)
        elapsed = max(0, int(time.time() - started_at))
        return (elapsed // granularity) * granularity


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_hex(_canonical_json(value).encode("utf-8"))


def _hash_public_dicts(values) -> str:
    return _sha256_json(list(values))


def _canonical_json(value: Any) -> str:
    return json.dumps(_stable_public(value), sort_keys=True, separators=(",", ":"))


def _stable_public(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _stable_public(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_public(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
