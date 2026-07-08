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
Tinker encumbrance: local contract plus runtime preflight exist; deployment and live funding remain incomplete.
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
      Started with the result-submission quote-verification decision. Remaining
      entries still need to record CVM topology, funding rails, data locality,
      and frontend deployment target before this P1 is complete.
- [x] `P1` Add a machine-readable manifest of deployed resources:
      contract addresses, Phala CVM IDs, app IDs, compose hashes, image digests,
      BaseScan links, and gateway endpoints.
      Done in `deployments/base-sepolia.json`: the manifest records the current
      funded operator deployer, legacy Base Sepolia contracts with on-chain
      owner/developer reads, historical Phala/CVM evidence from the runbook, and
      the fresh-deployment helper/status without storing secrets.
- [x] `P1` Add a one-command local verification script that runs:
      contract tests, Python imports, compile checks, lint where available,
      Docker compose config validation, and docs stale-phrase checks.
      Done for the current implemented gates in `scripts/verify-local.sh`: it
      runs the repo secret scan, Foundry build/tests, frozen `uv` sync,
      Python compile checks, and Python unit tests where test suites exist.
      Docker compose validation and docs stale-phrase checks remain candidates
      for a later broader verification pass.

## Milestone 1: Contract And Settlement Foundation

### DiligenceRoom vNext

- [x] `P0` Add a chain watcher that listens for `DealCreated`, `DealFunded`,
      `EvaluationSubmitted`, `DealAccepted`, `DealRejected`, and `DealExpired`
      and calls the TEE control plane.
      Done when a local Anvil or Base Sepolia event creates/updates the matching
      control-plane state without manual curl calls.
      - [x] Add a JSON-RPC DiligenceRoom event decoder/dispatcher, bounded
            `/deal/chain-event` audit endpoint, `watch-chain` CLI, and tests
            proving `DealCreated` + `DealFunded` dispatch can call
            `/deal/notify-funded` while resolution events call
            `/deal/{deal_id}/resolve`.
      - [x] Prove the watcher against a local Anvil or Base Sepolia event so a
            real contract log creates/updates matching control-plane state.
            Done with `⚙️/tinker-delegate/scripts/prove-chain-watcher-anvil.py`:
            it starts ephemeral Anvil, deploys `DiligenceRoom` through an
            unlocked local account, emits real `DealCreated`/`DealFunded`
            logs, runs the watcher over JSON-RPC, and verifies a bounded
            control-plane stub receives deal `0` funded state without manual
            curl calls or raw private-key flags.
      - [x] Add durable cursor storage, restart recovery, and reorg/confirmation
            policy before production use.
            Done with `ChainCursorStore` plus `watch-chain --cursor-store`:
            the watcher persists next block, confirmation depth, contract hash
            summary, and public `DealCreated` context; restart tests prove a
            later `DealFunded` can still notify `/deal/notify-funded`; polling
            advances only after successful dispatch and only over
            confirmation-safe blocks.
      Production note: deployment wiring, chain-lag alerting, and any stricter
      deep-reorg rollback policy remain covered by later operations tasks, not
      this local watcher P0.
- [ ] `P0` Implement TEE-to-chain transaction signing using a dstack-derived
      Ethereum key or equivalent TEE-held signer.
      Done when `submitResult()` can be broadcast from inside the CVM without raw
      private keys or `--private-key`.
      - [x] Add a dstack-derived Ethereum signer and bounded
            `submit-result` broadcaster for `DiligenceRoom.submitResult()`.
            The submitter has no raw-private-key CLI/env path, derives the
            production signer from dstack key material, preflights the public
            `deals(dealId)` state so the signer must match `teeIdentity`, checks
            funded state and compute budget before signing, broadcasts a raw
            transaction through JSON-RPC, and returns only bounded receipt
            metadata.
      - [x] Prove the submitter from a dstack simulator or deployed CVM against
            Anvil/Base Sepolia so `submitResult()` is actually broadcast from
            inside the attested runtime.
            Done with
            `⚙️/tinker-delegate/scripts/prove-chain-submitter-dstack-anvil.py`:
            it uses the Phala/dstack simulator as the key source, derives the
            TEE Ethereum signer inside the `submit-result` CLI path, funds that
            signer on ephemeral Anvil, creates/funds a DiligenceRoom deal with
            the derived signer as `teeIdentity`, broadcasts `submitResult()`,
            and verifies the real `EvaluationSubmitted` event without accepting
            or printing raw private keys.
      - [ ] Repeat the submitter proof from a deployed Phala CVM before marking
            production CVM signing complete.
- [ ] `P0` Bind `teeIdentity` to an attested compose/app identity instead of a
      bare trusted address.
      Done when result submission proves the signer is controlled by a verified
      measurement.
- [x] `P0` Add anti-replay material to submitted results:
      `chainId`, contract address, deal ID, nonce, compose hash, result hash,
      score band, compute cost, and expiry.
      Done in `tinker_delegate.chain_submitter`: the value submitted to
      `DiligenceRoom.resultHash` is now an anti-replay commitment over those
      fields, while the original bounded payload result hash remains separate
      in the bounded receipt as `payload_result_hash`. The dstack-simulator
      Anvil proof verifies the `EvaluationSubmitted.result_hash` equals the
      submission commitment and is not the raw payload hash.
- [x] `P0` Define whether quote verification happens on-chain, in a verifier
      contract, through an attestation registry, or through a verified off-chain
      verifier whose signature the contract accepts.
      Decision recorded in `docs/DECISIONS.md`: current path is a verified
      off-chain submitter gate plus a `DiligenceRoom` result-verifier signature.
      The remaining gap is the production verifier service that validates live
      Phala quote evidence, compose/app identity, freshness, and revocation
      before issuing signatures.
- [ ] `P0` Implement the chosen quote-verification path for `submitResult()`.
      Done when a bogus TEE address cannot submit a result even if it knows the
      deal ID.
      - [x] Implement the pre-broadcast off-chain verifier gate in the
            `submit-result` path: dstack mode is required, signer quote evidence
            must match signer address, chain ID, contract address, report data,
            quote report data, and compose hash, and the bounded receipt carries
            quote hash/report-data/size without raw secret egress.
      - [x] Add verifier-signature contract or registry enforcement so a bogus
            bare `teeIdentity` cannot submit through the Solidity entrypoint.
            Done in `DiligenceRoom.sol`: `submitResult()` now requires an
            Ethereum-signed verifier authorization over chain ID, contract
            address, deal ID, TEE identity, compose hash, score band, compute
            cost, result commitment, and authorization expiry. Contract tests
            prove wrong verifier, expired authorization, and zero compose hash
            fail; the dstack-simulator Anvil proof uses an unlocked local
            verifier account to authorize the real CLI submission without raw
            verifier key material.
      - [ ] Build the production verifier service/path that validates live
            Phala quote evidence, approved compose/app identity, freshness, and
            revocation policy before issuing verifier signatures.
            - [x] Add a bounded result-verifier authorization module.
                  Done in `tinker_delegate.result_verifier`: it validates signer
                  attestation evidence against signer address, chain ID,
                  contract, report data, quote report data, approved compose
                  hashes, approved app IDs, optional OS image hashes, revoked
                  quote hashes, revoked TEE signers, and a short authorization
                  TTL before signing the exact `DiligenceRoom` authorization
                  digest. Tests cover accepted authorization, policy mismatch,
                  quote-context mismatch, revocation, self-approval rejection,
                  and dstack-only verifier key custody.
            - [x] Wrap the verifier module as a deployed service or operator
                  path that receives bounded quote evidence from the submitter
                  and returns only authorization metadata/signature.
                  Done as the `result-verifier-address` and `authorize-result`
                  CLIs. `authorize-result` accepts bounded signer-attestation
                  JSON plus explicit compose/app/OS-image allowlists and
                  revocation lists, derives the verifier key from dstack, emits
                  only bounded authorization metadata plus the public verifier
                  signature needed by the contract, and has no raw-private-key
                  flags. The dstack-simulator Anvil proof now deploys
                  `DiligenceRoom` with the dstack-derived verifier address and
                  obtains authorization via this CLI path instead of Anvil
                  `eth_sign`.
            - [ ] Add cryptographic Intel TDX quote parsing/freshness once the
                  production quote evidence format is available.
      - [ ] Repeat the verifier-authorized submitter proof from a deployed Phala
            CVM against Base Sepolia or an Anvil fork.
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

