# TODO: Full Latent Vision Roadmap

Last updated: 2026-07-08
Branch context: `tinker-deligate`

This is the build backlog for turning `dnai-wikigen` from the current prototype
into the full latent project: a DevProof-style, attested diligence room where
private artifacts, credentials, source accounts, Tinker compute, bio-validation,
private verified rewards, coordination, and settlement all happen through
bounded, auditable, no-human-key control planes.

The north star:

```text
Seller/controller keeps raw private data and credentials out of human hands.
Buyer/sponsor funds a capped evaluation.
TEE-owned accounts and agents run the evaluation.
Private reward data can score optimization attempts without being disclosed.
Only bounded outputs, hashes, attestations, and settlement data leave.
Every credential, policy change, run, denial, and payout has a verification path.
```

The current repo already has meaningful pieces:

- `DiligenceRoom.sol` escrow and settlement tests.
- `EmailOracleAuth.sol` app-auth contract and tests.
- `tee-email-oracle` service for a TEE-held email account and OTP path.
- `tinker-delegate` service scaffold for a TEE-held Tinker account, billing,
  isolated sessions, evaluator shape, API server, and Phala deployment.
- `props-room` and `whatsapp-delegate` as source/controller/data-room stubs.
- `ARCHITECTURE.md` with the complete current architecture.
- `gate-health-frontend` on a separate branch with the Vite/React demo UI.

The honest current gap:

```text
Email encumbrance: real but runtime enforcement is incomplete.
Tinker encumbrance: scaffolded but signup/funding is blocked upstream.
TTT/RL bio validation: not built; current evaluator is stub/SFT-oriented.
Private verified reward/RLVR environments: concept now clarified, not built.
DNAI settlement: core escrow exists; live attestation, watcher, and full product flow are incomplete.
```

## Priority Legend

- `P0` means the project is not real without it.
- `P1` means the project can demo without it, but cannot be trusted or scaled.
- `P2` means it makes the system product-grade, useful, or defensible.
- `Research` means first prove the route, then split into implementation tasks.
- `Deploy` means a concrete deployment, account, or operational action.

## Non-Negotiable Invariants

- [ ] `P0` Raw private artifacts never leave the TEE boundary.
- [ ] `P0` Email, Tinker, Phala, chain, Stripe, and source-account credentials are
      never committed, logged, echoed into prompts, or exposed to the browser.
- [ ] `P0` No human operator can access the TEE-owned email account or Tinker
      account once production custody is established.
- [ ] `P0` Card/payment material is encrypted to a verified TEE before use and is
      never stored after the billing operation.
- [ ] `P0` Every production TEE image has a reproducible build story:
      git SHA -> image digest -> compose hash -> TDX quote.
- [ ] `P0` On-chain policy freezes compose/app measurements, not individual quote
      hashes. Quotes are fresh evidence; compose hashes are stable policy.
- [ ] `P0` Agents can request, evaluate, and report; agents cannot self-approve
      holds, widen grants, or bypass policy.
- [ ] `P0` Coordination composes policies by intersection, never union.
- [ ] `P0` Bounded outputs are the only egress: score bands, yes/no, hashes,
      offers within cap, methodology summaries, cost/fee records, and audit
      attestations.
- [ ] `P0` Private reward values derived from sealed data do not leave the TEE
      unless they are explicitly released through the bounded-output reducer.
- [ ] `P0` If optimization updates leave the TEE, prove they do not encode
      private reward/data; otherwise keep optimizer state and reward-derived
      gradients inside the attested boundary.
- [ ] `P0` Bio/dual-use outputs must fail closed until the risk screen,
      reviewer queue, and bounded schema are real.

## Milestone 0: Repo Truth, Baseline, And Documentation

- [x] `P0` Commit or otherwise intentionally land `ARCHITECTURE.md`.
      Done when the architecture doc is tracked and reviewers can diff it.
- [x] `P0` Fix stale docs that still say Tinker signup is fully solved by
      `cock.email`, no captcha, or disposable-domain choice.
      Done when `rg "fully working|no captcha|cock.email alone|RESOLVED"` has no
      misleading claims outside historical notes.
- [x] `P0` Update `⚙️/tinker-delegate/SPEC.md` to match current evidence:
      local Neko auth/API-key provisioning works, deployed CVM validation is
      pending, and funding reaches test-card decline but not real account
      funding.
- [x] `P0` Add a `STATUS.md` or status block in `README.md` with:
      built, partial, modeled, planned, deployed addresses, current blockers,
      and test commands.
- [ ] `P0` Sync `.claude/skills/`, `.codex/skills/`, and `.agents/skills/` if any
      skill instructions changed.
- [ ] `P1` Add a `docs/DECISIONS.md` log for irreversible architecture choices:
      one CVM vs split CVMs, quote verification model, funding rails, data
      locality policy, and frontend deployment target.
- [ ] `P1` Add a machine-readable manifest of deployed resources:
      contract addresses, Phala CVM IDs, app IDs, compose hashes, image digests,
      BaseScan links, and gateway endpoints.
- [ ] `P1` Add a one-command local verification script that runs:
      contract tests, Python imports, compile checks, lint where available,
      Docker compose config validation, and docs stale-phrase checks.

## Milestone 1: Contract And Settlement Foundation

### DiligenceRoom vNext

- [ ] `P0` Add a chain watcher that listens for `DealCreated`, `DealFunded`,
      `EvaluationSubmitted`, `DealAccepted`, `DealRejected`, and `DealExpired`
      and calls the TEE control plane.
      Done when a local Anvil or Base Sepolia event creates/updates the matching
      control-plane state without manual curl calls.
- [ ] `P0` Implement TEE-to-chain transaction signing using a dstack-derived
      Ethereum key or equivalent TEE-held signer.
      Done when `submitResult()` can be broadcast from inside the CVM without raw
      private keys or `--private-key`.
- [ ] `P0` Bind `teeIdentity` to an attested compose/app identity instead of a
      bare trusted address.
      Done when result submission proves the signer is controlled by a verified
      measurement.
- [ ] `P0` Add anti-replay material to submitted results:
      `chainId`, contract address, deal ID, nonce, compose hash, result hash,
      score band, compute cost, and expiry.
- [ ] `P0` Define whether quote verification happens on-chain, in a verifier
      contract, through an attestation registry, or through a verified off-chain
      verifier whose signature the contract accepts.
- [ ] `P0` Implement the chosen quote-verification path for `submitResult()`.
      Done when a bogus TEE address cannot submit a result even if it knows the
      deal ID.
