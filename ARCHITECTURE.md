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
TEE and clears the card payload from memory. The deployed auth/API-key browser
posture is now working, but low-value funding remains partial: the first live
operator-card validation left the account balance at `$0.00`; the payment-method
path likely reached card-on-file UI copy, while add-balance stopped at a missing
amount selector. Source now treats card-management copy as bounded
payment-method success and can choose scoped preset top-up amounts; that fix has
been deployed and approved, and `$10` preflight now passes. The latest real-card
packet still did not prove funding, but it did prove the deployed
encrypted-card/payment-method leg: the payment-method receipt succeeded at
`payment_submitted` with card payload destroyed and no raw secret egress.
Add-balance reached `add_balance_submitted` and then returned an unconfirmed
failure. Local source now narrows the billing-error classifier, requires
explicit add-balance success copy before returning success, and uses bounded DOM
signals such as remove-card controls for card-on-file status. That hardening has
now been built by GitHub Actions, verified with provenance and SBOM
attestations, and redeployed to the existing Phala CVM. The live TDX envelope
reports compose hash
`a3d0a1bc28983731db0fcc27be5680a312d3dc8a84c47e7e30596fe5dfb16fc9`; reauth
succeeds and bounded card status reports `card_on_file=true` /
`one_or_more`. The new compose hash is not yet approved on-chain, so a
successful bounded add-balance receipt is still required before funding is real.
The billing control plane also has a bounded card-on-file status path and
admin/operator card-removal path: callers can learn only whether a payment
method appears present and a zero/one-or-more/unknown count band, never card
brand, last4, expiry, billing address, or browser page text.

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
[real]      The main running Phala oracle has generated and sealed a mailbox in
            the CVM through a one-shot mailbox-genesis compose, then been
            redeployed back to the normal compose with `ORACLE_AUTO_GENESIS=false`.
            Public health/attestation expose `oracle_email=""`, readiness, and
            `oracle_email_hash`, while unauthenticated `/email` returns 401.
[partial]   Live Tinker OTP receipt in the CVM is still unproven; the mailbox is
            ready, but Tinker bootstrap remains disabled.
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
|  | browser session|----->| sealed browser state |           |
|  +-------+--------+                 |                       |
|          |                          v                       |
|          |              +----------+-----------+             |
|          |              | sealed API key store |             |
|          |              +----------+-----------+             |
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
[real]      A no-raw-key Base Sepolia deploy helper exists for
            TinkerAccountEncumbrance. It uses Foundry `--account dev`, validates
            the account commitment, initial compose hash, and caps, defaults the
            initial compose hash from the current Phala manifest, defaults the
            initial account commitment to the bounded `oracleEmailHash` only
            when no stronger Tinker account commitment is provided, runs
            build/tests and a simulation before broadcast, and updates
            `deployments/base-sepolia.json` only after successful on-chain
            reads.
[real]      TinkerAccountEncumbrance is deployed on Base Sepolia and recorded
            in the manifest as operator-controlled at
            `0x9f2616f3f7b0dc363bba19f7d72b9061f791a06e` with deployment tx
            `0x7679df09aa2e939d748be0e017f380f5e7e44331a482531380198e93bdcaed01`.
            On-chain reads confirm nonzero bytecode, owner
            `0xEd1Ade0bC26BD63A6e509Da3F5cDf6617369F4dD`, approved compose
            hash
            `0xb3fc9840dc7db51d2ba835f349564fbace5b64a0a122025c9c1c5923f88686f7`,
            emergency halt false, and measurements frozen false. A follow-up
            owner transaction
            `0x3ab263bb7cb7758787fa1136dd043cca002db9cf511b29ad20ef4d1216199d3f`
            raised both add-balance and spend caps to `$10`, with read-back
            returning `10000000000000000000` for both policy values. This makes
            the pre-card on-chain policy gate real for the current
            funding-validation compose hash.
[real]      Local Neko/CDP Tinker login, email OTP retrieval, onboarding, and API-key provisioning.
[real]      Signup/bootstrap stores captured Tinker API keys in encrypted
            storage and returns only bounded hash/status metadata.
[real]      Startup bootstrap runtime state preserves the bounded
            `api_key_provisioning` attempt record from signup success or
            selector/API-key-capture failure, plus early `tinker_auth`
            failures during account lookup, CDP/browser connection,
            context/page setup, auth, and onboarding. Public `/health` can
            therefore report `last_bootstrap_attempt_record` with outcome,
            furthest stage, hashes, and `raw_secret_egress=false` without
            exposing the mailbox, OTP, browser URL, page text, or API key.
[real]      Signup/signin observable egress is bounded before deployed bootstrap:
            stdout and return payloads expose `email_hash` / `url_hash` rather
            than raw mailbox addresses or Tinker browser URLs, and shared
            Tinker delegate redaction removes email addresses from rendered
            errors.
[real]      API-key provisioning uses a small selector fallback family for
            current Tinker key-creation copy plus aria-label/data-testid
            variants, returns bounded `api_key_provisioning` attempt records,
            including `selector_missing` when no key can be captured, and has
            replayable mock-page tests for successful extraction and selector
            drift failure paths.