- [x] `P0` Decide whether to create a dedicated `TinkerAccountEncumbrance.sol` or
      extend `DiligenceRoom.sol` plus `EmailOracleAuth.sol`.
      Decided in code/docs: use a dedicated minimal
      `TinkerAccountEncumbrance.sol` for Tinker account policy/audit, separate
      from `DiligenceRoom` escrow settlement and `EmailOracleAuth` OTP
      consumer policy.
- [x] `P0` Specify the on-chain responsibilities of Tinker encumbrance:
      account identity, funding policy, spend limits, approved measurements,
      allowed billing operations, emergency halt, and audit events.
      Done in `TinkerAccountEncumbrance.sol`: it stores a hashed account
      commitment, approved compose hashes, per-operation add-balance/spend caps,
      manager delegation, measurement freeze, emergency halt, operation
      authorization, and bounded receipt settlement events.
- [x] `P0` Implement a minimal `TinkerAccountEncumbrance.sol` if the separate
      contract route is chosen.
      Done with the dedicated contract under
      `⚙️/tinker-delegate/contracts/src/TinkerAccountEncumbrance.sol`.
- [x] `P0` Add tests proving no manager can exceed owner/deployer-granted
      authority.
      Done in `TinkerAccountEncumbrance.t.sol`: managers can authorize/settle
      bounded operations inside owner-set caps and approved measurements, but
      cannot set managers, change caps, approve measurements, toggle emergency
      halt, exceed caps, or bypass compose/emergency/duplicate guards.
- [x] `P0` Add a local runtime preflight/helper that reads
      `TinkerAccountEncumbrance` before browser-mediated Tinker funding.
      Done with `tinker_encumbrance.py`, the `tinker-encumbrance-preflight`
      CLI, funding-preflight integration, and card/add-balance handler gates.
      When `TINKER_ENCUMBRANCE_REQUIRED=true` or a contract address is
      configured, payment-method and add-balance automation deny before
      decryption/browser launch unless the compose hash is approved, the
      contract is not halted, and the amount is within cap.
- [ ] `P1` Add funding rail policy:
      developer prefund, buyer compute deposit, crypto top-up, A2A/ACH/card
      path, and manual emergency funding.
- [ ] `P1` Emit events for every funding operation:
      requested, authorized, attempted, succeeded, failed, card payload destroyed.
- [ ] `P1` Connect Tinker spend/cost records to buyer escrow and developer fee.

### EmailOracleAuth Completion

- [x] `P0` Enforce `EmailOracleAuth` at the FastAPI `/pin` and `/inbox`
      endpoints.
      Done when unauthenticated callers cannot retrieve OTPs or inbox metadata.
      - [x] Add runtime bearer guard for `/pin` and `/inbox` so unauthenticated
            network callers cannot retrieve OTPs or inbox metadata.
      - [x] Check the caller identity against the on-chain `EmailOracleAuth`
            consumer registry before releasing OTP or inbox data.
            Done with `email_oracle.chain_auth` and FastAPI guards for `/pin`
            and `/inbox`. When `ORACLE_AUTH_REQUIRED=true` or a contract is
            configured, the service fails closed before IMAP access unless
            `isConsumerAuthorized(ORACLE_AUTH_CONSUMER_APP_ID,
            ORACLE_AUTH_CONSUMER_COMPOSE_HASH)` returns true; optional
            `ORACLE_AUTH_EXPECTED_CALLER_IDENTITY` binds `/pin` request metadata.
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
      - [x] Pin the deploy-critical `tinker-delegate` and `tee-email-oracle`
            Dockerfile Python and `uv` image sources by versioned digest.
      - [x] Add GitHub-hosted image builds for the deploy-critical services
            that push `linux/amd64` GHCR images with BuildKit SBOM/provenance
            attestations plus GitHub-signed provenance and SPDX SBOM
            attestations.
      - [x] Add `scripts/verify-ghcr-image-attestation.sh` to fail deployment
            unless a digest-pinned GHCR image verifies against the expected
            GitHub repo, signer workflow, source commit, SLSA provenance
            predicate, and SPDX SBOM predicate.
      - [ ] Pin apt package versions, normalize timestamps, and generate
            release SBOM evidence for every remaining service Dockerfile.
- [x] `P0` Fix the `tinker-delegate` Dockerfile to install the optional Tinker
      agent dependency, not only the base package.
      Done when the CVM image reports `agent_stack_available=true`.
      `⚙️/tinker-delegate/scripts/verify-agent-image.sh` now rebuilds the image
      and verifies `import tinker` plus the `agent_stack_available` probe inside
      the packaged image.
- [x] `P0` Add a compose-hash verification script that reproduces the Phala
      compose hash from local source and deployed image digests.
- [ ] `P0` Add a TDX quote verifier script for the running CVM.
      Done when a user can verify app ID, compose hash, image digest, report
      data, freshness, and public keys from a laptop.
      - [x] Add an artifact uploader gate that refuses local/default
            attestation, compose-hash mismatch, app-ID mismatch, malformed
            quote/public-key fields, and report-data/key mismatch before
            encryption.
      - [x] Add a standalone `verify-attestation` CLI that live-fetches
            `/attestation?context=...` and verifies mode, quote presence,
            compose hash, app ID, OS image hash, public-key shape, report-data
            key binding, and client fetch freshness before accepting the
            evidence envelope.
      - [x] Reject exposed `quote_report_data` unless it is a 32-byte hex value
            exactly matching the context/key-bound `report_data`; this tightens
            the public quote envelope without claiming full quote parsing.
      - [x] Add `verify-cvm-attestation` and
            `scripts/verify-cvm-attestation.sh` so an operator can tie a live
            CVM attestation to the locally rendered Phala compose hash and
            required digest-pinned images from a laptop.
      - [x] Add `verify-deployment-bundle` so an operator can verify the full
            current deploy chain in one bounded JSON packet: GitHub-signed SLSA
            provenance and SPDX SBOM attestations for digest-pinned GHCR
            oracle/delegate images, those exact image refs in the Phala compose,
            required sidecar digests, and the live CVM app/compose/OS-image
            attestation envelope.
      - [ ] Add cryptographic Intel TDX quote parsing and quote-internal
            freshness checks; current `dstack_sdk` helpers do not expose a
            complete verifier.
      - [x] Run `verify-cvm-attestation` against a real Phala CVM and record
            app ID, compose hash, image digest, report data, public key,
            fetched-at time, and command evidence in `STATUS.md`.
      - [x] Run `verify-deployment-bundle` against the current Phala CVM and
            record the combined GitHub-attestation-to-Phala-attestation evidence
            in `STATUS.md`.
- [x] `P0` Deploy the combined email-oracle + tinker-delegate stack to Phala
      from registry images only, no local `build:` contexts.
      Done 2026-07-08: CVM `670b3b21-4338-4d4e-ae72-7c8922579f59`
      runs app ID `f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717` from
      digest-pinned GHCR oracle/delegate images plus digest-pinned Neko and
      Playwright sidecars. Oracle is intentionally degraded until email
      credentials are provisioned; delegate health is `ok` with no API key
      configured and `bootstrap_attempted=false`.
