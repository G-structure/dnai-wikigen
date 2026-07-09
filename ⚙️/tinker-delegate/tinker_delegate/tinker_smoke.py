"""Bounded real-Tinker SDK smoke test for the funded TEE account."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from typing import Any

from tinker_delegate.api_key_store import resolve_api_key
from tinker_delegate.redaction import redact_text
from tinker_delegate.run_metadata_store import stable_hash, value_band
from tinker_delegate.session import DEFAULT_TTL, IsolatedTinkerSession
from tinker_delegate.tinker_encumbrance import (
    TinkerOperationKind,
    preflight_tinker_operation,
)


HARD_SMOKE_MAX_USD = 0.50
DEFAULT_SMOKE_MAX_USD = 0.05


@dataclass(frozen=True)
class TinkerSmokeRequest:
    deal_id: str = ""
    max_usd: float | None = None
    model: str = ""
    rank: int | None = None
    ttl_seconds: int = DEFAULT_TTL
    compose_hash: str = ""
    require_encumbrance: bool = False


def run_tinker_sdk_smoke(settings, request: TinkerSmokeRequest | None = None) -> dict[str, Any]:
    """Run one tiny training/checkpoint/sample/cleanup path through Tinker.

    The returned receipt is intentionally bounded: no API key, prompt tokens,
    sample text, raw checkpoint path, or raw training-run id leaves the process.
    """

    request = request or TinkerSmokeRequest()
    issued_at = int(time.time())
    deal_id = request.deal_id or f"tinker-smoke-{uuid.uuid4()}"
    max_usd = _resolve_max_usd(settings, request.max_usd)
    model = request.model or getattr(settings, "real_sdk_model", "")
    rank = int(request.rank if request.rank is not None else getattr(settings, "real_sdk_rank", 4))
    ttl_seconds = int(request.ttl_seconds or DEFAULT_TTL)

    try:
        policy = preflight_tinker_operation(
            settings,
            operation_kind=TinkerOperationKind.SPEND_TINKER_COMPUTE,
            amount_dollars=max_usd,
            compose_hash=request.compose_hash,
            required=request.require_encumbrance,
        )
    except Exception as exc:
        return _base_receipt(
            issued_at=issued_at,
            deal_id=deal_id,
            model=model,
            rank=rank,
            max_usd=max_usd,
            success=False,
            outcome="policy_check_failed",
            furthest_stage="policy_checked",
            policy={
                "checked": False,
                "allowed": False,
                "reason": "policy_check_exception",
                "operation": TinkerOperationKind.SPEND_TINKER_COMPUTE.name.lower(),
                "operation_kind": int(TinkerOperationKind.SPEND_TINKER_COMPUTE),
                "raw_secret_egress": False,
            },
            error_kind=exc.__class__.__name__,
            bounded_message="policy_check_failed",
        )
    if not policy.allowed:
        return _base_receipt(
            issued_at=issued_at,
            deal_id=deal_id,
            model=model,
            rank=rank,
            max_usd=max_usd,
            success=False,
            outcome="policy_denied",
            furthest_stage="policy_checked",
            policy=policy.to_public_dict(),
            error_kind=policy.reason,
        )

    api_key = resolve_api_key(settings)
    if not api_key:
        return _base_receipt(
            issued_at=issued_at,
            deal_id=deal_id,
            model=model,
            rank=rank,
            max_usd=max_usd,
            success=False,
            outcome="api_key_missing",
            furthest_stage="policy_checked",
            policy=policy.to_public_dict(),
            error_kind="api_key_missing",
        )

    session: IsolatedTinkerSession | None = None
    furthest_stage = "api_key_loaded"
    checkpoint_path = ""
    cleanup = None
    try:
        import tinker

        service_client = tinker.ServiceClient(api_key=api_key)
        session = IsolatedTinkerSession(service_client, deal_id)

        session.create_training(base_model=model, rank=rank)
        furthest_stage = "training_created"
        tokenizer = session.get_tokenizer()

        prompt_tokens = tokenizer.encode("Question: What is 2 + 2?\nAnswer:", add_special_tokens=True)
        completion_tokens = tokenizer.encode(" 4", add_special_tokens=False)
        all_tokens = prompt_tokens + completion_tokens
        if len(all_tokens) < 4:
            raise RuntimeError("tokenizer returned too few smoke tokens")

        input_tokens = all_tokens[:-1]
        target_tokens = all_tokens[1:]
        weights = [0.0] * max(0, len(prompt_tokens) - 1) + [1.0] * len(completion_tokens)
        weights = weights[: len(target_tokens)]

        datum = tinker.Datum(
            model_input=tinker.ModelInput.from_ints(input_tokens),
            loss_fn_inputs={
                "weights": tinker.TensorData(
                    data=weights,
                    dtype="float32",
                    shape=[len(weights)],
                ),
                "target_tokens": tinker.TensorData(
                    data=target_tokens,
                    dtype="int64",
                    shape=[len(target_tokens)],
                ),
            },
        )

        _wait(session.forward_backward([datum], loss_fn="cross_entropy"))
        furthest_stage = "forward_backward_completed"
        _enforce_meter_cap(session, max_usd)
        _wait(session.optim_step(tinker.AdamParams(learning_rate=1e-4)))
        furthest_stage = "optimizer_step_completed"

        checkpoint_path = session.save_for_sampling("budgeted-smoke", ttl_seconds=ttl_seconds)
        furthest_stage = "checkpoint_saved"
        sampler = session.create_sampler(checkpoint_path)

        sampling_params = tinker.SamplingParams(max_tokens=1, temperature=0)
        sample_result = _wait(
            session.sample(
                sampler,
                tinker.ModelInput.from_ints(prompt_tokens),
                sampling_params=sampling_params,
                num_samples=1,
            )
        )
        furthest_stage = "sample_completed"
        _enforce_meter_cap(session, max_usd)

        cleanup = session.cleanup()
        furthest_stage = "cleanup_completed"
        return _success_receipt(
            issued_at=issued_at,
            deal_id=deal_id,
            model=model,
            rank=rank,
            max_usd=max_usd,
            policy=policy.to_public_dict(),
            session=session,
            checkpoint_path=checkpoint_path,
            cleanup=cleanup,
            sample_observed=sample_result is not None,
        )
    except Exception as exc:
        cleanup_error_kind = ""
        if session is not None:
            try:
                cleanup = session.cleanup()
            except Exception as cleanup_exc:  # pragma: no cover - defensive.
                cleanup_error_kind = cleanup_exc.__class__.__name__
        return _base_receipt(
            issued_at=issued_at,
            deal_id=deal_id,
            model=model,
            rank=rank,
            max_usd=max_usd,
            success=False,
            outcome="smoke_failed",
            furthest_stage=furthest_stage,
            policy=policy.to_public_dict(),
            error_kind=exc.__class__.__name__,
            bounded_message=redact_text(exc.__class__.__name__),
            session=session,
            checkpoint_path=checkpoint_path,
            cleanup=cleanup,
            cleanup_error_kind=cleanup_error_kind,
        )


def _resolve_max_usd(settings, requested: float | None) -> float:
    value = requested if requested is not None else getattr(settings, "real_sdk_max_usd", DEFAULT_SMOKE_MAX_USD)
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("max_usd must be finite and positive")
    if value > HARD_SMOKE_MAX_USD:
        raise ValueError(f"max_usd must be <= {HARD_SMOKE_MAX_USD}")
    return value


def _wait(value):
    if hasattr(value, "result"):
        return value.result()
    return value


def _enforce_meter_cap(session: IsolatedTinkerSession, max_usd: float) -> None:
    if session.meter.total_cost_usd > max_usd:
        raise RuntimeError("tinker smoke meter cap exceeded")


def _success_receipt(
    *,
    issued_at: int,
    deal_id: str,
    model: str,
    rank: int,
    max_usd: float,
    policy: dict[str, Any],
    session: IsolatedTinkerSession,
    checkpoint_path: str,
    cleanup,
    sample_observed: bool,
) -> dict[str, Any]:
    return _base_receipt(
        issued_at=issued_at,
        deal_id=deal_id,
        model=model,
        rank=rank,
        max_usd=max_usd,
        success=True,
        outcome="success",
        furthest_stage="cleanup_completed",
        policy=policy,
        session=session,
        checkpoint_path=checkpoint_path,
        cleanup=cleanup,
        sample_observed=sample_observed,
    )


def _base_receipt(
    *,
    issued_at: int,
    deal_id: str,
    model: str,
    rank: int,
    max_usd: float,
    success: bool,
    outcome: str,
    furthest_stage: str,
    policy: dict[str, Any],
    error_kind: str = "",
    bounded_message: str = "",
    session: IsolatedTinkerSession | None = None,
    checkpoint_path: str = "",
    cleanup=None,
    cleanup_error_kind: str = "",
    sample_observed: bool = False,
) -> dict[str, Any]:
    cleanup_public = _bounded_cleanup(cleanup)
    spent_usd = float(session.meter.total_cost_usd) if session is not None else 0.0
    return {
        "surface": "tinker_sdk_smoke",
        "success": bool(success),
        "outcome": outcome,
        "furthest_stage": furthest_stage,
        "issued_at": issued_at,
        "deal_hash": stable_hash(deal_id, prefix="deal"),
        "training_run_id_hash": stable_hash(
            session.training_run_id if session is not None else None,
            prefix="training_run_id",
        ),
        "checkpoint_path_hash": stable_hash(checkpoint_path or None, prefix="checkpoint_path"),
        "model_hash": stable_hash(model, prefix="tinker_model"),
        "rank": rank,
        "max_usd_band": _usd_band(max_usd),
        "metered_cost_band": _usd_band(spent_usd),
        "compute_cost_band": value_band(session.compute_cost_wei if session is not None else 0),
        "fee_band": value_band(session.fee_wei if session is not None else 0),
        "sample_observed": bool(sample_observed),
        "sample_output_returned": False,
        "cleanup": cleanup_public,
        "cleanup_error_kind": cleanup_error_kind,
        "policy": policy,
        "error_kind": error_kind,
        "bounded_message": bounded_message or outcome,
        "raw_secret_egress": False,
    }


def _bounded_cleanup(cleanup) -> dict[str, Any]:
    if cleanup is None:
        return {
            "success": False,
            "listed_checkpoint_count": 0,
            "deleted_checkpoint_count": 0,
            "failed_checkpoint_count": 0,
            "delete_attempts": 0,
            "checkpoint_ids_hash": "",
            "training_run_id_hash": "",
            "error_type": "",
        }
    return {
        "success": bool(cleanup.success),
        "listed_checkpoint_count": cleanup.listed_checkpoint_count,
        "deleted_checkpoint_count": cleanup.deleted_checkpoint_count,
        "failed_checkpoint_count": cleanup.failed_checkpoint_count,
        "delete_attempts": cleanup.delete_attempts,
        "checkpoint_ids_hash": cleanup.checkpoint_ids_hash,
        "training_run_id_hash": stable_hash(cleanup.training_run_id, prefix="training_run_id"),
        "error_type": cleanup.error_type,
    }


def _usd_band(value: float) -> str:
    if value <= 0:
        return "zero"
    if value <= 0.01:
        return "<=0.01"
    if value <= 0.05:
        return "<=0.05"
    if value <= 0.10:
        return "<=0.10"
    if value <= 0.50:
        return "<=0.50"
    if value <= 1.0:
        return "<=1.00"
    return ">1.00"