[real]      `tinker-delegate selector-map` emits a bounded, machine-readable
            selector/frame/auth-flow contract for email auth, magic-code OTP,
            onboarding, API-key creation, billing payment method, Stripe iframe,
            balance top-up, and auto-reload surfaces. The map exposes declared
            selector families, counts, evidence labels, and a recomputable map
            hash only; it contains no account identifiers, OTPs, API keys, card
            details, cookies, raw page text, or browser session URLs. A summary
            mode omits concrete selectors for compact deployment evidence.
[real]      `tinker-delegate selector-probe` is the read-only live browser
            observation command for that contract. It connects to the configured
            Playwright/CDP browser, inspects current pages and frames without
            navigation, clicking, typing, screenshots, or page-text capture,
            and emits only URL classes, URL hashes, selector match bands, frame
            kinds, selector-map hash, bounded timestamps, and
            `raw_secret_egress=false`. Browser connection failures return
            bounded `browser_unavailable` JSON instead of tracebacks.
[real]      Source/tests also include a raw DevTools-protocol fallback for
            `selector-probe` when Playwright `connect_over_cdp` fails. The
            fallback uses the advertised WebSocket debugger URL in memory only,
            upgrades the raw WebSocket, runs `Target.getTargets`, attaches to
            up to five page targets, reads `Page.getFrameTree`, and emits only
            `probe_backend=raw_cdp`, stage booleans, HTTP status band,
            target/page/frame count bands, URL classes/hashes, frame kinds, and
            bounded error kinds, even when the fallback cannot complete target
            inventory. Source/tests preserve page-level inventory when
            per-page attach or frame-tree commands fail by emitting only
            `attach_error_kind`, `frame_tree_error_kind`, `partial_error_kind`,
            and empty frame observations for the affected page. It performs no
            navigation, clicking, typing, screenshots, page-text capture,
            cookie reads, DOM text extraction, or raw URL egress. It does not
            require successful frame traversal before preserving page identity.
            In source/tests, the raw-CDP fallback now also sends one bounded
            `Runtime.evaluate` command after page attach to count declared
            selector families as `0`, `1`, `2+`, or `probe_error` bands. Python
            maps the returned matrix onto known flow/family names, so public
            output cannot include page text, raw DOM, raw selectors, cookies,
            account identifiers, OTPs, API keys, card data, or arbitrary
            page-controlled strings. Source/tests now precede that selector
            matrix with a constant page-scoped Runtime micro-probe and emit
            only `runtime_micro_probe_command_success`,
            `runtime_micro_probe_success`, and
            `runtime_micro_probe_error_kind`; this bounded diagnostic
            distinguishes Runtime transport failure from selector-expression
            timeout without exposing page-controlled values. A Phala one-shot
            measurement with
            GitHub-attested `50de0a9` images proved the selector command path
            is built into the deployed image and preserves bounded output, but
            the page-scoped Runtime selector command still timed out. A
            follow-up one-shot measurement with GitHub-attested `5943c61`
            images proved that even the constant page-scoped Runtime
            micro-probe times out after page attach:
            `partial_error_kind=runtime_micro_probe_timeout`,
            `runtime_micro_probe_command_success=false`,
            `runtime_micro_probe_error_kind=timeout`,
            `runtime_selector_command_success=false`, and
            `flow_observations=[]`. This narrows the blocker to page-scoped
            Runtime command delivery/evaluation in the deployed Neko/CDP path,
            not selector-expression complexity. Selector-family bands are
            therefore source/test-real but still not Phala-proven; the next
            source/test-real diagnostic now sends `Runtime.enable` before the
            constant micro-probe and emits only bounded runtime/session fields:
            `runtime_enable_command_success`,
            `runtime_execution_context_event_observed`,
            `runtime_enable_success`, `runtime_enable_error_kind`,
            `runtime_event_before_enable_response`,
            `runtime_event_count_band`, and
            `runtime_execution_context_created`. It does not emit event
            payloads, context IDs, frame IDs, raw URLs, page text, selectors,
            cookies, OTPs, API keys, or card material. It still needs a
            GitHub-attested image build and Phala measurement before it can be
            treated as deployed evidence. A follow-up one-shot Phala
            measurement with GitHub-attested `9d69364` images proved
            `Runtime.enable` itself times out on the attached page session:
            `partial_error_kind=runtime_enable_timeout`,
            `runtime_enable_command_success=false`,
            `runtime_execution_context_event_observed=false`,
            `runtime_enable_error_kind=timeout`,
            `runtime_event_count_band=0`,
            `runtime_execution_context_created=false`,
            `runtime_micro_probe_command_success=false`,
            `runtime_selector_command_success=false`, and
            `flow_observations=[]`. Selector-family bands are still not
            Phala-proven; next work is to repair or route around the deployed
            Neko/CDP attached-session Runtime domain timeout. Source/tests now
            add that route-around candidate: if attached-session
            `Runtime.enable` fails, the raw-CDP fallback fetches bounded
            page-target inventory from `/json/list`, connects directly to the
            matching page target WebSocket, and retries `Runtime.enable`, the
            constant micro-probe, and the selector-family matrix. The nested
            `direct_page_runtime` receipt emits only page-list success,
            page-WebSocket availability, Runtime enable/error/event-count
            bands, micro-probe success/error, selector success/error, and
            declared selector-family count bands. It emits no raw page URLs,
            WebSocket URLs, event payloads, context IDs, frame IDs, page text,
            raw selectors, cookies, OTPs, API keys, or card material. A
            follow-up Phala measurement with GitHub-attested `bf39f56` images
            proved the direct route can fetch `/json/list` and reach the page
            target WebSocket, but direct page `Runtime.enable` still timed out:
            `direct_page_runtime_attempted=true`,
            `direct_page_runtime.page_list_success=true`,
            `direct_page_runtime.page_websocket_available=true`,
            `direct_page_runtime_enable_success=false`,
            `direct_page_runtime.runtime_enable_error_kind=timeout`, no
            micro-probe, no selector-family matrix, empty `flow_observations`,
            and `raw_secret_egress=false`. The current deployed blocker is the
            page Runtime domain itself, not just the attached-session routing.
            Source/tests now add one more bounded discriminator before that
            Runtime step: both the attached-session path and direct page-target
            path send `Page.enable` before `Runtime.enable` and emit only
            `page_enable_command_success`,
            `page_enable_success`, and `page_enable_error_kind`. These fields
            reveal whether page-domain CDP commands succeed before the Runtime
            domain hangs, without emitting page text, raw URLs, selectors,
            cookies, OTPs, API keys, card material, event payloads, frame IDs,
            or execution-context IDs. The 2026-07-08 Phala measurement on
            GitHub-attested `556387a` images returned
            `partial_error_kind=page_enable_timeout`,
            `page_enable_command_success=false`, and direct page-target
            `page_enable_success=false` / `page_enable_error_kind=timeout`
            after proving `/json/list` and page-WebSocket availability. The
            deployed blocker is therefore lower than Runtime-specific command
            handling: page-target CDP command delivery through the Phala Neko
            path does not complete even for `Page.enable`.