- [ ] `P0` Persist only sealed data under the CVM data volume:
      email creds, Tinker API key, funding token state, and run metadata.
      - [x] Persist email-oracle OTP replay hashes in an encrypted/sealed ledger
            so OTP one-time-use survives service restart without storing OTPs.
      - [x] Add attestation-bound encrypted ingress for existing email
            credentials: `GET /attestation?context=oracle-credentials` exposes
            a quote-bound public key, `POST /credentials/encrypted` is disabled
            by default behind an explicit provisioning token, stores credentials
            through the sealed credential store, and returns only hashes/status.
      - [x] Store captured Tinker API keys in the encrypted key store and return
            only bounded hash/status metadata from signup/bootstrap.
      - [x] Bound Tinker signup/signin observable outputs before deployed
            bootstrap: signup/signin stdout and return payloads now expose
            `email_hash` / `url_hash` instead of raw mailbox addresses or
            Tinker URLs, and regression tests cover stdout and result egress.
      - [x] Confirm currently implemented funding state and run metadata are
            sealed/persisted only under the CVM data volume: bounded funding
            receipts use `/data/funding_receipts.enc`, and control-plane deal
            lifecycle metadata now uses `/data/run_metadata.enc` with a
            separate dstack key path and hashed/banded fields only.
      - [ ] Blocked until official/tokenized funding is available: if a future
            Tinker/Stripe payment-method token or reusable funding reference is
            captured, persist only opaque/token hashes or bounded status under
            sealed delegate storage and never expose raw card material.
- [x] `P0` Add log scrubbing for OTPs, API keys, card data, bearer tokens, and
      raw artifacts.
      - [x] Stop logging extracted OTP values in the email oracle and Tinker
            delegate, and stop binding raw OTP values into quote report data.
      - [x] Add centralized redaction helpers for bearer tokens, card payloads,
            API keys, OTP/password text, and raw artifact-shaped error text;
            wire them into API errors and high-risk automation logs.
      - [x] Hash email-oracle genesis/signup/check log identifiers instead of
            printing raw generated mailbox addresses, generated usernames,
            IMAP sender filters, or mail subject/sender headers. Covered by
            `tee-email-oracle/tests/test_log_hygiene.py`.
      - [x] Hash Tinker signup/signin mailbox and browser URL identifiers in
            stdout/CLI-visible results, and redact email addresses in shared
            Tinker delegate error rendering. Covered by
            `tests.test_signup_key_egress` and `tests.test_redaction`.
      - [x] Keep secret-bearing screenshots disabled by default and behind
            explicit debug flags.
      - [x] Add trace/HAR/video/card-screenshot deletion for configured browser
            debug artifact directories after card submission attempts.
- [x] `P0` Add a deployment runbook section for rollback:
      what is safe to redeploy, what must be frozen, what requires user notice.
      Done in `⚙️/tinker-delegate/docs/DEPLOYMENT-RUNBOOK.md`: rollback rules
      now distinguish safe test redeploys from frozen policy roots, funded
      contracts, published compose/image/app trust roots, and sealed state.
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
      - [x] Add the encrypted operator-provisioning path for an existing mailbox
            so credentials can enter the oracle only after the client verifies
            attestation and encrypts to the oracle's context-bound key.
      - [x] Debug current captcha/local-vs-Phala state.
            Done 2026-07-08: local cock.li captcha fetch/parse/solve previously
            worked against live registration pages, but an explicit Phala
            `dnai-wikigen-oracle-genesis-debug` CVM with auto-genesis enabled
            proved a Phala/runtime-specific failure: three HTTP signup attempts
            parsed and solved captchas but cock.li rejected each solution as
            incorrect; the browser fallback then reached the CDP WebSocket but
            timed out in `BrowserType.connect_over_cdp`. The debug CVM used
            public logs/dev OS only for this test and was deleted afterward.
      - [ ] Fix Phala oracle genesis before treating generated TEE mailbox
            custody as real: make captcha solving reproducible inside the
            deployed linux/amd64 image, and repair or replace the Neko/CDP
            browser fallback timeout.
            - [x] Repair the cock.li registration form contract in the oracle
                  source: the real confirmation field is currently
                  `password_confinm`, while `password_confirm` is a tabindex
                  `-1` honeypot that must stay empty; HTTP payloads also mirror
                  `csrf_valid`.
            - [x] Build/push a new oracle image, pin the debug/Phala compose to
                  it, and re-run the explicit auto-genesis debug CVM to prove
                  whether HTTP signup now reaches IMAP verification.
                  Done 2026-07-08: image
                  `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:19c4aae35b0e9ab2758b7f680c2638f838c8c5a08da1c37f7f1b3bd192bfa1e2`
                  from commit `ca1b17c` verified GitHub provenance/SBOM,
                  Phala debug app `4c92eec94e2d7b6e8c8a7940cb0b6eb4a0e8e1bd`
                  reached IMAP verification and healthy oracle state, and the
                  temporary public-log/dev-OS debug CVM was deleted afterward.
            - [x] Stop public `/health` and `/attestation` from exposing the raw
                  generated oracle mailbox when credentials exist; expose
                  readiness plus `oracle_email_hash` publicly and move raw email
                  address retrieval to runtime-authenticated `/email`.
            - [x] Build/push the bounded-health oracle image and re-run the
                  explicit debug proof to confirm public health/attestation do
                  not expose raw mailbox identifiers after successful genesis.
                  Temporary Phala redeploys for this proof may use public logs,
                  SSH, public sysinfo, and dev OS access for observability only
                  while Tinker bootstrap, billing, API-key provisioning, OTP
                  retrieval, and card handling remain disabled; record each use
                  here and delete/revert it before production wrap-up.
                  Done 2026-07-08: image
                  `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:99ce7765558a00699e265a8ca7cdcdc8f402dd93c50cf8ddb52a1ef175dffefe`
                  from commit `64739e4` verified GitHub provenance/SBOM,
                  Phala debug app `18ab03c040c9c327b9333230b6a405bbccd90bec`
                  with compose hash
                  `fe20b736b9db9b3b4b3e8d9ddbcdfffabecc4cdf3311ead6be1fb922a8892c41`
                  reached IMAP verification. Public `/health` returned
                  `oracle_email=""`, `oracle_ready=true`,
                  `imap_connected=true`, and an email hash only; public
                  `/attestation?context=attestation` returned the same bounded
                  email fields plus a verified TDX quote; unauthenticated
                  `/email` returned `401 Bearer token required`. The temporary
                  public-log/SSH/dev-OS debug CVM was deleted afterward.
            - [x] Run bounded mailbox genesis in the main combined Phala CVM
                  without enabling Tinker bootstrap, billing, API-key
                  provisioning, or credential provisioning.
                  Done 2026-07-08: added
                  `docker-compose.mailbox-genesis.phala.yaml` as an explicit
                  one-shot profile with `ORACLE_AUTO_GENESIS=true`,
                  `TINKER_BOOTSTRAP_SIGNUP=false`, and
                  `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`. Updating CVM
                  `670b3b21-4338-4d4e-ae72-7c8922579f59` reached
                  `oracle_ready=true`, `imap_connected=true`,
                  `oracle_email=""`, and
                  `oracle_email_hash=535adcedea37ac48af0e43720f390125749053a0a0215b669ce55c746cd10132`.
                  Unauthenticated `/email` still returned `401 Bearer token
                  required`. The CVM was then redeployed back to
                  `docker-compose.all.phala.yaml`; steady-state compose now has
                  `ORACLE_AUTO_GENESIS=false`, `TINKER_BOOTSTRAP_SIGNUP=false`,
                  public logs/sysinfo disabled, and the sealed mailbox remains
                  ready via hash-only public health.
            - [ ] If HTTP signup regresses, repair the Neko/CDP browser
                  fallback timeout separately.
      - [ ] Run the encrypted provisioning path against the deployed Phala CVM
            with real mailbox credentials and record only bounded hashes/status.
- [ ] `P0` Prove the email TEE can receive Tinker magic-code OTPs in the running
      CVM.
      - [ ] Provision mailbox credentials or run a separate explicit
            auto-genesis debug CVM, then re-test Tinker OTP receipt in Phala.
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

- [x] `P0` Decide the acceptable route for Tinker automation:
      official API/support path, approved service-account flow, or compliant
      browser automation for an account this project controls.
      Done in `⚙️/tinker-delegate/docs/TINKER-AUTOMATION-ROUTE.md`: prefer an
      official/support-approved Tinker route; allow browser automation only as
      bounded TEE custody for this project's own account, with no evasion.
