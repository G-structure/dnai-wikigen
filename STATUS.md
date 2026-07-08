# dnai-wikigen Status

Last updated: 2026-07-08

Scope: current repository evidence only. This file is a status ledger, not a
production deployment manifest.

## Legend

```text
[real]      Code exists and can be compiled, imported, tested, or run locally.
[partial]   Code exists, but the end-to-end path is incomplete or externally blocked.
[modeled]   The design is documented or stubbed, but enforcement is not complete.
[planned]   Architecture target only.
```

## Current Verdict

`dnai-wikigen` is a partially built private verified-reward and attested
diligence substrate. The strongest real vertical slice today is the local Tinker
delegate flow plus sealed artifact ingress:

```text
email OTP -> Tinker login/onboarding -> bounded API-key provisioning metadata
encrypted artifact upload -> TEE-bound attestation report_data -> hash-checked in-memory custody
```

Production deployment, real account funding, full TDX quote verification,
chain-watcher settlement, and RLVR/bio-validation remain incomplete.

## Built

[real] Contracts:

- `⚙️/tinker-delegate/contracts/src/DiligenceRoom.sol` implements the escrow
  state machine for created, funded, evaluated, accepted, rejected, and expired
  deals.
- `⚙️/tinker-delegate/contracts/src/EmailOracleAuth.sol` models on-chain
  app-auth policy for email-oracle consumers.
- Foundry tests exist under `⚙️/tinker-delegate/contracts/test/`.

[real] `tee-email-oracle`:

- FastAPI service with runtime bearer authentication for sensitive routes.
- Sealed credential store abstraction.
- Scoped OTP request path so callers receive only the OTP they requested.
- Encrypted OTP replay ledger.
- Redacted diagnostics for secret-like values.

[real] `tinker-delegate` local automation:

- Local Neko/CDP Tinker login, email OTP consumption, onboarding, and API-key
  provisioning have been validated locally.
- API keys are stored encrypted and leave only as bounded metadata such as
  status, hash, and masked prefix.
- Browser/control-plane diagnostics are redacted before egress.

[real] `tinker-delegate` funding channel:

- Card details use an encrypted channel by default.
- Plaintext card submission is disabled by default and is also disabled when
  dstack is detected.
- Local Stripe test-card automation reaches the bounded card-decline result.
- Add-balance fails closed when no funded payment method is available.

[real] Artifact ingress:

- `GET /attestation?context=artifact` exposes a context-bound public upload key
  and dstack attestation when available.
- Upload clients verify the attestation envelope before sending an artifact.
- Artifact uploads are encrypted client-side to the attested key.
- Server-side artifact keys are derived per deal and artifact hash.
- Upload AAD binds `deal_id` and expected Ethereum `keccak256` artifact hash.
- The service verifies plaintext artifact bytes against the committed hash
  before accepting custody.
- Accepted artifact bytes remain in memory; regression tests guard against disk
  writes on the upload path.

[real] Supporting CLIs and tests:

- `python -m tinker_delegate.main verify-attestation`
- `python -m tinker_delegate.main upload-artifact`
- Python unit tests for Tinker delegate and email oracle services.
- Mocked-SDK `IsolatedTinkerSession` tests cover one training run per deal,
  TTL on checkpoint save paths, path-checked sampling, cleanup deletion, and
  cost metering without calling real Tinker.
- Cleanup now returns a bounded attestation with deletion counts, retry
  attempts, success/error status, and a hash of checkpoint IDs instead of raw
  IDs; the control plane stores it on deal resolution.
- First-party SFT evaluator code uses wrapper methods only. Its base-model
  sampler path is scoped, and tests reject raw ServiceClient, REST,
  list/download, publish, and delete API usage in evaluator source.
- Skip-by-default real Tinker SDK smoke harness exists for tiny
  training/sampling/cleanup, gated by `TINKER_RUN_REAL_SDK_TESTS=1`,
  `TINKER_API_KEY`, and `TINKER_REAL_SDK_MAX_USD <= 0.50`.

[real] Private reward interface:

- `tinker_delegate.private_reward.PrivateRewardEnvironment` defines the core
  sealed-reward contract: public problem text, candidate schema, acceptance
  policy, internal reward, output reducer, query budget, final bounded result,
  and environment attestation metadata.
- `LeakageBudget` records max queries, feedback mode, reward precision policy,
  candidate-payload release policy, timing bands, and cost bands.
- Public evaluation returns `BoundedFeedback` and appends
  `QueryLeakageRecord` entries containing candidate hashes, decisions, reward
  bands or withheld feedback, timing bands, and transcript hashes.
- `OptimizerPolicy` now names where the optimizer runs: inside the same TEE, in
  an attested remote service, or outside the boundary with bounded feedback
  only.
- The default optimizer policy is external and fail-closed: exact rewards,
  reward-derived state, and private checkpoints are rejected for external
  optimizers.
- Internal dense-reward mode exists for optimizers inside the attested boundary;
  public evaluation still returns bounded feedback.
