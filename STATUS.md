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

Production deployment is now partially real on Phala: the combined
email-oracle + tinker-delegate CVM is running from digest-pinned registry
images and has live TDX envelope verification. Real account funding, full
quote-internal TDX verification, live CVM-originated TEE-to-chain signing, and
RLVR/bio-validation remain incomplete. Phala auth is configured for profile
`wikigen` in workspace `wiki`.

## Built

[real] Contracts:

- `⚙️/tinker-delegate/contracts/src/DiligenceRoom.sol` implements the escrow
  state machine for created, funded, evaluated, accepted, rejected, and expired
  deals.
- `⚙️/tinker-delegate/contracts/src/EmailOracleAuth.sol` models on-chain
  app-auth policy for email-oracle consumers.
- `⚙️/tinker-delegate/contracts/src/TinkerAccountEncumbrance.sol` models
  on-chain policy/audit controls for the TEE-owned Tinker account: hashed
  account commitment, approved compose hashes, managers, add-balance/spend caps,
  emergency halt, measurement freeze, bounded operation authorizations, and
  receipt hashes.
- Foundry tests exist under `⚙️/tinker-delegate/contracts/test/`.

[real] `tee-email-oracle`:

- FastAPI service with runtime bearer authentication for sensitive routes.
- Optional on-chain `EmailOracleAuth` consumer-registry checks for `/pin` and
  `/inbox`. When `ORACLE_AUTH_REQUIRED=true` or a contract is configured,
  sensitive routes fail closed before IMAP access unless the configured
  consumer app and compose hash are authorized by the contract.
- Sealed credential store abstraction.
- Attestation-bound encrypted credential provisioning for an existing mailbox:
  `GET /attestation?context=oracle-credentials` exposes a context-bound key,
  `POST /credentials/encrypted` is disabled by default behind a provisioning
  bearer token, and successful writes return only hashes/status.
- Scoped OTP request path so callers receive only the OTP they requested.
- Encrypted OTP replay ledger.
- Redacted diagnostics for secret-like values.

[real] `tinker-delegate` local automation:

- Local Neko/CDP Tinker login, email OTP consumption, onboarding, and API-key
  provisioning have been validated locally.
- API keys are stored encrypted and leave only as bounded metadata such as
  status, hash, and masked prefix.
- Signup/signin stdout and return payloads expose mailbox and browser-route
  hashes rather than raw account email or Tinker URLs; regression tests cover
  stdout and result egress before the deployed-CVM bootstrap path is retried.
- Startup bootstrap now preserves the last bounded attempt record in
  `/health.runtime.last_bootstrap_attempt_record`. It covers successful
  `api_key_provisioning`, selector/API-key-capture failures, and early
  `tinker_auth` failures during account lookup, CDP/browser connection,
  browser context/page setup, authentication, and onboarding. This is now
  Phala-proven for the `8fb6e3a` image: the latest one-shot bootstrap emitted
  a bounded `tinker_auth` `unknown_failure` record at `not_started`, with
  hashes and `raw_secret_egress=false`, not raw mailbox, OTP, browser URL,
  page text, or API key. The top-level
  `/health.runtime.bootstrap_error_kind` now preserves that bounded
  `unknown_failure` outcome when the serve-level catch handles the bubbled
  startup failure.
- `tinker-delegate selector-map` now emits the bounded machine-readable
  selector/frame/auth-flow contract for email auth, OTP, onboarding, API-key
  creation, billing, Stripe iframe, balance top-up, and auto-reload surfaces.
  It includes selector-family counts, evidence labels, and a recomputable map
  hash, with optional `--summary-only` output that omits concrete selectors.
  `tinker-delegate selector-probe` now provides the read-only browser
  observation path for deployed evidence capture: it observes current
  pages/frames without navigation, clicks, typing, screenshots, or page-text
  capture, emits only URL classes/hashes, selector match bands, frame kinds,
  selector-map hash, and `raw_secret_egress=false`, and fails closed with
  bounded `browser_unavailable` JSON if the browser cannot be reached. The
  matching `GET /browser/selector-probe` endpoint is now Phala-proven as a
  deployed gate/fail-closed path: one-shot compose with GitHub-attested
  `ca877db` images enabled only the selector-probe endpoint on top of the
  bounded bootstrap profile, the live response returned bounded
  `browser_unavailable` JSON with `raw_secret_egress=false`, and the restored
  normal compose returns 403. Deployed selector/frame match capture remains
  open because the browser connection was unavailable during that probe.
- `tinker-delegate browser-readiness` and disabled-by-default
  `GET /browser/readiness` now provide a bounded way to diagnose that deployed
  browser-control failure without logs, SSH, screenshots, page text, cookies,
  or raw browser/CDP URLs. Output is limited to endpoint classes/hashes, CDP
  metadata reachability, Playwright/CDP handshake status, context-count bands,
  and bounded error kinds. Normal Phala compose keeps
  `TINKER_ALLOW_BROWSER_READINESS_ENDPOINT=false`; the one-shot bootstrap
  measurement compose enables it alongside the selector probe.
- `docker-compose.tinker-bootstrap.phala.yaml` is the bounded one-shot
  main-CVM profile for Tinker OTP/login/API-key provisioning. It enables only
  `TINKER_BOOTSTRAP_SIGNUP=true`, reuses the main `delegate-data` volume, keeps
  `ORACLE_AUTO_GENESIS=false`, keeps credential provisioning and add-balance
  disabled, and uses the headed Neko Chrome CDP endpoint instead of a headless
  Playwright sidecar. It has been Phala-tested and reverted to the normal
  compose; live attempts still fail closed before API-key sealing.
- Browser/control-plane diagnostics are redacted before egress.

[real] `tinker-delegate` funding channel:

- Card details use an encrypted channel by default.
- Plaintext card submission is disabled by default and is also disabled when
  dstack is detected.
- Local Stripe test-card automation reaches the bounded card-decline result.
- Add-balance fails closed when no funded payment method is available.
- Bounded funding receipts are stored encrypted under the delegate data volume
  and reject unknown fields or `raw_secret_egress=true`.
- `TINKER_FUNDING_MODE=manual_prefund` is the default production model and
  denies card/add-balance browser automation before decryption or browser
  launch. `operator_capped_validation` is required for one-off approved
  operator validation attempts, and denied requests persist bounded
  `policy_denied` receipts.
- `tinker-delegate` can now read `TinkerAccountEncumbrance` policy before
  Tinker funding automation. If `TINKER_ENCUMBRANCE_REQUIRED=true` or an
  encumbrance contract address is configured, payment-method and add-balance
  operations fail closed before card decryption/browser launch unless public
  contract reads show the compose hash is approved, emergency halt is off, and
  the add-balance/spend amount is within cap.