- [ ] `P0` Reproduce the current Tinker auth blocker in a controlled probe:
      local headed Chrome, local Neko, Phala headed Neko, headless Playwright
      sidecar, same email, same IP class where possible.
      - [x] Local Neko/CDP probe against live Tinker UI succeeds: email OTP
            arrives through the oracle, onboarding completes, and API-key
            provisioning captures a one-time `tml-...` key.
      - [x] Re-test Phala/deployed browser posture with the current selector
            flow before calling production bootstrap solved.
            Done 2026-07-08: a one-shot
            `docker-compose.tinker-bootstrap.phala.yaml` Phala deploy reached
            the Tinker auth surface and failed closed with
            `bootstrap_error_kind=auth_access_blocked`; no API key was created,
            billing/add-balance and credential provisioning remained disabled,
            and the CVM was redeployed back to normal compose.
- [x] `P0` Replace the deployed headless Playwright sidecar in the one-shot
      Tinker bootstrap profile with a headed browser path that survives Phala
      packaging if browser automation remains the route.
      Done 2026-07-08: `docker-compose.tinker-bootstrap.phala.yaml` no longer
      includes the `delegate-browser` Playwright sidecar, points the delegate at
      the headed Neko Chrome CDP endpoint, passed local compose/tests, was
      deployed to the main Phala CVM, and passed `verify-deployment-bundle`.
      The live attempt still failed closed with generic
      `bootstrap_error_kind=bootstrap_error` before API-key sealing, so this
      only proves the browser packaging change, not production signup.
- [x] `P0` Instrument pre-signup, CDP connection, navigation, and onboarding
      exceptions with bounded stage/type receipts so the next deployed bootstrap
      failure preserves useful evidence without raw URL, page text, OTP, email,
      or API-key egress.
      Done in source/tests and Phala-proven 2026-07-08: `signup()` now returns bounded
      `tinker_auth` receipts for account lookup, CDP/browser connection,
      browser context/page setup, auth, and onboarding exceptions. Receipts
      expose only outcome, furthest stage, hashes, bounded message, and
      `raw_secret_egress=false`; tests inject fake email, OTP, URL, and
      key-shaped strings into exceptions and assert they do not appear in
      result/stdout/runtime state. The 2026-07-08 Phala retry with the
      GitHub-attested `74ad4b6` images captured a bounded
      `last_bootstrap_attempt_record` with `surface=tinker_auth`,
      `outcome=unknown_failure`, `furthest_stage=not_started`, and
      `raw_secret_egress=false`; no API key was created and the CVM was
      redeployed back to normal compose.
- [x] `P0` Preserve the bounded deployed-bootstrap attempt outcome in
      `/health.runtime.bootstrap_error_kind` instead of flattening the
      serve-level catch to generic `bootstrap_error`.
      Done in source/tests and Phala-proven 2026-07-08: the instrumented Phala retry recorded
      `last_bootstrap_attempt_record.outcome=unknown_failure`, but the outer
      runtime field still reported `bootstrap_error`. The serve catch now
      preserves the bounded attempt record's `outcome` before falling back to
      `AuthAccessBlockedError` or generic `bootstrap_error`, and
      `test_bootstrap_runtime_state` covers the bubbled failure path without
      leaking raw mailbox, OTP, browser URL, page text, or API-key-shaped
      values. A follow-up one-shot Phala retry using GitHub-attested `8fb6e3a`
      images proved `/health.runtime.bootstrap_error_kind=unknown_failure`
      alongside the bounded nested receipt; the CVM was redeployed back to
      normal compose afterward.