- [ ] `P1` Add ERC20/USDC support in addition to native ETH.
      Done when buyer deposits and pull payments work with a stablecoin.
- [ ] `P1` Add protocol-fee configuration with timelock/freeze semantics.
- [ ] `P1` Add staged rental states:
      `raw_inspection`, `training`, `inference`, `full_disclosure`, each with its
      own cap, reserve, result type, and consent requirements.
- [ ] `P1` Add per-query royalty settlement for corpus owners.
      Done when a surfaced turn can meter multiple corpus owners and accrue pull
      payments.
- [ ] `P1` Add settlement conservation fuzz tests for multi-owner and ERC20
      paths.
- [ ] `P1` Add contract-level tests for expiry around in-flight evaluations,
      double-submits, stale quote nonces, and over-budget compute.
- [ ] `P2` Add a public read API or subgraph/indexer for rooms, deals,
      attestations, and payout status.

### TinkerAccountEncumbrance.sol

- [ ] `P0` Decide whether to create a dedicated `TinkerAccountEncumbrance.sol` or
      extend `DiligenceRoom.sol` plus `EmailOracleAuth.sol`.
- [ ] `P0` Specify the on-chain responsibilities of Tinker encumbrance:
      account identity, funding policy, spend limits, approved measurements,
      allowed billing operations, emergency halt, and audit events.
- [ ] `P0` Implement a minimal `TinkerAccountEncumbrance.sol` if the separate
      contract route is chosen.
- [ ] `P0` Add tests proving no manager can exceed owner/deployer-granted
      authority.
- [ ] `P1` Add funding rail policy:
      developer prefund, buyer compute deposit, crypto top-up, A2A/ACH/card
      path, and manual emergency funding.
- [ ] `P1` Emit events for every funding operation:
      requested, authorized, attempted, succeeded, failed, card payload destroyed.
- [ ] `P1` Connect Tinker spend/cost records to buyer escrow and developer fee.

### EmailOracleAuth Completion

- [ ] `P0` Enforce `EmailOracleAuth` at the FastAPI `/pin` and `/inbox`
      endpoints.
      Done when unauthenticated callers cannot retrieve OTPs or inbox metadata.
      - [x] Add runtime bearer guard for `/pin` and `/inbox` so unauthenticated
            network callers cannot retrieve OTPs or inbox metadata.
      - [ ] Check the caller identity against the on-chain `EmailOracleAuth`
            consumer registry before releasing OTP or inbox data.
- [ ] `P0` Register the final oracle compose hash and consumer compose hash on
      Base Sepolia.
- [ ] `P0` Turn off `allowAnyDevice` for production or document why it remains
      allowed during a specific test phase.
- [x] `P0` Implement same-CVM derived-key bearer auth for the current combined
      deployment.
- [ ] `P1` Implement split-CVM runtime auth with RA-TLS or attestation-backed
      signed requests.
- [ ] `P1` Add consumer-manager role tests:
      manager can add/revoke consumers, cannot change oracle code policy, cannot
      unfreeze anything.
- [ ] `P1` Add emergency consumer revocation that is immediate, not timelocked.
- [ ] `P1` Freeze oracle code authorization after the final audited image.
- [ ] `P1` Optionally freeze the consumer registry after final consumer
      measurements are known.
- [ ] `P2` Add on-chain OTP delivery receipts or hashed audit events if needed
      for dispute resolution.

## Milestone 2: DevProof TEE Deployment And Verification

- [ ] `P0` Make every service Dockerfile reproducible:
      pin base images by digest, pin package manager versions, normalize
      timestamps, avoid mutable tags, and generate SBOMs.
- [ ] `P0` Fix the `tinker-delegate` Dockerfile to install the optional Tinker
      agent dependency, not only the base package.
      Done when the CVM image reports `agent_stack_available=true`.
- [ ] `P0` Add a compose-hash verification script that reproduces the Phala
      compose hash from local source and deployed image digests.
- [ ] `P0` Add a TDX quote verifier script for the running CVM.
      Done when a user can verify app ID, compose hash, image digest, report
      data, freshness, and public keys from a laptop.
      - [x] Add an artifact uploader gate that refuses local/default
            attestation, compose-hash mismatch, app-ID mismatch, malformed
            quote/public-key fields, and report-data/key mismatch before
            encryption.
      - [x] Add a standalone `verify-attestation` CLI that live-fetches
            `/attestation` and verifies mode, quote presence, compose hash,
            app ID, OS image hash, public-key shape, report-data key binding,
            and client fetch freshness before accepting the evidence envelope.
      - [ ] Add cryptographic Intel TDX quote parsing and freshness checks;
            current `dstack_sdk` helpers do not expose a complete verifier.
- [ ] `P0` Deploy the combined email-oracle + tinker-delegate stack to Phala
      from registry images only, no local `build:` contexts.
- [ ] `P0` Persist only sealed data under the CVM data volume:
      email creds, Tinker API key, funding token state, and run metadata.
      - [x] Persist email-oracle OTP replay hashes in an encrypted/sealed ledger
            so OTP one-time-use survives service restart without storing OTPs.
      - [x] Store captured Tinker API keys in the encrypted key store and return
            only bounded hash/status metadata from signup/bootstrap.
      - [ ] Confirm funding token state and run metadata are
            sealed/persisted only under the CVM data volume.
- [ ] `P0` Add log scrubbing for OTPs, API keys, card data, bearer tokens, and
      raw artifacts.
      - [x] Stop logging extracted OTP values in the email oracle and Tinker
            delegate, and stop binding raw OTP values into quote report data.
      - [x] Add centralized redaction helpers for bearer tokens, card payloads,
            API keys, OTP/password text, and raw artifact-shaped error text;
            wire them into API errors and high-risk automation logs.
      - [x] Keep secret-bearing screenshots disabled by default and behind
            explicit debug flags.
      - [ ] Add trace-file redaction/deletion if Playwright/browser tracing is
            enabled in a future deployed debugging mode.
- [ ] `P0` Add a deployment runbook section for rollback:
      what is safe to redeploy, what must be frozen, what requires user notice.
- [ ] `P1` Add health endpoints that separate:
      service up, oracle ready, browser ready, Tinker authenticated, funded,
      evaluator ready, chain signer ready, quote verifiable.
- [ ] `P1` Add structured runtime status to `/health` without leaking secrets.
- [ ] `P1` Add Prometheus/OpenTelemetry-compatible metrics:
      run count, denials, holds, funding attempts, Tinker balance band, compute
      cost, failed quote checks, cleanup failures.
