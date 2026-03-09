"""Evaluator agent stub — exercises the IsolatedTinkerSession for testing.

In production, this is replaced with a real evaluation function that:
1. Parses the seller's artifact (dataset, training recipe, etc.)
2. Fine-tunes a model using the IsolatedTinkerSession
3. Benchmarks the fine-tuned model against the base model
4. Returns raw metrics (the control plane bounds the output)

The stub simulates this by returning synthetic metrics without
actually calling the Tinker API — useful for testing the full
deal lifecycle without consuming API credits.
"""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tinker_delegate.session import IsolatedTinkerSession


async def stub_evaluate(
    artifact: bytes,
    artifact_type: str,
    session: IsolatedTinkerSession,
    budget_cap: int,
    reserve_price: int,
) -> dict:
    """Stub evaluator — returns synthetic metrics based on artifact hash.

    Deterministic: same artifact always produces the same score.
    This lets us test the full pipeline without real Tinker API calls.
    """
    # Derive a deterministic "quality" from the artifact content
    h = hashlib.sha256(artifact).hexdigest()
    # Use first 8 hex chars as a seed for reproducibility
    seed = int(h[:8], 16)
    rng = random.Random(seed)

    # Simulate quality delta (0.0 to 0.30)
    quality_delta = rng.uniform(0.0, 0.30)

    # Simulate compute cost (small fraction of budget)
    compute_fraction = rng.uniform(0.01, 0.10)
    simulated_compute = int(budget_cap * compute_fraction)

    # Simulate confidence based on artifact size
    if len(artifact) > 10000:
        confidence = "high"
    elif len(artifact) > 1000:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "quality_delta": quality_delta,
        "benchmark": "stub-perplexity",
        "confidence": confidence,
        "methodology": (
            f"Stub evaluation on {len(artifact)} byte artifact. "
            f"Simulated {artifact_type} assessment with deterministic seed {h[:8]}. "
            f"No actual Tinker API calls made."
        ),
        "compute_cost_override": simulated_compute,
    }


async def sft_evaluate(
    artifact: bytes,
    artifact_type: str,
    session: IsolatedTinkerSession,
    budget_cap: int,
    reserve_price: int,
) -> dict:
    """Real SFT evaluation — trains on artifact, benchmarks result.

    This is the production evaluator for supervised fine-tuning datasets.
    Requires a real Tinker API key and the tinker SDK installed.

    Protocol:
    1. Parse artifact as JSONL dataset (instruction/response pairs)
    2. Tokenize with base model's tokenizer
    3. Create LoRA training run (rank=32, 8B model)
    4. Train for N steps (cross_entropy loss)
    5. Save checkpoint for sampling
    6. Benchmark: compute perplexity on held-out eval set
    7. Compare against base model perplexity
    8. Return quality delta = (base_ppl - tuned_ppl) / base_ppl
    """
    import json

    import tinker

    # 1. Parse dataset
    lines = artifact.decode("utf-8", errors="replace").strip().split("\n")
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return {
            "quality_delta": 0.0,
            "benchmark": "sft-perplexity",
            "confidence": "low",
            "methodology": "Empty or unparseable dataset — no training performed.",
        }

    # 2. Split into train/eval (90/10)
    split = max(1, len(records) * 9 // 10)
    train_data = records[:split]
    eval_data = records[split:] or records[:1]

    # 3. Create training run
    base_model = "meta-llama/Llama-3.1-8B-Instruct"
    tc = session.create_training(base_model=base_model, rank=32)
    tokenizer = session.get_tokenizer()

    # 4. Tokenize and train
    for step, record in enumerate(train_data[:200]):  # cap at 200 steps
        text = record.get("instruction", "") + "\n" + record.get("response", "")
        tokens = tokenizer.encode(text, max_length=2048, truncation=True)
        data = [{"input_ids": tokens}]

        session.forward_backward(data, loss_fn="cross_entropy")
        session.optim_step(tinker.OptimStepRequest(
            adam_params=tinker.AdamParams(lr=1e-4, beta1=0.9, beta2=0.999),
        ))

    # 5. Save for sampling
    checkpoint_path = session.save_for_sampling("eval-checkpoint", ttl_seconds=3600)
    sampler = session.create_sampler(checkpoint_path)

    # 6. Benchmark: perplexity on eval set
    eval_losses = []
    for record in eval_data[:20]:
        text = record.get("instruction", "") + "\n" + record.get("response", "")
        logprobs = sampler.compute_logprobs(text).result()
        avg_loss = -sum(lp for lp in logprobs if lp is not None) / max(len(logprobs), 1)
        eval_losses.append(avg_loss)

    tuned_ppl = sum(eval_losses) / max(len(eval_losses), 1)

    # 7. Base model comparison
    base_sampler = session._sc.create_sampling_client(base_model=base_model)
    base_losses = []
    for record in eval_data[:20]:
        text = record.get("instruction", "") + "\n" + record.get("response", "")
        logprobs = base_sampler.compute_logprobs(text).result()
        avg_loss = -sum(lp for lp in logprobs if lp is not None) / max(len(logprobs), 1)
        base_losses.append(avg_loss)

    base_ppl = sum(base_losses) / max(len(base_losses), 1)

    # 8. Quality delta
    if base_ppl > 0:
        quality_delta = (base_ppl - tuned_ppl) / base_ppl
    else:
        quality_delta = 0.0

    return {
        "quality_delta": max(0.0, quality_delta),
        "benchmark": "sft-perplexity",
        "confidence": "high" if len(train_data) >= 100 else "medium",
        "methodology": (
            f"LoRA fine-tune on {base_model} (rank=32, {min(len(train_data), 200)} steps). "
            f"Eval: perplexity on {len(eval_data[:20])} held-out samples. "
            f"Base PPL: {base_ppl:.2f}, Tuned PPL: {tuned_ppl:.2f}, "
            f"Delta: {quality_delta:.1%}."
        ),
    }