- [ ] `P0` Capture a selector/frame/auth-flow map for:
      email input, magic-code page, OTP boxes, onboarding, keys page, billing,
      Stripe iframe, balance page, and auto-reload settings.
      - [x] Capture current local selectors for email auth, OTP boxes,
            onboarding, keys page, New key -> Generate key, balance page,
            Add payment method modal, and Stripe card iframe.
      - [x] Add selector-repair fallback families and bounded
            `selector_missing` attempt records for API-key provisioning.
      - [x] Add replayable mock-page tests for API-key creation selectors,
            including aria-label/data-testid fallback variants, successful key
            extraction, missing-create-selector, and extraction-failure paths.
      - [x] Preserve bounded deployed-bootstrap selector evidence in runtime
            health state.
            Done locally: startup bootstrap now stores the last bounded
            `api_key_provisioning` attempt record in
            `/health.runtime.last_bootstrap_attempt_record` on success or
            selector/API-key-capture failure, without raw mailbox, OTP, URL,
            page text, or API-key egress.
      - [x] Add a bounded machine-readable selector/frame/auth-flow map for the
            local contract.
            Done 2026-07-08: `tinker-delegate selector-map` emits the declared
            email auth, OTP, onboarding, API-key, billing, Stripe iframe,
            balance top-up, and auto-reload selector families with evidence
            status, selector counts, and a recomputable map hash. The output is
            guarded by the bounded CLI renderer and regression-tested to avoid
            secret-shaped material; `--summary-only` omits concrete selectors.
      - [x] Add a read-only bounded browser probe for deployed selector/frame
            evidence capture.
            Done 2026-07-08: `tinker-delegate selector-probe` connects to the
            configured browser, observes current pages/frames without
            navigation, clicks, typing, screenshots, or page-text capture, and
            emits only URL classes, URL hashes, selector match bands, frame
            kinds, selector-map hash, and `raw_secret_egress=false`. Browser
            connection failures return bounded `browser_unavailable` JSON
            instead of tracebacks.
      - [x] Add a disabled-by-default HTTP selector-probe endpoint for one-shot
            deployed evidence capture.
            Done 2026-07-08: `GET /browser/selector-probe` returns 403 unless
            `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=true`; when enabled it invokes
            the same read-only bounded probe and converts browser failures to a
            bounded `browser_unavailable` response without leaking browser URLs,
            account identifiers, page text, cookies, OTPs, API keys, or card
            material. This endpoint is Phala-proven in a one-shot measurement
            profile and remains disabled in the restored steady-state compose.
      - [x] Add bounded browser-control readiness diagnostics for deployed
            selector-probe failures.
            Done 2026-07-08: `tinker-delegate browser-readiness` and
            disabled-by-default `GET /browser/readiness` report only endpoint
            classes/hashes, CDP metadata reachability, Playwright/CDP handshake
            success bands, and bounded error kinds. They do not navigate,
            click, type, screenshot, return page text, or expose raw CDP/browser
            URLs. Normal Phala compose sets
            `TINKER_ALLOW_BROWSER_READINESS_ENDPOINT=false`; the one-shot
            bootstrap measurement profile sets it true alongside
            `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=true`.
      - [x] Add a bounded raw CDP WebSocket upgrade diagnostic.
            Done 2026-07-08: `browser-readiness` now includes
            `cdp_websocket_handshake`, which fetches the CDP metadata URL,
            keeps the advertised WebSocket URL in memory only, sends a raw HTTP
            Upgrade request, and emits only endpoint class/hash, TCP/TLS/upgrade
            stage booleans, HTTP status band, and bounded error kind. It does
            not navigate, send browser commands, read page data, or return raw
            URLs/headers. Unit tests cover accepted and rejected upgrades and
            rendered-output redaction. A Phala one-shot measurement with
            GitHub-attested `7973b27` images proved the raw upgrade reaches
            HTTP `101`, then Playwright `connect_over_cdp` still times out; the
            normal profile was restored and the readiness endpoint returned 403.
      - [ ] Capture deployed-CVM selector/frame evidence after Phala packaging.
            Attempted 2026-07-08 with GitHub-attested
            `a2e14b542314a16e07f20a17694e9da1a67b1f1c` oracle/delegate
            images and a one-shot Phala profile enabling only
            `TINKER_ALLOW_BROWSER_READINESS_ENDPOINT=true` and
            `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=true` on top of the existing
            bounded bootstrap profile. The readiness endpoint proved that Neko
            CDP `/json/version` is reachable and advertises Chromium WebSocket
            metadata, but Playwright `connect_over_cdp` times out. The selector
            probe still returned bounded `browser_unavailable` JSON with
            `raw_secret_egress=false`, then the CVM was restored to normal
            compose where both diagnostic endpoints return 403. This proves the
            deployed endpoint gates/fail-closed paths and narrows the blocker to
            the CDP WebSocket handshake, but does not yet capture selector/frame
            match evidence.
            Re-attempted 2026-07-08 with GitHub-attested
            `7973b27d27a3d3fba3a24efcc23c89498e8a04bf` oracle/delegate
            images and the new `cdp_websocket_handshake` diagnostic. The
            readiness endpoint showed CDP metadata reachable, raw WebSocket
            TCP connect true, HTTP Upgrade sent, HTTP status band `101`, and
            Playwright `connect_over_cdp` still timing out. The selector probe
            still returned bounded `browser_unavailable`, and the CVM was
            restored to normal compose where both diagnostic endpoints return
            403.
            Re-attempted 2026-07-08 with GitHub-attested
            `59a9eac5d22f9834d74e3f263de2f46130a0a898` oracle/delegate
            images and the new `cdp_protocol_probe`. The readiness endpoint
            showed CDP metadata reachable, raw WebSocket TCP connect true,
            HTTP Upgrade status band `101`, one browser-scoped
            `Browser.getVersion` command sent, bounded CDP `result` response
            received with Chromium browser-family band, and Playwright
            `connect_over_cdp` still timing out. The selector probe still
            returned bounded `browser_unavailable`, and the CVM was restored to
            normal compose where the readiness and selector endpoints return
            403. Later subitems added and Phala-measured the raw-CDP
            target/page fallback. Source/tests now add bounded Runtime selector
            family counting; deployed DOM selector match evidence remains open
            until that fallback is built into GitHub-attested images and
            measured on Phala.
      - [x] Add a bounded post-upgrade DevTools-protocol probe.
            Done in source/tests and Phala-proven 2026-07-08:
            `browser-readiness` now includes
            `cdp_protocol_probe`. It reuses the CDP metadata URL, keeps the
            advertised WebSocket URL in memory only, performs the HTTP Upgrade,
            sends one browser-scoped `Browser.getVersion` CDP command, and
            emits only URL class/hash, TCP/TLS/upgrade stage booleans, command
            and response booleans, response kind, browser family, HTTP status
            band, and bounded error kind. It does not navigate, click, type,
            screenshot, inspect frames/pages, return page text, expose raw
            browser/CDP URLs, or return the CDP response body. Unit tests cover
            accepted result and CDP error responses and prove rendered output
            omits raw CDP URLs and returned browser strings. A Phala one-shot
            measurement with GitHub-attested `59a9eac` images proved this basic
            DevTools protocol command path succeeds after HTTP `101`, even
            though Playwright `connect_over_cdp` still times out.
      - [x] Add a bounded raw-CDP target/frame inventory fallback.
            Done in source/tests 2026-07-08: if Playwright CDP attachment
            fails, `selector-probe` falls back to a raw DevTools WebSocket path
            that performs `Target.getTargets`, attaches read-only to up to five
            page targets, runs `Page.getFrameTree`, and emits only
            `probe_backend=raw_cdp`, stage booleans, HTTP status band,
            target/page/frame count bands, URL classes/hashes, frame kinds, and
            bounded error kinds, including when the raw-CDP fallback itself
            cannot complete. The raw CDP URL and WebSocket debugger URL stay in
            memory only; tests prove the rendered output omits raw browser URLs,
            query strings, Stripe frame URLs, page text, cookies, account data,
            OTPs, API keys, and card data. A Phala one-shot measurement with
            GitHub-attested `f63dd18` images proved the raw fallback reaches
            CDP metadata, WebSocket HTTP `101`, and `Target.getTargets`,
            returning bounded target count `2+` and page count `1`. It still
            timed out before `Page.getFrameTree`, so frame inventory and DOM
            selector counting remain open.
      - [x] Preserve bounded page-target inventory when raw-CDP frame-tree
            probing times out.
            Done in source/tests and Phala-proven 2026-07-08: per-page
            attach/frame-tree errors now stay inside the page observation,
            preserving page URL classes/hashes, target/page count bands,
            `attached`, `attach_error_kind`, `frame_tree_error_kind`,
            `partial_error_kind`, and zero frame observations when frame
            traversal times out. A GitHub Actions build for `a384db2` produced
            signed GHCR provenance/SBOM attestations for
            `tinker-delegate@sha256:7ddea52df75ab0392defbb35d568649ab21bb67352e6cc55ce1aeb154470c83e`
            and
            `tee-email-oracle@sha256:15085c1dadb2f771f8fa1faeb463413adc9351a5433d939b5155c602d229c9ca`.
            A one-shot Phala diagnostic compose returned
            `probe_backend=raw_cdp`, `success=true`, target count `2+`, page
            count `1`, `pages_observed=1`, one page observation with
            `attached=true`, `frame_tree_error_kind=timeout`,
            `partial_error_kind=frame_tree_timeout`, and
            `raw_secret_egress=false`. Normal compose was restored afterward
            and both diagnostic endpoints returned 403. It still avoids DOM
            text, raw URLs, cookies, account identifiers, OTPs, API keys, and
            card material. Frame inventory and DOM selector counting remain
            open.
      - [ ] Add bounded raw-CDP Runtime selector-family counting for deployed
            selector evidence.
            Done in source/tests 2026-07-08: after `Target.attachToTarget`,
            the raw-CDP fallback sends one `Runtime.evaluate` command that
            counts only declared selector families and returns a matrix of
            `0`, `1`, `2+`, or `probe_error` bands. Python maps that matrix
            onto known flow/family names, so the public receipt cannot include
            page text, raw DOM, raw selectors, cookies, account identifiers,
            OTPs, API keys, card data, or arbitrary page-controlled strings.
            Tests prove selector-family observations survive the same
            `Page.getFrameTree` timeout seen on Phala. Next step: build
            GitHub-attested images, measure this one-shot selector probe on
            Phala, and restore normal compose.
- [x] `P0` Narrow Phala redeploy runtime env handling to the minimal key set
      needed by each compose profile.
      Done 2026-07-08: `scripts/redeploy-phala-cvm.mjs` now defaults to
      `--runtime-env-policy compose-refs`, selecting only keys referenced by the
      compose source plus explicitly allowed keys. The legacy broad behavior
      requires `--runtime-env-policy all`. Default output is bounded to
      `runtime_env_policy`, `runtime_env_key_count`, and
      `runtime_env_keys_sha256`; printing key names requires
      `--print-runtime-env-keys`. Node tests cover compose-reference filtering,
      explicit missing-key fail-closed behavior, allow-file additions, and the
      explicit all-env fallback. The current Phala normal profile was redeployed
      with this policy: live compose hash
      `000ac9ba94fc8cf1870786f9a9a3f7b1586ce74ad21f23143ce4e3d88941318e`,
      `allowed_env_count=7`, public logs/sysinfo disabled, health OK, and both
      browser diagnostic endpoints still 403. Deployment-bundle verification
      passed against the narrowed allowed-env policy with `raw_secret_egress=false`.
- [x] `P0` Handle Tinker bot/fingerprint checks without evading legal or service
      boundaries.
      Done when the team can explain the account relationship and automation to
      Tinker/Stripe if asked.
      Current policy: fail closed on blocks, do not use stealth plugins,
      automation-control masking, rotating proxies, user-agent spoofing, or
      CAPTCHA-solving services for Tinker/Stripe account and billing flows.
      `test_automation_route_policy.py` rejects common evasion dependencies and
      flags in the runtime package, dependency manifest, and compose files.