- [ ] `P1` Add alerting for:
      low Tinker balance, failed funding, failed OTP, TEE quote mismatch,
      unexpected compose hash, chain watcher lag, stuck deal.
- [ ] `P1` Add a production custom domain via dstack gateway or Cloudflare,
      with verifier documentation.
- [ ] `P2` Add Proof-of-Cloud / platform provenance checks as they become
      available from providers.
      Alignment: Flashbots' recent Proof-of-Cloud work argues ordinary TEE
      attestation does not prove where the hardware is physically operated.
- [ ] `P2` Add a public verification page that walks users through:
      git SHA, image digest, compose hash, TDX quote, contract policy, and
      currently running endpoint.

## Milestone 3: Email, OTP, Browser, And Tinker Account Custody

### Email TEE

- [ ] `P0` Create a production email account whose credentials are generated or
      sealed inside the TEE and never held by a human.
- [ ] `P0` Prove the email TEE can receive Tinker magic-code OTPs in the running
      CVM.
- [ ] `P0` Add outbound email support for:
      reviewer holds, consent confirmations, revocations, bounded-result
      delivery, and recovery notices.
- [x] `P0` Add scoped OTP request API:
      target service, expected sender, expected subject pattern, max age, nonce,
      caller identity, and reason.
- [x] `P0` Add OTP one-time-use semantics so the same code cannot be replayed.
      Released OTP-use hashes are persisted in an encrypted/sealed replay ledger;
      raw OTPs are not stored.
- [ ] `P1` Add mailbox retention policy:
      delete or redact messages after OTP extraction unless retention is
      explicitly required for audit.
- [ ] `P1` Add phishing/prompt-injection handling for inbound email:
      parse only structured OTP and confirmation tokens; never pass arbitrary
      email bodies to an agent without policy checks.
- [ ] `P1` Add a second confirmation channel for high-risk actions:
      wallet signature, WebAuthn, passkey, device-bound Teleport-style session,
      or human reviewer approval.
- [ ] `P2` Add branded `wikigen.me` result delivery once the trust path is real.

### Tinker Browser Auth

- [ ] `P0` Decide the acceptable route for Tinker automation:
      official API/support path, approved service-account flow, or compliant
      browser automation for an account this project controls.
- [ ] `P0` Reproduce the current Tinker auth blocker in a controlled probe:
      local headed Chrome, local Neko, Phala headed Neko, headless Playwright
      sidecar, same email, same IP class where possible.
      - [x] Local Neko/CDP probe against live Tinker UI succeeds: email OTP
            arrives through the oracle, onboarding completes, and API-key
            provisioning captures a one-time `tml-...` key.
      - [ ] Re-test Phala/deployed browser posture with the current selector
            flow before calling production bootstrap solved.
- [ ] `P0` Replace the deployed headless Playwright sidecar with a headed browser
      path that survives Phala packaging if browser automation remains the route.
- [ ] `P0` Capture a selector/frame/auth-flow map for:
      email input, magic-code page, OTP boxes, onboarding, keys page, billing,
      Stripe iframe, balance page, and auto-reload settings.
      - [x] Capture current local selectors for email auth, OTP boxes,
            onboarding, keys page, New key -> Generate key, balance page,
            Add payment method modal, and Stripe card iframe.
      - [ ] Capture deployed-CVM selector/frame evidence after Phala packaging.
- [ ] `P0` Handle Tinker bot/fingerprint checks without evading legal or service
      boundaries.
      Done when the team can explain the account relationship and automation to
      Tinker/Stripe if asked.
- [ ] `P0` Complete Tinker signup inside the CVM:
      email OTP, onboarding, API key creation, encrypted key sealing.
      - [x] Complete local Neko signup/sign-in path through OTP, onboarding, and
            API-key creation.
      - [x] Store local captured API keys in the encrypted key store without
            returning or logging the raw key.
      - [ ] Complete the same flow inside the deployed CVM and seal the API key
            with the dstack-derived key path.
- [ ] `P0` Add a Tinker re-auth path for future OTP challenges.
- [ ] `P1` Add browser session recovery:
      stale OTP page detection, cookie/session expiration, login loop detection,
      screenshot artifacts with secrets redacted.
- [ ] `P1` Add a `cdp-playground` recipe specifically for Tinker auth and
      billing probes.
- [ ] `P1` Add replayable browser tests against mock pages for auth, onboarding,
      key creation, and billing.

### Tinker Funding

- [ ] `P0` Decide the production funding model:
      developer prefund, buyer-funded compute pool, per-deal top-up, account to
      account transfer, crypto-to-fiat bridge, or manual invoice.
- [ ] `P0` Finish the encrypted card channel:
      verify TEE quote, encrypt card payload to TEE public key, decrypt in memory,
      fill billing form, zero memory, and return only bounded status.
      - [x] Local plaintext development path fills the Stripe Elements card
            iframe, zeroes card payload objects, and returns bounded failure
            status without logging card details.
      - [x] Disable plaintext `POST /billing/card` by default, disallow it in
            dstack mode, and wipe plaintext card request objects on success and
            failure.
      - [ ] Exercise the encrypted `/billing/card/encrypted` path against the
            deployed attested endpoint after quote verification.
- [ ] `P0` Prove the Stripe/Tinker billing path end-to-end with a low-value test
      account and a safe test card or approved real card.
      - [x] Stripe test card reaches live Tinker/Stripe submission and returns
            `Your card was declined.`
      - [x] Add-balance fails closed with `Payment method required before adding
            balance` when no real payment method is on file.
      - [ ] Run a capped real-card add-payment-method and low-value add-balance
            attempt after receiving approved card details.
- [ ] `P0` Confirm PCI and Stripe obligations.
      Research whether the current encrypted-card-to-TEE flow is acceptable or
      whether the system must use Stripe-hosted tokenization / SetupIntent /
      PaymentMethod flows.
- [ ] `P0` Ensure no card details appear in:
      browser traces, Playwright logs, screenshots, API logs, exception messages,
      crash dumps, or Phala console output.
- [ ] `P1` Add funding receipt records:
      amount band, timestamp, payment method token/reference, Tinker balance band,
      CVM quote, and card payload destruction proof.
- [ ] `P1` Add budget enforcement:
      Tinker spend cannot exceed buyer cap, room cap, daily cap, or operator cap.
- [ ] `P1` Add top-up policy:
      minimum balance band, max top-up, auto-reload on/off, emergency disable.
- [ ] `P1` Add failure handling:
      card declined, 3DS challenge, bot check, rate limit, insufficient funds,
      Tinker billing outage, partial top-up.