[real]      `GET /browser/selector-probe` wraps the same probe for deployed
            one-shot evidence capture. It is disabled by default and returns
            403 unless `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=true`; when enabled
            it still performs no navigation, clicking, typing, screenshots, or
            page-text capture, and browser failures are reduced to bounded
            `browser_unavailable` JSON. The normal Phala compose keeps this
            endpoint disabled; enabling it is a temporary measurement profile,
            not a widened production interface.
[real]      `tinker-delegate browser-readiness` and `GET /browser/readiness`
            provide bounded browser-control diagnostics for the deployed
            selector-probe failure path. They report endpoint classes/hashes,
            CDP metadata reachability, raw WebSocket upgrade stage bands,
            one-command CDP protocol probe bands, Playwright/CDP handshake
            success bands, and bounded error kinds only. They do not navigate,
            click, type, screenshot, inspect pages/frames, return page text, or
            expose raw CDP/browser URLs. The raw WebSocket diagnostic keeps the
            advertised debugger URL in memory only and emits URL class/hash,
            TCP/TLS/upgrade stage booleans, HTTP status band, and bounded error
            kind. The post-upgrade protocol probe is source/test-real: it sends
            exactly one browser-scoped `Browser.getVersion` command after a
            successful Upgrade and emits only command/response booleans,
            response kind, browser family, URL class/hash, status band, and
            bounded error kind; it does not emit the CDP response body. The HTTP
            endpoint is disabled by default and normal Phala compose binds
            `TINKER_ALLOW_BROWSER_READINESS_ENDPOINT=false`; the one-shot
            measurement profile enables it temporarily. The pre-WebSocket-stage
            version is Phala-proven: the one-shot endpoint returned bounded
            `cdp_timeout` after CDP metadata succeeded, and the restored normal
            compose returns 403. The raw WebSocket stage is Phala-proven with
            GitHub-attested `7973b27` images: CDP metadata succeeded, the raw
            WebSocket TCP connect and HTTP Upgrade succeeded with status band
            `101`, and Playwright `connect_over_cdp` still timed out. The
            post-upgrade protocol probe is Phala-proven with GitHub-attested
            `59a9eac` images: after HTTP `101`, one browser-scoped
            `Browser.getVersion` command returned a bounded `result` response
            and Chromium browser-family band, while Playwright
            `connect_over_cdp` still timed out. This narrows the remaining
            deployed browser-control blocker to the Playwright CDP client path.
