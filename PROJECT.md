# PROJECT: dnai-wikigen

Last updated: 2026-07-08
Branch context: `tinker-deligate`

`dnai-wikigen` is becoming a platform for private evaluation, private reward,
and attested settlement.

The short version:

```text
Private data can be useful without being disclosed.

The data owner puts the data, verifier, reward function, or account credential
inside an attested TEE. Agents, buyers, sponsors, or optimizers may interact
with that protected object only through a narrow interface: bounded rewards,
score bands, pass/hold/deny decisions, hashes, attestations, and settlement.
```

The first pass of the project looked like an NDAI diligence room: seller uploads
a private artifact, buyer funds escrow, a TEE evaluator inspects the artifact,
and only bounded results leave. That is still true, but the project is larger
than a deal room.

The expanded project is a **private verified-reward substrate**:

```text
sealed data + attested reward function + controlled optimization loop
       -> private reward oracle
       -> RL/TTT/LLM/evolution can optimize against it
       -> bounded output and settlement, not raw data
```

The clean motivating example is the biology task in TTT-Discover: generated
computational-bio code is evaluated against single-cell data, and the score is
used as reward while the model improves at test time. In this repo's version,
the sensitive biological data and reward verifier live inside a TEE. The method
of optimization is intentionally not the core claim. It can be reinforcement
learning, test-time training, evolutionary search, an LLM repair loop, or a
hybrid. The core claim is that the reward can be verified and useful while the
data that defines the reward remains private.

## What The Project Is

`dnai-wikigen` combines four ideas:

1. **NDAI economics**
   A seller or controller has private information. A buyer or sponsor wants to
   value it without receiving it. The deal is mediated by reserve price, budget
   cap, bounded disclosure, and escrow settlement.

2. **TEE custody**
   Private artifacts, account credentials, reward functions, API keys, browser
   sessions, and verifier data are held inside dstack/Phala Intel TDX CVMs.
   Operators should not have raw access.

3. **Private verified rewards**
   Agents can optimize candidates against reward functions derived from private
   data. The reward is "verified" because it is computed by measured code over
   a sealed dataset, not by a free-form model opinion.

4. **DevProof verification**
   Users should be able to verify what code is running, what compose hash was
   authorized, what contract accepted the result, and what bounded transcript was
   released.

The project therefore has two product faces:

```text
Attested Diligence Room
  private artifact -> bounded valuation -> escrow settlement

Private Reward Lab
  private verifier/data -> reward oracle -> optimizer improves candidate -> bounded proof
```

Those are not separate systems. The private reward lab is the strongest form of
the diligence room. Instead of merely reading an artifact, the evaluator can
actively test candidate programs, policies, or model updates against the private
data while the data remains sealed.

## Current Repo Pieces

The current branch already contains:

- `⚙️/tinker-delegate/contracts/src/DiligenceRoom.sol`
  Escrow state machine with reserve price, budget cap, result submission,
  accept/reject/expire, pull payments, and tests.

- `⚙️/tinker-delegate/contracts/src/EmailOracleAuth.sol`
  App-auth policy for the email oracle and OTP consumers, including compose-hash
  policy, manager delegation, timelocks, and freeze controls.

- `⚙️/tee-email-oracle`
  A FastAPI service intended to hold an email account inside a TEE and provide
  OTP extraction.

- `⚙️/tinker-delegate`
  TEE-side Tinker account automation, encrypted card channel, billing scaffold,
  isolated Tinker sessions, bounded control plane, evaluator scaffold, and API.

- `⚙️/props-room`
  Source-controller and sealed-asset control plane stub.

- `⚙️/whatsapp-delegate`
  Browser-mediated private source acquisition and sealed storage pattern.

- `ARCHITECTURE.md`
  The current architecture map.

- `TODO.md`
  The implementation roadmap.

## The Expanded Thesis

The project is built around a single observation:

```text
Interaction with private data is not the same thing as disclosure of private data.
```

That statement is false for arbitrary interaction. If an adversary can ask any
query and receive exact answers forever, it can reconstruct a lot. The statement
becomes true under a constrained interface:

