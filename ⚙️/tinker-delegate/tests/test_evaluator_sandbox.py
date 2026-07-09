import json
import sys
import types
import unittest


sys.modules.setdefault(
    "tinker",
    types.SimpleNamespace(ServiceClient=object, TrainingClient=object, SamplingClient=object),
)

from tinker_delegate.evaluator_sandbox import (  # noqa: E402
    EvaluatorSandboxOutcome,
    EvaluatorSandboxPolicy,
    SandboxedEvaluatorRunner,
)
from tinker_delegate.fake_tinker_backend import FakeTinkerServiceClient  # noqa: E402
from tinker_delegate.private_reward_sandbox import SandboxFailureCode  # noqa: E402
from tinker_delegate.session import IsolatedTinkerSession  # noqa: E402


class SandboxedEvaluatorRunnerTest(unittest.TestCase):
    def test_process_bound_evaluator_executes_allowlisted_capability_plan(self):
        private_artifact = b"sealed evaluator artifact must stay parent-side"
        service_client = FakeTinkerServiceClient(api_key="sealed-upstream-key")
        session = IsolatedTinkerSession(service_client, "deal-sandbox")
        source = b"""
emit(
    [
        {"op": "create_training", "base_model": "meta-llama/Llama-3.1-8B", "rank": 4},
        {"op": "train", "token_count": 12},
        {"op": "optim_step"},
        {"op": "sample", "prompt_tokens": 8, "max_tokens": 4},
    ],
    {
        "quality_delta": 0.08,
        "benchmark": "sandbox-local",
        "confidence": "high",
        "methodology": "capability plan only",
    },
)
"""

        result = SandboxedEvaluatorRunner().run(
            evaluator_source=source,
            artifact=private_artifact,
            artifact_type="dataset",
            session=session,
            budget_cap=10**18,
            reserve_price=10**17,
        )

        self.assertEqual(result.outcome, EvaluatorSandboxOutcome.PASS)
        self.assertEqual(result.failure_code, SandboxFailureCode.NONE)
        self.assertEqual(result.metrics["quality_delta"], 0.08)
        self.assertEqual(result.metrics["benchmark"], "sandbox-local")
        self.assertEqual(result.operation_counts["create_training"], 1)
        self.assertEqual(result.operation_counts["train"], 1)
        self.assertEqual(result.operation_counts["sample"], 1)
        self.assertEqual(len(service_client.created_training_clients), 1)
        train_kwargs, training_client = service_client.created_training_clients[0]
        self.assertEqual(train_kwargs["user_metadata"]["deal_id"], "deal-sandbox")
        self.assertEqual(train_kwargs["user_metadata"]["surface"], "sandboxed_evaluator")
        self.assertEqual(train_kwargs["user_metadata"]["mode"], "capability_plan")
        self.assertEqual(len(training_client.forward_backward_calls), 1)
        self.assertEqual(len(service_client.samplers), 1)
        self.assertEqual(len(service_client.samplers[0].sample_calls), 1)

        public = json.dumps(result.to_public_dict(), sort_keys=True)
        forbidden_values = (
            private_artifact.decode("utf-8"),
            "sealed-upstream-key",
            "fake-run-1",
            "tinker://fake-run-1",
            "fake-sample-derived-from-sealed-artifact",
        )
        for forbidden in forbidden_values:
            self.assertNotIn(forbidden, public)
        self.assertFalse(result.to_public_dict()["raw_session_returned"])
        self.assertFalse(result.to_public_dict()["raw_artifact_returned"])
        self.assertFalse(result.to_public_dict()["raw_checkpoint_path_returned"])
        self.assertFalse(result.to_public_dict()["raw_secret_egress"])

    def test_evaluator_process_has_no_session_or_service_client_object(self):
        service_client = FakeTinkerServiceClient(api_key="sealed-upstream-key")
        session = IsolatedTinkerSession(service_client, "deal-sandbox")
        source = b"""
session_visible = 0
try:
    session
except Exception:
    session_visible = 0
else:
    session_visible = 1
emit(
    [{"op": "create_training", "base_model": "meta-llama/Llama-3.1-8B", "rank": 4}],
    {"quality_delta": 0.1 if session_visible else 0.0, "benchmark": "scope", "confidence": "high"},
)
"""

        result = SandboxedEvaluatorRunner().run(
            evaluator_source=source,
            artifact=b"private",
            artifact_type="dataset",
            session=session,
            budget_cap=10**18,
            reserve_price=10**17,
        )

        self.assertEqual(result.outcome, EvaluatorSandboxOutcome.PASS)
        self.assertEqual(result.metrics["quality_delta"], 0.0)
        self.assertNotIn("session", result.to_public_dict())
        self.assertNotIn("service_client", json.dumps(result.to_public_dict()))

    def test_rejects_escape_attempts_and_out_of_policy_plan(self):
        service_client = FakeTinkerServiceClient(api_key="sealed-upstream-key")

        rejected = SandboxedEvaluatorRunner().run(
            evaluator_source=b"print(open('/etc/passwd').read())",
            artifact=b"private",
            artifact_type="dataset",
            session=IsolatedTinkerSession(service_client, "deal-1"),
            budget_cap=10**18,
            reserve_price=10**17,
        )
        self.assertEqual(rejected.outcome, EvaluatorSandboxOutcome.POLICY_REJECTED)
        self.assertEqual(rejected.failure_code, SandboxFailureCode.POLICY_REJECTED)

        oversized_plan = b"""
emit(
    [{"op": "create_training", "base_model": "meta-llama/Llama-3.1-8B", "rank": 4},
     {"op": "train", "token_count": 999999}],
    {"quality_delta": 0.2, "benchmark": "bad", "confidence": "high"},
)
"""
        rejected_plan = SandboxedEvaluatorRunner(EvaluatorSandboxPolicy(max_train_tokens=32)).run(
            evaluator_source=oversized_plan,
            artifact=b"private",
            artifact_type="dataset",
            session=IsolatedTinkerSession(service_client, "deal-2"),
            budget_cap=10**18,
            reserve_price=10**17,
        )
        self.assertEqual(rejected_plan.outcome, EvaluatorSandboxOutcome.POLICY_REJECTED)
        self.assertEqual(rejected_plan.failure_code, SandboxFailureCode.POLICY_REJECTED)

    def test_timeout_is_bucketed_without_child_trace(self):
        result = SandboxedEvaluatorRunner(EvaluatorSandboxPolicy(timeout_seconds=0.1)).run(
            evaluator_source=b"while True:\n    pass",
            artifact=b"private",
            artifact_type="dataset",
            session=IsolatedTinkerSession(FakeTinkerServiceClient(), "deal-timeout"),
            budget_cap=10**18,
            reserve_price=10**17,
        )

        self.assertEqual(result.outcome, EvaluatorSandboxOutcome.TIMEOUT)
        self.assertEqual(result.failure_code, SandboxFailureCode.TIMEOUT)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.to_public_dict()["metrics"], {})


if __name__ == "__main__":
    unittest.main()
