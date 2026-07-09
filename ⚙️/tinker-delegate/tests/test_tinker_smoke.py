import json
import sys
import types
import unittest
from dataclasses import dataclass
from unittest.mock import patch


class Future:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value


@dataclass
class Info:
    training_run_id: str


@dataclass
class PathResponse:
    path: str


@dataclass
class Checkpoint:
    checkpoint_id: str


class ModelInput:
    def __init__(self, token_ids):
        self.token_ids = list(token_ids)
        self.length = len(self.token_ids)

    @classmethod
    def from_ints(cls, token_ids):
        return cls(token_ids)


class TensorData:
    def __init__(self, data, dtype, shape):
        self.data = data
        self.dtype = dtype
        self.shape = shape


class Datum:
    def __init__(self, model_input, loss_fn_inputs):
        self.model_input = model_input
        self.loss_fn_inputs = loss_fn_inputs


@dataclass
class AdamParams:
    learning_rate: float


@dataclass
class SamplingParams:
    max_tokens: int
    temperature: float


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        base = [ord(ch) % 251 for ch in text]
        return ([1] if add_special_tokens else []) + base


class FakeTrainingClient:
    def __init__(self, run_id):
        self.run_id = run_id
        self.forward_backward_calls = []
        self.optim_step_calls = []
        self.save_calls = []

    def get_info(self):
        return Info(training_run_id=self.run_id)

    def get_tokenizer(self):
        return FakeTokenizer()

    def forward_backward(self, data, loss_fn, loss_fn_config=None):
        self.forward_backward_calls.append((data, loss_fn, loss_fn_config))
        return Future({"ok": True})

    def optim_step(self, adam_params):
        self.optim_step_calls.append(adam_params)
        return Future({"ok": True})

    def save_weights_for_sampler(self, name, ttl_seconds):
        self.save_calls.append((name, ttl_seconds))
        return Future(PathResponse(f"tinker://{self.run_id}/sampler/{name}"))


class FakeSampler:
    def __init__(self):
        self.sample_calls = []

    def sample(self, prompt, sampling_params, num_samples=1):
        self.sample_calls.append((prompt, sampling_params, num_samples))
        return Future({"raw_text": "this sample must never leave"})


class FakeRestClient:
    def __init__(self):
        self.deleted = []

    def list_checkpoints(self, run_id):
        return Future([Checkpoint("cp-secret")])

    def delete_checkpoint(self, run_id, checkpoint_id):
        self.deleted.append((run_id, checkpoint_id))
        return Future({"deleted": True})


class FakeServiceClient:
    last_instance = None

    def __init__(self, api_key):
        self.api_key = api_key
        self.training_client = FakeTrainingClient("run-secret")
        self.sampling_paths = []
        self.rest_client = FakeRestClient()
        FakeServiceClient.last_instance = self

    def create_lora_training_client(self, **kwargs):
        self.training_kwargs = kwargs
        return self.training_client

    def create_sampling_client(self, model_path=None, base_model=None):
        self.sampling_paths.append(model_path or base_model)
        return FakeSampler()

    def create_rest_client(self):
        return self.rest_client


FAKE_TINKER = types.SimpleNamespace(
    ServiceClient=FakeServiceClient,
    TrainingClient=object,
    SamplingClient=object,
    Datum=Datum,
    ModelInput=ModelInput,
    TensorData=TensorData,
    AdamParams=AdamParams,
    SamplingParams=SamplingParams,
)
sys.modules["tinker"] = FAKE_TINKER

from tinker_delegate.config import Settings  # noqa: E402
from tinker_delegate import session as session_module  # noqa: E402
from tinker_delegate.tinker_encumbrance import TinkerEncumbrancePolicyResult  # noqa: E402
from tinker_delegate.tinker_smoke import (  # noqa: E402
    TinkerSmokeRequest,
    run_tinker_sdk_smoke,
)


def _allowed_policy():
    return TinkerEncumbrancePolicyResult(
        checked=True,
        allowed=True,
        reason="allowed",
        operation="spend_tinker_compute",
        operation_kind=2,
        compose_hash="0x" + "11" * 32,
        compose_approved=True,
        amount_wei=50_000_000_000_000_000,
        max_amount_wei=10_000_000_000_000_000_000,
        limit_kind="spend",
    )