```text
allowed query family
+ measured code
+ TEE confidentiality/integrity
+ authenticated caller policy
+ bounded output reducer
+ query and precision budgets
+ side-channel controls
+ attestable transcript
= useful interaction with controlled leakage
```

The private reward use case is exactly this. A candidate program may be executed
against secret data. It may receive a reward signal. But the reward interface is
not "read the data." It is a narrow oracle whose outputs are budgeted, reduced,
and attested.

## Running Example: Private RLVR For Computational Bio Code

TTT-Discover formulates discovery problems as environments with continuous
rewards. Its biology example uses single-cell denoising: candidate code is
scored on benchmark data, and the optimization process uses that score to find
better code. The paper reports a single-cell analysis task over OpenProblems
datasets and uses metrics related to denoising quality.

In `dnai-wikigen`, the same shape becomes:

```text
Private bio data D
  -> sealed inside TEE

Reward verifier R_D
  -> measured code computes denoising / prediction / utility score

Candidate code c
  -> proposed by RL, TTT, evolutionary search, or LLM loop

Reward R_D(c)
  -> exact value may be used internally
  -> public release is quantized, withheld, noised, or reduced to pass/hold/deny

Final result
  -> bounded score band, method hash, candidate hash, quote, settlement event
```

The optimization method is deliberately interchangeable:

```text
RLVR       policy learns from verified reward
TTT        model adapts at test time on the one problem
LLM loop   candidate -> verifier -> repair prompt -> candidate
evolution  mutation/search over candidates
manual     human proposes candidate, TEE verifies privately
```

The invariant is the same in every case:

```text
The private data and raw verifier stay inside the TEE.
Only the approved reward transcript leaves.
```

## Architecture

```text
                       public / user domain

 seller/controller       buyer/sponsor         reviewer/auditor
        |                     |                       |
        v                     v                       v
+----------------------------------------------------------------+
|                        web client / APIs                       |
| rooms, policies, budgets, attestations, review, settlement     |
+--------------------------+-------------------------------------+
                           |
                           v
+----------------------------------------------------------------+
|                         DNAI layer                             |
| deal lifecycle, access policy, coordination, bounded outputs    |
+-------------+---------------------------+----------------------+
              |                           |
              | OTP / confirmation        | execute / reward / settle
              v                           v
+--------------------------+    +--------------------------------+
| email oracle TEE         |    | tinker/private-reward TEE       |
| no-human-access mailbox  |    |                                |
| OTPs and confirmations   |    | sealed data D                  |
| EmailOracleAuth policy   |    | reward verifier R_D            |
+-------------+------------+    | candidate sandbox              |
              |                 | optimizer or Tinker session    |
              |                 | bounded output reducer         |
              |                 +---------------+----------------+
              |                                 |
              v                                 v
+--------------------------+    +--------------------------------+
| EmailOracleAuth.sol      |    | DiligenceRoom.sol / vNext      |
| compose hash policy      |    | escrow, result hash, payouts   |
| consumer authorization   |    | attested settlement            |
+--------------------------+    +--------------------------------+
                         Base Sepolia / Base-compatible chain
```

## Private Reward Environment

The project should expose a first-class environment abstraction.

```python
class PrivateRewardEnvironment:
    def problem(self) -> PublicProblem:
        """Public problem statement safe to show optimizers."""

    def candidate_schema(self) -> CandidateSchema:
        """Allowed candidate format: code, config, policy, model patch, etc."""

    def reward(self, candidate: Candidate) -> InternalReward:
        """Exact reward computed inside the TEE over sealed data."""

    def reduce(self, internal: InternalReward) -> PublicFeedback:
        """Approved feedback: band, pass/hold/deny, noised value, or nothing."""

    def finalize(self, transcript: Transcript) -> BoundedResult:
        """Final output and settlement payload."""
```

The environment owns:

- private data `D`
- reward function `R_D`
- candidate sandbox
- hidden train/reward/final-validation split
- query budget
- reward precision policy
- optimizer placement policy
- output reducer
- transcript hash
- attestation payload
- settlement payload

