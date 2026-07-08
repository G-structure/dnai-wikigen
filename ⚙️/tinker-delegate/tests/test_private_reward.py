import unittest

from tinker_delegate.private_reward import (
    BoundedFeedback,
    Candidate,
    CandidateSchema,
    Decision,
    FeedbackMode,
    InternalReward,
    LeakageBudget,
    OptimizerLocation,
    OptimizerPolicy,
    PrivateRewardEnvironment,
    PublicProblem,
    RewardBand,
    SecurityTier,
)


class ToyPrivateRewardEnvironment(PrivateRewardEnvironment):
    def __init__(self, mode=FeedbackMode.BAND, max_queries=2):
        super().__init__()
        self._budget = LeakageBudget(max_queries=max_queries, feedback_mode=mode)

    def problem(self) -> PublicProblem:
        return PublicProblem(
            title="Synthetic sealed score",
            statement="Find a candidate with high hidden overlap.",
            public_metadata={"dataset": "synthetic"},
        )

    @property
    def candidate_schema(self) -> CandidateSchema:
        return CandidateSchema(
            kind="bytes",
            json_schema={"type": "string", "contentEncoding": "base64"},
            max_bytes=32,
        )

    @property
    def query_budget(self) -> LeakageBudget:
        return self._budget

    @property
    def security_tier(self) -> SecurityTier:
        return SecurityTier.INTERNAL_TEE

    def reward(self, candidate: Candidate) -> InternalReward:
        return InternalReward(value=candidate.payload.count(b"x") / 10.0, metrics={"raw_count": 7})

    def output_reducer(self, reward: InternalReward) -> BoundedFeedback:
        if reward.value >= 0.3:
            band = RewardBand.HIGH
        elif reward.value > 0:
            band = RewardBand.LOW
        else:
            band = RewardBand.NEGLIGIBLE
        return BoundedFeedback(
            candidate_hash="",
            decision=Decision.PASS,
            feedback_mode=FeedbackMode.BAND,
            reward_band=band,
            public_message="bounded score band",
        )


class InternalDenseRewardEnvironment(ToyPrivateRewardEnvironment):
    @property
    def optimizer_policy(self) -> OptimizerPolicy:
        return OptimizerPolicy.internal_dense()


