# Tinker-Delegate

Automated Thinking Machines Tinker account signup, sign-in, and API key provisioning inside a TEE. No human ever touches the credentials — the email oracle handles OTP verification, Playwright over CDP handles browser automation.

## Current Status

As of 2026-07-08, the local Neko/CDP path works against the live Tinker auth flow: the email oracle creates a mailbox, receives the Thinking Machines magic-code OTP over IMAP, Playwright enters the OTP, onboarding completes, and API-key provisioning reaches the `/keys` page and captures a one-time `tml-...` key.

The March 2026 deployed Phala/headless browser blocker should be treated as historical evidence until re-tested. Local success does not prove the packaged Phala CVM browser posture is production-safe; that still needs a fresh deployed probe.

The email oracle is still required. It is not just a disposable inbox: it is the no-human-access OTP and confirmation channel for a TEE-owned Tinker account. Operators should not hold the Tinker account credentials or the email credentials; the TEE requests the magic-code email, reads it through the oracle, and completes auth inside the browser session.

The oracle's `/pin` and `/inbox` endpoints are now protected by runtime bearer auth when enabled. In the combined dstack/Phala deployment, the oracle and delegate derive the bearer token from the same dstack key path (`oracle/runtime-auth`). Local development can use an explicit `ORACLE_RUNTIME_AUTH_TOKEN` / `TINKER_ORACLE_AUTH_TOKEN` pair instead. `/pin` requests are scoped: the delegate sends target service, expected sender, caller identity, reason, nonce, max age, and bounded extraction pattern. The oracle persists released OTP hashes in an encrypted/sealed replay ledger so one-time-use survives restart, and logs only bounded metadata, not the OTP value.

Tinker account funding remains in progress. The intended payment path is card data encrypted to the TEE, then browser automation drives the Tinker/Stripe billing form and clears card material from memory. The card channel and billing code now reach Stripe in the local Neko session: a Stripe test card filled the live payment form and was rejected with `Your card was declined.` Adding balance correctly fails closed with `Payment method required before adding balance` when no real card is on file. On 2026-07-08, the same local session produced bounded `payment_method` and `add_balance` attempt records with outcome classes, furthest-stage markers, timestamps, evidence hashes, amount bands, and card-payload destruction status. The plaintext card API endpoint is disabled by default and unavailable in dstack mode; it can only be enabled as a local-development test hook with `TINKER_ALLOW_PLAINTEXT_CARD_ENDPOINT=true`. A capped real-card funding attempt is still required before funding can be called production-complete.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        tinker-delegate                          │
│                                                                 │
│  1. GET /health ──→ email oracle ──→ cock.email address         │
│  2. CDP ──→ neko Chrome ──→ tinker-console.thinkingmachines.ai  │
│  3. Fill email → Continue → magic-code (OTP) page               │
│  4. POST /pin ──→ email oracle ──→ polls IMAP ──→ 6-digit code  │
│  5. Enter code → authenticated → onboarding → API key           │
│  6. Seal API key → return { email, api_key_hash, stored }       │
└─────────────────────────────────────────────────────────────────┘
```

### Authentication Flow

Thinking Machines uses **passwordless magic-code auth** at `auth.thinkingmachines.ai`:

1. **Email entry** — user enters email, clicks Continue
2. **OTP delivery** — 6-digit code sent from `no-reply@thinkingmachines.ai`
3. **Code entry** — 6 individual `<input inputmode="numeric">` boxes, auto-submits on completion
4. **Redirect** — authenticated session, redirected to `tinker-console.thinkingmachines.ai`

For new accounts, there's an additional **onboarding** step after first auth:
- Name (required)
- Affiliation (optional)
- Purpose (optional)
- Terms of Service checkbox (required, custom styled — hidden `<input>`, click label text)

### Historical Domain Notes

Earlier recon suggested Thinking Machines was mainly blocking known disposable domains. Those notes are no longer enough to explain the current behavior.

| Domain | Status |
|--------|--------|
| `cock.li` | historically blocked |
| `airmail.cc` | historically blocked |
| `firemail.cc` | historically blocked |
| `cock.email` | previously observed as allowed |
| `protonmail.com` | previously observed as allowed |
| `outlook.com` | previously observed as allowed |
| `gmail.com` | currently reaches magic-code in headed local Chrome |

Current July 8, 2026 local finding: local Neko Chrome reaches magic-code auth, receives OTP through the oracle, completes onboarding, and provisions API keys. The older March 17, 2026 Phala/headless blocker still needs a fresh deployed probe; email domain selection alone should not be treated as the whole production answer.

## Prerequisites

### Running Services

Both from the `tee-email-oracle` project:

1. **Email oracle** — `http://localhost:8000`
   - Historically tested with `ORACLE_DOMAIN=cock.email`
   - Creates a cock.email account on first boot (genesis)
   - Exposes `/health`, `/pin`, `/inbox` endpoints