Implementation note: `tinker_delegate.private_reward` now contains the base
`PrivateRewardEnvironment`, leakage-budget, optimizer-policy,
bounded-feedback, transcript-hash, leakage-hash, and attestation dataclasses.
The default optimizer mode is external and bounded; exact rewards are exposed
only through an explicit internal or attested optimizer policy. This is the
interface layer only. `tinker_delegate.private_reward_sandbox` adds a local
Python sandbox for toy candidates with subprocess timeout, scratch cwd,
stripped environment, deterministic seed, capped stdout/stderr, timing bands,
public failure-code buckets, and file, network, process, and import guards.
`tinker_delegate.private_reward_holdout` adds a hidden-holdout split and
accounting contract with public split commitments, partition counts,
reward-query tracking, per-candidate repeat caps, minimum unique candidates
before final validation, and one-shot final-validation gating.
`tinker_delegate.private_reward_envs.synthetic` wires those contracts into a
toy hidden-keyword environment with bounded reward bands and final validation
over sealed synthetic records. Real RLVR, TTT, bio-validation, domain-specific
anti-overfitting rules, and hardened production candidate-sandbox environments
are still separate implementation work.

## Security Goal

The informal goal:

```text
An adversary can learn no more from the real system than it could learn from an
ideal private reward oracle that reveals only the approved leakage.
```

This is the right kind of claim. It does not say "no information leaks." Reward
queries necessarily leak something. It says the only leakage is the leakage the
system intentionally exposes through the reward interface and final bounded
outputs.

## Formal Model

Let:

- `D` be the private dataset or artifact.
- `C` be the candidate space: code, model patch, prompt, policy, or algorithm.
- `R_D: C -> Y` be the reward function induced by private data `D`.
- `P` be the public problem statement.
- `Q: Y -> Z` be the output reducer: quantization, banding, thresholding,
  noising, or withholding.
- `B` be the budget: max queries, max runtime, max spend, max precision.
- `Pi` be the policy deciding which candidates are admissible.
- `A` be an adaptive adversary/optimizer that proposes candidates.
- `View_A(D)` be everything `A` sees in the real protocol.

The ideal functionality `F_private_reward` works like this:

```text
Setup:
  Store D privately.
  Publish P, policy metadata, environment hash, quote, and contract addresses.

Query(c):
  If query budget exhausted: return reject_budget.
  If Pi(c) rejects: return reject_policy.
  Compute y = R_D(c).
  Store exact y internally.
  Return z = Q(y), or return no public reward if Q withholds feedback.

Finalize:
  Compute bounded result from the internal transcript.
  Return only approved fields:
    result band, confidence band, safety band, candidate hash,
    transcript hash, cost band, quote, and settlement payload.
```

The leakage function is:

```text
L(D) =
  public problem P
  public policy metadata
  number of accepted/rejected queries up to B
  candidate hashes and possibly candidate contents if policy permits
  reduced feedback z_i = Q(R_D(c_i))
  timing/cost bands
  final bounded result
  transcript hash
  attestation and chain events
```

Everything else should be hidden:

```text
D
raw rows / sequences / assays
exact reward values if Q withholds or bands them
hidden holdout split
raw model samples
private gradients
reward-derived optimizer state
checkpoints encoding private reward
API keys, account credentials, card details
```

## Main Theorem: Leakage-Only Realization

**Theorem 1.** Assume:

1. The TEE provides confidentiality and integrity for measured code and sealed
   storage.
2. Remote attestation is unforgeable and verifiers check freshness, app ID,
   compose hash, public keys, and policy.
3. Secrets are provisioned only to authorized compose hashes.
4. All candidate execution is sandboxed and cannot use unauthorized I/O.
5. All external outputs pass through `Q` and the transcript logger.
6. Side channels are either out of scope or bounded by the leakage function.
7. The optimizer that sees exact rewards or reward-derived updates is inside the
   trusted boundary. If it is not, exact rewards and reward-derived updates are
   not sent to it.

Then for every probabilistic polynomial-time adversary `A` controlling the
network, optimizer prompts, candidate submissions, public chain reads, and the
untrusted host outside the TEE, there exists a simulator `S` given only `L(D)`
such that:

```text
View_A(real protocol with D)  ~=c  S(L(D))
```

where `~=c` means computational indistinguishability up to the security of the
TEE, attestation scheme, authenticated encryption, signatures, and hash
functions.

