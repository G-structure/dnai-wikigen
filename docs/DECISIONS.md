# Architecture Decisions

This ledger records architecture choices that affect trust boundaries,
deployment topology, funding rails, quote verification, data locality, and
frontend verification. Status labels match `ARCHITECTURE.md`:

- `[real]` implemented and locally verified.
- `[partial]` implemented but not production-complete.
- `[modeled]` specified or stubbed but not enforced end to end.
- `[planned]` target only.

## 2026-07-08: Result-Submission Quote Verification Path

Status: `[partial]`

Decision:

`DiligenceRoom.submitResult()` quote verification will proceed in two stages.

1. `[real]` The current submitter uses an off-chain verifier gate before
   broadcast. In dstack mode it derives the Ethereum signer inside the TEE,
   fetches quote evidence whose `report_data` binds the signer address, chain
   ID, and DiligenceRoom contract address, verifies the quote envelope fields,
   and only then signs and broadcasts `submitResult()`.
2. `[real]` `DiligenceRoom.sol` requires a configured result-verifier
   signature before accepting `submitResult()`. The authorization binds chain
   ID, contract address, deal ID, TEE identity, compose hash, score band,
   compute cost, replay-bound result commitment, and authorization expiry.
3. `[partial]` The bounded receipt records the signer attestation hash,
   normalized report data, quote size, compose hash, signer address, chain ID,
   contract address, signer nonce, replay-bound result commitment,
   authorization expiry, and verifier-signature hash. This is enough for local
   verifier tooling and reviewer audit, but not yet enough for production quote
   verification because the verifier service/policy is not built.
4. `[real]` `tinker_delegate.result_verifier` implements the policy/signature
   core for the production verifier path. It accepts bounded signer attestation
   evidence only when it matches signer address, chain ID, contract address,
   report data, quote report data, approved compose hash, approved app ID,
   optional OS image hash, revocation policy, distinct verifier/TEE keys, and a
   short authorization TTL; then it signs the exact contract digest.
5. `[planned]` The production verifier service/path must wrap this module,
   consume live Phala quote evidence from the submitter, and add cryptographic
   Intel TDX quote parsing/freshness before the repo can claim complete
   production quote verification.

Rationale:

- Full Intel TDX quote parsing is not exposed by the current local dstack SDK
  helpers, so the repo should not claim complete cryptographic quote
  verification in Python or Solidity.
- The pre-broadcast gate is still meaningful progress: a normal operator path
  cannot use the `submit-result` CLI without dstack mode, dstack-derived signer
  custody, and signer quote evidence that matches the intended chain and
  contract.
- `DiligenceRoom.sol` now has the verifier-signature hook, which intentionally
  breaks the previous deployed ABI. Fresh deployments must configure
  `DILIGENCE_RESULT_VERIFIER` or explicitly accept the deployer as the local
  smoke-test verifier.

Open follow-ups:

- `[real]` Add a verifier signature format for result submissions.
- `[real]` Add contract enforcement so a bogus bare `teeIdentity` cannot submit
  without a verifier authorization.
- `[real]` Add the bounded policy/signature core for the production verifier
  path.
- `[planned]` Wrap the verifier module as a deployed service/operator path.
- `[planned]` Add full cryptographic quote parsing/freshness once production
  Phala quote evidence is available.
- `[planned]` Repeat the proof from a deployed Phala CVM, not only the local
  simulator.