[partial]   The selector-probe endpoint has been Phala-proven as an endpoint
            gate and fail-closed path using GitHub-attested `7973b27` images:
            one-shot bootstrap compose enabled the endpoint, live response was
            bounded `browser_unavailable` with `raw_secret_egress=false`, and
            the restored normal compose returns 403. The paired readiness
            endpoint showed CDP metadata reachable with Chromium WebSocket
            metadata advertised, raw WebSocket upgrade status `101`, a
            successful bounded one-command CDP protocol response, then
            `connect_over_cdp` timeout. The raw-CDP fallback is Phala-proven
            through target inventory with GitHub-attested `f63dd18` images:
            metadata succeeded, WebSocket Upgrade returned status band `101`,
            `Target.getTargets` succeeded, and the bounded receipt reported
            target count `2+` and page count `1` with no raw URL/page text
            egress. The timeout-preserving page observation path is also
            Phala-proven with GitHub-attested `a384db2` images: the one-shot
            selector probe returned `probe_backend=raw_cdp`, `success=true`,
            target count `2+`, page count `1`, `pages_observed=1`, a bounded
            page URL class/hash, `attached=true`,
            `frame_tree_error_kind=timeout`,
            `partial_error_kind=frame_tree_timeout`, empty frame observations,
            and `raw_secret_egress=false`. The CVM was restored to normal
            compose afterward, and both diagnostic endpoints returned 403.
            `Page.getFrameTree` still times out, so actual frame inventory
            remains open. Source/tests now add bounded raw-CDP Runtime selector
            counting that should capture deployed selector-family bands even
            when frame traversal times out, but the 2026-07-08 Phala
            measurement on `50de0a9` images returned
            `runtime_selector_error_kind=timeout` and empty
            `flow_observations`. The follow-up 2026-07-08 Phala measurement on
            GitHub-attested `5943c61` images added a preceding constant Runtime
            micro-probe and returned
            `partial_error_kind=runtime_micro_probe_timeout`,
            `runtime_micro_probe_command_success=false`,
            `runtime_micro_probe_error_kind=timeout`,
            `runtime_selector_command_success=false`, and empty
            `flow_observations`. The deployed timeout is therefore below the
            selector expression itself. Source/tests now add a bounded
            Runtime/session diagnostic by running `Runtime.enable` before the
            constant micro-probe and recording only success/error/event-count
            bands. The 2026-07-08 Phala measurement on GitHub-attested
            `9d69364` images returned `runtime_enable_timeout`, no Runtime
            execution-context event, no micro-probe, and no selector
            evaluation. The deployed blocker is therefore the attached-session
            Runtime domain itself. Source/tests now add a direct page-target
            WebSocket Runtime route that can recover selector-family bands
            after an attached-session `Runtime.enable` timeout in tests. The
            2026-07-08 Phala measurement on GitHub-attested `bf39f56` images
            proved `/json/list` and page-WebSocket availability, but direct
            page `Runtime.enable` also timed out, so deployed selector-family
            evidence remains blocked on Neko/Chrome Runtime-domain behavior.
            A follow-up Phala measurement on GitHub-attested `556387a` images
            shows `Page.enable` also times out on the deployed page target, so
            selector-family evidence remains blocked on lower-level Neko/Chrome
            CDP command delivery rather than selector expressions.
            A 2026-07-09 one-shot measurement using the tracked
            `docker-compose.selector-diagnostics.phala.yaml` profile and
            GitHub-attested `eb3bde3` images revalidated the same failure mode
            against the current funding-validation image set: browser-level CDP
            metadata, WebSocket upgrade, and `Browser.getVersion` succeed;
            raw-CDP target/page inventory and page attach succeed; both the
            attached-session and direct page-target paths time out at
            `Page.enable` before Runtime or selector-family counting can run.
            The CVM was restored to the funding-validation profile afterward
            and both diagnostic endpoints return 403 disabled.
[real]      Tinker re-auth exists as a bounded OTP refresh path through
            `reauth` and opt-in `POST /auth/reauth`; it returns only
            `tinker_auth` attempt records and does not expose account email,
            OTP, browser URL, API key, or page text.
[real]      Source/tests now persist successful signup/signin/reauth
            Playwright `storage_state` to an encrypted browser-session store
            under the delegate data volume, using a separate
            `tinker/browser_session` dstack key path from API keys and funding
            receipts. Billing creates fresh browser contexts from that sealed
            state when no reusable context exists, so `/auth/reauth` can
            prepare the later encrypted-card/add-balance request without
            exposing cookies, localStorage, raw URLs, OTPs, page text, or card
            data. Compose hardening tests keep the store under `/data`. The
            slice is now Phala-deployed in the funding-validation profile, but
            no useful live session has been saved yet because deployed
            `/auth/reauth` still fails before OTP with bounded
            `auth_access_blocked`.
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
[real]      Add-balance automation enforces whole-dollar
            `TINKER_MIN_ADD_BALANCE_USD` / `TINKER_MAX_ADD_BALANCE_USD`
            bounds before launching browser automation. Non-finite,
            non-positive, below-minimum, fractional, and over-cap requests
            return bounded `policy_denied` `add_balance` receipts at
            `not_started` with amount bands, not page text.
[real]      Card-on-file status is exposed only through bounded
            `GET /billing/payment-method-status`: `card_on_file` and
            `payment_method_count_band`. The admin/operator removal surface is
            `POST /billing/card/remove`, emits a bounded removal receipt, and
            does not expose card brand, last4, expiry, billing address, or raw
            page text.
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
[real]      Prompt-based real-card operator paths can also require the deployed
            TinkerAccountEncumbrance policy before any card field prompt.
            `add-card-encrypted-prompt` and
            `funding-validation-packet --prompt-card --run-card-attempt` accept
            `--require-encumbrance` plus contract/RPC/compose inputs; they run
            read-only contract checks for add-payment-method and, when a top-up
            amount is part of the same packet, add-balance cap approval. Denied
            or unavailable policy exits before card material is entered.
[real]      `funding-command-plan` turns the deployment manifest into a bounded
            operator command plan. It reads only public deployment evidence
            (`delegate` endpoint, compose hash, app ID, OS image hash, and
            TinkerAccountEncumbrance policy) and emits argv/shell templates for
            funding preflight, encumbrance preflight, and the eventual
            prompt-card funding-validation packet. It references
            `TINKER_RUNTIME_AUTH_TOKEN`
            and `BASE_SEPOLIA_RPC_URL` by environment-variable name only and
            never prints bearer tokens, card fields, API keys, OTPs, RPC
            values, cookies, or browser/session material. The deploy helper
            used Foundry `--account` through the encrypted keystore; no raw
            private-key path was emitted. The current manifest-derived plan is
            `ready=true` for the bounded policy/encumbrance checks, with a
            remaining warning that the CVM still reports dev OS.
