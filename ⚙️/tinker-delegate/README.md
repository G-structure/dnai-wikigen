# Tinker-Delegate

Automated Thinking Machines Tinker account signup, sign-in, and API key provisioning inside a TEE. No human ever touches the credentials — the email oracle handles OTP verification, Playwright over CDP handles browser automation.

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
│  6. Return { email, api_key }                                   │
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

### Email Domain Blocklist

Thinking Machines blocks known disposable email domains. Tested results:

| Domain | Status |
|--------|--------|
| `cock.li` | **BLOCKED** |
| `airmail.cc` | **BLOCKED** |
| `firemail.cc` | **BLOCKED** |
| `cock.email` | **ALLOWED** |
| `protonmail.com` | ALLOWED |
| `outlook.com` | ALLOWED |
| `gmail.com` | ALLOWED |

**`cock.email` is a cock.li domain that passes the blocklist.** The IMAP server is still `mail.cock.li` — only the domain suffix matters for signup.

The auth page also has a hidden `signals` field (bot detection) but it appears non-functional — it stays empty and doesn't affect the flow. The block is purely domain-based.

## Prerequisites

### Running Services

Both from the `tee-email-oracle` project:

1. **Email oracle** — `http://localhost:8000`
   - Must be configured with `ORACLE_DOMAIN=cock.email`
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
```

### Signup Output

```json
{
  "email": "d1074e2240b5311d@cock.email",
  "api_key": "tml-yIqm...",
  "success": true
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
| `TINKER_TINKER_CONSOLE_URL` | `https://tinker-console.thinkingmachines.ai` | Tinker console URL |
| `TINKER_EMAIL` | *(auto from oracle)* | Override email address |
| `TINKER_FIRST_NAME` | `Tinker` | First name for signup |
| `TINKER_LAST_NAME` | `Delegate` | Last name for signup |
| `TINKER_OTP_POLL_INTERVAL` | `3.0` | Seconds between OTP polls |
| `TINKER_OTP_POLL_TIMEOUT` | `120.0` | Max seconds to wait for OTP |
| `TINKER_OTP_MAX_AGE` | `300` | Max age of OTP email in seconds |

## Architecture

```
tinker_delegate/
├── __init__.py
├── config.py          # Pydantic Settings with TINKER_ prefix
├── oracle_client.py   # HTTP client for email oracle /pin /health /inbox
├── signup.py          # Browser automation: auth, onboarding, API key creation
└── main.py            # CLI: check, signup, signin
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
| `get_pin()` | `POST /pin` | Poll inbox for OTP matching `\b\d{6}\b` pattern |
| `list_inbox()` | `GET /inbox` | Debug: list recent emails |

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
- **API keys** (`/keys`): Table of keys, "New key" button → modal dialog
- **Key format**: `tml-[A-Za-z0-9_-]{60+}` (prefix `tml-`, shown once)
- **Key modal**: "This key will ONLY appear once" warning, Copy button, Close button
- **Initial load bug**: Keys page shows "Loading..." on first visit, requires `page.reload()` to render properly

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

This module handles Phase 1 (account provisioning). The remaining phases from SPEC.md:

- **IsolatedTinkerSession** — Python SDK wrapper enforcing session isolation + TTL cleanup
- **Evaluator agent** — trains on seller's artifact, benchmarks, emits bounded scores
- **Control plane API** — TEE-hosted service mediating escrow contract ↔ agent
- **DiligenceRoom contract** — escrow state machine on Base Sepolia
