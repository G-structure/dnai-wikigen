# dnai-wikigen Architecture

This document describes the full `dnai-wikigen` architecture as it exists in this
repository: the attested diligence room, the TEE-hosted email oracle, the Tinker
delegate, the NDAI escrow contracts, the data-room adapters, and the planned
TTT/RL bio-validation layer.

The short version:

```
Email encumbered contract <--> Tinker encumbered contract <--> TTT/RL bio validation
              |                            |                              |
              v                            v                              v
      tee-email-oracle            tinker-delegate                 bounded evaluator
              \                            |                              /
               \                           v                             /
                +-----------------------> DNAI <-------------------------+
                                  attested diligence room
```

In production terms, the project is an **attested diligence room**. A seller or
data controller brings private material into a TEE. A buyer, sponsor, or
delegated scientific agent can inspect it only through an attested evaluator.
Only bounded outputs leave the boundary: score bands, yes/no decisions, hashes,
offers within a budget cap, and audit attestations.

## Status Legend

```
[real]      Code exists and can be compiled, imported, tested, or deployed.
[partial]   Code exists but the end-to-end path is incomplete or externally blocked.
[modeled]   The shape is documented or stubbed, but enforcement is not complete.
[planned]   Architecture target only.
```

Important current status:

```
[real]      DiligenceRoom.sol escrow state machine and tests.
[real]      EmailOracleAuth.sol app-auth contract and tests.
[real]      tee-email-oracle FastAPI service, sealed credential store, IMAP OTP path.
[partial]   tinker-delegate service, browser automation, billing channel, API key store.
            Local Neko login, OTP, onboarding, API-key provisioning, and
            test-card billing rejection are validated; deployed CVM validation
            and real funding remain open.
[partial]   IsolatedTinkerSession and bounded control plane. Artifact ingress
            now has mocked-SDK coverage for one-run enforcement, mandatory
            checkpoint TTL, path-checked sampling, cleanup, and metering.
            Artifact ingress decrypts quote-key-encrypted artifact uploads and
            verifies Ethereum keccak256 against the committed artifactHash
            before storing the upload in memory.
[real]      PrivateRewardEnvironment interface and leakage accounting types.
            The base contract exposes public problem/schema metadata, query
            budget, optimizer placement policy, reward precision policy,
            bounded feedback, transcript hash, leakage hash, and attestable
            environment metadata.
[real]      Local PythonCandidateSandbox for toy private-reward environments.
            It runs candidate source in a subprocess with scratch cwd,
            stripped environment, deterministic seed, timeout, capped
            stdout/stderr, timing bands, public failure-code buckets, static
            preflight, and runtime import/file guards.
[real]      HiddenHoldoutSet split/accounting contract for private reward
            datasets. It creates train/reward/final-validation partitions,
            exposes public counts and split commitments, tracks reward-query
            counts, caps repeated candidate probes, requires minimum unique
            candidates before final validation, and gates final validation to
            bounded use.
[real]      SyntheticHiddenKeywordEnvironment toy private-reward environment.
            It wires HiddenHoldoutSet into bounded reward feedback and
            one-shot final validation over sealed synthetic records.
[partial]   Candidate sandboxing for arbitrary third-party code. The local
            Python sandbox is not OS/container isolation and is not sufficient
            for untrusted production candidate execution inside a CVM.
[partial]   Deployment manifest. `deployments/base-sepolia.json` now records
            current operator-controlled Base Sepolia `DiligenceRoom` and
            `EmailOracleAuth` deployments plus historical Phala records. BaseScan
            source verification, compose-hash registration, and fresh Phala
            quote evidence remain open. The recorded `DiligenceRoom` deployment
            predates the current verifier-signature `submitResult()` ABI, so a
            fresh deployment with `DILIGENCE_RESULT_VERIFIER` recorded is
            required before live-chain result-verifier enforcement is real.
[real]      Local chain watcher. `tinker_delegate.chain_watcher` can decode
            `DiligenceRoom` lifecycle logs from JSON-RPC, post bounded
            `/deal/chain-event` audit markers, call `/deal/notify-funded` when
            a funded event has matching created-deal context, and call
            `/deal/{deal_id}/resolve` for accept/reject/expire events. It has
            mocked JSON-RPC/API coverage, a `watch-chain` CLI, durable
            `ChainCursorStore` restart state, confirmation-safe polling, and a
            local Anvil proof script that emits real `DealCreated`/`DealFunded`
            logs and verifies bounded control-plane state updates.
[partial]   Chain-watcher operations. The watcher is not yet deployed as a
            Phala/CVM process and does not yet have chain-lag alerting or
            deep-reorg rollback beyond the configured confirmation policy.
[partial]   TEE-to-chain result submission. `tinker_delegate.chain_submitter`
            can derive an Ethereum signer from dstack key material, guard
            `submitResult()` against public `deals(dealId)` state, sign a raw
            transaction without a raw-private-key CLI/env path, broadcast it
            through JSON-RPC, and emit only bounded receipt metadata. The
            submitted `resultHash` is an anti-replay commitment over chain ID,
            contract, deal ID, signer nonce, compose hash, payload result hash,
            score band, compute cost, and expiry. `DiligenceRoom.sol` now
            requires a configured result verifier signature over chain ID,
            contract address, deal ID, TEE identity, compose hash, score band,
            compute cost, result commitment, and authorization expiry before
            accepting `submitResult()`. The `submit-result` path also fetches
            and verifies signer quote evidence whose report data binds signer
            address, chain ID, and contract address; the bounded receipt
            includes quote hash, report data, quote size, authorization expiry,
            and verifier-signature hash. `scripts/prove-chain-submitter-dstack-anvil.py`
            proves this against the Phala/dstack simulator plus ephemeral Anvil
            and verifies a real `EvaluationSubmitted` event. This still needs a
            production verifier service that signs only after live Phala quote
            verification and a deployed-CVM broadcast proof.
[real]      Result-verifier authorization policy module.
            `tinker_delegate.result_verifier` validates signer attestation
            evidence against signer address, chain ID, contract address, report
            data, quote report data, approved compose hashes, approved app IDs,
            optional OS image hashes, revoked quote hashes, revoked TEE signers,
            distinct verifier/TEE keys, and a short authorization TTL before it
            signs the exact `DiligenceRoom` authorization digest. Tests prove
            accepted authorization and fail-closed policy, context, revocation,
            self-approval, and non-dstack custody cases.
[real]      Result-verifier operator CLI path. `result-verifier-address` reports
            the dstack-derived verifier address for deployment, and
            `authorize-result` consumes bounded signer-attestation JSON plus
            explicit compose/app/OS-image allowlists and revocation lists before
            emitting bounded authorization metadata and the public verifier
            signature required by the contract. The dstack-simulator Anvil proof
            now uses this CLI path instead of ad hoc Anvil `eth_sign`.
[partial]   Production result-verifier service. The policy/signature library and
            operator CLI are real, but not yet deployed as a Phala/CVM service,
            and they still rely on bounded dstack quote envelope checks rather
            than full cryptographic Intel TDX quote parsing/freshness.
[modeled]   TTT/RL bio validation. Current evaluator is stub/SFT-oriented.
[modeled]   Multi-party coordination, corpus policy, royalty metering, consent/revocation.
[planned]   Real on-chain quote verification, DLP/egress enforcement, production frontend.
```

## Repository Map