- [ ] `P2` Add crypto/A2A rails only after the basic card or official funding
      route is safe and auditable.

## Milestone 4: Tinker Compute, Private Rewards, And TTT/RL Bio Validation

### Tinker SDK And Isolated Sessions

- [ ] `P0` Run a real Tinker SDK smoke test from inside the deployed CVM.
      Done when the service starts a tiny training job, saves a TTL checkpoint,
      samples from it, and deletes/lets it expire.
- [x] `P0` Add integration tests for `IsolatedTinkerSession` against a mocked
      Tinker SDK.
- [x] `P0` Add real SDK integration tests gated by an env var and budget cap.
- [x] `P0` Enforce one training run per deal in runtime, not only by convention.
- [x] `P0` Enforce checkpoint TTL on every save.
- [x] `P0` Enforce path-checked sampling:
      no arbitrary model path, no cross-deal checkpoint access.
- [x] `P0` Block download/publish/list-all operations from first-party evaluator
      paths.
      Done when `sft_evaluate()` uses only wrapper methods, the wrapper exposes
      no REST/list/download/publish methods, base-model sampling is scoped, and
      tests fail on raw `ServiceClient`/admin API usage in evaluator code.
- [ ] `P0` Put arbitrary third-party evaluator code behind a process or sandbox
      capability boundary.
      Done when untrusted evaluator code cannot use Python introspection to
      recover the raw `ServiceClient`, Tinker API key, checkpoint paths, or
      artifact bytes outside the approved wrapper calls.
- [x] `P0` Implement cleanup with retries and a cleanup attestation.
- [ ] `P1` Add cost metering that reconciles:
      Tinker reported cost, estimated tokens/steps, chain computeCost, and buyer
      budget remaining.
- [ ] `P1` Add model/run metadata limits so user-provided fields cannot leak raw
      private data through Tinker metadata.
- [ ] `P1` Add a simulator/fake Tinker backend for CI and offline demos.

### Private Verified Reward / RLVR Environments

- [x] `P0` Treat the project as building a private verified-reward substrate, not
      only a one-shot evaluator.
      Done when docs and APIs name the abstraction directly: sealed data defines
      a reward oracle; agents optimize candidates against that oracle; only
      bounded reward-derived outputs leave.
- [x] `P0` Create `PROJECT.md` with the formal private-reward security model:
      ideal functionality, leakage function, simulator theorem, query/reward
      leakage bound, assumptions, and limitations.
- [ ] `P0` Keep `PROJECT.md` synchronized with implementation.
      Any environment that releases more than the documented leakage must update
      the theorem assumptions, leakage function, and safety labels before merge.
- [x] `P0` Define the core `PrivateRewardEnvironment` interface:
      `problem()`, `candidate_schema`, `reward(candidate)`,
      `acceptance_policy`, `output_reducer`, `query_budget`, `finalize()`, and
      `attest()`.
- [x] `P0` Define the leakage function for every environment:
      public problem text, accepted candidate count, reward bands or no reward
      egress, final bounded result, timing/cost bands, hashes, and attestations.
- [x] `P0` Decide where the optimizer lives for each security tier:
      inside the same TEE, inside an attested remote Tinker/training service, or
      outside the TEE with no reward-derived state leaving.
- [x] `P0` Prohibit the unsafe default:
      do not send private reward labels, dense rewards, selected-example traces,
      reward-derived gradients, private holdout data, or checkpoints encoding
      private reward information to an untrusted external trainer.
- [x] `P0` Add an internal-only dense-reward mode.
      The optimizer may see exact rewards if it is inside the attested boundary;
      public egress still gets only bounded summaries.
- [x] `P0` Add an external-optimizer-safe mode.
      External LLMs or code generators can propose candidates, but they receive
      only public prompts and approved bounded feedback.
- [x] `P0` Add a reward-query budget and transcript hash for every private
      reward environment.
- [x] `P0` Add a reward precision budget.
      Exact continuous rewards are internal-only; any released reward must be
      quantized, thresholded, noised, or withheld.
- [ ] `P0` Add candidate sandboxing:
      no network, no arbitrary file reads, no write access outside scratch,
      fixed resource limits, bounded stdout/stderr, deterministic seeds where
      feasible, and redacted traces.
  - [x] `P0` Add a local Python candidate sandbox for toy private-reward
        environments: subprocess timeout, scratch cwd, stripped environment,
        deterministic seed, bounded stdout/stderr, static preflight, and
        runtime guards for file, network, process, and import escapes.
  - [ ] `P0` Harden candidate sandboxing with OS/container isolation suitable
        for untrusted third-party code in a deployed CVM.
- [ ] `P0` Add side-channel controls for reward evaluation:
      timing bands, output-size caps, timeout normalization, memory limits, and
      failure-code bucketing.
  - [x] `P0` Add local sandbox side-channel buckets: elapsed timing bands,
        stdout/stderr caps, timeout normalization, best-effort memory limits,
        and public failure-code buckets.
  - [ ] `P0` Harden deployed reward side-channel controls with CVM/container
        resource limits, timeout normalization, failure bucketing, and egress
        auditing for real evaluator/Tinker/browser paths.
- [ ] `P0` Add hidden-holdout separation:
      train/reward split, final validation split, and anti-overfitting checks
      for adaptive query attacks.
  - [x] `P0` Add a hidden-holdout split/accounting contract with train,
        reward, and final-validation partitions, public commitments, bounded
        reward-query tracking, and one-shot final-validation gating.
  - [x] `P0` Wire hidden-holdout checks into a synthetic private-reward
        environment with bounded reward feedback and final-validation gating.
  - [ ] `P0` Wire hidden-holdout checks into concrete private-reward
        environments and add domain-specific anti-overfitting rules.
- [ ] `P1` Implement a toy `private_reward_envs/` package with:
      environment base class, reward evaluator base class, bounded reducer,
      transcript logger, sandbox runner, and tests.
- [ ] `P1` Implement a TTT-Discover-style environment adapter.
      Candidate code is evaluated against private data in the TEE; optimization
      method can be RL, TTT, evolutionary search, or an LLM loop.
- [ ] `P1` Implement a single-cell denoising environment inspired by
      TTT-Discover's biology task.
      Start with public/synthetic OpenProblems-like data, MSE/Poisson-style
      rewards, hidden holdout, and bounded final score bands.
- [ ] `P1` Add reward-oracle proof tests:
      no direct data reads, no exact reward egress in public mode, query budget
      enforced, sandbox egress capped, transcript hash stable.
