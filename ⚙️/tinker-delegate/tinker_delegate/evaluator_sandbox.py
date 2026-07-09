"""Process-bound evaluator planner for local/source-modeled rooms.

Third-party evaluator code must not receive the raw ``IsolatedTinkerSession``.
This module runs simple evaluator code in a subprocess with a restricted
namespace. The child sees bounded context only and emits an allowlisted
capability plan. The parent validates and executes that plan through the real
session wrapper.

This is a local/source-real guardrail, not the final hostile-code production
sandbox. Production still needs CVM/container isolation and a real Tinker datum
adapter before arbitrary evaluator code can be accepted.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tinker_delegate.private_reward_sandbox import (
    SandboxFailureCode,
    _cap_text,
    _preflight_source,
)
from tinker_delegate.run_metadata_store import size_band, value_band
from tinker_delegate.session import IsolatedTinkerSession


class EvaluatorSandboxOutcome(str, Enum):
    PASS = "pass"
    POLICY_REJECTED = "policy_rejected"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class EvaluatorSandboxPolicy:
    timeout_seconds: float = 1.0
    max_source_bytes: int = 16_384
    max_output_bytes: int = 8_192
    max_plan_ops: int = 8
    max_train_tokens: int = 4096
    max_prompt_tokens: int = 512
    max_sample_tokens: int = 64
    allowed_base_models: tuple[str, ...] = ("meta-llama/Llama-3.1-8B",)
    timing_band_seconds: float = 0.1
    deterministic_seed: int = 0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_source_bytes <= 0:
            raise ValueError("max_source_bytes must be positive")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if self.max_plan_ops <= 0:
            raise ValueError("max_plan_ops must be positive")
        if self.max_train_tokens <= 0:
            raise ValueError("max_train_tokens must be positive")
        if self.max_prompt_tokens <= 0:
            raise ValueError("max_prompt_tokens must be positive")
        if self.max_sample_tokens <= 0:
            raise ValueError("max_sample_tokens must be positive")
        if self.timing_band_seconds <= 0:
            raise ValueError("timing_band_seconds must be positive")


@dataclass(frozen=True)
class EvaluatorSandboxResult:
    evaluator_hash: str
    outcome: EvaluatorSandboxOutcome
    failure_code: SandboxFailureCode
    metrics: dict[str, Any] = field(default_factory=dict)
    operation_counts: dict[str, int] = field(default_factory=dict)
    exit_code: int | None = None
    timed_out: bool = False
    elapsed_band_seconds: float = 0.0
    raw_secret_egress: bool = False

    @property
    def accepted(self) -> bool:
        return self.outcome == EvaluatorSandboxOutcome.PASS

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "surface": "sandboxed_evaluator",
            "evaluator_hash": self.evaluator_hash,
            "outcome": self.outcome.value,
            "failure_code": self.failure_code.value,
            "metrics": dict(self.metrics),
            "operation_counts": dict(self.operation_counts),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "elapsed_band_seconds": self.elapsed_band_seconds,
            "raw_session_returned": False,
            "raw_artifact_returned": False,
            "raw_checkpoint_path_returned": False,
            "raw_secret_egress": self.raw_secret_egress,
        }


@dataclass(frozen=True)
class _TokenPrompt:
    length: int

    def to_ints(self) -> list[int]:
        return [0] * self.length


@dataclass(frozen=True)
class _TokenDatum:
    model_input: _TokenPrompt


class SandboxedEvaluatorRunner:
    """Run evaluator code out-of-process and execute an allowlisted plan."""

    def __init__(self, policy: EvaluatorSandboxPolicy | None = None) -> None:
        self.policy = policy or EvaluatorSandboxPolicy()

    def run(
        self,
        *,
        evaluator_source: bytes,
        artifact: bytes,
        artifact_type: str,
        session: IsolatedTinkerSession,
        budget_cap: int,
        reserve_price: int,
    ) -> EvaluatorSandboxResult:
        started_at = time.monotonic()
        evaluator_hash = hashlib.sha256(evaluator_source).hexdigest()
        source = self._decode_source(evaluator_source)
        if source is None or len(evaluator_source) > self.policy.max_source_bytes:
            return self._reject(evaluator_hash, SandboxFailureCode.POLICY_REJECTED, started_at)
        preflight = _preflight_source(source)
        if preflight != SandboxFailureCode.NONE:
            return self._reject(evaluator_hash, preflight, started_at)

        child = self._run_child(
            source=source,
            context={
                "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                "artifact_size_band": size_band(len(artifact)),
                "artifact_type": artifact_type,
                "budget_cap_band": value_band(budget_cap),
                "reserve_price_band": value_band(reserve_price),
            },
            started_at=started_at,
        )
        if child.outcome != EvaluatorSandboxOutcome.PASS:
            return child

        try:
            plan = self._validate_plan(child.metrics.pop("_plan"))
            metrics = self._validate_metrics(child.metrics)
            operation_counts = self._execute_plan(plan, session)
        except Exception:
            return EvaluatorSandboxResult(
                evaluator_hash=evaluator_hash,
                outcome=EvaluatorSandboxOutcome.POLICY_REJECTED,
                failure_code=SandboxFailureCode.POLICY_REJECTED,
                exit_code=child.exit_code,
                elapsed_band_seconds=self._elapsed_band(started_at),
            )

        return EvaluatorSandboxResult(
            evaluator_hash=evaluator_hash,
            outcome=EvaluatorSandboxOutcome.PASS,
            failure_code=SandboxFailureCode.NONE,
            metrics=metrics,
            operation_counts=operation_counts,
            exit_code=child.exit_code,
            timed_out=False,
            elapsed_band_seconds=self._elapsed_band(started_at),
        )

    def _run_child(
        self,
        *,
        source: str,
        context: dict[str, Any],
        started_at: float,
    ) -> EvaluatorSandboxResult:
        request = json.dumps(
            {
                "source": source,
                "context": context,
                "seed": self.policy.deterministic_seed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            with tempfile.TemporaryDirectory(prefix="dnai-evaluator-") as scratch_dir:
                proc = subprocess.run(
                    [sys.executable, "-S", "-c", _EVALUATOR_WRAPPER],
                    input=request,
                    text=True,
                    cwd=scratch_dir,
                    env={
                        "PYTHONHASHSEED": str(self.policy.deterministic_seed),
                        "PYTHONIOENCODING": "utf-8",
                    },
                    capture_output=True,
                    timeout=self.policy.timeout_seconds,
                )
        except subprocess.TimeoutExpired:
            return EvaluatorSandboxResult(
                evaluator_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                outcome=EvaluatorSandboxOutcome.TIMEOUT,
                failure_code=SandboxFailureCode.TIMEOUT,
                exit_code=None,
                timed_out=True,
                elapsed_band_seconds=self._elapsed_band(started_at),
            )

        stdout, _truncated = _cap_text(proc.stdout, self.policy.max_output_bytes)
        if proc.returncode != 0:
            return EvaluatorSandboxResult(
                evaluator_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                outcome=EvaluatorSandboxOutcome.RUNTIME_ERROR,
                failure_code=SandboxFailureCode.RUNTIME_ERROR,
                exit_code=proc.returncode,
                elapsed_band_seconds=self._elapsed_band(started_at),
            )
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return EvaluatorSandboxResult(
                evaluator_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                outcome=EvaluatorSandboxOutcome.RUNTIME_ERROR,
                failure_code=SandboxFailureCode.RUNTIME_ERROR,
                exit_code=proc.returncode,
                elapsed_band_seconds=self._elapsed_band(started_at),
            )
        return EvaluatorSandboxResult(
            evaluator_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            outcome=EvaluatorSandboxOutcome.PASS,
            failure_code=SandboxFailureCode.NONE,
            metrics={
                "_plan": payload.get("plan"),
                **(payload.get("metrics") or {}),
            },
            exit_code=proc.returncode,
            elapsed_band_seconds=self._elapsed_band(started_at),
        )

    def _validate_plan(self, plan: Any) -> list[dict[str, Any]]:
        if not isinstance(plan, list) or len(plan) > self.policy.max_plan_ops:
            raise ValueError("invalid evaluator plan")
        validated: list[dict[str, Any]] = []
        for raw_op in plan:
            if not isinstance(raw_op, dict):
                raise ValueError("invalid evaluator plan op")
            op = str(raw_op.get("op", ""))
            if op == "create_training":
                base_model = str(raw_op.get("base_model", ""))
                if base_model not in self.policy.allowed_base_models:
                    raise ValueError("base model is not allowed")
                rank = int(raw_op.get("rank", 4))
                if rank <= 0 or rank > 64:
                    raise ValueError("rank is out of bounds")
                validated.append({"op": op, "base_model": base_model, "rank": rank})
            elif op == "train":
                token_count = int(raw_op.get("token_count", 0))
                if token_count <= 0 or token_count > self.policy.max_train_tokens:
                    raise ValueError("train token count is out of bounds")
                validated.append({"op": op, "token_count": token_count})
            elif op == "optim_step":
                validated.append({"op": op})
            elif op == "sample":
                prompt_tokens = int(raw_op.get("prompt_tokens", 0))
                max_tokens = int(raw_op.get("max_tokens", 0))
                if prompt_tokens <= 0 or prompt_tokens > self.policy.max_prompt_tokens:
                    raise ValueError("prompt token count is out of bounds")
                if max_tokens <= 0 or max_tokens > self.policy.max_sample_tokens:
                    raise ValueError("sample token count is out of bounds")
                validated.append({"op": op, "prompt_tokens": prompt_tokens, "max_tokens": max_tokens})
            else:
                raise ValueError("unsupported evaluator plan op")
        return validated

    @staticmethod
    def _validate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        quality_delta = float(metrics.get("quality_delta", 0.0))
        if quality_delta < 0.0 or quality_delta > 1.0:
            raise ValueError("quality_delta out of bounds")
        benchmark = _safe_label(metrics.get("benchmark", "sandbox"))
        confidence = str(metrics.get("confidence", "medium")).lower()
        if confidence not in ("low", "medium", "high"):
            confidence = "medium"
        methodology = _safe_text(metrics.get("methodology", "sandboxed evaluator capability plan"))
        return {
            "quality_delta": quality_delta,
            "benchmark": benchmark,
            "confidence": confidence,
            "methodology": methodology,
        }

    @staticmethod
    def _execute_plan(plan: list[dict[str, Any]], session: IsolatedTinkerSession) -> dict[str, int]:
        counts: dict[str, int] = {}
        sampler = None
        for operation in plan:
            op = operation["op"]
            counts[op] = counts.get(op, 0) + 1
            if op == "create_training":
                session.create_training(
                    operation["base_model"],
                    rank=operation["rank"],
                    user_metadata={"surface": "sandboxed_evaluator", "mode": "capability_plan"},
                )
            elif op == "train":
                session.forward_backward([_TokenDatum(_TokenPrompt(operation["token_count"]))]).result()
            elif op == "optim_step":
                session.optim_step({"learning_rate": 0.0}).result()
            elif op == "sample":
                if sampler is None:
                    sampler = session.save_and_get_sampler("sandboxed-eval")
                session.sample(
                    sampler,
                    _TokenPrompt(operation["prompt_tokens"]),
                    {"max_tokens": operation["max_tokens"], "temperature": 0.0},
                    num_samples=1,
                )
        return counts

    @staticmethod
    def _decode_source(evaluator_source: bytes) -> str | None:
        try:
            return evaluator_source.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _reject(
        self,
        evaluator_hash: str,
        failure_code: SandboxFailureCode,
        started_at: float,
    ) -> EvaluatorSandboxResult:
        return EvaluatorSandboxResult(
            evaluator_hash=evaluator_hash,
            outcome=EvaluatorSandboxOutcome.POLICY_REJECTED,
            failure_code=failure_code,
            exit_code=None,
            elapsed_band_seconds=self._elapsed_band(started_at),
        )

    def _elapsed_band(self, started_at: float) -> float:
        granularity = self.policy.timing_band_seconds
        elapsed = max(0.0, time.monotonic() - started_at)
        return int(elapsed / granularity) * granularity


def _safe_label(value: Any) -> str:
    text = str(value).strip().lower()
    if not text:
        return "sandbox"
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_.:-"
    clipped = "".join(char for char in text[:64] if char in allowed)
    return clipped or "sandbox"


def _safe_text(value: Any) -> str:
    text = str(value).strip()
    safe = "".join(char for char in text[:160] if char.isalnum() or char in " ._:/-")
    return safe or "sandboxed evaluator capability plan"


_EVALUATOR_WRAPPER = r"""
import json
import math
import random
import sys

request = json.loads(sys.stdin.read())
context = dict(request.get("context") or {})
random.seed(int(request.get("seed", 0)))
plan = []
metrics = {}

def emit(evaluator_plan, evaluator_metrics):
    global plan, metrics
    plan = evaluator_plan
    metrics = evaluator_metrics

def disabled(*_args, **_kwargs):
    raise PermissionError("sandbox disabled this operation")

safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
    "PermissionError": PermissionError,
    "open": disabled,
    "__import__": disabled,
}

namespace = {
    "__builtins__": safe_builtins,
    "context": context,
    "emit": emit,
    "math": math,
    "random": random,
}

exec(compile(str(request.get("source") or ""), "<sandboxed-evaluator>", "exec"), namespace, namespace)
sys.stdout.write(json.dumps({"plan": plan, "metrics": metrics}, sort_keys=True, separators=(",", ":")))
"""