2. **Neko Chrome** — `http://localhost:9222` (CDP)
   - Headful Chrome with remote debugging enabled
   - Visual UI at `http://localhost:52000` (optional, for debugging)

### Starting the Services

```bash
cd ⚙️/tee-email-oracle

# Set domain to cock.email (default is firemail.cc which is blocked)
echo "ORACLE_DOMAIN=cock.email" > .env

# Start with browser profile (neko + oracle)
docker compose --profile browser up -d

# Verify
curl http://localhost:8000/health
curl http://localhost:9222/json/version
```

## Usage

```bash
cd ⚙️/tinker-delegate

# Setup (first time)
uv venv && uv pip install playwright httpx pydantic pydantic-settings

# Check oracle is ready
.venv/bin/python -m tinker_delegate.main check

# Full signup: creates account, completes onboarding, generates API key
.venv/bin/python -m tinker_delegate.main signup

# Sign in: re-authenticates existing account via OTP
.venv/bin/python -m tinker_delegate.main signin

# Check balance
.venv/bin/python -m tinker_delegate.main balance

# Add payment method (card details -- use encrypted channel in production)
.venv/bin/python -m tinker_delegate.main add-card \
  --number <stripe-test-card-number> \
  --exp-month 12 --exp-year 2028 \
  --cvc 123 --name "Dev Team" \
  --address-line1 "123 Main St" --address-city "SF" \
  --address-state "CA" --address-postal "94105"

# Add balance (requires card on file)
.venv/bin/python -m tinker_delegate.main add-balance 50.00

# Start API server (for TEE deployment)
.venv/bin/python -m tinker_delegate.main serve --port 8080
```

The CLI card flags are for local development only. Production funding should use
the encrypted card channel after verifying the TEE attestation.

### Artifact Upload

Use `upload-artifact` from the seller/controller side after a deal exists. The
command fetches `/attestation`, refuses local/default attestation unless
explicitly allowed, checks the expected compose hash/app ID and report-data-bound
public key, then encrypts the artifact to `POST /deal/{id}/artifact/encrypted`.
It prints only bounded metadata: deal ID, artifact hash, size, status code, and
server response.

```bash
.venv/bin/python -m tinker_delegate.main upload-artifact \
  https://delegate.example \
  1 \
  ./artifact.jsonl \
  --compose-hash 0xEXPECTED_COMPOSE_HASH \
  --app-id 0xEXPECTED_APP_ID
```

Local development can pass `--allow-local-attestation`, but production uploads
must use the dstack/TDX attestation path.

### Attestation Verification

Use `verify-attestation` to check the public evidence envelope from a laptop
before sending payment material or artifacts. It live-fetches `/attestation` and
verifies mode, quote presence, expected compose hash, optional app ID, optional
OS image hash, public-key shape, report-data key binding, and client fetch
freshness. This is not a complete Intel quote-chain parser yet; that remains a
separate verifier task.

```bash
.venv/bin/python -m tinker_delegate.main verify-attestation \
  https://delegate.example \
  --compose-hash 0xEXPECTED_COMPOSE_HASH \
  --app-id 0xEXPECTED_APP_ID \
  --os-image-hash 0xEXPECTED_OS_IMAGE_HASH \
  --context artifact
```

### API Server

The `serve` command starts a FastAPI server for programmatic access:

```
GET  /health              — service health + oracle email
GET  /attestation         — TDX attestation quote + report_data-bound public key
GET  /billing/balance     — current Tinker balance
GET  /billing/funding-receipts — bounded funding attempt audit records
POST /billing/card        — plaintext local-dev hook, disabled by default
POST /billing/card/encrypted — add payment method after attestation-verified encryption
POST /billing/add-balance — add credit balance
POST /deal/{id}/artifact/encrypted — upload artifact encrypted to TEE key
POST /deal/{id}/artifact — plaintext local-dev hook, disabled by default
```

### Signup Output

```json
{
  "email": "d1074e2240b5311d@cock.email",
  "api_key_created": true,
  "api_key_hash": "9b3f...",
  "stored": true,
  "success": true,
  "attempt_record": {
    "surface": "api_key_provisioning",
    "outcome": "success",
    "furthest_stage": "api_key_stored",
    "evidence_hash": "sha256...",
    "account_hash": "sha256...",
    "raw_secret_egress": false
  }
}
```

### Sign-in Output

```json
{
  "email": "d1074e2240b5311d@cock.email",
  "url": "https://tinker-console.thinkingmachines.ai/keys",
  "success": true
}
```