- Exact `InternalReward` values remain in the environment; tests cover bounded
  feedback, budget exhaustion, policy rejection, pass/hold/deny precision
  reduction, reducer hash mismatch fail-closed behavior, optimizer policy
  enforcement, internal dense-reward access, and final transcript/leakage
  hashes.

[real] Local candidate sandbox:

- `tinker_delegate.private_reward_sandbox.PythonCandidateSandbox` runs UTF-8
  Python candidate source in a subprocess with a scratch working directory,
  stripped environment, deterministic random seed, timeout, best-effort
  CPU/memory limits, max source bytes, and capped stdout/stderr.
- Static preflight rejects file, network, process, import, builtin-import,
  dunder-attribute, and direct `open`/`eval`/`exec` style escape attempts.
- Public sandbox results expose candidate hash, bounded outcome, failure-code
  bucket, exit code, timeout flag, elapsed timing band, capped stdout/stderr,
  and truncation flags without echoing the source.
- Failure traces are bucketed into policy, syntax, runtime, and timeout classes
  instead of returning raw exception strings or preflight details.

[real] Hidden holdout accounting:

- `tinker_delegate.private_reward_holdout.HiddenHoldoutSet` creates deterministic
  train, reward, and final-validation partitions over TEE-held records.
- Public holdout manifests expose split commitment, split policy, partition
  counts, reward-query counts, unique candidate counts, maximum repeated
  candidate-query count, final-validation count, and whether reward queries are
  closed.
- Public manifests do not include raw record IDs, payloads, labels, or split
  membership.
- Reward-query accounting enforces a configured query budget, and final
  validation is gated to one-shot use by default; once final validation starts,
  additional reward queries fail closed.
- Generic adaptive-query guards enforce per-candidate repeat caps and a minimum
  number of unique reward candidates before final validation can run.

[real] Synthetic private reward environment:

- `tinker_delegate.private_reward_envs.synthetic.SyntheticHiddenKeywordEnvironment`
  extends `PrivateRewardEnvironment` and uses `HiddenHoldoutSet` for reward and
  final-validation partitions over sealed synthetic records.
- Candidate payloads are bounded UTF-8 keywords; invalid keywords fail policy
  before any holdout query is recorded.
- Public feedback exposes only bounded reward bands and transcript hashes, not
  exact scores, candidate text, match counts, record IDs, or payloads.
- Finalization uses the final-validation holdout once, caches the bounded final
  result, and closes later reward queries.

## Partial

[partial] Deployed Tinker automation:

- The selector/UI repair, OTP login, onboarding, API-key provisioning, and
  test-card decline are validated locally with Neko/CDP.
- API-key provisioning now has fallback selector families for current key
  creation labels plus aria-label/data-testid variants, emits bounded
  `api_key_provisioning` attempt records including `selector_missing` instead
  of raw page state, and has replayable mock-page tests for successful key
  extraction and selector-drift failures.
- Tinker re-auth now has a bounded local helper/CLI and opt-in API endpoint for
  future OTP challenges. It returns `tinker_auth` attempt records only and does
  not return account email, OTP, browser URL, API key, or raw page text.
- The same flow still needs fresh validation inside a deployed Phala CVM.
- The optional Tinker SDK dependency and runtime behavior inside the final CVM
  image are not yet proven.
- Real Tinker SDK training/sampling/cleanup tests have not been run here; they
  remain gated on credentials, budget cap, and deployed CVM validation.
- Cleanup attestations are local wrapper/control-plane evidence; deployed
  Tinker deletion and TTL expiry are still unproven.
- Arbitrary third-party evaluator code is not yet sandboxed against Python
  introspection; that remains a separate P0 before untrusted evaluators are
  accepted.

[partial] Account funding:

- Test-card billing reaches a clear declined-card outcome.
- Payment-method and add-balance operations return bounded attempt records with
  outcome class, furthest stage, issued timestamp, evidence hash, amount/balance
  bands, TDX quote hash when present, and card-payload destruction status.
- Bounded funding receipts are persisted in encrypted/sealed delegate storage
  under a separate funding-receipt key path and exposed through
  `GET /billing/funding-receipts`.
- The encrypted card client/harness verifies context-bound billing attestation,
  posts only ciphertext to `/billing/card/encrypted`, and was locally exercised
  against the Neko/Tinker/Stripe test-card path. It returned bounded
  `card_declined` and persisted one funding receipt.
- Payment-method screenshots after card entry/submission are suppressed even
  when debug screenshots are enabled; non-secret billing screenshots remain
  explicit debug artifacts only.
- Real card funding is intentionally not attempted until real payment details
  are provided out of band.
- Payment-method token/reference handling and the sealed long-lived funding
  token/session state still need production retention and rotation policy.

[partial] TEE attestation:

- The artifact ingress binds a dstack report to the upload key through
  `report_data`.
- The verifier checks the attestation envelope and public-key binding.
- Full cryptographic Intel TDX quote parsing, freshness, compose-hash policy,
  image-digest policy, signer allowlists, and anti-replay are not implemented.