[real]      `tinker-encumbrance-preflight` reads only public
            `TinkerAccountEncumbrance` state and exits before card prompting
            when the compose hash is not approved, emergency halt is set, or the
            requested amount exceeds the cap. Its bounded JSON renderer marks
            public chain fields (`contract_address`, `compose_hash`,
            `amount_wei`, `max_amount_wei`) as public before generic
            secret-shape checks, so public wei/address values do not create
            false positives while card/API-key/OTP-shaped material still fails
            closed.
[real]      Operator-only mutation endpoints now have delegate runtime bearer
            auth. When `TINKER_RUNTIME_AUTH_REQUIRED=true`,
            `/auth/reauth`, `/billing/card/encrypted`,
            `/billing/add-balance`, `/billing/funding-receipts`, and the
            explicitly local plaintext card endpoint require
            `Authorization: Bearer ...`; missing tokens fail 401, wrong tokens
            fail 403, and misconfigured required auth fails closed. The token
            can be supplied explicitly through `TINKER_RUNTIME_AUTH_TOKEN` for
            operator CLI runs, or derived inside dstack from
            `TINKER_RUNTIME_AUTH_KEY_PATH` for same-TEE callers.
[real]      Funding validation packets can also include separate add-balance
            evidence: an add-balance receipt, manifest, verification, and
            summary fields. The runner can bind an existing bounded top-up
            receipt, or POST only the amount to `/billing/add-balance` when
            `--run-add-balance-attempt` is explicitly set and `--amount` is
            provided.
[real]      `docker-compose.tinker-funding-validation.phala.yaml` is a
            temporary one-shot Phala profile for capped operator validation.
            It uses registry digest images only, disables signup/bootstrap and
            plaintext card submission, enables reauth/encrypted-card/add-balance
            only behind runtime bearer auth, sets
            `TINKER_FUNDING_MODE=operator_capped_validation`, source defaults
            cap top-ups at the current Tinker minimum `$10`, and routes browser
            work through the custom GitHub-attested `neko-chrome` CDP path with
            the baked proxy on `9222`. The live deployed encumbrance has been
            updated to `$10` add-balance/spend caps, but each refreshed Phala
            compose hash must still be explicitly approved on-chain before
            add-balance can proceed.
[real]      `docker-compose.selector-diagnostics.phala.yaml` is a temporary
            Phala diagnostics profile for the main CVM. It uses registry image
            digests only, disables Tinker bootstrap and all card/funding
            mutations, keeps runtime bearer auth enabled, and enables only the
            read-only bounded browser readiness and selector-probe routes. It
            is not a production or funding posture; it exists to collect
            bounded browser-control evidence and must be reverted immediately
            after each measurement.
[real]      The funding-validation profile was refreshed on Phala on
            2026-07-09 with GitHub-attested source
            `6ff5531aabb952b3266210afa6c0b6bfb8860103` images:
            `tee-email-oracle@sha256:f5c346912f3391e699252dba47c673902d06ffe528a8bab9732a76d551ec42ab`,
            `tinker-delegate@sha256:f9eb714c5630549441636b8a5525b20c9518e863940a3b8e072dff5a5dcab37d`,
            and
            `neko-chrome@sha256:525e43d585828d1d9aa1bceaf7c8cfffc2eec47abf67e0b10550bf05338c4a07`.
            Local image-attestation checks passed for all three images, the
            local image-policy hash is
            `a0045b4a0995f858dde0d473a16b997459a6bd009f78c55b0d5ee471ba58f81f`,
            the rendered compose SHA-256 is
            `e8938c5c3896376df2219ddcee78dd26c82963c6fc57ab98431ce6b39122302f`,
            and the live attested compose hash is
            `f4728f219572c09c6ccc013883a4a895f3e366ea6e9654459fd6b0002fe33552`.
            Health is OK, the email oracle is ready, IMAP is connected, the
            Tinker API key is available from encrypted storage, public logs
            remain disabled, and unauthenticated reauth/add-balance calls fail
            closed with `401 Bearer token required`.
