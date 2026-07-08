# Tinker Funding Model

Status: local policy enforced; live funding still not proven.

## Decision

The production funding model is **manual/developer prefund by default** until
Tinker exposes an official funding API, Stripe-hosted/tokenized collection, or
another support-approved route that can be verified without raw card custody.

The encrypted raw-card browser path remains only a one-off
operator-owned capped validation mode. It is not the production or repeated
funding model.

## Runtime Modes

`TINKER_FUNDING_MODE=manual_prefund`

- Default.
- Card automation is denied.
- Add-balance browser automation is denied.
- Balance checks and bounded funding receipts remain available.
- Use this for production-like deployments unless there is explicit approval to
  run a validation attempt.

`TINKER_FUNDING_MODE=operator_capped_validation`

- Allows encrypted card submission and add-balance browser automation.
- Must still obey `TINKER_MAX_ADD_BALANCE_USD`.
- The HTTP add-balance mutation endpoint remains separately disabled unless
  `TINKER_ALLOW_ADD_BALANCE_ENDPOINT=true`.
- The plaintext card endpoint remains separately disabled unless
  `TINKER_ALLOW_PLAINTEXT_CARD_ENDPOINT=true`, and is still unavailable in
  dstack mode.
- Use only for an approved operator-owned test-card or real-card validation
  attempt.

`TINKER_FUNDING_MODE=official_tokenized`

- Reserved for a future official/tokenized route.
- Raw-card browser automation remains denied until that route is implemented.

## Public Inspection

Operators and clients can inspect the bounded policy surface without seeing
account, card, or credential state:

```bash
python -m tinker_delegate.main funding-policy
curl http://localhost:8080/billing/funding-policy
```

The response includes the funding mode, whether card/add-balance automation is
allowed, the configured add-balance cap, endpoint flags, raw-card scope, and the
next evidence required to advance funding validation.

## Validation Boundary

What is real:

- The local test-card path reaches Stripe/Tinker submission and returns bounded
  `card_declined`.
- Add-balance fails closed without a payment method.
- Funding attempts persist bounded encrypted receipts.
- Policy-denied card and add-balance requests persist bounded receipts without
  launching browser automation.

What remains partial:

- No live Phala encrypted-card attempt has been validated yet.
- No real-card low-value top-up has been attempted.
- No reusable payment-method token/reference is captured or persisted.
- Production or repeated card funding still requires legal/compliance approval.