- [ ] `P1` Add optional differential-privacy accounting for individual-level
      bio data.
      If rewards are released over real individual data, track epsilon/delta or
      explicitly mark the environment as non-DP and not PHI-safe.
- [ ] `P1` Add final-solution disclosure policy.
      Candidate code may be public only if it cannot reconstruct private data
      and passes biosecurity/re-id checks; otherwise release only a hash,
      score band, or escrowed artifact.
- [ ] `P2` Add leaderboard-overfitting defenses:
      canary candidates, held-out final verifier, query throttling, adaptive
      budget cuts, and expert review for surprising high scores.
- [ ] `P2` Add proof-carrying reward transcripts:
      transcript Merkle root, environment hash, candidate hash, reward band,
      final result hash, quote, and chain event.

### Define The Bio Validation Target

- [ ] `P0` Treat `TTT` as method-agnostic in product docs.
      The central primitive is private verified reward. Optimization can be
      reinforcement learning, test-time training, evolutionary search, or an LLM
      loop.
- [ ] `P0` Define the first safe bio-validation use case.
      Candidates:
      synthetic assay QC, de-identified expression classifier, method validation,
      benchmark reproducibility, private reward for computational bio code, or
      non-dual-use model utility scoring.
- [ ] `P0` Define what data is allowed in the first demo.
      Prefer synthetic or public toy data until the policy and reviewer path are
      real.
- [ ] `P0` Define forbidden outputs for bio:
      wetlab protocol details, pathogen enhancement guidance, de novo harmful
      design, identifiable patient-level outputs, raw records, model weights,
      raw samples, and reconstruction-prone statistics.
- [ ] `P0` Define the bounded result schema:
      score band, confidence band, safety band, utility band, methodology class,
      compute cost, data-quality flags, and result hash.
- [ ] `P0` Define benchmark tasks:
      baseline model, adapted model, held-out evaluation, statistical confidence,
      and failure modes.
- [ ] `P0` Define when results must hold for human review instead of releasing.
- [ ] `P1` Add a `bio_validation/` module or package with:
      data loaders, validators, risk screens, evaluator registry, and result
      schema.
- [ ] `P1` Implement a deterministic stub bio evaluator over synthetic data.
- [ ] `P1` Implement a real SFT/LoRA evaluator using Tinker on a toy non-sensitive
      dataset.
- [ ] `P1` Implement the first TTT/RL loop using Tinker docs in
      `📄/thinking-machines/rl/`.
- [ ] `P1` Implement an RLVR-style loop where a candidate computational-bio
      program receives reward from a private TEE-held verifier.
      The loop must work even if the optimizer is swapped between RL, TTT,
      evolutionary search, and an LLM repair loop.
- [ ] `P1` Add data-quality checks:
      schema validation, missingness, leakage, duplicates, class imbalance,
      train/test contamination, and sample-size limits.
- [ ] `P1` Add re-identification risk checks for aggregates and small cohorts.
- [ ] `P1` Add dual-use/risk classifier as deterministic policy, not only LLM
      judgment.
- [ ] `P1` Add methodology summaries that are useful but cannot reconstruct raw
      data.
- [ ] `P2` Add multiple evaluator personas:
      buyer utility, seller protection, biosecurity, data quality, and economics.
- [ ] `P2` Add reproducibility certificates:
      run config hash, data hash, code hash, model base, hyperparameters, random
      seeds, quote, and result hash.

## Milestone 5: DNAI Data Room, Props Room, And Source Custody

### Artifact Ingress And Sealed Storage

- [ ] `P0` Encrypt artifact upload to the TEE public key after verifying the live
      quote.
      - [x] Add encrypted artifact upload endpoint using the attestation-exposed
            TEE public key, artifact-specific HKDF context, and deal/hash-bound
            AES-GCM associated data.
      - [x] Disable plaintext artifact upload by default and in dstack mode.
      - [x] Bind the TEE encryption public key and operation context into
            attestation report data.
      - [x] Add a client-side quote verifier/uploader that refuses to encrypt or
            upload until the live TDX quote, compose hash, and report data pass.
- [x] `P0` Verify `keccak256(rawArtifact) == artifactHash` inside the TEE before
      a deal can proceed.
- [ ] `P0` Add per-corpus/per-deal key derivation:
      no single static artifact key for all rooms.
      - [x] Derive artifact upload AES keys with per-deal/per-artifact HKDF
            context so ciphertexts cannot decrypt under another deal or
            artifact hash even under the same TEE public key.
      - [ ] Add a sealed-storage key hierarchy for retained corpora/rooms if
            post-settlement encrypted artifact retention is implemented.
- [ ] `P0` Ensure artifacts never touch disk unencrypted.
      - [x] Add no-disk-write regression tests around encrypted FastAPI ingress
            and control-plane evaluation dispatch so raw artifact buffers in
            this TEE service path cannot call Python file write/open APIs.
      - [ ] Audit the real SFT evaluator, Tinker SDK calls, browser tracing,
            and deployed debug tooling before claiming the full artifact
            lifecycle never touches disk unencrypted.
- [ ] `P0` Add memory zeroing for raw artifact buffers after resolution.
      - [x] Zero mutable API upload decode buffers after ingress and stored
            control-plane artifact buffers after deal resolution.
      - [ ] Audit evaluator copies and Python immutable byte lifetimes before
            making a production-grade memory-destruction claim.
- [ ] `P1` Add attested destruction or cleanup records:
      artifact deleted, keys dropped, checkpoints deleted/expired.
- [ ] `P1` Add source-controller records:
      who controls the source, what was approved, scope, expiry, revocation, and
      audit hash.
- [ ] `P1` Add data retention policy per room:
      immediate destruction, time-boxed retention, or post-settlement encrypted
      archive.

### Props Room

- [ ] `P0` Connect `props-room` to the on-chain deal lifecycle.
- [ ] `P0` Add real identity/wallet auth to `props-room`.
- [ ] `P0` Add attestation verification for downstream raw scrape, cleaning,
      training, and inference stages.
- [ ] `P1` Wire the `tv` adapter into a real sealed source acquisition demo.
- [ ] `P1` Add a WhatsApp source adapter using `whatsapp-delegate`.
- [ ] `P1` Add staged approvals:
      raw scrape, clean, train, inference, publish, revoke.
- [ ] `P1` Add contributor rights:
      participants receive inference rights or royalty rights on derived models.
- [ ] `P2` Add non-TV adapters:
      FHIR, OMOP, FAIR, GA4GH Beacon, S3/GCS, GitHub private repo, Notion/Drive,
      and arbitrary browser-export sources.