[partial]   The funding-validation profile is live, quote-bound, backed by a
            deployed TinkerAccountEncumbrance policy, and has working
            authenticated `/auth/reauth`. It was refreshed again on 2026-07-09
            from source `8a571347d946fd6c23a84db256fd99f7169061e5` with
            GitHub-attested digest images:
            `tee-email-oracle@sha256:beedfc6c3f1f0c9dca8604d6adf6522110e8dc2f15af1e8a9145e0e3227939a9`,
            `tinker-delegate@sha256:3e03e4dccde8ef732641fdd091597a683674ca3b065b950a983aab16c6b88878`,
            and
            `neko-chrome@sha256:fd6a65a894befc66901ed7b915c792f3a669b74ef4ace01813815e1f1030b456`.
            The existing CVM now attests live compose hash
            `9f0754be7b7bcd3db9c808e5630f7f0aca39a33bbe37f898b8714de6d9aa4d71`;
            the local image-policy hash is
            `880db4987c00ecd8643aedc794415accd83c47a337b4512810d9fe5cadab8e6a`,
            and the rendered compose SHA-256 is
            `962e0352a468460eaa6085a2a32a6b7005798c7e3e5f3ff71e9799fa0cf67ea7`.
            Live `/billing/funding-policy` reports `$10` minimum and `$10` cap,
            `/auth/reauth` succeeds, and bounded payment-method status reports
            `card_on_file=false` / count band `zero`. The owner approved the
            new live compose hash in `TinkerAccountEncumbrance` on Base Sepolia
            in tx
            `0xb7e6d0fc504146d88005339bd859142a5f2d6c3f99315d81cb00742ebc15d48e`
            at block `43905420`; read-only `$10` preflight now returns ready.
            Packet `/tmp/dnai-tinker-funding-validation-packet-20260709T065233Z`
            still timed out before payment-method or add-balance receipts were
            written, and a later bounded card-status probe still reported
            `card_on_file=false`. Local client fix `5ab9e81` adds masked prompt
            echo/backspace support and increases encrypted-card upload timeout
            to 180 seconds; no CVM redeploy is required for that client-only
            change. Packet
            `/tmp/dnai-tinker-funding-validation-packet-20260709T071145Z`
            completed wrapper/manifest generation but did not prove funding:
            payment-method fallback was blocked by an open modal scrim before
            it reached the card form, and add-balance was not confirmed. Local
            source now dismisses open billing dialogs before tab fallback,
            constrains browser-exception receipt messages to bounded outcome
            strings, and fixes prompt newlines; those browser-side source
            changes were built by GitHub Actions run `29001302688` from source
            `658f6020db9972e0f7e1e914f72422ff5d08535f` into verified delegate
            digest
            `35bcc693300644445af40e7d4eb5d488848a2006ed2d42b7f56638c60963c92c`
            and redeployed to the existing CVM. The live TDX envelope now
            reports compose hash
            `7edf41c2b7bec5531639df94b90e2d2b5d1ac181f07db17f012c085d8cdb6476`;
            reauth succeeds, and the operator approved that compose hash
            on-chain. The next deployed packet produced a real `payment_method`
            success at `payment_submitted`, proving the encrypted-card/payment
            method leg. Add-balance remains partial: the
            receipt reached `add_balance_submitted` but was unconfirmed and
            exposed an overly broad billing-error classifier for `Payment
            methods` navigation text. Source now tightens that classifier and
            requires explicit add-balance success copy before returning success.
            That fix was built from source
            `2ab388103817bfbfaa7e20579a79213ed87fd85a`, verified against
            GitHub provenance and SPDX SBOM attestations for delegate digest
            `06c8d0fadd98922f0c6f5bded92b414be2bf423fc3c3e6af1b8e9e36b8c6975f`,
            and redeployed. A later startup-deferred oracle refresh moved live
            TDX attestation to compose hash
            `1fc656544b1583b83d65d769f369f3d1ad6d07d7e812073fbd3c1f7f2f84eb28`;
            oracle health now serves degraded-but-bounded readiness without
            blocking on IMAP startup, and the owner approved that compose hash
            in `TinkerAccountEncumbrance` tx
            `0x9caf683b80b3c06a8b5de0f8ebeffcfd44d5a6f0305c285df9f32fdb687e402e`.
            On-chain add-balance preflight now returns `allowed=true` for
            `$10`. The profile is still not production-final because the CVM
            reports dev OS, quote internals are not parsed, and a successful
            live real-card add-balance receipt has not yet been produced.
[real]      Source/tests now distinguish billing selector drift from auth-state
            failure before card fields or top-up controls are touched. The
            payment-method and add-balance flows classify a billing navigation
            that lands on sign-in or magic-code surfaces as bounded
            `auth_required`, and a page containing Tinker's access-blocked
            surface as bounded `auth_access_blocked`, both at
            `billing_page_loaded` without echoing page text. This extends the
            bounded receipt vocabulary with `auth_required`.
[real]      Source/tests and the live Phala funding-validation profile now
            preserve bounded auth-flow stage evidence for Tinker auth blocks.
            `AuthAccessBlockedError`, signup, and `/auth/reauth` carry
            `auth_page_loaded`, `auth_email_submitted`, or
            `auth_otp_page_reached` as the receipt `furthest_stage` rather than
            collapsing every auth block to `not_started`. The 2026-07-08 live
            repro returned `auth_access_blocked` at `auth_email_submitted` with
            `raw_secret_egress=false`. The stage values are enum labels only;
            page text, raw URLs, OTPs, cookies, API keys, and account
            identifiers remain outside the public receipt.