[real] `tinker-delegate` bounded run metadata:

- Control-plane deal lifecycle events persist to an encrypted
  `run_metadata.enc` store under the delegate data volume.
- Stored records use hashed deal/account/Tinker-run handles, artifact hashes
  and size bands, score/offer/cost bands, and cleanup counts.
- Raw artifacts, API keys, card fields, checkpoint IDs, raw Tinker run IDs, and
  arbitrary extra fields are rejected by the store schema/tests.

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
- `scripts/verify-local.sh` runs the current local quality gate:
  secret-shaped material scan, Foundry build/tests, frozen `uv` sync,
  Python compile checks, and Python unit tests for implemented suites.
- `.github/workflows/ci.yml` runs the same secret scan, Foundry, and Python
  gates in CI for pushes and pull requests.
- The Foundry CI checkout intentionally does not recurse into the read-only
  research submodules; `forge-std` is vendored under the contracts package, and
  avoiding recursive submodules prevents the GitHub runner from failing in the
  emoji-path `🔬/` submodule metadata before Foundry starts.
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
- `python -m tinker_delegate.main synthetic-private-reward-demo` runs a
  replayable synthetic hidden-dataset reward demo and emits only optimizer view,
  bounded feedback, final bounded result, transcript/leakage hashes, and
  attestation metadata.

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
- The `tinker-delegate` Dockerfile now copies `uv.lock` and installs with
  `uv sync --frozen --no-dev --extra agent`; a local build/run of
  `dnai-tinker-delegate-agent-extra:local` returned
  `/health.agent_stack_available=true`.
- `⚙️/tinker-delegate/scripts/verify-agent-image.sh` is the repeatable local
  proof command for this packaging path: it rebuilds the image and runs an
  in-image `import tinker` plus `agent_stack_available` check with bounded JSON
  output.
- The same flow still needs fresh validation inside a deployed Phala CVM.
- Reusable payment-method token/reference capture is not implemented; if an
  official or tokenized funding path becomes available, that state still needs
  sealed-store integration and live validation.
- `⚙️/tinker-delegate/docs/TINKER-AUTOMATION-ROUTE.md` records the acceptable
  automation route: prefer official/support-approved Tinker workflows; allow
  browser automation only as bounded TEE custody for this project's own account.
- Runtime policy tests reject common stealth, CAPTCHA-solving, rotating-proxy,
  and automation-control masking dependencies or flags in the Tinker delegate
  runtime package, dependency manifest, and compose files.
- Real Tinker SDK training/sampling/cleanup tests have not been run here; they
  remain gated on credentials, budget cap, and deployed CVM validation.
- Cleanup attestations are local wrapper/control-plane evidence; deployed
  Tinker deletion and TTL expiry are still unproven.
- Arbitrary third-party evaluator code is not yet sandboxed against Python
  introspection; that remains a separate P0 before untrusted evaluators are
  accepted.

[partial] Account funding:

- A minimal `TinkerAccountEncumbrance.sol` contract now exists locally with
  tests proving managers cannot exceed owner-set caps or change owner-only
  policy. The runtime now has a read-only policy preflight and optional
  fail-closed card/add-balance gate, but the contract is not yet deployed or
  recorded in the Base Sepolia manifest.
- Test-card billing reaches a clear declined-card outcome.
- Payment-method and add-balance operations return bounded attempt records with
  outcome class, furthest stage, issued timestamp, evidence hash, amount/balance
  bands, TDX quote hash when present, and card-payload destruction status.
- Billing automation has selector fallback families for balance/payment
  controls, payment-method submission, cardholder/address fields, add-balance
  amount input, and top-up confirmation. Mock-page tests cover current selectors
  plus data-testid/aria-style drift, and missing top-up controls return bounded
  `selector_missing` receipts without exposing page text.
- Bounded funding receipts are persisted in encrypted/sealed delegate storage
  under a separate funding-receipt key path and exposed through
  `GET /billing/funding-receipts`.
- Add-balance automation enforces `TINKER_MAX_ADD_BALANCE_USD` before launching
  browser automation. Non-finite, non-positive, or over-cap requests return
  bounded `policy_denied` receipts at `not_started` with amount bands.
- The active funding mode is inspectable through `GET /billing/funding-policy`
  and `python -m tinker_delegate.main funding-policy`.
- Operator funding preflight is inspectable through
  `GET /billing/funding-preflight` and `python -m tinker_delegate.main
  funding-preflight`; it checks validation mode, amount cap, optional
  add-balance endpoint flag, encrypted receipt-store availability, and billing
  attestation policy without card material or browser launch.
- `python -m tinker_delegate.main funding-manifest` builds a bounded audit
  manifest from saved funding-preflight and funding-receipt JSON. It publishes
  only hashes, bands, outcome, TDX quote hash, card-destruction /
  no-raw-egress booleans, and an optional attestation-policy hash, and rejects
  raw card/API-key/secret-shaped inputs.
- `python -m tinker_delegate.main verify-funding-manifest` replay-verifies a
  saved preflight, receipt, manifest, validation ID, and attestation-policy
  tuple. It returns named bounded pass/fail checks and does not echo packet
  bodies.
- Operator CLIs can write validation artifacts directly:
  `funding-preflight --output` writes bounded preflight JSON, and billing
  receipt-producing commands support `--receipt-output` for bounded attempt
  records. CLI output fails closed if a response contains submitted card
  material or secret-shaped fields.
- `python -m tinker_delegate.main funding-validation-packet` creates a
  bounded packet directory containing preflight, receipt, manifest,
  verification, and summary JSON. It can bind an existing bounded receipt, or
  run encrypted card submission only when `--run-card-attempt` is explicitly
  set.
- `funding-validation-packet --prompt-card --run-card-attempt` prompts
  interactively for approved operator card details instead of reading them from
  command-line flags. Prompt mode is mutually exclusive with test-card fields
  and rejects missing deployed compose/app/OS-image attestation expectations
  before asking for card material unless local-development attestation is
  explicitly allowed.
- Funding validation packets can include a separate add-balance evidence lane:
  `--add-balance-receipt-json` binds an existing bounded top-up receipt, and
  `--run-add-balance-attempt` posts only the amount to `/billing/add-balance`
  before writing add-balance manifest and verification JSON.
- `python -m tinker_delegate.main check-funding-validation-packet` replay-checks
  packet directories and returns bounded pass/fail checks. It can require
  add-balance evidence and can require live deployed TDX attestation evidence;
  local packets remain internally checkable but are not production proof.