class PrivateRewardEnvironmentTest(unittest.TestCase):
    def test_evaluate_returns_bounded_feedback_not_exact_reward(self):
        env = ToyPrivateRewardEnvironment()
        candidate = Candidate(b"xxx")

        feedback = env.evaluate(candidate)

        self.assertEqual(feedback.candidate_hash, candidate.candidate_hash)
        self.assertEqual(feedback.reward_band, RewardBand.HIGH)
        self.assertEqual(feedback.decision, Decision.PASS)
        public = feedback.to_public_dict()
        self.assertNotIn("0.3", str(public))
        self.assertNotIn("raw_count", str(public))
        self.assertEqual(env.accepted_count, 1)
        self.assertEqual(env.rejected_count, 0)

    def test_query_budget_rejects_without_computing_reward(self):
        env = ToyPrivateRewardEnvironment(max_queries=1)
        env.evaluate(Candidate(b"x"))
        internal_count = len(env._internal_rewards)

        feedback = env.evaluate(Candidate(b"xxxxxxxxxx"))

        self.assertEqual(feedback.decision, Decision.BUDGET_EXHAUSTED)
        self.assertEqual(feedback.reward_band, RewardBand.WITHHELD)
        self.assertEqual(len(env._internal_rewards), internal_count)
        self.assertEqual(env.accepted_count, 1)
        self.assertEqual(env.rejected_count, 1)

    def test_policy_rejects_oversized_candidate_without_reward(self):
        env = ToyPrivateRewardEnvironment()

        feedback = env.evaluate(Candidate(b"x" * 33))

        self.assertEqual(feedback.decision, Decision.POLICY_REJECTED)
        self.assertEqual(feedback.reward_band, RewardBand.WITHHELD)
        self.assertEqual(len(env._internal_rewards), 0)

    def test_feedback_modes_reduce_public_precision(self):
        env = ToyPrivateRewardEnvironment(mode=FeedbackMode.PASS_HOLD_DENY)

        feedback = env.evaluate(Candidate(b"xxxx"))

        self.assertEqual(feedback.feedback_mode, FeedbackMode.PASS_HOLD_DENY)
        self.assertEqual(feedback.reward_band, RewardBand.WITHHELD)

    def test_attestation_and_finalize_use_hashes_and_counts(self):
        env = ToyPrivateRewardEnvironment()
        env.evaluate(Candidate(b"x"))
        result = env.finalize()

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(len(result.transcript_hash), 64)
        self.assertEqual(len(result.leakage_hash), 64)
        self.assertEqual(result.attestation["security_tier"], SecurityTier.INTERNAL_TEE.value)
        public = result.to_public_dict()
        self.assertNotIn("raw_count", str(public))
        self.assertNotIn("payload", str(public))

    def test_leakage_budget_fails_closed_on_public_precision(self):
        with self.assertRaisesRegex(ValueError, "public reward precision"):
            LeakageBudget(
                max_queries=1,
                feedback_mode=FeedbackMode.BAND,
                reward_precision_bits=8,
            )

    def test_reducer_candidate_hash_mismatch_fails_closed(self):
        class MismatchedReducerEnvironment(ToyPrivateRewardEnvironment):
            def output_reducer(self, reward: InternalReward) -> BoundedFeedback:
                return BoundedFeedback(
                    candidate_hash="not-the-candidate",
                    decision=Decision.PASS,
                    feedback_mode=FeedbackMode.BAND,
                    reward_band=RewardBand.HIGH,
                )

        env = MismatchedReducerEnvironment()

        with self.assertRaisesRegex(ValueError, "candidate_hash mismatch"):
            env.evaluate(Candidate(b"x"))

    def test_external_optimizer_is_bounded_by_default(self):
        env = ToyPrivateRewardEnvironment()
        env.evaluate(Candidate(b"xxx"))

        self.assertEqual(env.optimizer_policy.location, OptimizerLocation.EXTERNAL)
        self.assertFalse(env.optimizer_policy.allow_exact_rewards)
        with self.assertRaisesRegex(PermissionError, "forbids exact rewards"):
            env.internal_reward_for_optimizer()

        view = env.optimizer_view()
        self.assertEqual(view["optimizer_policy"]["location"], OptimizerLocation.EXTERNAL.value)
        self.assertNotIn("0.3", str(view))
        self.assertNotIn("raw_count", str(view))
        self.assertNotIn("xxx", str(view))

    def test_external_optimizer_policy_rejects_reward_derived_state(self):
        with self.assertRaisesRegex(ValueError, "external optimizers"):
            OptimizerPolicy(
                location=OptimizerLocation.EXTERNAL,
                allow_exact_rewards=True,
            )
        with self.assertRaisesRegex(ValueError, "external optimizers"):
            OptimizerPolicy(
                location=OptimizerLocation.EXTERNAL,
                allow_reward_derived_state=True,
            )
        with self.assertRaisesRegex(ValueError, "external optimizers"):
            OptimizerPolicy(
                location=OptimizerLocation.EXTERNAL,
                allow_private_checkpoints=True,
            )

    def test_internal_dense_optimizer_can_read_exact_reward_inside_boundary(self):
        env = InternalDenseRewardEnvironment()

        public_feedback = env.evaluate(Candidate(b"xxx"))
        reward = env.internal_reward_for_optimizer()

        self.assertEqual(reward.value, 0.3)
        self.assertEqual(reward.metrics["raw_count"], 7)
        self.assertEqual(public_feedback.reward_band, RewardBand.HIGH)
        self.assertNotIn("0.3", str(public_feedback.to_public_dict()))
        self.assertEqual(env.attest().optimizer_location, OptimizerLocation.INTERNAL_TEE)
        self.assertEqual(len(env.attest().optimizer_policy_hash), 64)

    def test_attested_remote_dense_policy_requires_attestation(self):
        with self.assertRaisesRegex(ValueError, "requires attestation"):
            OptimizerPolicy(
                location=OptimizerLocation.ATTESTED_REMOTE,
                allow_exact_rewards=True,
                require_attestation=False,
            )

        policy = OptimizerPolicy.attested_remote_dense()

        self.assertEqual(policy.location, OptimizerLocation.ATTESTED_REMOTE)
        self.assertTrue(policy.allow_exact_rewards)
        self.assertTrue(policy.require_attestation)


if __name__ == "__main__":
    unittest.main()