- [ ] `P0` Complete Tinker signup inside the CVM:
      email OTP, onboarding, API key creation, encrypted key sealing.
      - [x] Complete local Neko signup/sign-in path through OTP, onboarding, and
            API-key creation.
      - [x] Store local captured API keys in the encrypted key store without
            returning or logging the raw key.
      - [x] Remove raw mailbox and browser URL egress from signup/signin logs
            and return payloads before enabling deployed-CVM bootstrap.
      - [x] Add a bounded one-shot Phala bootstrap profile for the deployed-CVM
            attempt.
            Done locally: `docker-compose.tinker-bootstrap.phala.yaml` enables
            only `TINKER_BOOTSTRAP_SIGNUP=true`, reuses the main
            `delegate-data` volume for sealed API-key persistence, and keeps
            oracle genesis, credential provisioning, and add-balance disabled.
      - [ ] Resolve deployed Tinker auth access block without evasion.
            Evidence 2026-07-08: the first Phala one-shot bootstrap failed
            closed at Tinker auth with `auth_access_blocked`. A second
            Phala one-shot bootstrap using headed Neko CDP instead of the
            Playwright sidecar verified the packaging and endpoint gates, but
            failed closed with generic `bootstrap_error` before a bounded stage
            receipt or API-key capture. A third retry using GitHub-attested
            `74ad4b6` images captured a bounded `tinker_auth`
            `unknown_failure` receipt at `not_started`, with no raw secret
            egress and no API-key capture. The outer runtime
            `bootstrap_error_kind` preservation fix is now implemented and
            Phala-proven with GitHub-attested `8fb6e3a` images:
            `/health.runtime.bootstrap_error_kind=unknown_failure`.
            Local Neko still works, so next work should either repair the
            supportable headed-browser posture or obtain an official/support-
            approved Tinker service-account/API-key route.
      - [ ] Complete the same flow inside the deployed CVM and seal the API key
            with the dstack-derived key path.
- [x] `P0` Add a Tinker re-auth path for future OTP challenges.
      Done locally via bounded `reauth` CLI/helper and opt-in
      `POST /auth/reauth`; outputs are `tinker_auth` receipts only and do not
      expose account email, OTP, URL, API key, or raw page text. Deployed-CVM
      validation remains covered by the open Phala selector/posture tasks above.
- [ ] `P1` Add browser session recovery:
      stale OTP page detection, cookie/session expiration, login loop detection,
      screenshot artifacts with secrets redacted.
- [ ] `P1` Add a `cdp-playground` recipe specifically for Tinker auth and
      billing probes.
- [ ] `P1` Add replayable browser tests against mock pages for auth, onboarding,
      key creation, and billing.
      - [x] API-key creation mock-page tests cover selector fallback variants,
            one-time `tml-...` extraction, and bounded missing-selector /
            extraction-failure behavior without a live Tinker account.
      - [x] Auth and OTP mock-page tests.
      - [x] Onboarding mock-page tests.
      - [x] Billing and Stripe-frame mock-page tests.

### Tinker Funding

- [x] `P0` Decide the production funding model:
      production defaults to manual/developer prefund until an official or
      tokenized Tinker/Stripe route exists. Raw-card browser automation is
      limited to opt-in `operator_capped_validation` for one-off approved
      operator-owned validation attempts; `GET /billing/funding-policy` and the
      `funding-policy` CLI expose the bounded mode, and denied card/add-balance
      requests persist bounded `policy_denied` receipts without browser launch.
- [ ] `P0` Finish the encrypted card channel:
      verify TEE quote, encrypt card payload to TEE public key, decrypt in memory,
      fill billing form, zero memory, and return only bounded status.
      - [x] Local plaintext development path fills the Stripe Elements card
            iframe, zeroes card payload objects, and returns bounded failure
            status without logging card details.
      - [x] Disable plaintext `POST /billing/card` by default, disallow it in
            dstack mode, and wipe plaintext card request objects on success and
            failure.
      - [x] Exercise encrypted `/billing/card/encrypted` locally after
            context-bound billing attestation verification; Stripe test-card
            submission returns bounded `card_declined` and the encrypted receipt
            store records the attempt.
      - [x] Gate encrypted card and add-balance automation behind
            `TINKER_FUNDING_MODE=operator_capped_validation`; the default
            `manual_prefund` mode denies those browser paths before card
            decryption or browser launch and records bounded policy receipts.
      - [x] Add bounded operator funding preflight via
            `GET /billing/funding-preflight` and the `funding-preflight` CLI:
            checks funding mode, amount cap, optional add-balance endpoint flag,
            encrypted receipt-store availability, and billing attestation policy
            before any card payload or browser launch.
      - [x] Add a bounded funding validation manifest via the
            `funding-manifest` CLI: hashes saved preflight and receipt JSON,
            binds expected compose/app/OS-image policy by hash, and rejects raw
            card/API-key/secret-shaped inputs.
      - [x] Add durable bounded artifact output for operator validation:
            `funding-preflight --output` writes preflight JSON, and billing
            receipt-producing commands can write attempt records via
            `--receipt-output` for manifest binding.
      - [x] Add one-command bounded validation packet generation:
            `funding-validation-packet` writes preflight, receipt, manifest,
            verification, and summary JSON, with explicit `--run-card-attempt`
            required before card fields are accepted.
      - [x] Extend validation packets with optional add-balance evidence:
            bind an existing bounded add-balance receipt or explicitly run
            `POST /billing/add-balance` with `--run-add-balance-attempt`, and
            write separate top-up manifest/verification JSON.
      - [x] Add a bounded packet-directory checker:
            `check-funding-validation-packet` verifies required files,
            replays payment/top-up manifests, catches tampering, and can require
            add-balance evidence or deployed TDX attestation evidence.
      - [x] Add payment-method and add-balance selector-repair fallback
            families for the Tinker billing UI, with mock-page tests covering
            data-testid/aria-style drift and bounded `selector_missing`
            receipts when top-up controls cannot be found.
      - [x] Add `add-card-encrypted-prompt` so approved operator card details
            are entered interactively instead of as command-line flags; the
            prompt path requires deployed compose/app/OS-image attestation
            expectations unless explicitly run in local-dev mode.
      - [x] Extend `funding-validation-packet` with `--prompt-card` so an
            approved real-card validation can create the full bounded packet
            without placing card fields in command-line arguments; prompt mode
            rejects missing deployed attestation expectations before asking for
            card material.
      - [x] Run a fresh local FastAPI encrypted-card smoke with local billing
            attestation and a Stripe test card: `$5` operator preflight returns
            ready, `$10` with add-balance endpoint required returns not ready,
            encrypted `/billing/card/encrypted` reaches bounded
            `payment_submitted` receipt output, and the temp encrypted receipt
            file does not contain the test card number, CVC, name, postal code,
            or raw card field names.
      - [ ] Exercise the encrypted `/billing/card/encrypted` path against the
            deployed attested endpoint after quote verification.
- [ ] `P0` Prove the Stripe/Tinker billing path end-to-end with a low-value test
      account and a safe test card or approved real card.
      - [x] Stripe test card reaches live Tinker/Stripe submission and returns
            `Your card was declined.`
      - [x] Add-balance fails closed with `Payment method required before adding
            balance` when no real payment method is on file.
      - [x] Enforce `TINKER_MAX_ADD_BALANCE_USD` before launching browser
            automation so real-card top-ups cannot exceed the approved cap by
            caller input alone.
      - [x] Disable the HTTP add-balance mutation endpoint by default behind
            `TINKER_ALLOW_ADD_BALANCE_ENDPOINT`; the capped CLI/internal path
            also requires `TINKER_FUNDING_MODE=operator_capped_validation` for
            deliberate operator validation attempts.
      - [x] Locally verify `POST /billing/add-balance` rejects with 403 while
            `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`, even when
            `operator_capped_validation` mode is enabled.
      - [ ] Run a capped real-card add-payment-method and low-value add-balance
            attempt after receiving approved card details.
- [x] `P0` Confirm PCI and Stripe obligations.
      Research whether the current encrypted-card-to-TEE flow is acceptable or
      whether the system must use Stripe-hosted tokenization / SetupIntent /
      PaymentMethod flows.
      Done in `⚙️/tinker-delegate/docs/STRIPE-PCI-FUNDING-SCOPE.md`: raw-card
      encrypted delivery is limited to a one-off operator-owned capped
      validation path, while production/repeated funding should use an official
      Tinker route, Stripe-hosted/tokenized collection, SetupIntent /
      PaymentMethod style reuse with consent, or manual/developer prefunding
      until compliance review approves otherwise.