- The HTTP `POST /billing/add-balance` mutation endpoint is disabled by default
  behind `TINKER_ALLOW_ADD_BALANCE_ENDPOINT`; the capped CLI/internal path also
  requires `TINKER_FUNDING_MODE=operator_capped_validation` for deliberate
  operator validation attempts.
- Stripe/PCI stance is recorded in
  `⚙️/tinker-delegate/docs/STRIPE-PCI-FUNDING-SCOPE.md`: the encrypted raw-card
  channel is limited to a one-off operator-owned capped validation path, while
  production/repeated funding should use an official Tinker route,
  Stripe-hosted/tokenized collection, SetupIntent / PaymentMethod style reuse
  with consent, or manual/developer prefunding until compliance review approves
  otherwise.
- The encrypted card client/harness verifies context-bound billing attestation,
  posts only ciphertext to `/billing/card/encrypted`, and was locally exercised
  against the Neko/Tinker/Stripe test-card path. It returned bounded
  `card_declined` and persisted one funding receipt.
- A fresh local FastAPI smoke on 2026-07-08 used
  `TINKER_FUNDING_MODE=operator_capped_validation`,
  `TINKER_MAX_ADD_BALANCE_USD=5`, local billing attestation, and a Stripe test
  card. `GET /billing/funding-preflight` returned ready for `$5`; `$10` plus
  `require_add_balance_endpoint=true` returned not ready because the amount was
  over cap and the HTTP add-balance mutation was disabled. The encrypted
  test-card submission reached `payment_submitted`, returned only a bounded
  `payment_method` receipt, set `card_payload_destroyed=true` and
  `raw_secret_egress=false`, and persisted one encrypted receipt. A binary
  string scan of that temp receipt did not find the test card number, CVC,
  cardholder name, postal code, or raw card field names.
- `python -m tinker_delegate.main add-card-encrypted-prompt` prompts for card
  fields interactively instead of taking them as command-line flags, requires
  deployed compose/app/OS-image attestation expectations unless explicitly run
  in local-development mode, zeros the in-memory card dictionary after upload,
  and emits only bounded response/receipt JSON.
- Payment-method screenshots after card entry/submission are suppressed even
  when debug screenshots are enabled; non-secret billing screenshots remain
  explicit debug artifacts only.
- Card submission attempts purge known secret-bearing browser debug artifacts
  such as trace archives, HARs, videos, and card/Stripe screenshots when an
  explicit debug artifact directory is configured.
- Tinker delegate Python entrypoints disable core dumps with `RLIMIT_CORE=0`,
  and local/Phala compose services set `ulimits.core: 0` for the delegate and
  browser path.
- Real card funding is intentionally not attempted until real payment details
  are provided out of band.
- Production or repeated card funding still needs legal/compliance approval.
- Payment-method token/reference handling and the sealed long-lived funding
  token/session state still need an official/tokenized route plus production
  retention and rotation policy.

[partial] TEE attestation:

- The artifact ingress binds a dstack report to the upload key through
  `report_data`.
- The verifier checks the attestation envelope, public-key binding, and
  exposed `quote_report_data` equality when the endpoint provides it.
- `verify-cvm-attestation` and `scripts/verify-cvm-attestation.sh` now combine
  local Phala compose-hash verification with live `/attestation?context=...`
  checks, including required digest-pinned image references or sha256 image
  digests, app ID, OS image hash, report data, public key, and client fetch
  freshness.
- `verify-deployment-bundle` now combines GitHub image-attestation verification
  with live CVM attestation verification in one bounded JSON certificate:
  GitHub-signed SLSA provenance and SPDX SBOM attestations for digest-pinned
  GHCR oracle/delegate images, required Phala compose image refs, required
  sidecar image digests, app ID, OS image hash, report data, public key, and
  client fetch freshness.
- Full cryptographic Intel TDX quote parsing, quote-internal freshness,
  signer allowlists, and anti-replay checks are still incomplete.

[partial] Contracts and settlement:

- Core escrow and auth contracts exist with tests.
- A local chain watcher exists in `tinker_delegate.chain_watcher`: it decodes
  the six public `DiligenceRoom` lifecycle events from JSON-RPC logs, posts
  every event to bounded `/deal/chain-event` audit metadata, calls
  `/deal/notify-funded` when a `DealFunded` event has matching prior
  `DealCreated` context, and calls `/deal/{deal_id}/resolve` for accepted,
  rejected, or expired events. The `watch-chain` CLI exposes the same path for
  operator/CVM use.
- `⚙️/tinker-delegate/scripts/prove-chain-watcher-anvil.py` proves the watcher
  against a real local Anvil contract log: it starts ephemeral Anvil, deploys
  `DiligenceRoom` through an unlocked local account, emits `DealCreated` and
  `DealFunded`, runs the watcher over JSON-RPC, and verifies a bounded
  control-plane stub receives funded state for deal `0` without manual curl
  calls or raw private-key flags.
- `ChainCursorStore` gives the watcher durable restart state: it stores the
  next block, confirmation depth, contract address hash summary, and public
  `DealCreated` context. Restart tests and the Anvil proof show a later
  `DealFunded` can still notify funded state after the created context has
  crossed a process boundary. The watcher advances the cursor only after
  successful dispatch and only scans confirmation-safe blocks.
- `tinker_delegate.chain_submitter` provides partial TEE-to-chain signing
  plumbing: in dstack mode it derives an Ethereum signer from dstack key
  material, has no raw-private-key CLI/env path, verifies the public
  `deals(dealId)` state before signing, requires the signer to match
  `teeIdentity`, checks funded state and compute budget, signs
  `submitResult()` in memory, broadcasts through JSON-RPC, and returns only
  bounded receipt metadata. The submitted `resultHash` is an anti-replay
  commitment over chain ID, contract address, deal ID, signer nonce, compose
  hash, payload result hash, score band, compute cost, and expiry; the original
  bounded payload hash remains separate as `payload_result_hash` in the receipt.
  Current tests use an injected test signer to verify signed transaction
  recovery, commitment drift under replay-context changes, and bounded receipt
  shape without committing or accepting raw keys.
- `DiligenceRoom.sol` now requires a result-verifier signature before accepting
  `submitResult()`. The signed authorization binds chain ID, contract address,
  deal ID, TEE identity, compose hash, score band, compute cost, replay-bound
  result commitment, and authorization expiry. Contract tests cover wrong
  verifier, expired authorization, and zero compose hash.
- `tinker_delegate.result_verifier` implements the bounded verifier
  authorization path that should issue those signatures: it validates signer
  attestation evidence against signer address, chain ID, contract, report data,
  quote report data, approved compose hashes, approved app IDs, optional OS
  image hashes, revoked quote hashes, revoked TEE signers, distinct
  verifier/TEE keys, and a short authorization TTL before signing the exact
  `DiligenceRoom` authorization digest. Tests cover accepted authorization and
  fail-closed policy, context, revocation, self-approval, and non-dstack custody
  cases.