## Configuration

All settings use the `TINKER_` env prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `TINKER_CDP_URL` | `http://localhost:9222` | Neko Chrome CDP endpoint |
| `TINKER_ORACLE_URL` | `http://localhost:8000` | Email oracle API |
| `TINKER_ORACLE_AUTH_TOKEN` | *(empty)* | Local-dev bearer token for protected oracle `/pin` and `/inbox` calls |
| `TINKER_ORACLE_AUTH_KEY_PATH` | `oracle/runtime-auth` | dstack key path used to derive the same-CVM oracle bearer token |
| `TINKER_TINKER_CONSOLE_URL` | `https://tinker-console.thinkingmachines.ai` | Tinker console URL |
| `TINKER_EMAIL` | *(auto from oracle)* | Override email address |
| `TINKER_FIRST_NAME` | `Tinker` | First name for signup |
| `TINKER_LAST_NAME` | `Delegate` | Last name for signup |
| `TINKER_OTP_POLL_INTERVAL` | `3.0` | Seconds between OTP polls |
| `TINKER_OTP_POLL_TIMEOUT` | `120.0` | Max seconds to wait for OTP |
| `TINKER_OTP_MAX_AGE` | `300` | Max age of OTP email in seconds |
| `TINKER_FUNDING_RECEIPT_STORE_PATH` | `./data/funding_receipts.enc` | Encrypted bounded funding receipt store |
| `TINKER_FUNDING_RECEIPT_STORE_KEY` | *(empty)* | Local-dev hex key override; dstack should derive the key instead |
| `TINKER_FUNDING_RECEIPT_KEY_PATH` | `tinker/funding_receipts` | dstack key path for funding receipt storage |
| `TINKER_ALLOW_PLAINTEXT_CARD_ENDPOINT` | `false` | Local-dev only flag for `POST /billing/card`; production uses `/billing/card/encrypted` |

## Architecture

```
tinker_delegate/
├── __init__.py
├── config.py          # Pydantic Settings with TINKER_ prefix
├── oracle_client.py   # HTTP client for email oracle /pin /health /inbox
├── signup.py          # Browser automation: auth, onboarding, API key creation
├── billing.py         # Browser automation: Stripe card form, balance, auto-reload
├── card_channel.py    # Secure card delivery channel (encrypted in production)
├── crypto.py          # X25519 + AES-256-GCM encryption for card channel
├── session.py         # IsolatedTinkerSession: sandboxed SDK wrapper + cost meter
├── control_plane.py   # Deal lifecycle orchestration + output bounding
├── evaluator.py       # Stub + SFT evaluator agents
├── api.py             # FastAPI server: billing, attestation, deal lifecycle
└── main.py            # CLI: check, signup, signin, balance, add-card, add-balance, serve

contracts/
├── src/DiligenceRoom.sol       # Escrow state machine (Base Sepolia)
├── test/DiligenceRoom.t.sol    # 22 tests (unit + fuzz)
├── script/DiligenceRoom.s.sol  # Deployment script
└── foundry.toml                # Foundry config for Base networks
```

### signup.py — Key Functions

| Function | Purpose |
|----------|---------|
| `signup()` | Full flow: authenticate → onboarding → create API key |
| `signin()` | Re-authenticate existing account via OTP |
| `_authenticate()` | Handle email entry, OTP wait, code entry |
| `_handle_onboarding()` | Fill name, check TOS, submit (skipped if already done) |
| `_create_api_key()` | Navigate to /keys, click "New key", extract `tml-...` token |
| `wait_for_otp()` | Poll email oracle `/pin` endpoint until 6-digit code arrives |
| `enter_otp()` | Fill 6 individual `<input inputmode="numeric">` boxes |

### oracle_client.py — Email Oracle Interface

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `health()` | `GET /health` | Check oracle status, get email address |
| `get_email()` | `GET /health` | Extract oracle email from health response |
| `get_pin()` | `POST /pin` | Poll inbox with scoped OTP metadata and bearer auth; returns one bounded code plus request/use hashes |
| `list_inbox()` | `GET /inbox` | Debug: list recent emails; sends bearer auth when configured |

## Recon Findings

### auth.thinkingmachines.ai

- **Framework**: Next.js SPA (React)
- **Auth provider**: Custom (not Clerk/WorkOS despite similar UX)
- **Sign-in page**: `input[name="email"]` + `button[type="submit"]` ("Continue")
- **Sign-up page**: `first_name`, `last_name`, `email` fields + Continue
- **OTP page**: URL contains `magic-code`, 6x `input[inputmode="numeric"]`
- **OTP sender**: `Thinking Machines Lab <no-reply@thinkingmachines.ai>`
- **OTP format**: 6-digit numeric code, regex `\b\d{6}\b`
- **OTP arrival**: ~5-8 seconds after form submission