- [ ] `P0` Obtain legal/compliance approval before enabling production or
      repeated card funding, especially any third-party/customer card funding.
      Until approved, keep raw-card encrypted delivery limited to the
      operator-owned capped validation path in
      `⚙️/tinker-delegate/docs/STRIPE-PCI-FUNDING-SCOPE.md`.
- [ ] `P0` Ensure no card details appear in:
      browser traces, Playwright logs, screenshots, API logs, exception messages,
      crash dumps, or Phala console output.
      - [x] Suppress payment-method screenshots after card entry/submission even
            when debug screenshots are enabled; only non-secret billing debug
            screenshots may be written.
      - [x] Add trace/HAR/video/card-screenshot deletion for configured browser
            debug artifact directories after card submission attempts.
      - [ ] Add deployed log/Phala-console verification for the encrypted
            card path once the CVM endpoint is available.
      - [x] Add crash-dump/core-dump policy for browser and delegate processes:
            Python entrypoints set `RLIMIT_CORE=0`, and Tinker local/Phala
            compose services set `ulimits.core: 0`.
      - [x] Make billing CLI output fail closed before printing or writing JSON
            if a delegate response contains submitted card material or
            secret-shaped fields.
- [ ] `P1` Add funding receipt records:
      amount band, timestamp, payment method token/reference, Tinker balance band,
      CVM quote, and card payload destruction proof.
      - [x] Return bounded payment-method and add-balance attempt records from
            billing automation/API responses: surface, outcome, furthest stage,
            issued timestamp, evidence hash, amount band, balance band, TDX
            quote hash when present, and card-payload destruction status.
      - [x] Persist bounded funding receipts in encrypted/sealed delegate
            storage and expose only bounded records through
            `GET /billing/funding-receipts`.
      - [x] Build a bounded funding validation manifest from preflight and
            receipt records so a capped operator validation attempt can publish
            hashes, bands, outcome, TDX quote hash, and card-destruction /
            no-raw-egress booleans without card material.
      - [x] Add a bounded funding manifest verifier that replays saved
            preflight/receipt/policy hashes, checks manifest integrity, and
            reports named pass/fail checks without echoing packet contents.
      - [x] Add CLI `--receipt-output` support for bounded billing attempt
            records so validation receipts can be saved without console
            scraping.
      - [x] Add a packet summary artifact for funding validation runs so
            reviewers can see preflight readiness, receipt outcome, manifest
            hash, and verification status without packet body disclosure.
      - [x] Add optional add-balance receipt, manifest, verification, and
            summary fields to funding validation packets so low-value top-up
            evidence can be audited separately from payment-method evidence.
      - [x] Add a checker summary for validation packets so reviewers can
            distinguish internally consistent local packets from packets with
            live deployed TDX attestation evidence.
      - [ ] Add payment-method token/reference to funding receipts once the
            live funding path exposes a safe non-card reference.
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
  - [x] `P0` Add generic anti-overfitting guards for adaptive query attacks:
        per-candidate repeat caps, minimum unique reward candidates before
        final validation, and public aggregate repeat accounting.
  - [x] `P0` Add a bounded synthetic hidden-dataset demo command.
        Done with `synthetic-private-reward-demo`: it runs
        `SyntheticHiddenKeywordEnvironment` over a synthetic sealed dataset and
        emits optimizer view, bounded feedback, final result, transcript hash,
        leakage hash, and attestation metadata without hidden records or
        submitted candidate strings.
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
- [x] `P0` Decide Stripe/PCI stance before real card funding.
      Stance recorded in
      `⚙️/tinker-delegate/docs/STRIPE-PCI-FUNDING-SCOPE.md`: no production or
      repeated raw-card funding path without compliance review; only a capped
      operator-owned validation attempt is allowed before tokenized/official
      funding exists.
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

- [x] `P0` Add CI for Foundry contracts:
      `forge build`, `forge test`, gas snapshot, coverage if feasible.
      Done in `.github/workflows/ci.yml`: the Foundry job installs Foundry and
      runs `scripts/verify-local.sh foundry`, which executes `forge build
      --sizes` and `forge test`. Refreshed 2026-07-08: the Foundry checkout no
      longer requests recursive research submodules, because the needed
      `forge-std` files are vendored in the contract package.
- [x] `P0` Add CI for Python packages:
      `uv sync`, import checks, unit tests, compileall, type checks where set up.
      Done in `.github/workflows/ci.yml`: the Python job installs `uv` and runs
      `scripts/verify-local.sh python` across `tinker-delegate`,
      `tee-email-oracle`, `props-room`, `whatsapp-delegate`, and
      `cdp-playground`. Stub packages now have `uv.lock` so CI can use
      `uv sync --frozen`.
- [ ] `P0` Add CI for frontend once merged:
      `npm ci`, `npm test`, `npm run build`, `npm audit --omit=dev`.
- [x] `P0` Add secret scanning in CI.
      Done in `.github/workflows/ci.yml` and `scripts/ci-secret-scan.sh`.
      The scanner excludes read-only reference material and generated lock/build
      outputs, allows only explicit fake test fixtures, and fails on common
      Phala/Tinker/GitHub/OpenAI/token/private-key/card-shaped material.
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
- [x] `Deploy` Verify Foundry keystore account `dev` exists and is funded for
      Base Sepolia.
      Done 2026-07-08: `0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD` has
      Base Sepolia ETH and can pay deployment gas; raw private key material is
      not stored in repo or `.env`.
- [ ] `Deploy` Verify Cloudflare Wrangler login for frontend deployment.
- [x] `Deploy` Verify Phala CLI login and profile.
      Done 2026-07-08: `phala status` reports user `g-structure`, workspace
      `wiki`, profile `wikigen`.
- [x] `Deploy` Verify Docker registry credentials and decide permanent registry.
      - [x] Add GHCR as the CI image publication path for deploy-critical
            TEE images.
      - [x] Run the GitHub image workflow, verify published image attestations,
            and record final image digests.
            Refreshed 2026-07-08 for commit
            `b49ff2ca678d8860cccd69fb38a385dbc853bfbc` with GitHub Actions run
            `28941069823`.
            Refreshed again 2026-07-08 for bounded oracle/delegate commit
            `81e3188591aadba26ab124217624e6341d2def74` with GitHub Actions run
            `28945611577`.
            Refreshed again 2026-07-08 for main-CVM mailbox-genesis evidence
            commit `1acdebd0c1e07c03b57533852985ac174d4f1261` with GitHub
            Actions run `28947685641`.
            Refreshed again 2026-07-08 for bounded Tinker bootstrap evidence
            commit `24ba5edf3b9d56429499bdcd602b3a808e37ba12` with GitHub
            Actions run `28949229390`.
            Refreshed again 2026-07-08 for bounded early-stage bootstrap
            receipts commit `74ad4b6d7359d418507d131a5f30ad7e541987af` with
            GitHub Actions run `28952111920`.
            Refreshed again 2026-07-08 for preserved bounded bootstrap error
            kind commit `8fb6e3a7dac3ef58f1e4c1e902a36ebd612b910e` with
            GitHub Actions run `28954112809`.
            Refreshed again 2026-07-08 for bounded selector-probe endpoint
            commit `ca877db2d02ee4498d30560f19d4d394cf165676` with GitHub
            Actions run `28957360340`.
            Refreshed again 2026-07-08 for bounded browser-readiness diagnostics
            commit `a2e14b542314a16e07f20a17694e9da1a67b1f1c` with GitHub
            Actions build run `28958905325`.
            Refreshed again 2026-07-08 for bounded raw CDP WebSocket diagnostic
            commit `7973b27d27a3d3fba3a24efcc23c89498e8a04bf` with GitHub
            Actions build run `28960362186`.
            Refreshed again 2026-07-08 for bounded post-upgrade CDP protocol
            probe commit `59a9eac5d22f9834d74e3f263de2f46130a0a898` with
            GitHub Actions build run `28961851866`.
- [ ] `Deploy` Rebuild and publish pinned images for:
      email oracle, tinker delegate, Neko/browser sidecar, props room, frontend
      worker if any.