### Proof Sketch

The simulator receives the allowed leakage `L(D)`. It fabricates the public
network transcript, chain events, API responses, attestation-shaped records, and
bounded feedback values exactly as described by `L(D)`.

The only places where the real protocol uses private data are:

1. reward computation `R_D(c)`
2. internal optimizer state updates, if the optimizer is inside the TEE
3. final bounded-result reduction
4. sealed storage and cleanup

By assumption, these computations run inside measured TEE code and their raw
inputs/outputs are not externally visible. The real external messages are
therefore either public setup data, adversary-provided candidates, or outputs of
`Q` and the transcript logger. Those are exactly the values in `L(D)`.

If an adversary distinguishes the real view from the simulated view, then one of
the assumptions was broken: TEE confidentiality, attestation unforgeability,
sealed-key policy, sandbox confinement, output mediation, or the declared
side-channel bound.

So the real system reveals no more than the ideal private reward oracle.

## Information Bound

Simulation says the infrastructure leaks only approved outputs. The next
question is how much information those outputs can contain.

Suppose:

- at most `n` reward queries are accepted,
- each public feedback value `z_i` has at most `k` bits of entropy,
- the final bounded result has at most `b` bits of entropy,
- all other public metadata is independent of `D` or separately counted.

Then:

```text
I(D ; public transcript) <= n * k + b
```

This follows from the data processing inequality:

```text
D -> (R_D(c_1), ..., R_D(c_n)) -> (Q(R_D(c_1)), ..., Q(R_D(c_n)), final)
```

and from the entropy bound:

```text
I(D ; Z) <= H(Z)
```

If `Q` returns one of `m` reward bands, then `k <= log2(m)`. If the public
system withholds per-query reward and releases only one final band among `m`
bands, then the reward transcript leaks at most `log2(m)` bits plus separately
counted timing/cost metadata.

This is the clean reason the security model is surprisingly strong:

```text
The optimizer can interact with private data many times inside the TEE, but
outside observers only receive a small, budgeted transcript.
```

The exact rewards can still drive learning internally. They just do not have to
be public.

## Adaptive Queries

The adversary may choose candidate `c_t` after seeing previous public feedback:

```text
c_t = A(P, z_1, ..., z_{t-1})
```

The theorem still holds because the ideal functionality is also adaptive. It
computes the same reduced feedback for each candidate and reveals only `z_t`.

Adaptive querying matters for leakage quantity, not for the simulation theorem.
That is why the environment must enforce:

- query budget
- reward precision budget
- hidden final holdout
- overfitting checks
- side-channel controls
- candidate sandboxing

Without those, an adaptive adversary can turn even a legitimate oracle into a
data-extraction channel.

## Differential Privacy Option

The bounded-transcript guarantee protects against infrastructure leakage. It is
not automatically a patient-level privacy guarantee.

If the reward mechanism released to the outside world is `(eps, delta)`
differentially private with respect to neighboring datasets `D` and `D'`, then
the public reward transcript inherits standard DP composition:

```text
q adaptive releases, each eps-DP
  -> at most q * eps basic composition
```

with the usual stronger bounds available through advanced composition or a
privacy accountant.

This gives a second, statistical privacy layer:

```text
TEE isolation controls where computation happens.
Output reduction controls what the infrastructure reveals.
Differential privacy controls what the released rewards reveal about one record.
```

DP is optional because some use cases are dataset-level IP protection rather
than individual-level privacy. For real PHI or sensitive bio data, the project
should either implement DP accounting or explicitly mark the environment as not
PHI-safe.

## Why This Is Strong Despite Interaction

A naive view says: "If the agent can run code on the data, the data is exposed."

That is true if the agent controls the process. It is false if the agent only
controls candidates submitted to a measured verifier.

The distinction:

```text
Bad: agent gets shell / notebook / database / exact metrics / logs.
Good: agent submits candidate c; TEE returns Q(R_D(c)).
```

In the good case, interaction is mediated by a reward oracle. The security is
not "no interaction." The security is:

```text
No unmediated interaction.
No unbounded reward precision.
No unlimited query count.
No raw verifier logs.
No raw data or exact holdout labels.
No reward-derived state leaving the boundary unless accounted for.
```