- The verifier path is exposed through bounded operator CLIs:
  `result-verifier-address` prints the dstack-derived verifier address for
  deployment, and `authorize-result` consumes bounded signer-attestation JSON
  plus explicit compose/app/OS-image allowlists and revocation lists before
  emitting authorization metadata and the public verifier signature needed by
  the contract. CLI help tests assert these commands do not expose
  raw-private-key, seed, or mnemonic flags.
- The `submit-result` path now uses a pre-broadcast off-chain verifier gate:
  it fetches dstack signer quote evidence whose report data binds the signer
  address, chain ID, and contract address; rejects signer/chain/contract/report
  data/compose mismatches; and records only bounded quote hash, report data,
  quote size, authorization expiry, and verifier-signature hash in the receipt.
  This is the chosen current quote-verification path documented in
  `docs/DECISIONS.md`.
- `⚙️/tinker-delegate/scripts/prove-chain-submitter-dstack-anvil.py` proves the
  submitter against Phala/dstack simulator key derivation and real local Anvil:
  it derives the signer through the same dstack path used by the CLI, funds that
  signer on ephemeral Anvil, derives the result verifier through the
  `result-verifier-address` CLI, deploys `DiligenceRoom` with that verifier,
  creates and funds a deal whose `teeIdentity` is the derived signer, obtains a
  verifier signature through `authorize-result`, runs `tinker-delegate
  submit-result`, and verifies the real `EvaluationSubmitted` event carries the
  replay-bound submission commitment, not the raw payload hash, with signer
  attestation metadata, verifier-signature hash, and `raw_secret_egress=false`.
- The watcher is not yet deployed as a Phala/CVM process and does not include
  chain-lag alerting or deep-reorg rollback beyond the configured confirmation
  policy.
- A deployed-CVM proof of verifier-authorized `submitResult()` broadcast has
  not yet been run. The verifier policy/signature module and operator CLI path
  are real, but they have not yet been deployed as a verifier service and full
  cryptographic Intel TDX quote parsing/freshness is still incomplete. Full
  settlement-event integration is still incomplete.

[partial] Data custody:

- The upload endpoint keeps accepted plaintext in memory and avoids intentional
  disk writes.
- The downstream evaluator, Tinker SDK/browser handoff, heap lifetime, crash
  logs, browser download directory, and deployed debug tooling still need a
  full no-disk/no-egress audit.
- Sealed retention keys are not implemented for long-lived artifact custody.

[partial] Private reward environments:

- The base interface, leakage accounting, one synthetic toy environment, and a
  bounded synthetic hidden-dataset CLI packet are real.
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

[partial] Deployment and verification:

- `verify-compose-hash` renders registry-image compose files, rejects local
  `build:` services and mutable tag-only images, emits the digest-pinned image
  manifest, and computes the Phala Cloud-style compose hash over the rendered
  app-compose object. It also supports the Phala raw-compose/allowed-env mode
  needed to check local image policy when Phala's full app-compose hash includes
  platform metadata not reproduced by the public compose file alone.
- The Phala Playwright sidecar image is pinned by amd64 digest.
- The deploy-critical `tinker-delegate` and `tee-email-oracle` Dockerfiles now
  pin the Python runtime and `uv` helper images by versioned digest.
- `.github/workflows/build-tee-images.yml` builds those two images on
  GitHub-hosted runners, pushes `linux/amd64` images to GHCR, attaches
  BuildKit SBOM/provenance attestations, generates SPDX SBOMs, and emits
  GitHub-signed provenance and SBOM attestations.
- `⚙️/tinker-delegate/scripts/verify-ghcr-image-attestation.sh` verifies a
  digest-pinned GHCR image against this repo, the TEE image workflow, expected
  source commit, SLSA provenance predicate, SPDX SBOM predicate, and
  non-self-hosted-runner policy before the image digest is allowed into Phala
  deployment inputs.
- `python -m tinker_delegate.main verify-deployment-bundle` verifies the
  current deployment as one bounded certificate by combining the GitHub image
  attestation gate, digest-pinned compose policy, sidecar digest requirements,
  and live Phala CVM attestation envelope.
- GitHub Actions run `28954112809` built the current deploy-critical images on
  GitHub-hosted workers from source commit
  `8fb6e3a7dac3ef58f1e4c1e902a36ebd612b910e` and attached
  GitHub-signed SLSA provenance plus SPDX SBOM attestations. The local deploy
  gate verified both image digests with
  `⚙️/tinker-delegate/scripts/verify-ghcr-image-attestation.sh`.
- Current deploy-critical image digests:
  - Oracle:
    `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19359e6df891cb48ecf1b051d499d39f2f8a7be2dfe5c62e3c568402cb372f79`.
  - Delegate:
    `ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:16b2dfa8428a8a2f234b5a2ad1dbb57db7cd67ca1e1e655d02633f4201a8506b`.
- Local `verify-ghcr-image-attestation` checks passed for both current image
  indexes with source commit `ca877db2d02ee4498d30560f19d4d394cf165676`,
  source ref `refs/heads/codex/wikigen-private-reward-pitch`, verified
  provenance attestation, verified SBOM attestation, and
  `raw_secret_egress=false`.
- The current Phala compose hardcodes these deploy-critical image refs and the
  disabled secret-bearing gates directly. An intermediate redeploy on
  2026-07-08 showed that changing encrypted image env values alone did not
  change the live attested compose hash, so env-provided image refs are not
  treated as quote-bound deployment evidence.
- Full reproducible container images for every side service, apt package
  pinning, timestamp normalization, and published digest evidence for
  non-critical side services remain open.