class TinkerSmokeTest(unittest.TestCase):
    def test_smoke_runs_tiny_training_sampling_and_cleanup_with_bounded_output(self):
        with (
            patch.object(session_module, "tinker", FAKE_TINKER),
            patch("tinker_delegate.tinker_smoke.resolve_api_key", return_value="tml-secret-value"),
            patch("tinker_delegate.tinker_smoke.preflight_tinker_operation", return_value=_allowed_policy()),
        ):
            result = run_tinker_sdk_smoke(
                Settings(real_sdk_max_usd=0.05),
                TinkerSmokeRequest(deal_id="deal-secret", max_usd=0.05, ttl_seconds=3600),
            )

        rendered = json.dumps(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(result["furthest_stage"], "cleanup_completed")
        self.assertTrue(result["sample_observed"])
        self.assertFalse(result["sample_output_returned"])
        self.assertTrue(result["cleanup"]["success"])
        self.assertEqual(result["cleanup"]["listed_checkpoint_count"], 1)
        self.assertEqual(result["cleanup"]["deleted_checkpoint_count"], 1)
        self.assertFalse(result["raw_secret_egress"])
        self.assertNotIn("tml-secret-value", rendered)
        self.assertNotIn("deal-secret", rendered)
        self.assertNotIn("run-secret", rendered)
        self.assertNotIn("cp-secret", rendered)
        self.assertNotIn("tinker://", rendered)
        self.assertNotIn("this sample must never leave", rendered)

        service_client = FakeServiceClient.last_instance
        self.assertEqual(service_client.training_kwargs["base_model"], "meta-llama/Llama-3.2-1B")
        self.assertEqual(service_client.training_kwargs["rank"], 4)
        self.assertEqual(service_client.training_client.save_calls, [("budgeted-smoke", 3600)])
        self.assertEqual(service_client.rest_client.deleted, [("run-secret", "cp-secret")])

    def test_smoke_fails_closed_when_encumbrance_denies(self):
        denied = TinkerEncumbrancePolicyResult(
            checked=True,
            allowed=False,
            reason="compose_hash_not_approved",
            operation="spend_tinker_compute",
            operation_kind=2,
        )
        with (
            patch("tinker_delegate.tinker_smoke.resolve_api_key", return_value="tml-secret-value") as resolve_key,
            patch("tinker_delegate.tinker_smoke.preflight_tinker_operation", return_value=denied),
        ):
            result = run_tinker_sdk_smoke(
                Settings(),
                TinkerSmokeRequest(max_usd=0.05, require_encumbrance=True),
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["outcome"], "policy_denied")
        self.assertEqual(result["furthest_stage"], "policy_checked")
        self.assertEqual(result["error_kind"], "compose_hash_not_approved")
        resolve_key.assert_not_called()

    def test_smoke_fails_closed_when_policy_check_raises(self):
        with (
            patch("tinker_delegate.tinker_smoke.resolve_api_key", return_value="tml-secret-value") as resolve_key,
            patch("tinker_delegate.tinker_smoke.preflight_tinker_operation", side_effect=RuntimeError("rpc exploded")),
        ):
            result = run_tinker_sdk_smoke(
                Settings(),
                TinkerSmokeRequest(max_usd=0.05, require_encumbrance=True),
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["outcome"], "policy_check_failed")
        self.assertEqual(result["furthest_stage"], "policy_checked")
        self.assertEqual(result["policy"]["reason"], "policy_check_exception")
        self.assertEqual(result["error_kind"], "RuntimeError")
        self.assertNotIn("rpc exploded", json.dumps(result))
        self.assertFalse(result["raw_secret_egress"])
        resolve_key.assert_not_called()

    def test_smoke_rejects_overlarge_budget_before_sdk_call(self):
        with self.assertRaisesRegex(ValueError, "<= 0.5"):
            run_tinker_sdk_smoke(Settings(), TinkerSmokeRequest(max_usd=0.51))


if __name__ == "__main__":
    unittest.main()