This is similar in spirit to cryptographic ideal functionalities. The real
system should behave like a trusted third party holding `D` and answering only
approved reward queries.

## Trusted Boundary Choices

There are three security tiers.

### Tier 1: Full Private Optimizer

```text
candidate generation, reward computation, optimizer updates, and archive
all inside the same TEE
```

This is the strongest tier. Exact rewards and dense gradients may exist, but
only inside the TEE. Public leakage can be just the final bounded result.

### Tier 2: Attested Remote Trainer

```text
reward TEE + trainer TEE + attested channel + policy binding
```

This can support true RL/TTT updates with dense reward, but only if the trainer
is itself attested and included in the trust story. The attestation transcript
must bind both sides.

### Tier 3: External Optimizer With Bounded Feedback

```text
external LLM/optimizer proposes candidates
TEE computes reward
external optimizer receives only bounded feedback
```

This is useful and often enough, but it is not the same as sending dense reward
labels or gradients to an external service. If Tinker is untrusted for a given
environment, the project must not send private reward labels, private
gradients, selected-example traces, or checkpoints that encode the private data.

## Tinker Implication

Tinker is valuable compute for fine-tuning, RL, sampling, and TTT-style loops.
But the security claim depends on what Tinker sees.

Safe patterns:

- Tinker account credentials stay sealed in the TEE.
- Tinker receives only non-sensitive prompts/candidates.
- TEE computes private rewards and releases only bounded feedback.
- Tinker is used for candidate generation or public/synthetic training.
- Dense reward training happens only when Tinker is part of the trusted boundary
  or the reward signal is safe to reveal.

Unsafe pattern:

```text
TEE computes exact private reward -> sends dense reward labels or gradients to
an untrusted external trainer -> trainer logs/checkpoints can encode D.
```

That pattern breaks the private reward theorem because reward-derived state has
left the ideal functionality.

So the implementation must label every environment by security tier.

## Candidate Code Security

For computational-bio code, the candidate itself can be adversarial. It may try
to exfiltrate data through stdout, timing, memory pressure, exceptions, output
files, or resource usage.

The candidate sandbox must enforce:

- no network
- no arbitrary file reads
- no access to raw data paths except through verifier-controlled APIs
- bounded stdout/stderr
- bounded return schema
- fixed time/memory limits
- timeout normalization
- deterministic seeds when feasible
- scratch directory only
- no access to attestation socket or secrets
- no outbound browser/CDP
- no environment variables containing secrets

Candidate outputs must then pass through the reducer before release.

## What The Contract Guarantees

Contracts do not hide data. They provide public coordination and settlement.

`DiligenceRoom.sol` and vNext contracts should guarantee:

- buyer budget cap is enforced
- seller reserve is enforced
- compute cost and fees fit inside the budget
- only an authorized attested evaluator can submit results
- result hash binds the transcript
- settlement is pull-payment based
- expiry/reject/accept are well-defined
- public events let auditors verify the lifecycle

`EmailOracleAuth.sol` should guarantee:

- only authorized oracle compose hashes receive email KMS material
- only authorized consumers can request OTPs
- consumer managers cannot modify oracle code policy
- production policy can be frozen
- fresh quotes are checked against stable compose-hash policy

The contracts complete the private reward story by making the reward transcript
economically consequential without putting raw data on-chain.

## What The TEE Guarantees

The TEE and attestation layer should guarantee:

- the reward code is the measured code
- the private data is sealed to that measured code
- callers can establish an encrypted channel to the measured code
- secrets are unavailable to other code measurements
- public keys and quotes are bound to the running app
- outputs are mediated by measured code

This is not magic. It depends on the TEE threat model. Physical attacks,
provider provenance, side channels, malicious host scheduling, and bugs in the
measured code must be handled explicitly or listed as assumptions. Flashbots'
Proof-of-Cloud work is directly relevant here because ordinary TEE attestation
does not fully answer where the hardware is operated.

## What The System Does Not Guarantee Yet

The current repo does not yet guarantee:

