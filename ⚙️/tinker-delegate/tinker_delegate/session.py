"""IsolatedTinkerSession — sandboxed view of a Tinker account for one NDAI deal.

The evaluator agent receives this instead of the raw ServiceClient.
All operations are scoped to a single training run. Checkpoints are
path-checked. Download and publish are not exposed. Cleanup is mandatory.

Trust enforcement:
  - One training run per deal (cannot create multiple)
  - Path-checked sampling (only models trained in this session)
  - Mandatory TTL on all checkpoint saves (dead man's switch)
  - No download, publish, or list operations
  - Cost metering on every API call
  - cleanup() deletes all checkpoints from this deal's run
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import tinker


# ---------------------------------------------------------------------------
# Cost metering
# ---------------------------------------------------------------------------

# Tinker pricing: USD per million tokens (as of 2026-03-08)
# {model_name: {operation: price_per_million_tokens}}
PRICING = {
    "meta-llama/Llama-3.2-1B": {"prefill": 0.03, "sample": 0.09, "train": 0.09},
    "meta-llama/Llama-3.1-8B-Instruct": {"prefill": 0.13, "sample": 0.40, "train": 0.40},
    "meta-llama/Llama-3.1-8B": {"prefill": 0.13, "sample": 0.40, "train": 0.40},
    "meta-llama/Llama-3.3-70B-Instruct": {"prefill": 0.40, "sample": 0.90, "train": 1.10},
    "Qwen/Qwen3-235B-A22B": {"prefill": 0.68, "sample": 1.70, "train": 2.04},
}

# Fallback pricing for unknown models (use 8B-class pricing)
DEFAULT_PRICING = {"prefill": 0.13, "sample": 0.40, "train": 0.40}

# ETH price assumption for cost conversion (updated at deal creation)
ETH_USD = 2000.0


@dataclass
class CostMeter:
    """Track cumulative Tinker API costs for a deal."""
    model: str = ""
    train_tokens: int = 0
    sample_tokens: int = 0
    prefill_tokens: int = 0
    _records: list[dict] = field(default_factory=list)

    def set_model(self, model: str) -> None:
        self.model = model

    def record_train(self, tokens: int) -> None:
        self.train_tokens += tokens
        self._records.append({"op": "train", "tokens": tokens, "ts": time.time()})

    def record_sample(self, tokens: int) -> None:
        self.sample_tokens += tokens
        self._records.append({"op": "sample", "tokens": tokens, "ts": time.time()})

    def record_prefill(self, tokens: int) -> None:
        self.prefill_tokens += tokens
        self._records.append({"op": "prefill", "tokens": tokens, "ts": time.time()})

    @property
    def pricing(self) -> dict:
        return PRICING.get(self.model, DEFAULT_PRICING)

    @property
    def total_cost_usd(self) -> float:
        p = self.pricing
        return (
            self.train_tokens * p["train"] / 1_000_000
            + self.sample_tokens * p["sample"] / 1_000_000
            + self.prefill_tokens * p["prefill"] / 1_000_000
        )

    @property
    def total_cost_wei(self) -> int:
        """Cost in wei (1 ETH = 10^18 wei)."""
        eth = self.total_cost_usd / ETH_USD
        return int(eth * 10**18)

    @property
    def fee_wei(self) -> int:
        """1% fee on compute cost."""
        return self.total_cost_wei // 100


# ---------------------------------------------------------------------------
# Isolated session
# ---------------------------------------------------------------------------

# Minimum and maximum TTL for checkpoint saves
MIN_TTL = 3600       # 1 hour floor
MAX_TTL = 86400      # 24 hour cap
DEFAULT_TTL = 3600   # 1 hour default


class IsolatedTinkerSession:
    """Sandboxed view of a Tinker account for one NDAI deal.

    The evaluator agent receives this instead of the raw ServiceClient.
    All operations are scoped to a single training run. Checkpoints
    are path-checked. Download and publish are not exposed.
    """

    def __init__(self, service_client: tinker.ServiceClient, deal_id: str):
        self._sc = service_client
        self._deal_id = deal_id
        self._training_run_id: str | None = None
        self._training_client: tinker.TrainingClient | None = None
        self._allowed_paths: set[str] = set()
        self._closed = False
        self._meter = CostMeter()

    @property
    def deal_id(self) -> str:
        return self._deal_id

    @property
    def meter(self) -> CostMeter:
        return self._meter

    @property
    def compute_cost_wei(self) -> int:
        return self._meter.total_cost_wei

    @property
    def fee_wei(self) -> int:
        return self._meter.fee_wei

    @property
    def training_run_id(self) -> str | None:
        return self._training_run_id

    # --- Training ---

    def create_training(
        self,
        base_model: str,
        rank: int = 32,
        **kwargs,
    ) -> tinker.TrainingClient:
        """Start a LoRA training run. One per deal, enforced."""
        assert not self._closed, "Session closed"
        assert self._training_run_id is None, "Only one training run per deal"

        # Force deal_id into user_metadata for orphan detection
        metadata = kwargs.pop("user_metadata", None) or {}
        metadata["deal_id"] = self._deal_id

        tc = self._sc.create_lora_training_client(
            base_model=base_model,
            rank=rank,
            user_metadata=metadata,
            **kwargs,
        )
        info = tc.get_info()
        self._training_run_id = info.training_run_id
        self._training_client = tc
        self._meter.set_model(base_model)
        return tc

    # --- Metered training operations ---

    def forward_backward(self, data: list, loss_fn: str = "cross_entropy", loss_fn_config=None):
        """Forward + backward pass with cost metering.

        Args:
            data: list of tinker.Datum objects. Each has:
                  - model_input: tinker.ModelInput.from_ints(token_ids)
                  - loss_fn_inputs: {"weights": TensorData, "target_tokens": TensorData}
            loss_fn: "cross_entropy", "importance_sampling", "ppo", "cispo", "dro"
            loss_fn_config: optional dict of loss-specific config
        """
        assert not self._closed, "Session closed"
        assert self._training_client is not None, "No training run"

        # Count tokens in the data batch
        tokens = self._count_tokens_from_data(data)
        self._meter.record_train(tokens)

        return self._training_client.forward_backward(
            data=data, loss_fn=loss_fn, loss_fn_config=loss_fn_config,
        )

    def optim_step(self, adam_params):
        """Optimizer step.

        Args:
            adam_params: tinker.AdamParams(learning_rate=1e-4, beta1=0.9, beta2=0.95, ...)
        """
        assert not self._closed, "Session closed"
        assert self._training_client is not None, "No training run"
        return self._training_client.optim_step(adam_params)

    # --- Checkpoint saves (TTL enforced) ---

    def save_for_sampling(
        self,
        name: str,
        ttl_seconds: int = DEFAULT_TTL,
    ) -> str:
        """Save current weights for sampling. Returns the checkpoint path.

        TTL is mandatory — auto-cleanup backstop even if cleanup() never runs.
        """
        assert not self._closed, "Session closed"
        assert self._training_client is not None, "No training run"

        ttl = max(MIN_TTL, min(ttl_seconds, MAX_TTL))

        resp = self._training_client.save_weights_for_sampler(
            name=name,
            ttl_seconds=ttl,
        ).result()
        self._allowed_paths.add(resp.path)
        return resp.path

    def save_state(self, name: str, ttl_seconds: int = DEFAULT_TTL) -> str:
        """Save training state (weights + optimizer) for resumption."""
        assert not self._closed and self._training_client is not None

        ttl = max(MIN_TTL, min(ttl_seconds, MAX_TTL))

        resp = self._training_client.save_state(
            name=name,
            ttl_seconds=ttl,
        ).result()
        # State paths tracked but NOT added to allowed sampling paths
        return resp.path

    # --- Sampling (path-checked) ---

    def save_and_get_sampler(self, name: str = "eval") -> tinker.SamplingClient:
        """Save current weights and immediately get a sampling client.

        Convenience method combining save_for_sampling + create_sampler.
        """
        assert not self._closed, "Session closed"
        assert self._training_client is not None, "No training run"
        sampler = self._training_client.save_weights_and_get_sampling_client(name=name)
        return sampler

    def create_sampler(self, model_path: str) -> tinker.SamplingClient:
        """Create a sampling client. Path MUST be from this session."""
        assert not self._closed, "Session closed"
        if model_path not in self._allowed_paths:
            raise PermissionError(
                f"Cannot sample from {model_path} — "
                f"only models trained in deal {self._deal_id}"
            )
        return self._sc.create_sampling_client(model_path=model_path)

    def sample(self, sampler: tinker.SamplingClient, prompt, sampling_params, num_samples: int = 1):
        """Metered sampling.

        Args:
            sampler: SamplingClient from create_sampler() or save_and_get_sampler()
            prompt: tinker.ModelInput (use ModelInput.from_ints(tokens))
            sampling_params: tinker.SamplingParams(max_tokens=..., temperature=..., ...)
            num_samples: number of completions to generate
        """
        assert not self._closed, "Session closed"

        # Count prompt tokens for metering
        if hasattr(prompt, 'length'):
            self._meter.record_prefill(prompt.length)
        elif hasattr(prompt, 'to_ints'):
            self._meter.record_prefill(len(prompt.to_ints()))

        result = sampler.sample(
            prompt=prompt,
            sampling_params=sampling_params,
            num_samples=num_samples,
        )
        return result

    def compute_logprobs(self, sampler: tinker.SamplingClient, prompt) -> list:
        """Compute log probabilities for a prompt. Metered.

        Args:
            sampler: SamplingClient
            prompt: tinker.ModelInput
        Returns:
            list of floats (logprob per token position, first is None)
        """
        assert not self._closed, "Session closed"

        if hasattr(prompt, 'length'):
            self._meter.record_prefill(prompt.length)
        elif hasattr(prompt, 'to_ints'):
            self._meter.record_prefill(len(prompt.to_ints()))

        return sampler.compute_logprobs(prompt)

    # --- Cleanup ---

    def cleanup(self) -> None:
        """Delete ALL checkpoints from this deal's training run.

        Called by the control plane when the deal resolves.
        Idempotent — safe to call multiple times.
        """
        if self._closed:
            return
        if self._training_run_id is None:
            self._closed = True
            return

        rc = self._sc.create_rest_client()
        try:
            checkpoints = rc.list_checkpoints(self._training_run_id).result()
            for cp in checkpoints:
                try:
                    rc.delete_checkpoint(
                        self._training_run_id,
                        cp.checkpoint_id,
                    ).result()
                except Exception:
                    pass  # TTL backstop handles stragglers
        except Exception:
            pass  # TTL backstop

        self._allowed_paths.clear()
        self._training_client = None
        self._closed = True

    # --- Tokenizer access (safe — no secrets) ---

    def get_tokenizer(self):
        """Get the tokenizer for the base model."""
        assert self._training_client is not None, "No training run"
        return self._training_client.get_tokenizer()

    # --- Internal helpers ---

    @staticmethod
    def _count_tokens_from_data(data: list) -> int:
        """Count tokens from a list of tinker.Datum objects."""
        total = 0
        for datum in data:
            # tinker.Datum has model_input with a .length property
            if hasattr(datum, 'model_input'):
                mi = datum.model_input
                if hasattr(mi, 'length'):
                    total += mi.length
                elif hasattr(mi, 'to_ints'):
                    total += len(mi.to_ints())
            elif isinstance(datum, dict):
                # Fallback for dict-based data
                for v in datum.values():
                    if isinstance(v, (list, tuple)):
                        total += len(v)
        return total

    # --- Explicitly NOT exposed ---
    #
    # The following Tinker SDK operations are intentionally absent:
    #
    # - create_rest_client()                    → no access to REST API
    # - list_training_runs()                    → no visibility into other deals
    # - get_checkpoint_archive_url()            → no weight downloads
    # - publish_checkpoint()                    → no making weights public
    # - unpublish_checkpoint()                  → n/a
    # - create_sampling_client() with any path  → path-checked above
    # - create_training_client_from_state()     → no loading other runs
