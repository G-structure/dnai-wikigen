"""Synthetic hidden-data private reward environment."""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Mapping

from tinker_delegate.private_reward import (
    BoundedFeedback,
    BoundedResult,
    Candidate,
    CandidateSchema,
    Decision,
    FeedbackMode,
    InternalReward,
    LeakageBudget,
    PrivateRewardEnvironment,
    PublicProblem,
    RewardBand,
    SecurityTier,
)
from tinker_delegate.private_reward_holdout import (
    HiddenHoldoutSet,
    HoldoutPartition,
    HoldoutRecord,
    HoldoutSplitPolicy,
)


class SyntheticHiddenKeywordEnvironment(PrivateRewardEnvironment):
    """Toy environment that scores a keyword against hidden record partitions."""

    def __init__(
        self,
        records: Mapping[str, bytes | HoldoutRecord],
        holdout_policy: HoldoutSplitPolicy | None = None,
        query_budget: LeakageBudget | None = None,
        max_candidate_bytes: int = 64,
    ) -> None:
        super().__init__()
        self.holdout = HiddenHoldoutSet(records, holdout_policy)
        self._query_budget = query_budget or LeakageBudget(
            max_queries=self.holdout.policy.max_reward_queries,
            feedback_mode=FeedbackMode.BAND,
        )
        if self._query_budget.max_queries > self.holdout.policy.max_reward_queries:
            raise ValueError("query_budget cannot exceed hidden holdout reward-query budget")
        self._max_candidate_bytes = max_candidate_bytes
        self._accepted_candidates: list[Candidate] = []
        self._final_result: BoundedResult | None = None

    def problem(self) -> PublicProblem:
        return PublicProblem(
            title="Synthetic hidden keyword search",
            statement="Submit one UTF-8 keyword. The private environment returns only a bounded score band.",
            public_metadata={
                "environment": "synthetic_hidden_keyword",
                "holdout": self._holdout_setup_public(),
            },
        )

    @property
    def candidate_schema(self) -> CandidateSchema:
        return CandidateSchema(
            kind="utf8_keyword",
            json_schema={
                "type": "string",
                "minLength": 1,
                "maxLength": self._max_candidate_bytes,
                "pattern": "^[A-Za-z0-9_-]+$",
            },
            max_bytes=self._max_candidate_bytes,
        )

    @property
    def query_budget(self) -> LeakageBudget:
        return self._query_budget

    @property
    def security_tier(self) -> SecurityTier:
        return SecurityTier.INTERNAL_TEE

    @property
    def environment_hash(self) -> str:
        return _sha256_json({
            "problem": self.problem().to_public_dict(),
            "candidate_schema": self.candidate_schema.to_public_dict(),
            "query_budget": self.query_budget.to_public_dict(),
            "security_tier": self.security_tier.value,
            "optimizer_policy": self.optimizer_policy.to_public_dict(),
            "holdout": self._holdout_setup_public(),
        })

    @property
    def leakage_hash(self) -> str:
        leakage = {
            "problem": self.problem().to_public_dict(),
            "candidate_schema": self.candidate_schema.to_public_dict(),
            "query_budget": self.query_budget.to_public_dict(),
            "optimizer_policy": self.optimizer_policy.to_public_dict(),
            "holdout": self.holdout.public_manifest().to_public_dict(),
            "records": [record.to_public_dict() for record in self.leakage_records()],
        }
        return _sha256_json(leakage)

    def acceptance_policy(self, candidate: Candidate) -> Decision:
        decision = super().acceptance_policy(candidate)
        if decision != Decision.PASS:
            return decision
        if self.holdout.closed_to_reward_queries:
            return Decision.POLICY_REJECTED
        keyword = _candidate_keyword(candidate)
        if keyword is None:
            return Decision.POLICY_REJECTED
        return Decision.PASS

    def reward(self, candidate: Candidate) -> InternalReward:
        self.holdout.record_reward_query(candidate.candidate_hash)
        score, matches, total = self._score_partition(candidate, HoldoutPartition.REWARD)
        return InternalReward(
            value=score,
            metrics={
                "partition": HoldoutPartition.REWARD.value,
                "matches": matches,
                "total": total,
            },
        )

    def output_reducer(self, reward: InternalReward) -> BoundedFeedback:
        return BoundedFeedback(
            candidate_hash="",
            decision=Decision.PASS,
            feedback_mode=FeedbackMode.BAND,
            reward_band=_score_band(reward.value),
            public_message="bounded synthetic holdout score",
        )

    def evaluate(self, candidate: Candidate) -> BoundedFeedback:
        feedback = super().evaluate(candidate)
        if feedback.decision == Decision.PASS:
            self._accepted_candidates.append(candidate)
        return feedback

    def finalize(self) -> BoundedResult:
        if self._final_result is not None:
            return self._final_result
        if not self._accepted_candidates:
            self._final_result = super().finalize()
            return self._final_result

        candidate = self._accepted_candidates[-1]
        self.holdout.record_final_validation(candidate.candidate_hash)
        final_score, _matches, _total = self._score_partition(candidate, HoldoutPartition.FINAL_VALIDATION)
        final_band = _score_band(final_score)
        decision = Decision.PASS if final_score > 0 else Decision.DENY
        attestation = self.attest().to_public_dict()
        attestation["holdout"] = self.holdout.public_manifest().to_public_dict()
        self._final_result = BoundedResult(
            decision=decision,
            result_band=final_band,
            accepted_count=self.accepted_count,
            rejected_count=self.rejected_count,
            transcript_hash=self.transcript_hash,
            leakage_hash=self.leakage_hash,
            attestation=attestation,
            public_message="bounded synthetic final validation result",
        )
        return self._final_result

    def _score_partition(
        self,
        candidate: Candidate,
        partition: HoldoutPartition,
    ) -> tuple[float, int, int]:
        keyword = _candidate_keyword(candidate)
        if keyword is None:
            return 0.0, 0, 0
        records = self.holdout.records_for(partition)
        if not records:
            return 0.0, 0, 0
        matches = 0
        for record in records:
            text = record.payload.decode("utf-8", errors="ignore").lower()
            if keyword in text:
                matches += 1
        return matches / len(records), matches, len(records)

    def _holdout_setup_public(self) -> dict[str, Any]:
        manifest = self.holdout.public_manifest().to_public_dict()
        return {
            "split_commitment": manifest["split_commitment"],
            "policy": manifest["policy"],
            "partition_counts": manifest["partition_counts"],
        }


def _candidate_keyword(candidate: Candidate) -> str | None:
    try:
        value = candidate.payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    keyword = value.strip().lower()
    if not keyword:
        return None
    if any(not (char.isalnum() or char in {"_", "-"}) for char in keyword):
        return None
    return keyword


def _score_band(score: float) -> RewardBand:
    if score >= 0.9:
        return RewardBand.EXCEPTIONAL
    if score >= 0.5:
        return RewardBand.HIGH
    if score >= 0.25:
        return RewardBand.MEDIUM
    if score > 0:
        return RewardBand.LOW
    return RewardBand.NEGLIGIBLE


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_hex(json.dumps(_stable_public(value), sort_keys=True, separators=(",", ":")).encode("utf-8"))


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
