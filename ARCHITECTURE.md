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
            now decrypts quote-key-encrypted artifact uploads and verifies
            Ethereum keccak256 against the committed artifactHash before
            storing the upload in memory.
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
   |  submitResult(dealId, scoreBand, computeCost, resultHash)
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
[partial]   App-auth contract is not yet enforced on every OTP API request.
[planned]   Reviewer notification, consent confirmation, outbound bounded-result delivery.
```

### 2. Tinker Encumbered Contract

There is not yet a separate `TinkerAccountEncumbrance.sol` contract. In the
current repo, the Tinker encumbrance is split across:

```
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
clean up checkpoints after resolution
submit bounded result to DiligenceRoom
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
[real]      Local Neko/CDP Tinker login, email OTP retrieval, onboarding, and API-key provisioning.
[real]      Signup/bootstrap stores captured Tinker API keys in encrypted
            storage and returns only bounded hash/status metadata.
[real]      Local Stripe test-card billing path reaches submission and returns a bounded decline.
[real]      Plaintext card API is disabled by default and unavailable in dstack mode.
[real]      Central redaction helpers scrub bearer, OTP/password, card, API-key,
            and artifact-shaped values from bounded errors and high-risk logs.
[real]      Artifact upload verifies Ethereum keccak256 against artifactHash
            before DealContext state changes; mutable API decode buffers and
            stored control-plane artifact buffers are best-effort zeroed.
[real]      Encrypted artifact upload uses the attestation-exposed TEE public
            key, artifact-specific HKDF context, and deal/hash-bound AES-GCM
            associated data; plaintext artifact upload is disabled by default.
[real]      Attestation report data binds operation context plus the TEE
            encryption public key so verifiers can detect key substitution.
[real]      Client-side artifact uploader fetches `/attestation` and refuses to
            encrypt or upload unless mode, quote presence, compose hash, app ID,
            public-key shape, and report data match policy.
[real]      Standalone `verify-attestation` CLI live-fetches `/attestation` and
            checks the public evidence envelope: mode, quote presence, compose
            hash, app ID, OS image hash, report-data key binding, and client
            fetch freshness.
[real]      In dstack mode `/attestation` includes public dstack evidence fields
            when available: event log, VM config, instance/device IDs,
            aggregated measurement, OS image hash, compose hash, and TCB info.
[real]      Encrypted FastAPI artifact ingress and control-plane evaluation
            dispatch have regression tests that fail on Python file open/write
            calls while raw artifact buffers are in scope.
[partial]   Deployed Phala/CVM browser posture has not been revalidated with the current selectors.
[partial]   Funding is in progress: card data can be encrypted to the TEE, but a capped real-card funding attempt still needs to be proven.
[partial]   Optional Tinker SDK dependency must be installed for real evaluator execution.
[partial]   Artifact upload still needs full cryptographic Intel TDX quote
            parsing/freshness validation, downstream evaluator/Tinker/browser
            no-disk audit, and evaluator-side raw-byte lifetime audit.
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

The repo currently includes Tinker RL docs and an evaluator shape, but the real
TTT/RL bio-validation loop is not implemented. The current evaluator code is:

```
stub_evaluate()       deterministic synthetic result for testing
sft_evaluate()        LoRA/SFT-oriented evaluator shape using Tinker SDK
```

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

Implementation status:

```
[modeled]   TTT/RL bio-validation concept.
[partial]   SFT evaluator scaffold.
[real]      Output banding and offer computation.
[planned]   Domain-specific bio benchmark, risk classifier, and validation report schema.
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
TINKER_ORACLE_AUTH_TOKEN. Full on-chain EmailOracleAuth consumer-registry
checks are still [planned].
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
submitResult() trusts a bare teeIdentity address. It does not yet verify a TDX
quote or bind result acceptance to a measured compose hash on-chain.
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
GET  /attestation
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

### tinker-delegate

Purpose:

```
create and use a Tinker account from inside a TEE, then expose only scoped,
metered, bounded evaluation behavior
```

Endpoints:

```
GET  /health
GET  /attestation
GET  /billing/balance
POST /billing/card            local-dev plaintext hook, disabled by default
POST /billing/card/encrypted  production encrypted card channel
POST /billing/add-balance
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
[planned] real wallet auth, chain watcher, attestation verification, Tinker integration.
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
|                                                               |
|  service: oracle                                              |
|    - tee-email-oracle                                         |
|    - IMAP credentials sealed at /data                         |
|    - dstack socket mounted                                    |
|                                                               |
|  service: delegate                                            |
|    - tinker-delegate                                          |
|    - Tinker API key sealed at /data                           |
|    - dstack socket mounted                                    |
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
   card API is disabled by default, but real funding is not yet proven.
5. Real TTT/RL bio-validation is not implemented.
6. DLP/egress enforcement is not implemented.
7. Corpus policy and consent/revocation are modeled but not enforced.
8. Per-query royalty settlement is not wired to a live chain watcher.
9. The production frontend is not present on this branch.
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
7. Seller uploads private bio artifact to TEE.
8. Gate checks purpose and dual-use risk.
9. Tinker delegate starts an isolated evaluation session.
10. Target future evaluator runs TTT/RL bio-validation.
11. Control plane converts raw metric to score band.
12. TEE submits resultHash, scoreBand, and computeCost.
13. Buyer accepts or rejects.
14. Contract accrues seller payment, developer compute+fee, and buyer refund.
15. Parties withdraw.
16. TEE cleans up artifact and Tinker checkpoints.
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
2. Add real TDX quote verification for result submitters.
3. Replace bare teeIdentity trust with measured-code trust.
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