### ConSECA-Style Policy Kernel

- [ ] `P0` Keep the gate as a pure function of `(AccessRequest, CorpusPolicy)`.
- [ ] `P0` Replace hardcoded illustrative gate verdicts with a deterministic
      policy engine.
- [ ] `P0` Add LLM-drafted policy authoring only as a drafting step.
      Enforcement must be deterministic and testable.
- [ ] `P0` Add fail-closed behavior for unknown policy fields, unknown purposes,
      unsupported pipelines, and ambiguous restricted categories.
- [ ] `P1` Add policy tests for every allowed purpose, denied purpose, hold route,
      and restricted category.
- [ ] `P1` Add policy versioning and migration.
- [ ] `P1` Add policy diff review for corpus owners and reviewers.

## Milestone 6: Coordination, Consent, Review, And Governance

- [ ] `P0` Implement the pure coordination reducer described in
      `⚙️/tinker-delegate/docs/COORDINATION-ENGINE-SPEC.md`.
- [ ] `P0` Add tests for:
      all-pass, one-deny, one-hold, restricted-deny, missing consent, revoke
      mid-turn, and delegate-exceeds-scope.
- [ ] `P0` Implement human-review queue:
      ticket creation, role routing, release/deny, reviewer identity, expiry,
      audit trail.
- [ ] `P0` Enforce that delegated agents cannot resolve their own holds.
- [ ] `P0` Implement consent grants:
      purpose, pipeline, requester, expiry, revocation, quorum, and owner.
- [ ] `P0` Implement revocation:
      future and in-flight turns fail closed; prior settled attestations remain
      valid.
- [ ] `P1` Implement joint attestations for multi-corpus turns.
- [ ] `P1` Implement royalty metering for multi-owner surfaced turns.
- [ ] `P1` Implement M-of-N and two-person review for high-stakes routes.
- [ ] `P1` Add separation-of-duties enforcement:
      data owner, session custodian, reviewer, auditor, requester, sponsor.
- [ ] `P2` Add governance templates:
      one-owner, two-biobank collaboration, CRO agent, clinician request,
      sponsor-funded validation, public-good dataset.
- [ ] `P2` Add legal/ethics escalation workflows:
      IRB, DUA, consent evidence, DURC/biosecurity review, export controls where
      applicable.

## Milestone 7: Frontend, Cloudflare, And User Product

- [ ] `P0` Decide how to merge `gate-health-frontend` into `tinker-deligate`.
      Recommended: cherry-pick or merge `⚙️/tinker-delegate/web/`, not replace
      backend/contracts work.
- [ ] `P0` Wire the frontend to real APIs instead of synthetic data:
      health, attestation, rooms, deals, gate verdicts, funding, evaluator status,
      and result verification.
- [ ] `P0` Add wallet connection and role-aware auth:
      seller/controller, buyer/sponsor, reviewer, auditor, admin.
- [ ] `P0` Add seller/controller flow:
      create room, upload encrypted artifact, set reserve, set policy, review
      quote, open deal.
- [ ] `P0` Add buyer/sponsor flow:
      inspect room metadata, verify quote, fund escrow, set budget cap, start
      evaluation, accept/reject.
- [ ] `P0` Add reviewer flow:
      holds queue, policy context, release/deny, reviewer signature, audit record.
- [ ] `P0` Add result verification page:
      result hash, score band, quote, compose hash, chain transaction, payout
      status, cleanup status.
- [ ] `P0` Deploy the frontend to Cloudflare Pages.
- [ ] `P0` Add Cloudflare Worker or API boundary for any server-side frontend
      tasks; no secrets in the static client.
- [ ] `P1` Add optimistic UI and polling for chain/TEE state transitions.
- [ ] `P1` Add a demo mode using synthetic data that is clearly labeled and
      cannot be confused with real private bio data.
- [ ] `P1` Add "explain why denied/held" UI that reveals policy reasons but not
      sensitive internals.
- [ ] `P1` Add an attestation explorer:
      image digest, compose hash, app ID, TDX quote, contract policy, endpoint.
- [ ] `P2` Add guided onboarding:
      create wallet, verify TEE, submit first toy artifact, fund testnet deal.
- [ ] `P2` Add branded `wikigen.me` product language once the trust path is
      actually backed by code.

## Milestone 8: External Alignment And Design Imports

These are not dependencies to blindly copy. They are alignment targets for the
vision Wiki is reaching for.

### Flashbots / Flashbots X Alignment

- [ ] `Research` Study Flashbots' Proof-of-Cloud/DCEA direction and decide how
      much platform provenance `dnai-wikigen` needs for health/bio private-data
      use cases.
      Reference: https://writings.flashbots.net/mind-the-gap-tee-poc
- [ ] `Research` Study the Sirrah/TEE-coprocessor pattern for keeping as much
      trust logic visible in Solidity as possible.
      Reference: https://writings.flashbots.net/suave-tee-coprocessor
- [ ] `P1` Add a "role separation" threat model mirroring Flashbots-style
      mutually distrusting parties:
      operator, data owner, evaluator owner, sponsor, reviewer, hardware/cloud
      provider, chain verifier.
- [ ] `P1` Add a Proof-of-Cloud placeholder in attestation records so it can be
      filled when provider support exists.
- [ ] `P2` Consider whether the evaluation marketplace should eventually look
      like a confidential coprocessor market:
      private inputs, private strategies/agents, public settlement, verifiable
      bounded output.

### Teleport / Account-Link Alignment

- [ ] `Research` Extract the core pattern from Teleport:
      one-time or scoped use of a web2 account, represented as a transferable or
      programmable commitment, enforced by a TEE.
      Reference: https://github.com/teleport-computer/teleport-gramine-rs
- [ ] `P1` Apply the Teleport pattern to Tinker:
      the Tinker account should expose scoped, one-deal compute authority rather
      than raw credentials.
- [ ] `P1` Apply the Teleport pattern to email:
      one OTP or one confirmation is one use; no skipping policy.
- [ ] `P1` Decide whether account-use rights should be represented on-chain:
      NFT, ERC-1155, signed capability, or non-transferable grant.
- [ ] `P2` Build a small one-time capability demo:
      "run this one bounded evaluation" link that expires after use and can be
      verified against a TEE quote.

### Andrew Miller / outh3 / DevProof Alignment

- [ ] `P0` Treat `🔬/amiller/skill-verifier` as the closest implementation
      reference:
      ephemeral execution, inspection certificates, escrow, and deletion.