### tinker-console.thinkingmachines.ai

- **Onboarding** (`/onboarding`): `fullName` (text), `affiliation` (text, optional), `whatWillYouCreate` (text, optional), `tos` (checkbox, hidden input — click label)
- **Welcome** (`/welcome`): Quick tips page, "Get started" button
- **API keys** (`/keys`): Table of keys, "New key" button → modal dialog → "Generate key"
- **Key format**: `tml-[A-Za-z0-9_-]{60+}` (prefix `tml-`, shown once)
- **Key modal**: "This key will ONLY appear once" warning, Copy button, Close button
- **Initial load bug**: Keys page shows "Loading..." on first visit, requires `page.reload()` to render properly

### Billing (tinker-console.thinkingmachines.ai/billing)

- **Payment**: Stripe Elements (cross-origin iframe for PCI compliance)
- **Card iframe**: `input[name="cardnumber"]`, `input[name="exp-date"]`, `input[name="cvc"]`
- **Parent fields**: `#cardholder-name`, `#service-line1`, `#service-city`, `#service-state`, `#service-postal-code`, `#service-country`
- **hCaptcha**: Invisible on form (no manual solve needed in neko)
- **Model**: Prepaid balance (add credit, spend on API usage)
- **Local test-card result**: Stripe test card reaches submission and returns `Your card was declined.`
- **No-card funding result**: add-balance fails closed with `Payment method required before adding balance`
- **Attempt records**: payment-method and add-balance responses expose bounded
  `surface`, `outcome`, `furthest_stage`, `issued_at`, `evidence_hash`,
  amount/balance bands, TDX quote hash when present, and card-payload
  destruction status; they do not return raw card fields or browser page bodies.
- **Receipt storage**: bounded funding attempt records are persisted in the
  encrypted delegate store and can be read through `/billing/funding-receipts`.
  The store rejects unknown fields and any receipt claiming raw secret egress.
- **Auto-reload**: Configurable threshold + amount
- **Pricing** (USD/million tokens): Llama-3.2-1B $0.03-$0.09, Llama-3.1-8B $0.13-$0.40, Qwen3-235B $0.68-$2.04
- **Trust model**: Developer encrypts card to TEE's TDX key → TEE fills Stripe form → zeroes memory → card never persisted

### Browser Automation Notes

- **CDP connection**: `playwright.chromium.connect_over_cdp("http://localhost:9222")`
- **Reuse existing tab**: `browser.contexts[0].pages[0]` (neko always has one page)
- **Wait strategy**: `domcontentloaded` (not `networkidle` — SPA redirects cause hangs)
- **Stale state**: Check for leftover OTP page on connect, navigate fresh if found
- **TOS checkbox**: Hidden `<input>` with overlay `<div>` intercepting clicks — use `page.locator('text=I have read and agree').click()` instead
- **Typing vs fill**: Email fields use `type(email, delay=30)` for realistic input; name fields use `fill()` since they don't have bot detection

## TEE Deployment

In production (Phala Cloud), this runs alongside the email oracle in the same CVM:

```yaml
# docker-compose.dstack.yaml additions
services:
  delegate:
    environment:
      TINKER_CDP_URL: http://172.30.0.3:9222      # neko on internal network
      TINKER_ORACLE_URL: http://oracle:8000         # oracle service
    volumes:
      - /var/run/dstack.sock:/var/run/dstack.sock   # TDX attestation
```

The API key is sealed via dstack-KMS after creation — only the same enclave can unseal it.

## What's Next

All core components are implemented. Remaining integration work:

- **Web frontend** — the public publication + interactive gate demo lives in [`web/`](web/) ("The Gate: Health", Vite + React + TS). It renders the deployment-locality spine, the four-stage pre-inference safeguards gate, a live gate simulator (with per-run attestation JSON), the health/bio app catalog, and the capability registry — all against synthetic data. Run `cd web && npm install && npm run dev`. This is the missing "Frontend: TBD" from the root README.
- **Deployment record** — see `docs/DEPLOYMENT-RUNBOOK.md` for the live Base Sepolia contract addresses, verification links, and current Phala CVM state
- **Deploy DiligenceRoom.sol** to Base Sepolia via `/forge-deploy`
- **On-chain watcher** — listen for DiligenceRoom events, call control plane API
- **Test SFT evaluator** end-to-end with real Tinker API key
- **TEE deployment** — merge docker-compose with email oracle, deploy to Phala Cloud
- **API key sealing** — code uses the encrypted key store locally and `dstack_sdk.TappdClient.derive_key("tinker/api_key")` in dstack mode; deployed CVM validation is still pending