- Current Phala deployment:
  - CVM ID: `670b3b21-4338-4d4e-ae72-7c8922579f59`
  - App ID: `f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717`
  - Status: `running`
  - Gateway base: `dstack-pha-prod9.phala.network`
  - Public logs/sysinfo: `false` / `false`.
  - Temporary public-log debug exception on the main CVM: reverted on
    2026-07-08. Public logs and public sysinfo are disabled.
    `ORACLE_AUTO_GENESIS=false`,
    `TINKER_BOOTSTRAP_SIGNUP=false`,
    `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`, and
    `TINKER_ALLOW_BROWSER_READINESS_ENDPOINT=false`,
    `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=false`,
    `ORACLE_ALLOW_CREDENTIAL_PROVISIONING_ENDPOINT=false` are still bound
    directly in compose so no mailbox genesis, Tinker login, credential
    provisioning, add-balance endpoint, browser-readiness endpoint, or
    selector-probe endpoint is active.
  - OS posture: still partial. `phala cvms get` reports
    `dstack-dev-0.5.9`, `is_dev=true`, and OS image hash
    `de9c74f0c85d0820ce075cb4a99f8e39f7b681be632907c5bf8bdc95ea72feb9`
    after the current bounded-image update. Attempts to update the existing CVM to
    `dstack-0.5.10-4c9bd024` or `dstack-0.5.10` with `--no-dev-os` failed in
    the Phala CLI/API with a required `correlationId` validation error; a later
    compose/image update using `--no-dev-os` completed, but the live CVM still
    reported the dev OS afterward.
  - OS image hash:
    `de9c74f0c85d0820ce075cb4a99f8e39f7b681be632907c5bf8bdc95ea72feb9`
  - Attested compose hash:
    `d8dbb33db7ec175838c3aca1c4bc2226bf745925b38105c1807789003f594009`
  - Local raw-compose/image-policy hash:
    `313d34a589316197740b1f81e43b2d1b5bc4ee98985e078bc551e61c96b7c728`
  - Rendered compose SHA-256:
    `c0cec8d59f80a8e2bb97da12a3b1a46fbc4a59a4a67f0506bbedf84d2762b1df`
  - Delegate endpoint:
    `https://f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717-8080.dstack-pha-prod9.phala.network`
  - Oracle endpoint:
    `https://f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717-8000.dstack-pha-prod9.phala.network`
  - Delegate `/health`: `status=ok`, `agent_stack_available=true`,
    `api_key_configured=false`, `bootstrap_attempted=false`,
    `last_bootstrap_attempt_record=null`.
  - Oracle `/health` after the main-CVM mailbox genesis proof:
    `status=ok`, `oracle_email=""`,
    `oracle_email_hash=535adcedea37ac48af0e43720f390125749053a0a0215b669ce55c746cd10132`,
    `oracle_ready=true`, `imap_connected=true`, `dstack_enabled=true`.
  - Current captcha/genesis finding: an explicit temporary
    `dnai-wikigen-oracle-genesis-debug` Phala CVM was deployed with the
    log-hardened oracle image, `ORACLE_AUTO_GENESIS=true`, public logs, public
    sysinfo, and dev OS access, while Tinker bootstrap, billing, and credential
    provisioning were absent/disabled. Its app ID was
    `8958416343d338e1e95f1c0a78a1747970d57cb5` and compose hash was
    `2cf555237c0e3ed7dee2fbced583721cb00cb75bfdced14cd9cf6a155c4e43b0`.
    The oracle derived a dstack key at `email/creds-debug`, found no
    credentials, ran auto-genesis, parsed/solved three HTTP cock.li captchas,
    and cock.li rejected all three as incorrect. Browser fallback then reached
    `ws://172.20.0.3:9223/devtools/browser/...` but timed out in
    `BrowserType.connect_over_cdp`. The debug CVM was deleted after collecting
    this bounded evidence, so no temporary public-log/dev-OS debug CVM is left
    running.
  - Current source-level genesis fix: live form inspection showed cock.li's real
    password confirmation field is currently `password_confinm`, while
    `password_confirm` is a tabindex `-1` honeypot. The oracle HTTP payload now
    fills `password_confinm`, mirrors `csrf_valid`, and leaves
    `password_confirm` empty; the browser fallback now fills
    `password_confinm`.
  - Current Phala proof after the form-contract fix: GitHub-built oracle image
    `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19c4aae35b0e9ab2758b7f680c2638f838c8c5a08da1c37f7f1b3bd192bfa1e2`
    from commit `ca1b17cd5d7478e54020fa91065ce9ebcef49223` verified
    provenance/SBOM locally, then an explicit temporary auto-genesis debug CVM
    with app ID `4c92eec94e2d7b6e8c8a7940cb0b6eb4a0e8e1bd` and compose hash
    `142408b66a30aecac87cb172b615ca12675de1f764a0eaa71d7cc8bc30197a58`
    reached IMAP verification and loaded credentials with email hash
    `a97ad16221ab3a550c42be406ff01638b68659c18eaf507461a399fe8874edd3`.
    The temporary public-log/dev-OS debug CVM was deleted immediately after
    evidence collection.
  - Debug-surface finding from that proof: successful genesis made public
    `/health` expose a raw generated mailbox address. The debug CVM was deleted,
    and source now bounds public `/health` and `/attestation` to readiness plus
    `oracle_email_hash`; raw address retrieval has moved to runtime-authenticated
    `/email`.
  - Current bounded-health Phala proof: GitHub-built oracle image
    `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:99ce7765558a00699e265a8ca7cdcdc8f402dd93c50cf8ddb52a1ef175dffefe`
    from commit `64739e48f1ac2af63a6f1c19053eaa281790fa6a` verified
    provenance/SBOM locally, then an explicit temporary auto-genesis debug CVM
    with app ID `18ab03c040c9c327b9333230b6a405bbccd90bec` and compose hash
    `fe20b736b9db9b3b4b3e8d9ddbcdfffabecc4cdf3311ead6be1fb922a8892c41`
    reached IMAP verification and loaded credentials with email hash
    `ac5745b07e812ca450e7e16a51cea0cb3b6dcf5d6168cee96e7931312a68be81`.
    Public `/health` returned `oracle_email=""`, `oracle_ready=true`,
    `imap_connected=true`, and only that hash; public
    `/attestation?context=attestation` returned `oracle_email=""`, the same
    hash/readiness fields, compose hash, and a verified TDX quote;
    unauthenticated `/email` returned `401 Bearer token required`. The temporary
    public-log/SSH/dev-OS debug CVM was deleted after evidence collection.
    This proof did not run Tinker bootstrap, billing, API-key provisioning, OTP
    retrieval, or card handling.
  - Historical temporary-public-log evidence from before the 2026-07-08 revert
    confirmed the oracle derived the dstack storage key, found no credentials,
    started in degraded mode, and loaded zero OTP replay entries; delegate logs
    confirmed no Tinker API key was configured. No genesis, captcha, OTP, Tinker
    login, API-key capture, or billing flow ran during that debug window.
  - Source-level email-oracle log hardening and bounded public email surfaces
    are now in the main Phala CVM's pinned oracle image. Public `/health` and
    `/attestation?context=oracle-credentials` return `oracle_email=""` and
    only hash/readiness fields for the sealed mailbox.
  - Main-CVM mailbox genesis proof: a one-shot
    `docker-compose.mailbox-genesis.phala.yaml` update enabled
    `ORACLE_AUTO_GENESIS=true` while keeping `TINKER_BOOTSTRAP_SIGNUP=false`,
    `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`, and credential provisioning
    disabled. Its local raw-compose/image-policy hash was
    `90f4f45c12b645b3b43f6e56c5d5708f2be4c488999a65cd6c391fd09209c027`,
    rendered compose SHA-256 was
    `88f39d901797c5839a8b9cbf11bfa2bb680b54e92fa84e794e79c5a717d0bad3`,
    and live attested compose hash was
    `0541c599acc399f943c6b1804cbf0e8b15aedbf2efeea98d9b2ac856b826f101`.
    `verify-deployment-bundle` passed for that one-shot deployment. The CVM
    was then redeployed back to `docker-compose.all.phala.yaml`; final
    `phala cvms get` showed `auto_genesis=false`, `bootstrap_signup=false`,
    public logs/sysinfo disabled, and the sealed mailbox still ready with the
    same public email hash.
    The one-shot mailbox-genesis compose file has since been refreshed to the
    current GitHub-built oracle/delegate image digests; its local
    raw-compose/image-policy hash is
    `93171544e7dcad7738df2b623625e6fb97ea16557d0e5af6e6fcf9cf9b7a8cac`
    and rendered compose SHA-256 is
    `3bb385928598d63e5697f06d3c34a5ffab23ac547f0c633ac62bf921c7f73d88`.
    That refreshed one-shot profile has not been re-run live because the main
    CVM mailbox is already sealed and ready.
  - Main-CVM Tinker bootstrap proofs: one-shot
    `docker-compose.tinker-bootstrap.phala.yaml` updates enabled only
    `TINKER_BOOTSTRAP_SIGNUP=true` while keeping `ORACLE_AUTO_GENESIS=false`,
    `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`, and credential provisioning
    disabled. The first live run used the pinned headless Playwright sidecar:
    local raw-compose/image-policy hash
    `ae49a564f5b2a49a5ef4942230f293d6437a30c30f9d9e5bce1a5bc21eff6975`,
    rendered compose SHA-256
    `6a6ecc35faa323f9506b259677b4a9747c483ee7c3087f931a5b450f019b5664`,
    and live attested compose hash
    `1a5dc7877d02f15b920736469c1fd4cde750f10f68773b74365257647629c42f`.
    It reached the Tinker auth surface and failed closed with
    `bootstrap_error_kind=auth_access_blocked`; no API key was configured or
    stored. The second live run removed the Playwright sidecar from the
    bootstrap profile and forced the delegate through headed Neko CDP:
    local raw-compose/image-policy hash
    `eabfc81083c93d7ba215a85f23d082641b4e13856cb1c15fe89b40ba8939465b`,
    rendered compose SHA-256
    `07d945588defbf49b1446db916c6bb5a9da1c2aaf2851bfacc6d62848bb26ea1`,
    and live attested compose hash
    `72f91374633541d1f02e467df87473bcd4a7c6e3b539c49be905ae7867023a4c`.
    The third live run used GitHub-attested oracle/delegate images from commit
    `74ad4b6d7359d418507d131a5f30ad7e541987af` with bounded early-stage
    bootstrap instrumentation: local raw-compose/image-policy hash
    `c6da04d12d7bdbfcca6b63a992efed38b2efa1cfc57b7d8e91cec7c15a9f77cc`,
    rendered compose SHA-256
    `70743002dcec8d10d7bacab0da0d0b6c08c54477383edd8a50465fb3f86e5cb8`,
    and live attested compose hash
    `57bbe96fa774fc2e9cfc266ee94526ab6177902654c833b32fced8bc1c801443`.
    `verify-deployment-bundle` passed for all one-shot deployments. In the
    latest headed-Neko run,
    `/health` showed `browser_ws_endpoint=""`,
    `cdp_url=http://172.20.0.3:9223`, `api_key_source=bootstrap`,
    `bootstrap_success=false`, and `bootstrap_error_kind=bootstrap_error`,
    and captured a bounded `last_bootstrap_attempt_record` with
    `surface=tinker_auth`, `outcome=unknown_failure`,
    `furthest_stage=not_started`, and `raw_secret_egress=false`. The outer
    `bootstrap_error_kind` still flattened to `bootstrap_error` in that run.
    The fourth live run used GitHub-attested oracle/delegate images from commit
    `8fb6e3a7dac3ef58f1e4c1e902a36ebd612b910e` and proved the preservation
    fix in Phala: local raw-compose/image-policy hash
    `7773f9be4bfcc5da7eea12f98f49361729879c2aef0c2ba345b6a8cd515215e7`,
    rendered compose SHA-256
    `a71def49759337daf47ed9cb5467614bdfa8970611f4761a9d6494e613eea5aa`,
    live attested compose hash
    `a1d5b65bd12a1a7842cf0999cffea0d3ce665be3e419aeb87e6f9110b4431d34`,
    and `/health.runtime.bootstrap_error_kind=unknown_failure` alongside the
    same bounded nested `tinker_auth` receipt. The oracle stayed ready with
    `oracle_email=""` and the existing mailbox hash, `/pin` still returned 401
    without bearer auth, `/credentials/encrypted` returned 403 while disabled,
    and `/billing/add-balance` returned 403 while disabled. The CVM was then
    redeployed back to `docker-compose.all.phala.yaml`; final health showed
    `api_key_configured=false`, `api_key_source=none`, and
    `bootstrap_attempted=false`.
    The fifth live run used GitHub-attested oracle/delegate images from commit
    `ca877db2d02ee4498d30560f19d4d394cf165676` and enabled
    `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=true` only in the one-shot bootstrap
    profile. Its local raw-compose/image-policy hash was
    `329c9bb241f3ab8c068e38e0321ee7c3a0cc182e1b33f17d06b0521e71316293`,
    rendered compose SHA-256 was
    `5b93911f98626d33ec4d8ca5c42ec031e7d8700ff1e024756f071e8941f58e37`,
    and live attested compose hash was
    `276cf111536f8ac1bdfe628a1e5d7451ea43a8bd895a8e120dd47d16ef7a98d9`.
    `/health` again showed bounded `tinker_auth` `unknown_failure` bootstrap
    evidence with `raw_secret_egress=false`. `GET /browser/selector-probe`
    returned HTTP 503 with bounded `browser_unavailable`,
    `bounded_output=true`, `read_only=true`, and `raw_secret_egress=false`;
    no page text, account identifier, OTP, API key, card material, cookie, or
    raw browser URL was returned. The CVM was then redeployed back to
    `docker-compose.all.phala.yaml`; final health showed
    `api_key_configured=false`, `api_key_source=none`,
    `bootstrap_attempted=false`, and `/browser/selector-probe` returned 403.
  - Public logs are disabled; OTP, Tinker API-key, or card-bearing flows must
    still use only bounded interfaces and disabled endpoint gates must be
    intentionally reopened with fresh evidence.
  - Oracle `/pin` without bearer auth returns `401 Bearer token required`.
  - Public CDP gateway `/json/version` returns host-header rejection rather than
    a usable browser-control response.
  - `verify-cvm-attestation` succeeded against delegate
    `/attestation?context=artifact`: mode `tdx`, quote size `5010`, report data
    `670328b0232c9ed5c7d5dea1b64d4f34a4fcc9c15d3f732466331c31f1a94240`,
    encryption public key
    `44faa46a2b7e25c60899d9f59a7b1e5eb202a5f98653a1e8f31caf0d0f676500`,
    and the attested compose/app/OS-image/image-digest policy above.
  - `verify-deployment-bundle` succeeded against the same delegate endpoint:
    both deploy-critical GHCR image refs verified GitHub SLSA provenance and
    SPDX SBOM attestations for source commit
    `ca877db2d02ee4498d30560f19d4d394cf165676`, the rendered compose included
    those exact oracle/delegate refs plus required Neko and Playwright sidecar
    digests, and the live CVM attestation matched app ID, attested compose hash,
    OS image hash, report data
    `b4c353d94d3295246021b9c8aadc2ede1ae4fdfa09059d13fffdc8d6892302bc`,
    public key
    `5c7f4a6edabf4428bcb8faf7ba1590ed8c28741b73ae5c958af82b52bae3f07e`,
    and quote size `5010`.
  - Oracle `/attestation?context=oracle-credentials` now returns a live TDX
    credential-ingress envelope with report data
    `561e8fd43159ed838406827fb19531880c82e795ddb636dd0fec08f99b91203e`,
    encryption public key
    `6b56f04928d2fe1a6150d3fa48d2591a87a92ebb8d614ef79508ff21dabf5215`,
    quote size `5010`,
    `oracle_email_hash=535adcedea37ac48af0e43720f390125749053a0a0215b669ce55c746cd10132`,
    `oracle_ready=true`, `oracle_email=""`, and no raw credential output.
    `POST /credentials/encrypted` rejects while disabled by default.
  - Delegate `POST /billing/add-balance` rejects while disabled by default
    with a bounded `403` policy error, and no card material is accepted through
    the public endpoint in the current compose.