- [ ] `P0` Treat `🔬/amiller/devproof-audits-guide` as the audit checklist:
      on-chain attestation, auditable code, reproducible builds, no secret
      access, upgrade notice, no centralized hidden dependencies, no backdoors.
- [ ] `P1` Import the dstack-openclaw domain-separation idea:
      the evaluator cannot forge its own genesis/attestation story.
- [ ] `P1` Study `github-zktls-1--groupauth` for multi-TEE trust federation:
      Sigstore/GitHub Actions, dstack KMS, and future Tinker/Phala attestations
      should be able to join one trust graph.
- [ ] `P1` Study `oauth3-openclaw--conseca-policy-engine` for deterministic
      policy enforcement after LLM-assisted drafting.
- [ ] `P1` Study `dshield` / verifiable egress ideas before claiming DLP.
- [ ] `P2` Build a `devproof verify` command for this repo that an external
      judge can run without trusting Wiki, Codex, or the deployer.

### Wiki Leks / Wikigen Product Alignment

- [ ] `P0` Preserve the product's concrete promise:
      "private technical information can be valued without direct disclosure."
- [ ] `P0` Decide the first market:
      bio validation, bug bounty/code audit, private research memo, source-data
      contribution, model/data-room licensing, or agent skill verification.
- [ ] `P1` Build one tight demo story rather than all markets at once.
      Recommended first real story:
      synthetic/private bio artifact -> TEE ingress -> Tinker toy training ->
      bounded validation band -> Base Sepolia settlement -> verifier page.
- [ ] `P1` Add copy that distinguishes:
      NDAI economics, TEE custody, Tinker compute, email OTP custody, and
      coordination/governance.
- [ ] `P2` Build "catalog" only after the backend trust path can support at least
      one real room end-to-end.

## Milestone 9: Compliance, Safety, And Abuse Resistance

- [ ] `P0` Write a data-classification policy:
      public demo, synthetic, confidential business, PHI/health, biosecurity
      sensitive, dual-use, illegal/forbidden.
- [ ] `P0` Until reviewed, restrict real demos to synthetic or public toy data.
- [ ] `P0` Decide HIPAA/PHI stance:
      not supported, supported only with BAA/compliant infra, or supported only
      for de-identified data.
- [ ] `P0` Decide Stripe/PCI stance before real card funding.
- [ ] `P0` Decide Tinker Terms-of-Service stance for browser automation and
      delegated account use.
- [ ] `P0` Add abuse policy for:
      credential theft, spam, bot evasion, account resale, dual-use bio,
      re-identification, malware, exploit sale, and sanctions/export issues.
- [ ] `P1` Add legal terms for:
      seller warranties, buyer usage limits, data retention, dispute process,
      evaluator error, and bounded-output limitations.
- [ ] `P1` Add incident response:
      leaked secret, wrong compose hash, TEE compromise, bad reviewer release,
      result over-disclosure, card data exposure, stuck funds.
- [ ] `P1` Add kill switches:
      pause new rooms, pause Tinker execution, pause funding, revoke consumers,
      freeze oracle code, pause frontend.
- [ ] `P1` Add audit log retention rules and privacy-preserving audit views.
- [ ] `P2` Commission external security review before any real private health or
      payment data.

## Milestone 10: CI, Testing, And Quality Gates

- [ ] `P0` Add CI for Foundry contracts:
      `forge build`, `forge test`, gas snapshot, coverage if feasible.
- [ ] `P0` Add CI for Python packages:
      `uv sync`, import checks, unit tests, compileall, type checks where set up.
- [ ] `P0` Add CI for frontend once merged:
      `npm ci`, `npm test`, `npm run build`, `npm audit --omit=dev`.
- [ ] `P0` Add secret scanning in CI.
- [ ] `P0` Add Docker build checks for every service.
- [ ] `P0` Add integration test for local simulator:
      Anvil + Phala simulator + email oracle + tinker fake backend + frontend.
- [ ] `P1` Add property tests for:
      settlement conservation, coordination reducer, policy fail-closed, bounded
      output schema, revocation behavior.
- [ ] `P1` Add browser tests for:
      Tinker auth mock, Stripe mock, reviewer queue, deal creation, result page.
- [ ] `P1` Add load tests for:
      many rooms, many OTP requests, chain watcher reorgs, evaluator timeouts.
- [ ] `P1` Add disaster tests:
      CVM restarts during evaluation, chain watcher misses event, Tinker outage,
      browser crash, cleanup failure.
- [ ] `P2` Add reproducibility test:
      clean checkout -> build images -> same digest/compose hash or explainable
      delta.

## Milestone 11: Operational Deployment Tasks

- [ ] `Deploy` Create/fill `.env` locally from `example.env` without committing
      secrets.
- [ ] `Deploy` Verify Foundry keystore account `dev` exists and is funded for
      Base Sepolia.
- [ ] `Deploy` Verify Cloudflare Wrangler login for frontend deployment.
- [ ] `Deploy` Verify Phala CLI login and profile.
- [ ] `Deploy` Verify Docker registry credentials and decide permanent registry.
- [ ] `Deploy` Rebuild and publish pinned images for:
      email oracle, tinker delegate, Neko/browser sidecar, props room, frontend
      worker if any.
- [ ] `Deploy` Redeploy Phala CVM with final image digests.
- [ ] `Deploy` Verify CVM endpoints:
      `/health`, `/attestation`, oracle `/pin` auth rejection, delegate status,
      browser CDP internal-only or protected.
- [ ] `Deploy` Deploy or update Base Sepolia contracts with the chosen vNext
      interfaces.
- [ ] `Deploy` Verify contracts on BaseScan.
- [ ] `Deploy` Register compose hashes in `EmailOracleAuth`.
- [ ] `Deploy` Register consumer app/compose hash for Tinker delegate.
- [ ] `Deploy` Create a test Tinker account under TEE custody.
- [ ] `Deploy` Fund the Tinker account through the chosen safe route.
- [ ] `Deploy` Run a tiny funded Tinker job and record the attestation.
- [ ] `Deploy` Create a synthetic test room on Base Sepolia.
- [ ] `Deploy` Fund the synthetic test deal.
- [ ] `Deploy` Upload encrypted synthetic artifact.
- [ ] `Deploy` Run evaluator.
- [ ] `Deploy` Submit result on-chain.
- [ ] `Deploy` Accept/reject/expire the deal and withdraw funds.
- [ ] `Deploy` Confirm cleanup of artifact and checkpoints.
- [ ] `Deploy` Deploy frontend to Cloudflare Pages.
- [ ] `Deploy` Smoke-test the public URL from a clean browser.
- [ ] `Deploy` Archive deployment evidence:
      git SHA, image digests, compose hash, quote, tx hashes, screenshots, logs
      with secrets redacted.