[real]      The billing auth-state classifier was rebuilt by GitHub Actions,
            verified with provenance/SBOM attestations, pinned by digest,
            redeployed to the funding-validation Phala profile, and live-tested
            against encrypted Stripe test-card and `$5` add-balance probes.
            The deployed result proves the blocker is Tinker auth/session
            continuity rather than true billing selector drift.
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
[real]      Email-oracle genesis, browser signup, IMAP search, and check-command
            logs use stable SHA-256 hashes for generated mailbox identifiers,
            sender filters, and mail subject/sender headers instead of printing
            the raw values. This supports temporary Phala public-log debugging
            after a log-hardened image is built/deployed, but does not change
            `/pin` response contracts.
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
[real]      Current Phala deploy-critical image references are literal
            digest-pinned `image:` entries in `docker-compose.all.phala.yaml`,
            not encrypted-env substitutions. The current deployment also binds
            `ORACLE_AUTO_GENESIS=false`, `TINKER_BOOTSTRAP_SIGNUP=false`,
            `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=false`, and
            `TINKER_ALLOW_SELECTOR_PROBE_ENDPOINT=false`, and
            `ORACLE_ALLOW_CREDENTIAL_PROVISIONING_ENDPOINT=false` directly in
            that compose file. This avoids treating encrypted env values as
            quote-bound trust roots; a 2026-07-08 intermediate redeploy showed
            changing only image env values did not by itself change the live
            attested compose hash.
[real]      `scripts/redeploy-phala-cvm.mjs` now defaults to a least-privilege
            runtime-env policy for existing CVM updates. `compose-refs` selects
            only encrypted env keys referenced by the compose source plus any
            operator-approved explicit keys; the legacy broad `.env` behavior
            requires `--runtime-env-policy all`. CLI output is bounded to
            policy, selected-key count, and a SHA-256 of the key set unless
            `--print-runtime-env-keys` is explicitly requested. The current
            normal Phala profile was redeployed with this policy and reports
            `allowed_env_count=7` instead of the earlier broad 90-key surface.
[real]      `.github/workflows/build-tee-images.yml` builds the deploy-critical
            `tee-email-oracle`, `tinker-delegate`, and custom `neko-chrome`
            browser images on GitHub-hosted runners for `linux/amd64`, pushes
            SHA-tagged images to GHCR, asks BuildKit to attach SBOM/provenance
            attestations, generates an SPDX SBOM with Syft, and emits
            GitHub-native signed provenance and SBOM attestations bound to the
            pushed image digest. The delegate/oracle Dockerfiles pin the
            Python runtime image and `uv` helper image by versioned digest; the
            custom Neko browser Dockerfile pins the upstream Neko base by
            linux/amd64 manifest digest.
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
[partial]   Current Phala deployment runs the combined oracle/delegate/browser stack in
            CVM `670b3b21-4338-4d4e-ae72-7c8922579f59` / `cvm_1w85mGjo`
            with app ID `f6a3219ce4b3c13e1c8bbbb56ce2217f9ebd7717`,
            digest-pinned GHCR images verified by GitHub attestations,
            delegate `/health` returning `ok`, and live delegate
            deployment-bundle verification passing against local raw compose
            image-policy hash
            `a0045b4a0995f858dde0d473a16b997459a6bd009f78c55b0d5ee471ba58f81f`,
            rendered compose SHA-256
            `e8938c5c3896376df2219ddcee78dd26c82963c6fc57ab98431ce6b39122302f`,
            and live Phala attested compose hash
            `f4728f219572c09c6ccc013883a4a895f3e366ea6e9654459fd6b0002fe33552`.
            The current oracle image is
            `tee-email-oracle@sha256:f5c346912f3391e699252dba47c673902d06ffe528a8bab9732a76d551ec42ab`,
            the current delegate image is
            `tinker-delegate@sha256:f9eb714c5630549441636b8a5525b20c9518e863940a3b8e072dff5a5dcab37d`,
            and the current browser image is
            `neko-chrome@sha256:525e43d585828d1d9aa1bceaf7c8cfffc2eec47abf67e0b10550bf05338c4a07`,
            all built from source commit
            `6ff5531aabb952b3266210afa6c0b6bfb8860103`. Tinker bootstrap,
            selector-probe, browser-readiness, and plaintext card submission
            are disabled in the current funding-validation profile; add-balance
            and reauth are enabled only behind runtime bearer auth for capped
            operator validation.
[partial]   2026-07-09 debug exception: the current main CVM was temporarily
            redeployed with public logs, public sysinfo, dev OS, and SSH key
            injection to diagnose a deployed Python-service gateway timeout.
            This is not production posture and must be reverted before claiming
            a locked-down deployment. The debug redeploy reports live compose
            hash
            `a479a1ca1595e7b717e8c8e28ea60dfcef5430bb7792800180453a6b3790aa89`.
            Container logs show the delegate returning internal `/health` and
            `/attestation?context=billing` `200 OK` responses, while local
            clients still receive zero bytes from the public Phala gateway for
            delegate/oracle ports. Neko and Chrome/CDP public ports respond, so
            the active blocker is the Phala gateway/Python service delivery path
            plus oracle IMAP TLS EOFs, not a broadened trust claim.
[real]      Source now prevents slow synchronous readiness checks from blocking
            the delegate API event loop. `/health`, `/attestation`,
            `/billing/funding-policy`, `/billing/funding-preflight`, and
            `/billing/funding-receipts` are synchronous FastAPI handlers, so
            blocking key-store, oracle-health, local attestation, and preflight
            work is dispatched to FastAPI's worker threadpool instead of
            monopolizing Uvicorn's event loop. A regression test starts the
            real ASGI server, makes oracle health sleep, and proves billing
            attestation still returns promptly.