- `deployments/base-sepolia.json` is now the machine-readable deployment
  manifest. It records the funded current operator deployer, current
  operator-controlled Base Sepolia contracts, and their deployment transaction
  hashes.
- Current operator-controlled Base Sepolia contracts are deployed:
  `DiligenceRoom` at `0x5d8a18628b4c8427eea89aa5498d81ff5ad3f423` and
  `EmailOracleAuth` at `0xf52c18a33bd172ae94282132649d80bcd4b872ff`.
  On-chain reads confirm the current funded Foundry deployer is the
  `DiligenceRoom` developer and `EmailOracleAuth` owner.
- The current Base Sepolia `DiligenceRoom` deployment predates the
  verifier-signature `submitResult()` ABI in this branch. A fresh deployment
  with `DILIGENCE_RESULT_VERIFIER` recorded in the manifest is required before
  claiming the live contract enforces result-verifier authorization.
- Phala CVM deployment with current recorded CVM ID, app ID, compose hash, image
  digests, gateway endpoint, and public dstack quote envelope was revalidated
  with `verify-deployment-bundle`; full Intel TDX quote-internal parsing remains
  incomplete.
- Docker compose validation, docs stale-phrase checks, and broader container
  build CI remain open beyond the current local/CI verification gate.

[planned] Security hardening:

- Full TDX quote verifier.
- Contract-bound attestation policy.
- DLP/egress enforcement beyond bounded route design and redaction tests.
- Reviewer approval flows for widened access.
- Fail-closed bio/dual-use result schema.

## Deployed Resources

Deployment manifest: `deployments/base-sepolia.json`.

`example.env` intentionally leaves these deployment outputs blank:

```text
ESCROW_ADDRESS=
JUDGE_ADDRESS=
PHALA_CVM_ID=
```

Current Base Sepolia contracts:

```text
DiligenceRoom:   0x5d8a18628b4c8427eea89aa5498d81ff5ad3f423
Deployment tx:   0xfa50ada33f0a2c9f434c58b6cadf98defa01302b7c3e444116c021370d28169e
Developer:       0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD

EmailOracleAuth: 0xf52c18a33bd172ae94282132649d80bcd4b872ff
Deployment tx:   0xa29d749517a69f868db1785c7f091ea75f60a76ef657badedb0848e44be7a349
Owner:           0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD
```

On-chain verification reads from the deploy helper:

```text
DiligenceRoom:   0x5d8a18628b4c8427eea89aa5498d81ff5ad3f423
  developer:     0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD
  tx:            0xfa50ada33f0a2c9f434c58b6cadf98defa01302b7c3e444116c021370d28169e
EmailOracleAuth: 0xf52c18a33bd172ae94282132649d80bcd4b872ff
  owner:         0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD
  allowAny:      true
  delay:         172800
  tx:            0xa29d749517a69f868db1785c7f091ea75f60a76ef657badedb0848e44be7a349
```

The historical Base Sepolia `DiligenceRoom` and `EmailOracleAuth` addresses are
now superseded and remain useful only as legacy evidence in older runbooks and
broadcast artifacts.

A deployment is considered production-current only after the manifest records
chain, transaction hashes, verified contract links, Phala CVM ID, app ID,
compose hash, image digest, endpoint, quote evidence, and the commands used to
reproduce or verify them. Missing values must stay `null`, `partial`, or
explicitly legacy.

## Current Blockers

- Real-card Tinker funding requires real payment details and an explicit capped
  attempt.
- Production or repeated card funding needs legal/compliance approval; raw-card
  encrypted delivery remains limited to an operator-owned capped validation
  path.
- Deployed Phala/CVM credential provisioning is present and attested, but
  intentionally disabled by default. It has not been run with real mailbox
  credentials; the oracle has no sealed email credentials, and the delegate has
  no Tinker API key configured.
- Cock.li account genesis inside Phala is source-fixed and debug-proven for the
  standalone oracle-genesis compose, including bounded public `/health` and
  `/attestation` plus runtime-authenticated `/email`. The main combined Phala
  CVM now consumes the bounded oracle image, but `ORACLE_AUTO_GENESIS=false`
  means it still has no generated mailbox credentials for Tinker OTP/login.
- The main Phala CVM still runs a dev OS image (`dstack-dev-0.5.9`,
  `is_dev=true`). Public logs and public sysinfo are off, but production wrap-up
  must move to a non-dev dstack OS image or record a Phala-side blocker; earlier
  `--image dstack-0.5.10* --no-dev-os` attempts failed with a Phala
  `correlationId` validation error, and the latest successful compose/image
  update with `--no-dev-os` still left the CVM reporting dev OS.