```
dnai-wikigen/
|
|-- README.md                         Product thesis and hackathon overview
|-- ARCHITECTURE.md                   This document
|-- AGENTS.md / CLAUDE.md             Agent instructions and project boundaries
|-- example.env                       Environment template, no secrets
|-- quickstart.sh                     Dependency bootstrap
|
|-- .codex/skills/                    Codex workflow skills
|-- .claude/skills/                   Claude workflow skills
|-- .agents/skills/                   Agent workflow skills
|
|-- gear: services and executable prototypes
|   |
|   |-- cdp-playground/               Neko Chrome + CDP automation sandbox
|   |-- tee-email-oracle/             TEE email account + OTP oracle
|   |-- tinker-delegate/              TEE Tinker account + evaluation + escrow API
|   |-- props-room/                   Source/controller/data-room stub
|   `-- whatsapp-delegate/            Browser-mediated personal-data delegate
|
|-- papers: read-only research/spec material
|   |
|   |-- ndai/                         NDAI paper
|   |-- dstack/                       dstack paper
|   |-- conseca/                      ConSECA paper
|   |-- thinking-machines/            Tinker docs snapshot
|   |-- tee-email-oracle/             Email oracle specs
|   `-- tinker-delegate/              Tinker delegate specs
|
`-- specimens: read-only reference submodules
    |
    |-- dstack, dstack-examples
    |-- amiller/*                     Devproof, dstack, oracle, OpenClaw refs
    |-- thinking-machines/*           Tinker SDK/cookbook/project ideas
    |-- m1k1o/neko, G-structure/neko
    `-- tv                            Corpus/data pipeline reference
```

The directories named with emoji are rendered above as `gear`, `papers`, and
`specimens` for readability. In the repository they are `⚙️/`, `📄/`, and `🔬/`.

## System Overview

```
                         users, agents, reviewers
          seller/data owner     buyer/sponsor      human reviewer
                 |                  |                    |
                 v                  v                    v
        +---------------------------------------------------------+
        |                    web client / API clients             |
        |    room creation, reserve price, budget cap, policy     |
        +--------------------------+------------------------------+
                                   |
                                   v
        +---------------------------------------------------------+
        |                 DNAI coordination layer                  |
        |  access request -> gate -> consent -> execute -> settle |
        |                                                         |
        |  [modeled] multi-party reducer                          |
        |  [modeled] corpus policy and consent grants             |
        |  [real]    bounded result types and escrow primitives   |
        +-------------+----------------------+--------------------+
                      |                      |
                      | notify / OTP / hold | execute / evaluate / settle
                      v                      v
        +----------------------------+   +----------------------------+
        | tee-email-oracle CVM       |   | tinker-delegate CVM        |
        |                            |   |                            |
        | email account sealed in TEE|   | Tinker account sealed in TEE
        | IMAP OTP extraction        |   | browser login automation   |
        | reviewer/owner confirmation|   | API key provisioning       |
        | attestation endpoint       |   | billing automation         |
        +-------------+--------------+   | IsolatedTinkerSession      |
                      |                  | evaluator + cost meter     |
                      |                  +-------------+--------------+
                      |                                |
                      v                                v
        +----------------------------+   +----------------------------+
        | EmailOracleAuth.sol        |   | DiligenceRoom.sol         |
        | app/compose-hash policy    |   | escrow + result hash      |
        | consumer authorization     |   | reserve + budget cap      |
        +----------------------------+   +----------------------------+
                         Base Sepolia / Base-compatible chain
```

The architecture is split into three trust domains:

```
1. Public / user domain
   Browser clients, wallets, reviewers, sellers, buyers, sponsors.

2. Attested compute domain
   dstack CVMs on Phala Cloud. Secrets and raw artifacts are usable only here.

3. Public settlement / verification domain
   Base Sepolia contracts, result hashes, app-auth policy, and withdrawals.
```

## Core Concepts

### Encumbered Account

An encumbered account is an account whose credentials are not held by a human
operator. The account is created, stored, and used inside an attested TEE. Human
users interact with the account through bounded APIs and attestations rather
than through raw credentials.

In this repo there are two main encumbered-account patterns:

```
Email encumbered account
  - TEE creates or stores an email account.
  - TEE reads OTPs over IMAP.
  - TEE exposes bounded OTP/notification APIs.
  - EmailOracleAuth.sol governs measured-code boot / consumer policy.

Tinker encumbered account
  - TEE logs into Tinker through browser automation.
  - TEE captures and seals a Tinker API key.
  - TEE funds or checks balance through Tinker billing UI once funding is unblocked.
  - TEE exposes only metered, scoped evaluation APIs.
  - DiligenceRoom.sol settles escrow around bounded evaluation results.
```

The email TEE is not just disposable email or a convenience inbox. Its job is to
hold an email account that no human can access, so OTPs, confirmations, and
future reviewer/owner messages can be consumed by attested code without giving
operators the account credentials. That matters for Tinker because the Tinker
account is supposed to be agent-owned: the TEE requests the magic-code email,
the email oracle reads it, and the Tinker delegate uses it inside the browser
session.

The Tinker side is intentionally marked in progress. The account can only become
useful once it can be funded without leaking card details or handing account
credentials to a human. The intended path is card data encrypted to the TEE,
then browser automation drives the Tinker/Stripe billing form from inside the
TEE and clears the card payload from memory. The current blocker is reliable
browser posture around Tinker auth and Stripe/Tinker bot checks, not the
existence of the email oracle.

### Bounded Output

Bounded output is the safety boundary. Raw artifacts, raw private data, full
model weights, raw samples, card data, and account credentials should not leave
the TEE. Outputs are reduced before egress:

```
raw artifact            -> artifact hash
raw benchmark delta     -> score band
raw model output        -> yes/no or category band
raw deal valuation      -> offer within buyer cap
raw run record          -> result hash + attestation
raw messages / corpus   -> aggregate counts or activity bands
```

### NDAI Diligence Room

The NDAI diligence room maps the paper's mechanism into product primitives:

```
seller reserve price  -> minimum acceptable payment
buyer budget cap      -> maximum spend / overpayment bound
TEE evaluator         -> buyer-side agent inside the boundary
bounded output        -> no direct disclosure of the seller artifact
escrow state machine  -> settle, reject, expire, withdraw
```

## Primary Control Flow

This is the intended end-to-end flow for a private artifact or bio dataset.

```
1. Seller / controller prepares artifact
   |
   |  artifact bytes stay private
   v
2. Seller creates deal
   |
   |  createDeal(reservePrice, expiry, artifactHash, teeIdentity)
   v
3. Buyer funds deal
   |
   |  fundDeal() with ETH as budget cap
   v
4. TEE receives artifact
   |
   |  encrypted to the attestation-exposed TEE public key
   |  ciphertext is bound to deal ID and artifactHash
   |  verify keccak256(rawArtifact) == artifactHash
   |  artifact held in enclave memory or sealed store
   v
5. Gate / coordination layer checks request
   |
   |-- identity and role
   |-- purpose and allowlist
   |-- bio-risk / dual-use screen
   `-- attested execution requirement
   |
   v
6. Tinker delegate starts isolated session
   |
   |-- create one training/evaluation run for the deal
   |-- meter compute cost
   |-- enforce checkpoint TTL
   |-- restrict sampling to session-owned checkpoint paths
   v
7. Evaluator runs bounded assessment
   |
   |  current: stub/SFT evaluator
   |  target: TTT/RL bio-validation loop
   v
8. Control plane bounds raw metrics
   |
   |  raw delta -> ScoreBand
   |  score/budget/reserve -> offer
   |  full result -> resultHash
   v
9. TEE submits result to contract
   |
   |  submitResult(..., resultHash, composeHash, authorizationExpiry, verifierSignature)
   v
10. Buyer accepts, rejects, or deal expires
   |
   |-- acceptDeal(dealPayment)
   |-- rejectDeal()
   `-- expireDeal()
   |
   v
11. Pull-payment settlement
   |
   |-- seller withdraws payment if accepted
   |-- developer withdraws compute + fee
   `-- buyer withdraws refund
```

## Primary Data Flow

```
                         public chain data
             +--------------------------------------+
             | reserve, budget cap, result hash     |
             | score band, state, withdrawals       |
             +------------------+-------------------+
                                ^
                                |
seller artifact                 | bounded result only
or private corpus               |
        |                       |
        v                       |
+-------------------+       +---+-------------------+
| TEE ingress       |       | Tinker delegate TEE   |
|                   |       |                       |
| upload bytes      +------>| raw evaluation        |
| seal/store data   |       | TTT/RL/SFT/stub eval  |
| hash artifact     |       | cost meter            |
+-------------------+       | output bounding       |
                            +---+-------------------+
                                |
                                | no raw data, no weights,
                                | no exact metric leakage
                                v
                       +------------------+
                       | bounded output   |
                       | score band       |
                       | recommendation   |
                       | offer            |
                       | result hash      |
                       | attestation      |
                       +------------------+
```

Sensitive data classes and where they are allowed to exist:

```
email password / IMAP creds      tee-email-oracle sealed store only
email OTP                        tee-email-oracle memory, then bounded OTP response
Tinker session cookies           browser inside TEE only
Tinker API key                   tinker-delegate encrypted key store or Phala encrypted env
payment card details             encrypted-to-TEE payload, transient memory, Stripe iframe
seller artifact                  TEE memory or sealed store, never public
training checkpoints             Tinker run scoped to deal, TTL-enforced, cleaned up
raw model samples                evaluator-internal only
bounded score/offer/result hash  API response and chain
```

## The Four-Part Spine

The user-facing architecture can be read as a four-part chain:

```
        +------------------------+
        | Email encumbrance      |
        | "who may coordinate?"  |
        +-----------+------------+
                    |
                    v
        +------------------------+
        | Tinker encumbrance     |
        | "who may spend/run?"   |
        +-----------+------------+
                    |
                    v
        +------------------------+
        | TTT/RL bio validation  |
        | "what did it prove?"   |
        +-----------+------------+
                    |
                    v
        +------------------------+
        | DNAI settlement        |
        | "what may be revealed |
        |  and who gets paid?"   |
        +------------------------+
```

### 1. Email Encumbered Contract

Current concrete contract:

```
EmailOracleAuth.sol
```

Purpose:

```
authorize which measured TEE app may boot as the email oracle
authorize which consumer app compose hashes may request OTPs
allow owner-managed upgrade delay
allow owner to freeze oracle code authorization
allow separate freeze for consumer registry
support non-escalating delegation through consumer managers
```

Runtime service:

```
tee-email-oracle
```

Runtime role:

```
create / load email credentials
seal email credentials with AES-256-GCM or dstack-derived key
connect to IMAP
extract magic-code OTPs for Tinker or other delegated accounts
serve health, inbox, pin, and attestation endpoints
act as future notification / confirmation channel for reviewers and owners
```

Clarification:

```
The email TEE is a no-human-access control channel.
It is used for OTPs and confirmations that an agent-owned account needs.
It is not the funding mechanism, and it does not by itself solve Tinker signup.
```

Diagram:

```
                     Base Sepolia
                 +-------------------+
                 | EmailOracleAuth   |
                 |-------------------|
                 | owner             |
                 | compose hashes    |
                 | device policy     |
                 | consumer hashes   |
                 | freeze flags      |
                 +---------+---------+
                           ^
                           | app auth / policy anchor
                           |
+--------------------------+---------------------------+
| tee-email-oracle CVM                                 |
|                                                      |
|  +-------------+      +-------------+      +-------+ |
|  | Credential  |<---->| IMAP client |<---->| email | |
|  | store       |      | OTP parser  |      | host  | |
|  +------+------+      +------+------+      +-------+ |
|         |                    |                       |
|         v                    v                       |
|  sealed email creds     /pin response                |
|                                                      |
|  endpoints: /health /pin /inbox /attestation         |
|             /credentials/encrypted                   |
+------------------------------------------------------+
```

Implementation status:

```
[real]      EmailOracleAuth.sol and tests.
[real]      email_oracle API, credential store, IMAP client.
[real]      Scoped `/pin` requests require target service, sender scope, nonce,
            caller identity, and reason; released OTP hashes are persisted for
            one-time-use across oracle restarts when the replay ledger decrypts.
[real]      OTP replay ledger is persisted under encrypted/sealed oracle storage.
[real]      Attestation-bound encrypted credential provisioning exists for an
            operator-held mailbox: `GET /attestation?context=oracle-credentials`
            exposes a context-bound public key and report-data hash, while
            `POST /credentials/encrypted` is disabled by default, requires an
            explicit provisioning bearer token, stores only through the sealed
            credential store, and returns hashes/status rather than raw mailbox
            credentials.
[partial]   The running Phala oracle has not yet been provisioned with real
            mailbox credentials through that path, so live Tinker OTP receipt in
            the CVM is still unproven.
[partial]   App-auth contract is not yet enforced on every OTP API request.
[planned]   Reviewer notification, consent confirmation, outbound bounded-result delivery.
```

### 2. Tinker Encumbered Contract

`TinkerAccountEncumbrance.sol` is now the dedicated on-chain policy/audit
surface for the TEE-owned Tinker account. It does not custody card data,
credentials, or Tinker balances. It records and enforces bounded account
operation policy while the actual browser/API automation remains inside the TEE.
The current repo splits Tinker encumbrance across:

```
TinkerAccountEncumbrance.sol      account policy, manager limits, measurement allowlist, audit events
DiligenceRoom.sol                 on-chain escrow and bounded-result settlement
tinker-delegate service           TEE-held Tinker account and API key
IsolatedTinkerSession             runtime confinement around Tinker SDK usage
card_channel.py / billing.py      encrypted card channel and billing automation
```

Runtime role:

```
use tee-email-oracle OTP to create/sign into a Tinker account
seal Tinker API key
drive Tinker billing through a browser session once auth/funding is unblocked
add balance using card-on-file or encrypted card payload once Stripe flow works
create a one-deal isolated Tinker session
meter compute and fee
check operation against TinkerAccountEncumbrance policy before funding/spend
clean up checkpoints after resolution
submit bounded result to DiligenceRoom
```

Current concrete policy contract:

```
TinkerAccountEncumbrance.sol
  owner
  accountCommitment = hash/commitment for the TEE-owned Tinker account
  approvedComposeHashes[composeHash] = true/false
  managers[account] = true/false
  maxAddBalanceWei
  maxSpendWei
  emergencyHalted
  measurementsFrozen

  authorizeOperation(operationId, kind, requester, composeHash, amountWei)
  settleOperation(operationId, success, receiptHash)
```

Diagram:

```
                          Base Sepolia
                 +---------------------------+
                 | DiligenceRoom.sol         |
                 |---------------------------|
                 | deals[dealId]             |
                 | seller / buyer            |
                 | reservePrice / budgetCap  |
                 | artifactHash              |
                 | teeIdentity               |
                 | scoreBand / resultHash    |
                 | pendingWithdrawals        |
                 +-------------+-------------+
                               ^
                               | submitResult / settle
                               |
+------------------------------+------------------------------+
| tinker-delegate CVM                                         |
|                                                             |
|  +----------------+       +----------------------+          |
|  | signup.py      |<----->| tee-email-oracle     |          |
|  | browser OTP    | OTP   | /pin                 |          |
|  +-------+--------+       +----------------------+          |
|          |                                                  |
|          v                                                  |
|  +----------------+      +----------------------+           |
|  | Tinker console |----->| sealed API key store |           |
|  | browser session|      +----------+-----------+           |
|  +-------+--------+                 |                       |
|          |                          v                       |
|          |              +--------------------------+        |
|          |              | IsolatedTinkerSession    |        |
|          |              | one training run/deal    |        |
|          |              | TTL checkpoints          |        |
|          |              | path-checked sampling    |        |
|          |              | cost meter               |        |
|          |              +------------+-------------+        |
|          |                           |                      |
|          v                           v                      |
|  +---------------+        +------------------------+        |
|  | billing.py    |        | evaluator/controlPlane |        |
|  | Stripe iframe |        | score band + offer     |        |
|  +---------------+        +------------------------+        |
+-------------------------------------------------------------+
```

Implementation status:

```
[real]      API routes, billing code, encrypted card channel, key store, control plane.
[real]      DiligenceRoom.sol and tests.
[real]      TinkerAccountEncumbrance.sol and tests. The contract stores a
            hashed Tinker account commitment, approved compose hashes,
            owner-managed managers, add-balance/spend caps, emergency halt,
            measurement freeze, operation authorization records, and bounded
            settlement receipt hashes. Managers can authorize/settle only
            operations inside owner-set caps and approved measurements; tests
            prove managers cannot set managers, change caps, approve
            measurements, toggle halt, exceed caps, or bypass compose,
            duplicate, and settlement guards.
[real]      The tinker-delegate runtime has a read-only
            TinkerAccountEncumbrance preflight helper and CLI. When
            `TINKER_ENCUMBRANCE_REQUIRED=true` or an encumbrance contract
            address is configured, payment-method and add-balance automation
            deny before card decryption or browser launch unless public
            contract reads show the compose hash is approved, emergency halt is
            off, and the amount is within cap.
[partial]   TinkerAccountEncumbrance is not yet deployed or recorded in the
            Base Sepolia manifest, so deployed funding still needs the live
            contract address, compose hash, policy caps, and on-chain evidence.
[real]      Local Neko/CDP Tinker login, email OTP retrieval, onboarding, and API-key provisioning.
[real]      Signup/bootstrap stores captured Tinker API keys in encrypted
            storage and returns only bounded hash/status metadata.
[real]      API-key provisioning uses a small selector fallback family for
            current Tinker key-creation copy plus aria-label/data-testid
            variants, returns bounded `api_key_provisioning` attempt records,
            including `selector_missing` when no key can be captured, and has
            replayable mock-page tests for successful extraction and selector
            drift failure paths.
[real]      Tinker re-auth exists as a bounded OTP refresh path through
            `reauth` and opt-in `POST /auth/reauth`; it returns only
            `tinker_auth` attempt records and does not expose account email,
            OTP, browser URL, API key, or page text.
[real]      `⚙️/tinker-delegate/docs/TINKER-AUTOMATION-ROUTE.md` records the
            acceptable Tinker automation route: prefer official/support-approved
            workflows; use browser automation only as bounded TEE custody for
            this project's own account; fail closed rather than add stealth,
            CAPTCHA-solving, rotating-proxy, or automation-control masking.
            Static tests enforce those no-evasion runtime dependencies/flags.
[real]      Local Stripe test-card billing path reaches submission and returns a bounded decline.
[real]      Billing automation returns bounded payment-method and add-balance
            attempt records: outcome class, furthest stage, issued timestamp,
            evidence hash, amount/balance bands, TDX quote hash when present,
            and card-payload destruction status. Raw card values and page text
            are not returned.
[real]      Billing automation uses explicit selector fallback families for
            Tinker balance/payment controls, payment-method submit controls,
            cardholder/address fields, add-balance amount fields, and top-up
            confirmation controls. Replayable mock-page tests cover current
            selectors plus data-testid/aria-style drift, and missing top-up
            controls return bounded `selector_missing` receipts without page
            text.
[real]      Payment-method debug screenshots are suppressed after card entry
            and payment submission even when debug screenshots are enabled;
            non-secret billing screenshots still require explicit debug opt-in.
[real]      Card submission attempts purge known secret-bearing browser debug
            artifacts (`trace*.zip`, HAR, video, card/Stripe screenshots) from
            an explicitly configured debug artifact directory.
[real]      Tinker delegate Python entrypoints set `RLIMIT_CORE=0`, and local /
            Phala compose services for the delegate and browser path set
            `ulimits.core: 0` to prevent core dumps from persisting secrets.
[real]      Bounded funding attempt records are persisted in encrypted/sealed
            delegate storage with a separate `tinker/funding_receipts` dstack
            key path and can be read through `GET /billing/funding-receipts`.
            The store rejects unknown fields and `raw_secret_egress=true`.
[real]      Bounded deal/run lifecycle metadata is persisted in a separate
            encrypted/sealed delegate store at `/data/run_metadata.enc` in
            compose profiles, with its own `tinker/run_metadata` dstack key
            path. Control-plane events store hashed deal/account/run handles,
            artifact hashes and size bands, score/offer/cost bands, and
            cleanup counts; raw artifacts, API keys, card fields, checkpoint
            IDs, and raw Tinker run IDs are not allowed in the schema.
[real]      Add-balance automation enforces `TINKER_MAX_ADD_BALANCE_USD`
            before launching browser automation. Non-finite, non-positive, and
            over-cap requests return bounded `policy_denied` `add_balance`
            receipts at `not_started` with amount bands, not page text.
[real]      `TINKER_FUNDING_MODE=manual_prefund` is the default production
            funding model and denies card/add-balance browser automation before
            decryption or browser launch. `operator_capped_validation` is
            required for one-off approved operator validation attempts; denied
            requests persist bounded `policy_denied` receipts. The bounded
            policy is inspectable through `GET /billing/funding-policy` and
            the `funding-policy` CLI.
[real]      Operator funding preflight is available through
            `GET /billing/funding-preflight` and the `funding-preflight` CLI.
            It checks funding mode, requested amount cap, optional add-balance
            endpoint flag, encrypted receipt-store availability, and billing
            attestation policy before any card payload or browser launch. The
            CLI can write the bounded preflight JSON directly with `--output`.
[real]      A local FastAPI funding smoke on 2026-07-08 verified the current
            operator guardrails without real card material: `$5` preflight
            passed under `operator_capped_validation`, `$10` preflight failed
            the cap and disabled add-balance endpoint checks, `/attestation`
            returned a context-bound local billing key, encrypted
            `/billing/card/encrypted` posted only ciphertext and returned a
            bounded `payment_method` receipt at `payment_submitted`, and the
            encrypted temp receipt file did not contain the test card number,
            CVC, cardholder name, postal code, or raw card field names.
[real]      Bounded funding validation manifests can be built from saved
            preflight and receipt JSON through the `funding-manifest` CLI. The
            manifest stores hashes, bands, outcome, TDX quote hash, and
            card-destruction/no-raw-egress booleans; it rejects raw card,
            API-key, and secret-shaped inputs and does not store card material.
[real]      Saved funding manifests can be replay-verified with
            `verify-funding-manifest`, which recomputes preflight, receipt,
            validation-ID, attestation-policy, and manifest hashes and returns
            named bounded pass/fail checks without echoing packet contents.
[real]      Billing receipt-producing CLIs can write bounded attempt records
            with `--receipt-output` for later manifest binding. CLI rendering
            fails closed before printing or writing JSON when output contains
            secret-shaped material or submitted card values.
[real]      `funding-validation-packet` generates a bounded operator packet in
            one command: preflight JSON, receipt JSON, manifest JSON,
            verification JSON, and summary JSON. It can bind an existing
            bounded receipt, or run encrypted card submission only when
            `--run-card-attempt` is explicitly set; card fields without that
            flag are rejected before any network or browser path.
[real]      Packet generation supports `--prompt-card` for approved operator
            validation: card fields are prompted interactively instead of
            accepted through command-line arguments, prompt mode is mutually
            exclusive with test-card flags, and deployed compose/app/OS-image
            attestation expectations are required before prompting unless
            local-development attestation is explicitly allowed.
[real]      Funding validation packets can also include separate add-balance
            evidence: an add-balance receipt, manifest, verification, and
            summary fields. The runner can bind an existing bounded top-up
            receipt, or POST only the amount to `/billing/add-balance` when
            `--run-add-balance-attempt` is explicitly set and `--amount` is
            provided.
[real]      `check-funding-validation-packet` replay-checks packet directories:
            required files, payment manifest replay, optional add-balance
            manifest replay, summary hash consistency, and optional deployed
            TDX attestation evidence. It returns only bounded pass/fail checks
            and does not echo packet bodies.
[real]      The FastAPI `POST /billing/add-balance` mutation endpoint is
            disabled by default behind `TINKER_ALLOW_ADD_BALANCE_ENDPOINT`.
            The lower-level CLI/internal handler still requires
            `operator_capped_validation` mode before deliberate capped operator
            validation attempts.
[real]      Stripe/PCI funding stance is documented in
            `⚙️/tinker-delegate/docs/STRIPE-PCI-FUNDING-SCOPE.md`: the
            encrypted raw-card channel is only an operator-owned capped
            validation path, while production or repeated funding should use an
            official Tinker route, Stripe-hosted/tokenized collection,
            SetupIntent / PaymentMethod style reuse with consent, or
            manual/developer prefunding until compliance review approves
            otherwise.
[real]      Plaintext card API is disabled by default and unavailable in dstack mode.
[real]      Central redaction helpers scrub bearer, OTP/password, card, API-key,
            and artifact-shaped values from bounded errors and high-risk logs.
[real]      Artifact upload verifies Ethereum keccak256 against artifactHash
            before DealContext state changes; mutable API decode buffers and
            stored control-plane artifact buffers are best-effort zeroed.
[real]      Encrypted artifact upload uses the attestation-exposed TEE public
            key, artifact-specific HKDF context, and deal/hash-bound AES-GCM
            associated data; plaintext artifact upload is disabled by default.
[real]      Artifact upload AES keys are derived with per-deal/per-artifact
            HKDF info, so ciphertexts cannot decrypt under another deal ID or
            artifact hash even with the same TEE public key.
[real]      Attestation report data binds operation context plus the TEE
            encryption public key so verifiers can detect key substitution.
[real]      `/attestation` accepts an explicit bounded context query
            (`ingress`, `artifact`, or `billing`) and rejects unsupported
            contexts. Encrypted artifact and billing clients request their
            context before encrypting payloads.
[real]      Client-side artifact uploader fetches
            `/attestation?context=artifact` and refuses to encrypt or upload
            unless mode, quote presence, compose hash, app ID, public-key shape,
            and report data match policy.
[real]      Client-side encrypted billing uploader fetches context-bound
            billing attestation, refuses local/non-matching evidence unless
            explicitly allowed, encrypts card JSON to `/billing/card/encrypted`,
            wipes its plaintext buffer, and posts only ciphertext.
[real]      `add-card-encrypted-prompt` supports approved operator validation
            attempts without putting card fields in command-line arguments. It
            prompts interactively, requires deployed compose/app/OS-image
            attestation expectations unless explicitly run in local-development
            mode, zeros the in-memory card dictionary after upload, and emits
            only bounded response/receipt JSON.
[real]      Standalone `verify-attestation` CLI live-fetches
            `/attestation?context=...` and checks the public evidence envelope:
            mode, quote presence, compose hash, app ID, OS image hash,
            report-data key binding, exposed quote-report-data equality when
            present, and client fetch freshness.
[real]      Standalone `verify-compose-hash` CLI renders a registry-image
            Docker Compose file with explicit env, rejects local `build:`
            services and mutable tag-only images, emits the digest-pinned image
            manifest, and computes the Phala Cloud-style compose hash over the
            rendered app-compose object. It also has a Phala raw-compose mode
            for deployed CVMs where the local image-policy hash is separate
            from Phala's attested full app-compose hash, because Phala includes
            allowed encrypted env names and platform metadata in the live hash.
            The Phala Playwright sidecar image is pinned by amd64 digest in
            `docker-compose.all.phala.yaml`.
[real]      `.github/workflows/build-tee-images.yml` builds the deploy-critical
            `tee-email-oracle` and `tinker-delegate` images on GitHub-hosted
            runners for `linux/amd64`, pushes SHA-tagged images to GHCR, asks
            BuildKit to attach SBOM/provenance attestations, generates an SPDX
            SBOM with Syft, and emits GitHub-native signed provenance and SBOM
            attestations bound to the pushed image digest. The Dockerfiles for
            those two services pin the Python runtime image and `uv` helper
            image by versioned digest.
[real]      `scripts/verify-ghcr-image-attestation.sh` is the pre-Phala image
            gate: it accepts only digest-pinned GHCR image references and uses
            `gh attestation verify` against OCI-attached attestations to enforce
            this repository, `.github/workflows/build-tee-images.yml`, the
            expected source commit, GitHub-hosted runner provenance, SLSA
            provenance predicate, and SPDX SBOM predicate before a digest is
            allowed into the Phala compose file.
[real]      Standalone `verify-cvm-attestation` CLI and
            `scripts/verify-cvm-attestation.sh` render the Phala compose file,
            enforce required digest-pinned image references or sha256 image
            digests, fetch `/attestation?context=...`, and accept only a live
            attestation whose compose hash, app ID, OS image hash, report-data
            key binding, public key, and client freshness match policy. The
            emitted bundle is bounded public evidence and labels Intel TDX
            quote internals as not yet cryptographically parsed.
[real]      Standalone `verify-deployment-bundle` CLI combines the deploy-time
            and runtime gates in one public certificate: it verifies
            GitHub-signed SLSA provenance and SPDX SBOM attestations for each
            digest-pinned GHCR oracle/delegate image, requires those exact image
            refs inside the rendered Phala compose, optionally requires sidecar
            image digests, then verifies the live CVM app/compose/OS-image
            attestation envelope. The bundle records `raw_secret_egress=false`
            and does not include raw quotes, app-compose bodies, secrets, OTPs,
            card material, artifacts, or API keys.
[real]      Current Phala deployment runs the combined oracle/delegate stack in
            CVM `670b3b21-4338-4d4e-ae72-7c8922579f59` with app ID
            `f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717`, public logs/sysinfo
            disabled, digest-pinned GHCR images verified by GitHub
            attestations, delegate `/health` returning `ok`, oracle `/health`
            returning degraded until credentials are sealed, and live delegate
            attestation verification passing against Phala compose hash
            `0c745547099dd2c1f0777cc60deb163b040b920dfcf736697edd53dce1d26985`.
            Oracle credential-ingress attestation is live for
            `context=oracle-credentials`, but credential provisioning is
            disabled by default and no real mailbox credentials have been
            sealed into the running CVM.
            The current source commit, image digests, endpoints, and bounded
            quote-envelope fields are recorded in `deployments/base-sepolia.json`.
[real]      In dstack mode `/attestation` includes public dstack evidence fields
            when available: event log, VM config, instance/device IDs,
            aggregated measurement, OS image hash, compose hash, and TCB info.
[real]      Encrypted FastAPI artifact ingress and control-plane evaluation
            dispatch have regression tests that fail on Python file open/write
            calls while raw artifact buffers are in scope.
[real]      IsolatedTinkerSession has mocked-SDK tests for explicit one training
            run per deal enforcement, TTL clamping on every checkpoint save
            path including save-and-sample, path-checked sampling, state
            checkpoints not being sampleable, cleanup deletion, retry-backed
            cleanup attestations, and metering.
[real]      Deal resolution stores a bounded cleanup attestation with counts,
            success flag, attempts, error type, and checkpoint-ID hash; raw
            checkpoint IDs are not included in the public record.
[real]      First-party SFT evaluator no longer reaches the raw Tinker
            ServiceClient. It uses wrapper methods only, including a scoped
            base-model sampler for tuned-vs-base comparison, and tests reject
            raw ServiceClient/REST/list/download/publish API usage in evaluator
            source.
[real]      Real Tinker SDK smoke-test harness exists but is disabled by
            default. It requires `TINKER_RUN_REAL_SDK_TESTS=1`,
            `TINKER_API_KEY`, and `TINKER_REAL_SDK_MAX_USD <= 0.50` before it
            will create a tiny training run, save a TTL checkpoint, sample, and
            cleanup.
[real]      The `tinker-delegate` Dockerfile copies `uv.lock` and installs with
            `uv sync --frozen --no-dev --extra agent`, so the packaged delegate
            image includes the optional Tinker SDK. A local build/run of
            `dnai-tinker-delegate-agent-extra:local` returned
            `/health.agent_stack_available=true`.
[real]      `scripts/verify-agent-image.sh` rebuilds the delegate image and
            verifies `import tinker` plus the `agent_stack_available` probe
            inside the image, emitting bounded JSON only.
[partial]   Deployed Phala/CVM browser posture has not been revalidated with the current selectors.
[partial]   Funding is in progress: card data can be encrypted to the TEE and
            bounded attempt receipts are returned/persisted, but payment-method
            token/reference capture and a capped real-card funding attempt still
            need to be proven. A bounded manifest can now summarize a saved
            preflight/receipt pair for audit, but it does not prove account
            funding by itself. Production or repeated card funding also needs
            legal/compliance approval.
[partial]   The real SDK harness must still be run inside the deployed CVM
            before claiming real evaluator execution.
[partial]   Cleanup attestations are generated locally, but deployed Tinker
            deletion and TTL-expiry behavior still need real SDK/CVM evidence.
[partial]   Arbitrary third-party evaluator code is not yet isolated from
            Python introspection. Before accepting untrusted evaluator code, run
            it behind a process/sandbox capability boundary rather than passing
            an in-process Python object.
[partial]   Artifact upload still needs full cryptographic Intel TDX quote
            parsing/freshness validation, downstream evaluator/Tinker/browser
            no-disk audit, sealed-retention key hierarchy if retention is added,
            and evaluator-side raw-byte lifetime audit.
[planned]   Dedicated Tinker account encumbrance contract / funding-rail policy contract.
```

### 3. TTT/RL Bio Validation

The target bio-validation layer is the place where Tinker compute becomes
scientific diligence:

```
private bio artifact or corpus
        |
        v
TTT/RL evaluator inside TEE
        |
        v
bounded proof of utility / safety / validation result
```

The repo currently includes Tinker RL docs, an evaluator shape, and the
`tinker_delegate.private_reward` environment contract. The real TTT/RL
bio-validation loop is not implemented. The current evaluator code is:

```
stub_evaluate()       deterministic synthetic result for testing
sft_evaluate()        LoRA/SFT-oriented evaluator shape using Tinker SDK
```

The private reward contract is:

```
PrivateRewardEnvironment.problem()          public problem text
PrivateRewardEnvironment.candidate_schema   allowed candidate envelope
PrivateRewardEnvironment.reward()           exact internal reward, TEE-only
PrivateRewardEnvironment.output_reducer()   approved bounded feedback
PrivateRewardEnvironment.query_budget       max queries and reward precision
PrivateRewardEnvironment.optimizer_policy   internal / attested remote / external
PrivateRewardEnvironment.optimizer_view()   public optimizer setup view
PrivateRewardEnvironment.internal_reward_for_optimizer()
                                            exact reward only for trusted optimizers
PrivateRewardEnvironment.finalize()         bounded result and hashes
PrivateRewardEnvironment.attest()           environment/transcript metadata
```

The local candidate sandbox contract is:

```
PythonCandidateSandbox.run(candidate)
  input:  UTF-8 Python source bytes
  guard:  AST preflight blocks file, process, network, import, dunder escapes
  runtime: subprocess, scratch cwd, stripped environment, deterministic seed
  limits: timeout, CPU/memory best-effort, max source bytes, capped stdout/stderr
  output: candidate hash, pass/reject/error/timeout, failure bucket,
          elapsed timing band, exit code, capped traces
```

This sandbox is a real local development guardrail, not the final production
answer for hostile third-party code. Production CVM execution still needs
OS/container isolation, no-network policy, mounted scratch-only filesystem,
resource cgroups/ulimits, and egress auditing.

The hidden holdout contract is:

```
HiddenHoldoutSet(records, policy)
  internal: raw records and record IDs
  split:    train / reward / final_validation
  public:   split commitment, partition counts, query counts, seed hash
  guard:    reward-query budget, per-candidate repeat cap, minimum unique
            reward candidates, and one-shot final validation gate
```

Public holdout manifests intentionally do not include record IDs, payloads, raw
labels, or split membership. Concrete private-reward environments still need to
wire this into their reward/final-validation control flow and add
domain-specific anti-overfitting tests.

Target architecture:

```
+--------------------------------------------------------------+
| TTT/RL Bio Validation                                        |
|--------------------------------------------------------------|
| input: sealed artifact / corpus / assay data / reward fn     |
|                                                              |
|  1. parse and validate artifact schema                       |
|  2. split train/eval or construct environment                |
|  3. run TTT/RL/SFT loop through IsolatedTinkerSession        |
|  4. evaluate against approved benchmark                      |
|  5. screen bio-risk and dual-use constraints                 |
|  6. reduce raw metrics to bounded outputs                    |
|  7. attach result hash and TDX quote                         |
|                                                              |
| output: yes/no, score band, confidence band, offer, hash     |
+--------------------------------------------------------------+
```

Data-flow guardrails:

```
raw sequences, assays, model samples, weights, gradients
        |
        | must stay inside TEE / Tinker session
        v
bounded output reducer
        |
        v
score band, pass/hold/deny, confidence, result hash
```

Optimizer placement guardrails:

```
internal TEE optimizer
  may read exact rewards and reward-derived state inside the attested boundary

attested remote optimizer
  may read exact rewards only when the remote service is separately attested

external optimizer
  receives public problem/schema metadata and bounded feedback only
  exact rewards, reward-derived state, private checkpoints, and holdout data
  are rejected by default policy
```

Implementation status:

```
[real]      PrivateRewardEnvironment base interface, LeakageBudget,
            QueryLeakageRecord, transcript hash, leakage hash, bounded
            feedback/result dataclasses, OptimizerPolicy, external bounded
            default mode, internal dense-reward mode, attested remote policy
            guard, and toy unit tests.
[real]      PythonCandidateSandbox for local toy candidates with preflight,
            subprocess timeout, deterministic seed, capped stdout/stderr, and
            no supported network/filesystem/process access.
[real]      Local sandbox side-channel buckets for elapsed timing, timeout
            normalization, capped output, best-effort memory limits, and
            policy/syntax/runtime/timeout failure codes.
[real]      HiddenHoldoutSet with deterministic private split, public split
            commitment, reward-query accounting, per-candidate repeat caps,
            minimum unique candidates before final validation, and one-shot
            final-validation gating.
[real]      SyntheticHiddenKeywordEnvironment with bounded reward bands,
            hidden reward partition queries, final-validation gating, and
            public manifests that omit record IDs and payloads.
[real]      `synthetic-private-reward-demo` CLI runs the synthetic hidden
            dataset environment and emits a bounded public packet: optimizer
            view, candidate hashes, reward bands, final result, transcript hash,
            leakage hash, and attestation metadata. Hidden records and submitted
            candidate strings are forbidden from the rendered output.
[modeled]   TTT/RL bio-validation concept.
[partial]   SFT evaluator scaffold.
[real]      Output banding and offer computation.
[planned]   Hardened production sandbox and deployed side-channel controls,
            domain-specific bio benchmark, risk classifier, and validation
            report schema.
```

### 4. DNAI

DNAI is the mechanism layer that composes the previous pieces:

```
DNAI = NDAI economic controls + TEE boundary + bounded evaluator + settlement
```

It answers:

```
Who owns the private artifact?
Who may inspect it?
What may the evaluator do?
What may leave the TEE?
How much can the buyer spend?
What is the seller's reserve?
Who gets paid if the buyer accepts?
What public evidence proves the result was produced by the expected enclave?
```

The current DNAI implementation is distributed:

```
README.md                         product description
getting-started.md                build plan and source map
tinker_delegate/control_plane.py  deal lifecycle inside TEE
tinker_delegate/evaluator.py      stub/SFT evaluator
tinker_delegate/session.py        isolated Tinker session
DiligenceRoom.sol                 escrow and settlement
docs/USER-FUNCTIONS.md            status and user capability catalog
docs/COORDINATION-ENGINE-SPEC.md  multi-party gate and effects model
```

## Smart Contract Architecture

### Contract Map

```
                         Base Sepolia

       +------------------------------------+
       | EmailOracleAuth.sol                |
       |------------------------------------|
       | Governs which email oracle code    |
       | and consumer compose hashes are    |
       | authorized.                        |
       +----------------+-------------------+
                        |
                        | supports app-auth policy
                        v
       +------------------------------------+
       | tee-email-oracle CVM               |
       +------------------------------------+


       +------------------------------------+
       | DiligenceRoom.sol                  |
       |------------------------------------|
       | Governs deal escrow, result hash,  |
       | buyer accept/reject/expire, and    |
       | pull-payment withdrawals.          |
       +----------------+-------------------+
                        |
                        | called by teeIdentity
                        v
       +------------------------------------+
       | tinker-delegate CVM                |
       +------------------------------------+
```

### EmailOracleAuth.sol

State model:

```
+---------------------------------------------------------+
| EmailOracleAuth                                         |
|---------------------------------------------------------|
| owner                                                   |
| ORACLE_UPGRADE_DELAY                                    |
| allowAnyDevice                                          |
| oracleCodeFrozen                                        |
| consumerRegistryFrozen                                  |
| allowedOracleComposeHashes[composeHash]                 |
| pendingOracleComposeHashes[composeHash] -> activatesAt  |
| allowedDeviceIds[deviceId]                              |
| consumerManagers[address]                               |
| allowedConsumerComposeHashes[consumerApp][composeHash]  |
+---------------------------------------------------------+
```

Control flow:

```
owner deploys auth contract
        |
        v
optional initial oracle compose hash is allowed
        |
        v
owner proposes new compose hash
        |
        v
upgrade delay passes
        |
        v
anyone activates pending hash
        |
        v
dstack KMS / boot check calls isAppAllowed(bootInfo)
        |
        |-- appId must equal contract address
        |-- composeHash must be allowed
        |-- deviceId must be allowed unless allowAnyDevice
        v
oracle boot allowed or denied
```

Consumer-management flow:

```
owner
  |
  | setConsumerManager(manager, true)
  v
manager
  |
  | addConsumerComposeHash(consumerApp, composeHash)
  v
consumer app may be recognized by off-chain/oracle policy
```

Freeze flow:

```
freezeOracleCodeAuth()
        |
        v
oracle compose/device policy can no longer mutate

freezeConsumerRegistry()
        |
        v
consumer compose-hash registry can no longer mutate
```

Security intent:

```
oracle policy is controlled by owner
consumer registry can be delegated
manager cannot change oracle boot policy
freezing separates production oracle code from development consumer onboarding
```

Current caveat:

```
The contract exists and is tested. The FastAPI /pin and /inbox paths now have
[real] runtime bearer enforcement for same-CVM deployments: the oracle and
delegate derive the same secret from the dstack key path
oracle/runtime-auth, and local dev can use ORACLE_RUNTIME_AUTH_TOKEN /
TINKER_ORACLE_AUTH_TOKEN. The routes also have [real] optional on-chain
EmailOracleAuth consumer-registry enforcement: when ORACLE_AUTH_REQUIRED=true
or a contract is configured, /pin and /inbox fail closed before IMAP access
unless isConsumerAuthorized(consumerApp, composeHash) returns true. Live
compose-hash registration on Base Sepolia is still [partial]/[planned] until
the final oracle and consumer compose hashes are registered.
```

### DiligenceRoom.sol

Deal state machine:

```
          createDeal()
        +------------+
        |  Created   |
        +-----+------+
              |
              | fundDeal() with msg.value = budgetCap
              v
        +------------+
        |   Funded   |
        +-----+------+
              |
              | submitResult() by teeIdentity
              v
        +------------+
        | Evaluated  |
        +--+------+--+
           |      |
 acceptDeal()   rejectDeal()
           |      |
           v      v
    +----------+ +----------+
    | Accepted | | Rejected |
    +----------+ +----------+

 expiry may move Created/Funded/Evaluated -> Expired
 withdrawals happen after settlement through pendingWithdrawals
```

Storage model:

```
+------------------------------------------------+
| Deal                                           |
|------------------------------------------------|
| seller                                         |
| buyer                                          |
| reservePrice                                   |
| budgetCap                                      |
| expiry                                         |
| state                                          |
| artifactHash                                   |
| teeIdentity                                    |
| scoreBand                                      |
| computeCost                                    |
| fee                                            |
| resultHash                                     |
+------------------------------------------------+
```

Settlement flow:

```
acceptDeal(dealPayment)
        |
        | require buyer
        | require dealPayment >= reservePrice
        | require dealPayment + computeCost + fee <= budgetCap
        v
pendingWithdrawals[seller]    += dealPayment
pendingWithdrawals[developer] += computeCost + fee
pendingWithdrawals[buyer]     += refund
        |
        v
each party calls withdraw()
```

Reject flow:

```
rejectDeal()
        |
        | seller gets nothing
        v
pendingWithdrawals[developer] += computeCost + fee
pendingWithdrawals[buyer]     += budgetCap - computeCost - fee
```

Expire flow:

```
expireDeal()
        |
        | if Created: no funds to return
        | if Funded/Evaluated: buyer refund minus any submitted compute cost
        v
state = Expired
```

Security intent:

```
seller cannot force disclosure outside TEE
buyer cannot exceed budget cap
TEE identity is the only result submitter
result details are represented by bounded scoreBand and resultHash
pull payments avoid recipient reverting during settlement
```

Current caveat:

```
submitResult() no longer trusts only a bare teeIdentity address in the current
contract source. The delegate has partial TEE-held signing plumbing: in dstack
mode it derives an Ethereum key from a dstack key path, preflights
`deals(dealId)` so the signer must match the public teeIdentity, checks funded
state and compute budget, commits the payload result hash to chain ID, contract
address, deal ID, signer nonce, compose hash, score band, compute cost, and
expiry, verifies signer quote evidence whose report data binds the signer
address to the chain ID and contract address, signs the transaction in memory,
and returns bounded receipt metadata. `DiligenceRoom.sol` requires a
result-verifier signature over the same bounded submission context plus
authorization expiry before accepting the call. The result-verifier module now
applies approved compose/app policy, optional OS image policy, revoked
quote/signer lists, distinct verifier/TEE keys, and short authorization TTLs
before signing that digest. The `authorize-result` CLI exposes this as a bounded
operator path, and a local Phala/dstack simulator proof deploys the contract
with the dstack-derived verifier address, gets authorization through that CLI,
broadcasts `submitResult()` to ephemeral Anvil, and verifies
`EvaluationSubmitted` carries the replay-bound commitment rather than the raw
payload hash. The remaining production gap is deployed service integration and
deeper quote verification: full Intel TDX quote parsing/freshness is still
incomplete, and the deployed Phala CVM-origin broadcast path still needs live
validation.
```

## Service Architecture

### cdp-playground

Purpose:

```
generic browser automation sandbox for Neko Chrome + Playwright/CDP
```

Why it exists:

```
the email oracle, Tinker delegate, and WhatsApp delegate all need a browser
inside or adjacent to the TEE; cdp-playground is the minimal reusable probe
for discovering selectors, frames, auth redirects, bot checks, and UI flows.
```

Flow:

```
operator / test agent
        |
        v
cdp-playground API
        |
        v
Neko Chrome over CDP
        |
        v
target website / screenshot / DOM extraction
```

### tee-email-oracle

Purpose:

```
hold an email account inside a TEE and provide bounded OTP extraction
```

Endpoints:

```
GET  /health
POST /pin        runtime bearer required when auth is enabled
GET  /inbox      runtime bearer required when auth is enabled
GET  /attestation?context=attestation|oracle-credentials|pin
POST /credentials/encrypted
     disabled by default; explicit provisioning bearer required
```

Flow:

```
startup
  |
  | load encrypted credentials or wait for genesis
  v
CredentialStore
  |
  | local AES key or dstack-derived key
  v
IMAPClient connects
  |
  v
/pin and /inbox require the same-CVM runtime bearer token
  |
  v
if configured, /pin and /inbox read EmailOracleAuth.isConsumerAuthorized
before mailbox access
  |
  v
/pin request must include target service, expected sender, subject scope,
caller identity, nonce, reason, max age, and bounded extraction regex
  |
  v
PinResponse with OTP, oracle email, sender, subject, request hash,
one-time OTP-use hash, timestamp, optional quote over hashes
  |
  v
Encrypted OTP replay ledger persists released OTP-use hashes across restarts
```

Encrypted mailbox provisioning:

```
operator client
  |
  | fetch /attestation?context=oracle-credentials
  | verify mode, compose hash, app id, OS image hash, report_data/key binding
  v
encrypt username/domain/password to attested X25519 key
  |
  | POST /credentials/encrypted with provisioning bearer
  v
oracle decrypts inside CVM -> sealed CredentialStore -> hash/status response
```

The provisioning endpoint is active only when
`ORACLE_ALLOW_CREDENTIAL_PROVISIONING_ENDPOINT=true` and
`ORACLE_CREDENTIAL_PROVISIONING_TOKEN` is set in the runtime environment. The
credential-ingress attestation context intentionally omits the raw oracle email,
and the response returns credential hashes, IMAP connectivity status,
`raw_secret_egress=false`, and an optional TDX quote hash.

### tinker-delegate

Purpose:

```
create and use a Tinker account from inside a TEE, then expose only scoped,
metered, bounded evaluation behavior
```

Endpoints:

```
GET  /health
GET  /attestation?context=ingress|artifact|billing
POST /auth/reauth opt-in bounded OTP re-auth; disabled by default
GET  /billing/balance
GET  /billing/funding-policy bounded funding-mode policy
GET  /billing/funding-preflight bounded operator funding readiness checks
GET  /billing/funding-receipts bounded funding attempt audit records
POST /billing/card            local-dev plaintext hook, disabled by default
POST /billing/card/encrypted  production encrypted card channel
POST /billing/add-balance
POST /deal/chain-event        bounded chain-event audit marker
POST /deal/notify-funded
POST /deal/{deal_id}/artifact/encrypted
POST /deal/{deal_id}/artifact local-dev plaintext hook, disabled by default
POST /deal/{deal_id}/evaluate
GET  /deal/{deal_id}/result
POST /deal/{deal_id}/resolve
GET  /deals
```

Control flow:

```
serve startup
  |
  | if TINKER_API_KEY exists, use it
  | else if encrypted API key exists, decrypt it
  | else if bootstrap enabled, run signup automation
  |   and persist captured key before returning bounded metadata
  | else run with control plane unavailable
  v
FastAPI app
```

Deal flow:

```
watch-chain CLI
  |
  | JSON-RPC eth_getLogs over DiligenceRoom lifecycle events
  v
ChainCursorStore persists next block + public DealCreated context
  |
  | only scan blocks older than configured confirmations
  v
/deal/chain-event records bounded audit metadata
  |
  | DealFunded with matching DealCreated context
  v
/deal/notify-funded
  |
  v
ControlPlane creates DealContext + IsolatedTinkerSession
  |
  v
/deal/{id}/artifact/encrypted decrypts, verifies artifactHash, then stores bytes in memory
  |
  v
/deal/{id}/evaluate runs evaluator_fn
  |
  v
raw metrics -> bound_output() -> compute_offer()
  |
  v
EvaluationResult returned through bounded response
```

### props-room

Purpose:

```
bridge source-controller approvals, NDAI deals, sealed raw acquisition jobs,
and downstream training/inference permissions
```

Flow:

```
controller registers private source
        |
        v
sponsor opens access deal
        |
        v
controller approves raw scrape scope
        |
        v
TEE job runs raw scrape / tv adapter
        |
        v
outputs sealed in asset store
        |
        v
future cleaning, training, and inference approvals
```

Current status:

```
[partial] FastAPI/control-plane/sealed-store stubs exist.
[planned] real wallet auth, attestation verification, Tinker integration, and
          props-room wiring into the partial tinker-delegate chain watcher.
```

### whatsapp-delegate

Purpose:

```
attested account delegation for WhatsApp Web, with sealed message export and
bounded pipeline queries
```

Flow:

```
owner starts login
        |
        v
Neko Chrome opens WhatsApp Web
        |
        v
owner links device from phone
        |
        v
delegate exports message history
        |
        v
messages sealed in TEE store
        |
        v
owner approves pipeline digest
        |
        v
pipeline query returns bounded output only
```

This service is not the core Tinker/NDAI path, but it demonstrates the same
pattern: browser-mediated account delegation, sealed private data, owner
approval, bounded output.

## TEE Deployment Model

The intended production substrate is Phala Cloud dstack CVMs:

```
Docker image digest
        |
        v
docker-compose file
        |
        v
compose hash
        |
        v
dstack CVM boot
        |
        v
TDX quote
        |
        v
verifier checks quote, app id, compose hash, and runtime measurements
```

Runtime service layout for the Tinker path:

```
+---------------------------------------------------------------+
| dstack CVM                                                    |
|                                                               |
|  service: neko / delegate-browser                             |
|    - headful browser / Playwright server / CDP                |
|    - core dumps disabled by compose ulimits                   |
|                                                               |
|  service: oracle                                              |
|    - tee-email-oracle                                         |
|    - IMAP credentials sealed at /data                         |
|    - dstack socket mounted                                    |
|    - core dumps disabled by compose ulimits                   |
|                                                               |
|  service: delegate                                            |
|    - tinker-delegate                                          |
|    - Tinker API key sealed at /data                           |
|    - funding receipts + bounded run metadata sealed at /data  |
|    - dstack socket mounted                                    |
|    - RLIMIT_CORE=0 plus compose core ulimit                   |
|                                                               |
|  volumes: oracle-data, delegate-data                          |
+---------------------------------------------------------------+
```

Deployment artifacts:

```
docker-compose.yaml              local delegate
docker-compose.dstack.yaml       dstack overlay
docker-compose.all.yaml          local all-in-one oracle + browser + delegate
docker-compose.all.dstack.yaml   all-in-one dstack overlay
docker-compose.all.phala.yaml    registry-image Phala deployment
scripts/redeploy-phala-cvm.mjs   update compose/env for existing Phala CVM
```

## Security Boundaries

### What Must Never Leave the TEE

```
raw seller artifact
raw corpus / source data
email password
Tinker session cookies
Tinker API key
payment card number / CVC
raw TTT/RL training data
model checkpoints / weights
unbounded samples
unredacted WhatsApp messages
```

### What May Leave

```
artifact hash
compose hash
TDX quote
score band
yes/no verdict
offer within budget cap
confidence band
methodology summary without raw data
compute cost and fee
result hash
withdrawal events
bounded aggregate results
```

### Current Gaps

```
1. On-chain TDX quote verification is not implemented.
2. EmailOracleAuth's on-chain consumer registry is not yet checked by the
   FastAPI OTP endpoint; same-CVM bearer auth and scoped runtime OTP requests
   are implemented.
3. Tinker browser automation works locally through Neko/CDP but still needs a
   fresh deployed Phala/CVM validation run.
4. Reliable Tinker account funding through Stripe browser automation is in progress:
   the test-card path reaches Stripe and declines as expected, the plaintext
   card API is disabled by default, `manual_prefund` is the default production
   funding mode, and real funding is not yet proven.
5. Real TTT/RL bio-validation is not implemented.
6. DLP/egress enforcement is not implemented.
7. Corpus policy and consent/revocation are modeled but not enforced.
8. Chain watcher wiring is locally implemented: JSON-RPC decoding, API dispatch,
   bounded chain-event audit metadata, CLI entrypoint, durable cursor storage,
   confirmation-safe polling, restart recovery, and local Anvil proof exist.
   Production deployment, chain-lag alerting, and deep-reorg rollback beyond
   confirmation depth remain open.
9. Per-query royalty settlement is not wired to a live chain watcher.
10. The production frontend is not present on this branch.
11. Current-operator Base Sepolia contracts are deployed, but source
    verification and compose-hash/consumer registration are still pending.
```

## Public / Web Client Layer

The current `tinker-deligate` branch does not contain a React/Vite/Cloudflare
Pages app. The architecture expects a web client with these responsibilities:

```
seller/data-owner UI
  - create room
  - upload or register artifact
  - set reserve price
  - inspect attestation / compose hash

buyer/sponsor UI
  - fund deal
  - set budget cap
  - submit access/evaluation request
  - accept/reject bounded result

reviewer UI
  - inspect held request
  - confirm release/deny via attested email channel

verification UI
  - display contract address
  - display docker digest / compose hash
  - display TDX quote
  - display result hash
```

The web client should not hold Tinker, OpenRouter, Phala, or card secrets.
Server-side functions or TEE services should own those secret-bearing calls.

## Example End-to-End Scenario

```
Actors:
  Seller: Bio data owner
  Buyer: Sponsor with model-validation budget
  TEE:    dstack CVM running email oracle + Tinker delegate
  Chain:  Base Sepolia DiligenceRoom

Flow:

1. TEE boots and exposes attestation.
2. Email oracle creates/loads sealed email credentials.
3. Tinker delegate signs into Tinker using email OTP from oracle.
4. Tinker API key is sealed inside the delegate.
5. Seller creates DiligenceRoom deal with artifactHash and teeIdentity.
6. Buyer funds deal with budget cap.
7. Control-plane lifecycle metadata is sealed as bounded event records.
8. Seller uploads private bio artifact to TEE.
9. Gate checks purpose and dual-use risk.
10. Tinker delegate starts an isolated evaluation session.
11. Target future evaluator runs TTT/RL bio-validation.
12. Control plane converts raw metric to score band.
13. TEE submits replay-bound resultHash commitment, scoreBand, and computeCost.
14. Buyer accepts or rejects.
15. Contract accrues seller payment, developer compute+fee, and buyer refund.
16. Parties withdraw.
17. TEE cleans up artifact and Tinker checkpoints.
```

ASCII sequence:

```
Seller          Buyer          Email TEE        Tinker TEE        Chain
  |              |                |                 |               |
  | create deal  |                |                 |-------------->|
  | artifactHash |                |                 |               |
  |              | fund budget    |                 |-------------->|
  |              |                |                 |               |
  | upload artifact ------------->|?                |               |
  | upload artifact ------------------------------->|               |
  |              |                |                 |               |
  |              |                | OTP request     |               |
  |              |                |<----------------|               |
  |              |                | OTP response    |               |
  |              |                |---------------->|               |
  |              |                |                 | Tinker login  |
  |              |                |                 | eval session  |
  |              |                |                 | bounded score |
  |              |                |                 |-------------->|
  |              | accept/reject  |                 |               |
  |              |----------------------------------------------->|
  | withdraw     | withdraw       |                 |               |
  |<--------------------------------------------------------------|
```

## How the Requested Chain Fits

The requested phrase:

```
Email encumbered contract <--> tinker encumbered contract <--> TTT RL Bio validation
                                                                       |
                                                                    DNAI
```

maps to the repo like this:

```
+-----------------------------+
| Email encumbered contract   |
|-----------------------------|
| EmailOracleAuth.sol         |
| tee-email-oracle            |
| OTP and human confirmation  |
+--------------+--------------+
               |
               | magic-code auth / reviewer confirmation
               v
+-----------------------------+
| Tinker encumbered contract  |
|-----------------------------|
| DiligenceRoom.sol           |
| tinker-delegate             |
| IsolatedTinkerSession       |
| billing/card channel        |
+--------------+--------------+
               |
               | scoped compute authority
               v
+-----------------------------+
| TTT/RL Bio validation       |
|-----------------------------|
| target evaluator            |
| current stub/SFT evaluator  |
| bounded bio-risk outputs    |
+--------------+--------------+
               |
               | bounded result, offer, result hash
               v
+-----------------------------+
| DNAI                        |
|-----------------------------|
| NDAI diligence room         |
| reserve + budget cap        |
| disclosure boundary         |
| settlement                  |
+-----------------------------+
```

The important design point is that these are not four unrelated modules. They
are four boundaries on the same transaction:

```
email boundary       proves/coordinates human or delegated identity
tinker boundary      controls paid compute and model access
bio-validation       performs the sensitive evaluation
DNAI boundary        decides what can be disclosed and how payment settles
```

Current project truth:

```
email boundary       real service + contract, but API enforcement is still incomplete
tinker boundary      service scaffold exists, auth/funding still blocked upstream
bio-validation       target TTT/RL loop is not built; current evaluator is stub/SFT-oriented
DNAI boundary        escrow/result-bounding primitives exist, full live path needs the above
```

## Build and Verification Surfaces

Focused validation currently available:

```
contracts:
  cd "⚙️/tinker-delegate/contracts"
  forge test

tinker-delegate Python:
  cd "⚙️/tinker-delegate"
  uv run python -m compileall tinker_delegate
  uv run python -c 'import tinker_delegate.api as api; print(api.app.title)'

tee-email-oracle Python:
  cd "⚙️/tee-email-oracle"
  uv run python -m compileall email_oracle
  uv run python -c 'import email_oracle.api as api; print(api.app.title)'

props-room Python:
  cd "⚙️/props-room"
  uv run python -m compileall props_room
```

External verification:

```
cast chain-id --rpc-url https://sepolia.base.org
cast code <contract-address> --rpc-url https://sepolia.base.org
phala status
wrangler whoami
```

## Roadmap to a Production-Complete Architecture

```
1. Enforce EmailOracleAuth on OTP consumers.
2. Add the production verifier service that validates live TDX quote evidence
   before issuing result-authorization signatures.
3. Prove deployed-CVM-originated verifier-authorized `submitResult()` broadcast
   and replace local-simulator evidence with live measured-code evidence.
4. Stabilize Tinker browser posture or use an official non-browser account API.
5. Implement the TTT/RL bio-validation evaluator and benchmark schema.
6. Add fail-closed DLP/egress enforcement.
7. Implement corpus policy, consent, revocation, and human-review queue.
8. Wire chain watcher to tinker-delegate control plane.
9. Build/merge the production web client and Cloudflare Pages deployment.
10. Add reproducible image builds and compose-hash release gates.
11. Add transparency log for accepted, rejected, held, denied, and expired runs.
```

## Architecture Invariants

These invariants should hold as the project grows:

```
No raw artifact leaves the TEE.
No Tinker API key leaves the TEE.
No card details are logged or persisted by repo services.
Error and automation logs are passed through service-local redaction helpers
before they become API responses or operator-visible diagnostics.
No result is accepted as "attested" without a quote and compose-hash story.
Every evaluator output is bounded before public release.
Buyer spend is capped by the contract budget cap.
Seller payment cannot be below reserve on accept.
Delegated authority cannot exceed the grantor's authority.
Human-review holds fail closed until released by a separate reviewer.
All settlement uses pull payments.
All deploy secrets live in environment, Phala encrypted env, or TEE-sealed storage.
```