[real]      Source/tests now make oracle `/health` a non-mutating readiness
            view. It reports cached mailbox connection state and credential
            hashes only; it no longer calls IMAP reconnect logic from a Docker
            or delegate health probe. `/pin` remains the operation that touches
            IMAP, fails closed with a bounded `503 IMAP unavailable` response,
            and updates cached connection state. This prevents healthcheck
            reconnect storms. Source/tests also defer IMAP connection during
            FastAPI startup so a flaky mailbox provider cannot prevent
            `/health` or `/attestation` from serving. The startup-deferred
            oracle image is GitHub-built, pinned, and redeployed in the
            funding-validation Phala compose. Live health now serves in
            degraded mode without IMAP connection, while `/pin` remains the
            fail-closed path that must prove mailbox access before OTP use.
[real]      Main-CVM mailbox genesis has been Phala-proven without enabling
            Tinker bootstrap or billing. A one-shot
            `docker-compose.mailbox-genesis.phala.yaml` deployment reached
            `oracle_ready=true`, `imap_connected=true`, `oracle_email=""`, and
            a non-empty `oracle_email_hash`; unauthenticated `/email` returned
            401. The CVM was then redeployed back to the normal compose with
            `ORACLE_AUTO_GENESIS=false`, and the sealed mailbox remained ready.
[real]      `docker-compose.tinker-bootstrap.phala.yaml` is the explicit
            one-shot profile for deployed Tinker bootstrap attempts. It reuses
            the main `delegate-data` volume, keeps `ORACLE_AUTO_GENESIS=false`,
            keeps credential provisioning and add-balance disabled, enables
            only `TINKER_BOOTSTRAP_SIGNUP=true`, uses fail-open bounded
            evidence mode so selector/posture failures can be inspected through
            `/health` runtime state, and now drives the headed Neko Chrome CDP
            endpoint instead of the headless Playwright sidecar. The Tinker
            bootstrap and selector-diagnostics Phala composes now use the
            GitHub-attested custom `neko-chrome` digest and the baked Nginx CDP
            proxy on port `9222`; they no longer rewrite Chrome/CDP with an
            inline Python TCP proxy at container startup. A Phala bootstrap run
            with the custom browser image succeeded: `/health` reported
            `bootstrap_success=true`, `api_key_configured=true`, and a bounded
            `api_key_captured_and_stored` attempt record with
            `raw_secret_egress=false`.
[real]      Earlier Phala-proven Tinker bootstrap attempts remain useful
            history because they isolated the failure to the old deployed
            browser transport. The first, using the headless Playwright sidecar,
            reached the Tinker auth surface with
            `bootstrap_error_kind=auth_access_blocked`. Later headed-Neko runs
            preserved bounded failure records without exposing raw mailbox,
            OTP, page text, cookies, URLs, or API keys. The custom
            `neko-chrome` run fixed the deployed `Page.enable` timeout and
            sealed the API key in the delegate data volume. Stealth/evasion
            remains out of scope; the accepted browser route is bounded TEE
            custody for this project's own account.
[partial]   Production OS posture is not solved. The main CVM still reports
            `dstack-dev-0.5.9` / `is_dev=true`; earlier attempts to update the
            existing CVM to `dstack-0.5.10*` with `--no-dev-os` failed in the
            Phala CLI/API with a required `correlationId` validation error, and
            a later successful compose/image update with `--no-dev-os` still
            left the live CVM reporting the dev OS.
[real]      The email-oracle source now tracks cock.li's current registration
            form contract: `password_confinm` is filled as the real password
            confirmation field, `password_confirm` is treated as a honeypot and
            left empty, and `csrf_valid` mirrors `csrf` on HTTP submissions.
[real]      A temporary Phala auto-genesis debug CVM using a GitHub-attested
            image from that form-contract fix reached IMAP verification and
            loaded sealed oracle credentials. The temporary public-log/dev-OS
            CVM was deleted after bounded evidence collection.
[real]      Public successful-genesis surfaces are now bounded in source and
            Phala-proven for the standalone oracle-genesis debug compose:
            `/health` and `/attestation` expose `oracle_email=""`, readiness,
            and `oracle_email_hash`; raw address retrieval is isolated to
            runtime-authenticated `/email`, which returned 401 without a bearer
            token in the fresh Phala proof. The temporary public-log/SSH/dev-OS
            debug CVM was deleted after evidence collection.
[partial]   Oracle credential-ingress attestation is live for
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
[partial]   Deployed Phala/CVM browser posture has not been revalidated with
            selector-map capture evidence from the running headed browser path.
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
  |   and persist captured key before returning bounded metadata,
  |   or preserve bounded selector/failure receipt in runtime state
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
|  service: neko                                                |
|    - headful browser / Chrome CDP                             |
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
scripts/redeploy-phala-cvm.mjs   update compose/env for existing Phala CVM;
                                  defaults to compose-referenced env keys
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
3. Tinker browser automation works locally and on the deployed Phala path
   through the custom GitHub-attested Neko/CDP image. Deployed bootstrap now
   seals the Tinker API key and deployed `/auth/reauth` succeeds, with bounded
   receipts and no raw secret egress.
4. Reliable Tinker account funding through Stripe browser automation is in progress:
   the test-card path reaches Stripe and declines as expected, the plaintext
   card API is disabled by default, `manual_prefund` is the default production
   funding mode, the capped validation profile is live, and real funding is not
   yet proven. Production also still requires non-dev OS and quote-internal
   verification.
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