- production quote verification for result submission
- runtime enforcement of `EmailOracleAuth` on every OTP endpoint
- safe Tinker account funding
- Tinker signup through current bot-check/browser posture
- real TTT/RL private reward environments
- candidate sandboxing for generated computational-bio code
- differential privacy for individual-level bio data
- real DLP/egress controls
- human reviewer queue
- multi-party coordination engine
- production frontend wired to real APIs
- Proof-of-Cloud or equivalent platform provenance

These are roadmap items, not solved facts.

## Product Modes

### Mode A: Diligence Room

```text
seller artifact -> TEE evaluator -> score band / offer -> escrow settlement
```

Use for private memos, code, datasets, SOPs, benchmarks, or model artifacts.

### Mode B: Private Reward Environment

```text
sealed verifier data -> candidate code -> private reward -> optimizer loop
```

Use for RLVR, TTT-Discover-style tasks, computational-bio code, private
benchmarks, code optimization against proprietary tests, or reward-function
licensing.

### Mode C: Source Custody Room

```text
web2/source account -> TEE browser/export -> sealed artifact -> policy-gated use
```

Use for WhatsApp, email, private repos, data portals, or user-contributed source
data.

### Mode D: Multi-Owner Collaboration

```text
N private corpora -> fan-out gates -> unanimous/quorum consent -> joint result
```

Use for biobank collaboration, sponsor/CRO workflows, and cross-institution
private analysis.

## Relation To Flashbots, Teleport, Andrew Miller, And Wikigen

### Flashbots / Flashbots X

Flashbots' TEE work emphasizes that mutually distrusting parties can share a
confidential execution environment, but also that vanilla attestation is not the
end of the trust story. `dnai-wikigen` should import that seriousness:

- name all roles separately: operator, host/cloud provider, data owner, sponsor,
  evaluator owner, reviewer, auditor
- verify not only code measurement, but also platform provenance where possible
- treat Proof-of-Cloud as a future hardening layer
- keep the contract-facing trust story explicit

### Teleport / Account-Link

Teleport demonstrates scoped use of a web2 account through a TEE: one action,
under policy, without handing over the account. `dnai-wikigen` uses the same
shape:

- one OTP use
- one Tinker compute grant
- one private reward environment
- one bounded evaluation
- one settlement

The account or data is not sold outright. A scoped capability is exercised under
policy.

### Andrew Miller / outh3 / DevProof

The Andrew Miller references in `🔬/amiller` point toward DevProof apps:
reproducible code, attestable deployments, no hidden developer powers,
inspection certificates, escrow, and domain separation. The proof in this file
is written in that style:

```text
Define the ideal functionality.
State the leakage.
Show the real protocol leaks no more.
List the assumptions.
Do not claim side channels or TEE hardware are solved by prose.
```

### Wiki Leks / Wikigen

Wikigen's product insight is that private information has latent value, but
ordinary disclosure destroys leverage. The larger version says:

```text
Private information can become a reward, a verifier, a capability, or an
evaluation market without becoming public data.
```

That is the project.

## Implementation Priorities

The next concrete build should be:

1. Build a synthetic hidden-data reward environment.
2. Add candidate sandboxing.
3. Prove the reducer prevents exact reward egress in public mode.
4. Wire the environment into the existing `control_plane`.
5. Run one end-to-end local test:
   candidate -> private reward -> bounded result -> result hash.
6. Only then connect a real Tinker/TTT loop.

This order keeps the security claim ahead of the optimizer hype. The optimizer
can be swapped later. The private reward boundary is the product.

## References

- TTT-Discover paper: https://arxiv.org/abs/2601.16175
- TTT-Discover code: https://github.com/test-time-training/discover
- TTT-Discover project page: https://test-time-training.github.io/discover/
- Flashbots Proof-of-Cloud discussion:
  https://writings.flashbots.net/mind-the-gap-tee-poc
- Flashbots Sirrah TEE coprocessor:
  https://writings.flashbots.net/suave-tee-coprocessor
- Teleport / Account-Link:
  https://github.com/teleport-computer/teleport-gramine-rs
- Gramine attestation and secret provisioning:
  https://gramine.readthedocs.io/en/latest/attestation.html
- Andrew Miller:
  https://soc1024.ece.illinois.edu/