- [x] `Deploy` Redeploy Phala CVM with final image digests.
      Refreshed 2026-07-08: CVM `670b3b21-4338-4d4e-ae72-7c8922579f59` now
      runs oracle image
      `ghcr.io/g-structure/dnai-wikigen/tee-email-oracle@sha256:15085c1dadb2f771f8fa1faeb463413adc9351a5433d939b5155c602d229c9ca`
      and delegate image
      `ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:7ddea52df75ab0392defbb35d568649ab21bb67352e6cc55ce1aeb154470c83e`.
      The Phala compose now hardcodes these digests and the disabled
      secret-bearing gates rather than passing them through encrypted env
      values, so the live attested compose hash changes when the deploy-critical
      image refs change. The current normal profile is live at attested compose
      hash `000ac9ba94fc8cf1870786f9a9a3f7b1586ce74ad21f23143ce4e3d88941318e`
      with narrowed `allowed_env_count=7`. Live update with disabled public
      logs/sysinfo succeeded, but Phala still reports `dstack-dev-0.5.9` /
      `is_dev=true`.
- [ ] `Deploy` Verify CVM endpoints:
      `/health`, `/attestation`, oracle `/pin` auth rejection, delegate status,
      browser CDP internal-only or protected.
      - [x] Delegate `/health` returns `status=ok`, oracle `/health` returns
            `status=ok` with `oracle_ready=true`, `imap_connected=true`, and
            only the sealed mailbox hash, and containers are healthy/running.
      - [x] Delegate `/attestation?context=artifact` verifies with
            `verify-cvm-attestation`.
      - [x] Oracle `/pin` rejects unauthenticated requests with `401 Bearer
            token required`.
      - [x] Public CDP gateway probe returns host-header rejection rather than
            a usable `/json/version` browser-control response.
      - [x] Oracle `/attestation?context=oracle-credentials` returns a live
            TDX credential-ingress envelope, and `POST /credentials/encrypted`
            rejects while disabled by default.
      - [x] `verify-deployment-bundle` passes against the live log-hardened
            Phala deployment with GitHub image provenance/SBOM checks, required
            sidecar digests, local raw compose hash
            `63b4b43e50ba1938bf0f1d266eff60a67a431ccc4b4d0e1829d3f738d53e4993`,
            and live attested compose hash
            `000ac9ba94fc8cf1870786f9a9a3f7b1586ce74ad21f23143ce4e3d88941318e`.
      - [x] Redeploy the fresh bounded-signup Tinker delegate image to the
            main CVM and re-run live health, attestation, credential endpoint,
            and add-balance endpoint gates.
            Done 2026-07-08: live delegate image
            `ghcr.io/g-structure/dnai-wikigen/tinker-delegate@sha256:7ddea52df75ab0392defbb35d568649ab21bb67352e6cc55ce1aeb154470c83e`
            is GitHub-attested from commit
            `a384db22f442f19796e4818c68060aa107bd54ee`; `/pin` rejects
            unauthenticated requests with `401`, `/browser/readiness` and
            `/browser/selector-probe` reject while disabled with `403`,
            `/credentials/encrypted` is closed on the delegate port with `404`,
            and `/billing/add-balance` rejects while disabled with `403`.
      - [x] Revert temporary Phala public-log debug posture on the main CVM
            before any real mailbox, OTP, Tinker API-key, or card material is
            handled.
            Done 2026-07-08: redeployed the log-hardened pinned compose with
            public logs off, public sysinfo off, and secret-bearing gates still
            disabled.
      - [ ] Move the main Phala CVM off dev OS before production wrap-up.
            Evidence 2026-07-08: `phala cvms get` still reports
            `dstack-dev-0.5.9` / `is_dev=true`; attempts to update with
            `--image dstack-0.5.10-4c9bd024 --no-dev-os` and
            `--image dstack-0.5.10 --no-dev-os --prepare-only` failed in the
            Phala CLI/API with a required `correlationId` validation error. A
            later compose/image update using `--no-dev-os` succeeded, but the
            live CVM still reported the dev OS afterward.
      - [ ] Before production wrap-up, remove or disable every temporary
            Phala debug posture used during oracle genesis work: public logs,
            public sysinfo, SSH/dev OS access, exposed browser/CDP debug ports,
            and the standalone oracle-genesis debug compose.
      - [ ] Verify credential provisioning with real mailbox credentials,
            Tinker API-key capture, and funded billing flow inside the
            deployed CVM.
- [x] `Deploy` Deploy or update Base Sepolia contracts with the chosen vNext
      interfaces.
      - [x] Verify the historical deployed contracts are not controlled by the
            current funded operator deployer and record that evidence in the
            deployment manifest.
      - [x] Add a no-raw-key deploy helper at
            `⚙️/tinker-delegate/contracts/scripts/deploy-base-sepolia.sh` that
            builds, tests, dry-runs, broadcasts with Foundry `--account dev`,
            performs on-chain reads, and rewrites the manifest.
      - [x] Broadcast fresh current-operator `DiligenceRoom` and
            `EmailOracleAuth` contracts from an interactive terminal so Foundry
            can prompt for the encrypted keystore password.
            Done 2026-07-08: `DiligenceRoom` deployed at
            `0x5d8a18628b4c8427eea89aa5498d81ff5ad3f423`
            (`0xfa50ada33f0a2c9f434c58b6cadf98defa01302b7c3e444116c021370d28169e`)
            and `EmailOracleAuth` deployed at
            `0xf52c18a33bd172ae94282132649d80bcd4b872ff`
            (`0xa29d749517a69f868db1785c7f091ea75f60a76ef657badedb0848e44be7a349`).
            On-chain reads confirm the funded `dev` deployer is the
            DiligenceRoom developer and EmailOracleAuth owner.
      - [ ] Redeploy `DiligenceRoom` after the verifier-signature
            `submitResult()` ABI change, set `DILIGENCE_RESULT_VERIFIER`, and
            record `resultVerifier()` in `deployments/base-sepolia.json`.
      - [ ] Deploy `TinkerAccountEncumbrance`, set initial account commitment,
            compose hash, add-balance/spend caps, and record the address/policy
            in `deployments/base-sepolia.json`.
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
4. [x] Build a fake private-reward environment with a synthetic hidden dataset.
       `SyntheticHiddenKeywordEnvironment` plus
       `synthetic-private-reward-demo` now provide a replayable local bounded
       private-reward proof over a synthetic hidden dataset.
5. [x] Fix `tinker-delegate` Docker install so the Tinker SDK path is present in
       the deployed image.
       Dockerfile installs `uv sync --frozen --no-dev --extra agent`, and
       `scripts/verify-agent-image.sh` verifies the optional Tinker SDK import
       inside the built delegate image. Fresh Phala CVM validation remains
       separate because no CVMs are currently deployed.
6. [x] Enforce oracle auth on `/pin` and `/inbox`.
       Runtime bearer auth and optional on-chain `EmailOracleAuth` consumer
       registry enforcement are implemented locally. Base Sepolia compose-hash
       registration remains a separate deployment step.
7. [ ] Add chain watcher + TEE chain signer for `DiligenceRoom`.
       Local watcher and signer/broadcaster plumbing now exist; remaining proof
       is dstack/CVM-originated `submitResult()` broadcast and measured-code
       binding.
8. [ ] Build a fake Tinker backend and full local synthetic room test.
9. [x] Rework the one-shot deployed bootstrap browser path to headed Neko
       inside Phala.
       Done 2026-07-08 for `docker-compose.tinker-bootstrap.phala.yaml`; signup
       remains blocked, but the latest Phala retry now emits a bounded
       `tinker_auth` `unknown_failure` receipt rather than a null attempt record.
10. [ ] Get an official Tinker service-account/API route, or complete the
        bounded headed-Neko signup repair without evasion.
11. [ ] Prove safe Tinker account funding with a low-value test.
       Test-card path reaches Stripe decline and add-balance fail-closed state;
       real capped funding attempt needs approved card details.
12. [ ] Run one real tiny Tinker training session through `IsolatedTinkerSession`.
13. [ ] Merge the `gate-health-frontend` UI and wire it to real verifier/status
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