[partial] Contracts and settlement:

- Core escrow and auth contracts exist with tests.
- Chain watcher, TEE-derived transaction signing, on-chain quote verification,
  compose/app identity binding, and settlement-event integration are not built.

[partial] Data custody:

- The upload endpoint keeps accepted plaintext in memory and avoids intentional
  disk writes.
- The downstream evaluator, Tinker SDK/browser handoff, heap lifetime, crash
  logs, browser download directory, and deployed debug tooling still need a
  full no-disk/no-egress audit.
- Sealed retention keys are not implemented for long-lived artifact custody.

[partial] Private reward environments:

- The base interface, leakage accounting, and one synthetic toy environment are
  real.
- Real RLVR, TTT, computational-bio, code-audit, or model-evaluation
  environments are not implemented.
- Candidate sandboxing has a local Python runner for toy candidates, but
  hardened OS/container isolation for arbitrary third-party code is not
  implemented.
- Local sandbox side-channel controls exist, but deployed reward side-channel
  hardening for real evaluator/Tinker/browser paths remains open.
- Hidden-holdout split/accounting and generic adaptive-query guards are wired
  into the synthetic environment, but real environments still need
  domain-specific anti-overfitting checks.
- Integration of optimizer policy with real Tinker/browser execution remains
  open P0 work.

[partial] Frontend and product surface:

- The project has service and contract surfaces, but no production-ready
  integrated buyer/seller frontend for the full diligence-room path.
- Gate-health and manual operation affordances are still separate or planned.

## Modeled

[modeled] Private verified rewards:

- The architecture preserves the larger substrate vision: private data,
  verifier code, reward functions, and credentials live inside an attested
  boundary, while agents and optimizers receive bounded outputs only.
- The optimizer is intentionally swappable: RL, TTT, LLM repair loops,
  evolutionary search, or hybrids.
- `PrivateRewardEnvironment` is the real code-level interface for this model,
  while concrete production environments remain partial or planned.

[modeled] RLVR and bio-validation:

- Bio-validation over sealed datasets is conceptual and stub-level only.
- Risk screening, reviewer queues, dual-use controls, bounded biological
  schemas, and fail-closed policies are not implemented.

[modeled] Multi-party governance:

- Corpus policy intersection, consent/revocation, royalty metering,
  production-room account custody, and third-party reviewer lanes remain design
  targets rather than enforced production flows.

## Planned

[planned] Deployment and verification:

- Reproducible container images pinned by digest.
- SBOMs and build provenance.
- Phala CVM deployment with recorded CVM ID, app ID, compose hash, image digest,
  gateway endpoint, and quote evidence.
- Base Sepolia or mainnet deployments with BaseScan verification links.
- Machine-readable deployment manifest.
- One-command local verification script.

[planned] Security hardening:

- Full TDX quote verifier.
- Contract-bound attestation policy.
- DLP/egress enforcement beyond bounded route design and redaction tests.
- Reviewer approval flows for widened access.
- Fail-closed bio/dual-use result schema.

## Deployed Resources

Final deployed-resource manifest: none yet.

`example.env` intentionally leaves these deployment outputs blank:

```text
ESCROW_ADDRESS=
JUDGE_ADDRESS=
PHALA_CVM_ID=
```

Historical local broadcast artifacts or scratch deployment outputs must not be
treated as final production evidence. A deploy is considered real only when a
manifest records the chain, transaction hashes, verified contract links, Phala
CVM ID, app ID, compose hash, image digest, endpoint, quote evidence, and the
commands used to reproduce or verify them.

## Current Blockers

- Real-card Tinker funding requires real payment details and an explicit capped
  attempt.
- Deployed Phala/CVM validation for the headed Neko browser path is still
  pending.
- Full Intel TDX quote verification and freshness checking need implementation.
- Registry images, pinned digests, SBOMs, and compose-hash release evidence are
  not complete.
- Base Sepolia deployment needs configured RPC, Foundry keystore account, and
  verification credentials in local environment.
- Tinker SDK availability inside the final CVM image is not yet proven.
- Bio-validation must remain fail-closed until risk screening, reviewer queues,
  and bounded schemas exist.

## Validation Commands

Focused commands used for the currently built surfaces:

```bash
cd "⚙️/tinker-delegate" && uv run python -m unittest discover -s tests -v
cd "⚙️/tinker-delegate" && uv run python -m compileall tinker_delegate
cd "⚙️/tinker-delegate" && uv lock --check
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main verify-attestation --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main upload-artifact --help

cd "⚙️/tee-email-oracle" && uv run python -m unittest discover -s tests -v
cd "⚙️/tee-email-oracle" && uv run python -m compileall email_oracle

cd "⚙️/tinker-delegate/contracts" && forge test

git diff --check
```

Before claiming production deployment, also record the deployed-resource
manifest described above and update `ARCHITECTURE.md` from `[partial]` or
`[planned]` to `[real]` only for evidence-backed paths.
