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
2. `[partial]` The bounded receipt records the signer attestation hash,
   normalized report data, quote size, compose hash, signer address, chain ID,
   contract address, signer nonce, and replay-bound result commitment. This is
   enough for local verifier tooling and reviewer audit, but not yet enough for
   trustless on-chain enforcement.
3. `[planned]` A vNext contract or attestation registry should accept results
   only when a verified off-chain attestation verifier signs a policy statement
   binding the signer address to an approved compose/app measurement, quote
   freshness window, chain ID, contract address, deal ID, nonce, and result
   commitment. Until that contract path exists, `DiligenceRoom.sol` still trusts
   a bare `teeIdentity` address at the Solidity level.

Rationale:

- Full Intel TDX quote parsing is not exposed by the current local dstack SDK
  helpers, so the repo should not claim complete cryptographic quote
  verification in Python or Solidity.
- The pre-broadcast gate is still meaningful progress: a normal operator path
  cannot use the `submit-result` CLI without dstack mode, dstack-derived signer
  custody, and signer quote evidence that matches the intended chain and
  contract.
- Keeping `DiligenceRoom.sol` unchanged preserves the deployed ABI while the
  verifier/registry design matures.

Open follow-ups:

- `[planned]` Add a verifier signature format for result submissions.
- `[planned]` Add contract or registry enforcement so a bogus bare
  `teeIdentity` cannot submit even if it controls the private key.
- `[planned]` Add quote freshness/revocation policy once production Phala quote
  evidence is available.
- `[planned]` Repeat the proof from a deployed Phala CVM, not only the local
  simulator.

