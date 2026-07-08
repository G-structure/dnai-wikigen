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

Before a one-off operator validation attempt, run the bounded preflight:

```bash
python -m tinker_delegate.main funding-preflight \
  --amount 5 \
  --api-url https://delegate.example \
  --compose-hash EXPECTED_COMPOSE_HASH \
  --app-id EXPECTED_APP_ID \
  --fetch-attestation \
  --output ./preflight.json

curl 'http://localhost:8080/billing/funding-preflight?amount_dollars=5&api_url=http://localhost:8080&allow_local_attestation=true'
```

The preflight checks funding mode, amount cap, optional add-balance endpoint
flag, encrypted receipt-store availability, and billing attestation policy. It
does not accept card material and does not launch browser automation. The CLI
`--output` flag writes the same bounded preflight JSON to disk.

After an approved validation attempt, write bounded receipt artifacts directly
from the receipt-producing commands:

```bash
python -m tinker_delegate.main add-card-encrypted https://delegate.example \
  --number <operator-approved-card-number> \
  --exp-month 12 --exp-year 2028 \
  --cvc <operator-approved-cvc> \
  --name "Operator Name" \
  --address-postal "94105" \
  --compose-hash EXPECTED_COMPOSE_HASH \
  --app-id EXPECTED_APP_ID \
  --os-image-hash EXPECTED_OS_IMAGE_HASH \
  --receipt-output ./payment-method-receipt.json

python -m tinker_delegate.main add-balance 5 \
  --receipt-output ./add-balance-receipt.json
```

The CLI refuses to print or write a response that contains submitted card
values or secret-shaped fields.

Build a bounded public manifest from the saved preflight and bounded receipt:

```bash
python -m tinker_delegate.main funding-manifest \
  --preflight-json ./preflight.json \
  --receipt-json ./payment-method-receipt.json \
  --validation-id operator-run-1 \
  --compose-hash EXPECTED_COMPOSE_HASH \
  --app-id EXPECTED_APP_ID \
  --os-image-hash EXPECTED_OS_IMAGE_HASH \
  --output ./funding-manifest.json

python -m tinker_delegate.main verify-funding-manifest \
  --preflight-json ./preflight.json \
  --receipt-json ./payment-method-receipt.json \
  --manifest-json ./funding-manifest.json \
  --validation-id operator-run-1 \
  --compose-hash EXPECTED_COMPOSE_HASH \
  --app-id EXPECTED_APP_ID \
  --os-image-hash EXPECTED_OS_IMAGE_HASH \
  --require-ready
```

The manifest publishes only hashes, bands, outcome, TDX quote hash,
card-destruction/no-raw-egress booleans, and the attestation-policy hash. It
rejects raw card, API-key, and secret-shaped inputs and does not prove funding
by itself; it is the audit envelope around the preflight/receipt pair. The
verifier recomputes the saved packet hashes and returns named bounded checks
without echoing the packet bodies.

## Validation Boundary

What is real:

- The local test-card path reaches Stripe/Tinker submission and returns bounded
  `card_declined`.
- Add-balance fails closed without a payment method.
- Funding attempts persist bounded encrypted receipts.
- Policy-denied card and add-balance requests persist bounded receipts without
  launching browser automation.
- Operator funding preflight returns bounded readiness checks before card
  payloads or browser automation.
- Funding preflight and billing receipt CLIs can write bounded validation JSON
  artifacts for later manifest binding.
- Funding validation manifests can be built from already-bounded preflight and
  receipt JSON.
- Funding validation manifests can be replay-verified against saved preflight,
  receipt, validation ID, and attestation policy inputs.

What remains partial:

- No live Phala encrypted-card attempt has been validated yet.
- No real-card low-value top-up has been attempted.
- No reusable payment-method token/reference is captured or persisted.
- Production or repeated card funding still requires legal/compliance approval.