- Deployed headed-Neko bootstrap packaging has now been Phala-tested without the
  Playwright sidecar, but Tinker login/API-key capture inside the deployed CVM
  is not yet proven. Bounded early-stage bootstrap receipts and the
  disabled-by-default selector-probe and browser-readiness endpoints are now in
  source and compose; the latest one-shot selector probe returned bounded
  `browser_unavailable`, so actual deployed selector/frame match evidence is
  still open until the readiness diagnostic is built, deployed, and used against
  the live CVM.
- Full Intel TDX quote-internal parsing and quote freshness checking need
  implementation; current verifier checks the public dstack envelope and
  report-data binding only.
- Registry images, pinned digests, SBOM/provenance attestations, and
  compose-hash evidence are complete only for the deploy-critical oracle and
  delegate images, not every side service.
- Real Tinker SDK training/sampling/cleanup inside a deployed CVM is not yet
  proven.
- Bio-validation must remain fail-closed until risk screening, reviewer queues,
  and bounded schemas exist.

## Validation Commands

Focused commands used for the currently built surfaces:

```bash
cd "⚙️/tinker-delegate" && uv run python -m unittest discover -s tests -v
cd "⚙️/tinker-delegate" && uv run python -m compileall tinker_delegate
cd "⚙️/tinker-delegate" && uv lock --check
cd "⚙️/tinker-delegate" && docker build -t dnai-tinker-delegate-agent-extra:local .
cd "⚙️/tinker-delegate" && docker run --rm -d --name dnai-tinker-delegate-agent-extra-check -p 18080:8080 dnai-tinker-delegate-agent-extra:local
cd "⚙️/tinker-delegate" && curl --retry 12 --retry-delay 1 --retry-connrefused --silent --show-error http://127.0.0.1:18080/health
cd "⚙️/tinker-delegate" && docker stop dnai-tinker-delegate-agent-extra-check
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main verify-attestation --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main verify-cvm-attestation --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main verify-deployment-bundle --help
cd "⚙️/tinker-delegate" && scripts/verify-cvm-attestation.sh --help
cd "⚙️/tinker-delegate" && scripts/verify-ghcr-image-attestation.sh --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main verify-compose-hash --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main upload-artifact --help
cd "⚙️/tinker-delegate" && uv run python -m tinker_delegate.main funding-preflight --help

cd "⚙️/tee-email-oracle" && uv run python -m unittest discover -s tests -v
cd "⚙️/tee-email-oracle" && uv run python -m compileall email_oracle

cd "⚙️/tinker-delegate" && \
  scripts/verify-ghcr-image-attestation.sh \
    ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19359e6df891cb48ecf1b051d499d39f2f8a7be2dfe5c62e3c568402cb372f79 \
    --source-digest ca877db2d02ee4498d30560f19d4d394cf165676 \
    --source-ref refs/heads/codex/wikigen-private-reward-pitch \
    --repo G-structure/dnai-wikigen

cd "⚙️/tinker-delegate" && \
  scripts/verify-ghcr-image-attestation.sh \
    ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:16b2dfa8428a8a2f234b5a2ad1dbb57db7cd67ca1e1e655d02633f4201a8506b \
    --source-digest ca877db2d02ee4498d30560f19d4d394cf165676 \
    --source-ref refs/heads/codex/wikigen-private-reward-pitch \
    --repo G-structure/dnai-wikigen

cd "⚙️/tinker-delegate" && \
  uv run python -m tinker_delegate.main verify-cvm-attestation \
    https://f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717-8080.dstack-pha-prod9.phala.network \
    --compose docker-compose.all.phala.yaml \
    --phala-raw-compose \
    --expected-compose-hash 313d34a589316197740b1f81e43b2d1b5bc4ee98985e078bc551e61c96b7c728 \
    --attested-compose-hash d8dbb33db7ec175838c3aca1c4bc2226bf745925b38105c1807789003f594009 \
    --app-id f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717 \
    --os-image-hash de9c74f0c85d0820ce075cb4a99f8e39f7b681be632907c5bf8bdc95ea72feb9 \
    --require-image ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19359e6df891cb48ecf1b051d499d39f2f8a7be2dfe5c62e3c568402cb372f79 \
    --require-image ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:16b2dfa8428a8a2f234b5a2ad1dbb57db7cd67ca1e1e655d02633f4201a8506b \
    --require-image-digest 320c62313c38fd3e6567eef6c8ee78e1d115deb0b88ba60ef02cc4ea7d6ebbea \
    --require-image-digest e3dca7b3c921ce1ebf45a50a6ac77982532c987e5926eb06535b5f56b363b94f

cd "⚙️/tinker-delegate" && \
  uv run python -m tinker_delegate.main verify-deployment-bundle \
    https://f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717-8080.dstack-pha-prod9.phala.network \
    --compose docker-compose.all.phala.yaml \
    --image ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19359e6df891cb48ecf1b051d499d39f2f8a7be2dfe5c62e3c568402cb372f79 \
    --image ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:16b2dfa8428a8a2f234b5a2ad1dbb57db7cd67ca1e1e655d02633f4201a8506b \
    --source-digest ca877db2d02ee4498d30560f19d4d394cf165676 \
    --source-ref refs/heads/codex/wikigen-private-reward-pitch \
    --repo G-structure/dnai-wikigen \
    --phala-raw-compose \
    --expected-compose-hash 313d34a589316197740b1f81e43b2d1b5bc4ee98985e078bc551e61c96b7c728 \
    --attested-compose-hash d8dbb33db7ec175838c3aca1c4bc2226bf745925b38105c1807789003f594009 \
    --app-id f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717 \
    --os-image-hash de9c74f0c85d0820ce075cb4a99f8e39f7b681be632907c5bf8bdc95ea72feb9 \
    --require-image-digest 320c62313c38fd3e6567eef6c8ee78e1d115deb0b88ba60ef02cc4ea7d6ebbea \
    --require-image-digest e3dca7b3c921ce1ebf45a50a6ac77982532c987e5926eb06535b5f56b363b94f

cd "⚙️/tee-email-oracle" && uv run python -m unittest discover -s tests -v
cd "⚙️/tee-email-oracle" && uv run python -m compileall email_oracle
cd "⚙️/tee-email-oracle" && uv run python -m email_oracle.main provision-credentials-encrypted-prompt --help

cd "⚙️/tinker-delegate/contracts" && forge test

git diff --check
```

Before claiming production deployment, also record the deployed-resource
manifest described above and update `ARCHITECTURE.md` from `[partial]` or
`[planned]` to `[real]` only for evidence-backed paths.