## Milestone 12: Demo Ladder

### Demo 1: Honest Current Demo

- [ ] `P0` Show contracts deployed and verified.
- [ ] `P0` Show live Phala CVM health and quote.
- [ ] `P0` Show email oracle receives OTPs, but do not claim Tinker funding is
      solved.
- [ ] `P0` Show stub evaluator and bounded output only.
- [ ] `P0` Show Base Sepolia fund -> result -> accept/reject/expire.

### Demo 2: End-To-End Synthetic DNAI

- [ ] `P0` Synthetic private artifact upload encrypted to TEE.
- [ ] `P0` Buyer funds escrow with cap.
- [ ] `P0` Evaluator runs inside TEE.
- [ ] `P0` Result hash and bounded band submitted on-chain.
- [ ] `P0` Frontend verifies quote, compose hash, and chain events.
- [ ] `P0` Settlement and cleanup complete.

### Demo 3: Tinker-Funded Training

- [ ] `P0` TEE-owned Tinker account exists.
- [ ] `P0` Tinker account has safe test funding.
- [ ] `P0` Isolated session runs tiny training.
- [ ] `P0` Checkpoints are TTL-limited and cleaned up.
- [ ] `P0` No weights, samples, raw artifact, or API key leave the TEE.

### Demo 4: Bio Validation

- [ ] `P1` Use synthetic/non-sensitive bio data.
- [ ] `P1` Run SFT or TTT/RL validation.
- [ ] `P1` Apply dual-use screen.
- [ ] `P1` Release only bounded score/safety/methodology bands.
- [ ] `P1` Route ambiguous result to reviewer hold.

### Demo 5: Multi-Owner Coordination

- [ ] `P1` Two synthetic corpora.
- [ ] `P1` Fan-out gate per corpus.
- [ ] `P1` Unanimous consent for pass.
- [ ] `P1` One hold route to human reviewer.
- [ ] `P1` One restricted deny that consent cannot override.
- [ ] `P1` Joint attestation and per-owner royalty meters.

### Demo 6: DevProof Public Verification

- [ ] `P1` External user verifies:
      source, image digest, compose hash, quote, contract policy, result hash,
      settlement, and cleanup evidence.
- [ ] `P1` Public docs explain what is trusted, what is verified, and what is not
      yet guaranteed.

## Open Questions To Resolve

- [ ] `Research` Which private-reward security tier is acceptable for the first
      demo:
      all optimizer state inside TEE, attested remote trainer, or external LLM
      with only bounded feedback?
- [ ] `Research` If Tinker receives training updates, can it be included in the
      trusted boundary by attestation, contract, or policy? If not, what reward
      signals are forbidden from leaving the TEE?
- [ ] `Research` Which reward leakage budget is acceptable:
      no public reward egress, k-bit reward bands, noisy rewards, only final
      score, or differential privacy?
- [ ] `Research` What exact TTT-Discover biology task should be cloned first:
      OpenProblems-style single-cell denoising, synthetic denoising, or a safer
      toy computational-bio benchmark?
- [ ] `Research` What exact Tinker billing/funding flow is allowed by Tinker and
      Stripe?
- [ ] `Research` Should card details ever be delivered to the TEE, or should the
      system use a Stripe-hosted tokenization flow where the TEE only receives a
      payment method token?
- [ ] `Research` Should the Tinker account be one global TEE-owned account,
      per-sponsor, per-room, or per-corpus?
- [ ] `Research` What is the correct legal owner of the Tinker account and email
      account?
- [ ] `Research` Which jurisdiction/data-residency requirements matter for bio
      data?
- [ ] `Research` What is the minimum bio demo that is useful but cannot enable
      dual-use harm?
- [ ] `Research` When can candidate code be revealed?
      Public release is only safe if the code cannot encode private data,
      exploit reward overfitting, or reveal bio-sensitive methods.
- [ ] `Research` How much quote verification belongs on-chain vs off-chain?
- [ ] `Research` Can Phala/dstack expose enough platform provenance for the
      health/bio trust model, or do we need an explicit Proof-of-Cloud caveat?
- [ ] `Research` What should be represented on-chain:
      rooms, policies, grants, attestations, capabilities, result hashes,
      royalties, or only settlement?
- [ ] `Research` Should `wikigen` support public catalog/search before it can
      enforce private data policy?
- [ ] `Research` Is the first launch a developer demo, bio diligence product,
      private data marketplace, agent credential delegation product, or all of
      those staged separately?

## Suggested Immediate Next Build Order

1. [x] Track `PROJECT.md`, `ARCHITECTURE.md`, and this `TODO.md`.
2. [x] Fix stale Tinker status in `⚙️/tinker-delegate/SPEC.md`.
3. [x] Define the `PrivateRewardEnvironment` interface and leakage model.
4. [ ] Build a fake private-reward environment with a synthetic hidden dataset.
5. [ ] Fix `tinker-delegate` Docker install so the Tinker SDK path is present in
       the deployed image.
6. [ ] Enforce oracle auth on `/pin` and `/inbox`.
       Runtime bearer auth is implemented; on-chain `EmailOracleAuth` consumer
       registry enforcement remains.
7. [ ] Add chain watcher + TEE chain signer for `DiligenceRoom`.
8. [ ] Build a fake Tinker backend and full local synthetic room test.
9. [ ] Rework deployed browser path to headed Neko inside Phala, or get an
       official Tinker service-account/API route.
10. [ ] Prove safe Tinker account funding with a low-value test.
       Test-card path reaches Stripe decline and add-balance fail-closed state;
       real capped funding attempt needs approved card details.
11. [ ] Run one real tiny Tinker training session through `IsolatedTinkerSession`.
12. [ ] Merge the `gate-health-frontend` UI and wire it to real verifier/status
       APIs.

## External Alignment References

- Flashbots, "Mind the Gap - Where TEE Attestations Fall Short and Why Do TEEs
  Need Proof of Cloud": https://writings.flashbots.net/mind-the-gap-tee-poc
- Flashbots, "Sirrah: Speedrunning a TEE Coprocessor":
  https://writings.flashbots.net/suave-tee-coprocessor
- Teleport / Account-Link one-time account delegation:
  https://github.com/teleport-computer/teleport-gramine-rs
- Gramine attestation and secret provisioning reference:
  https://gramine.readthedocs.io/en/latest/attestation.html
- Andrew Miller research profile: https://soc1024.ece.illinois.edu/
