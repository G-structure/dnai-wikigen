# TEE Email Oracle — Spec & Threat Model

> **Status**: Draft
> **Date**: 2026-03-07
> **Context**: NDAI / tinker-deligate hackathon

## 1. Problem

Many services require email-based verification (pins, OTPs, magic links) during
signup or login. If a human holds the email credentials, they can intercept
these codes — breaking the trust boundary of any TEE-based agent system.

We need an email account that:

1. Is **created inside a TEE** — credentials never touch human hands
2. Has **no recovery path** — no human can ever regain access
3. Can **securely deliver verification pins** to other trusted dstack apps
4. Is **verifiable** — anyone can confirm only the attested code has access

This is the "Setting Your Pet Rock Free" pattern applied to email.

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                 dstack CVM (Intel TDX)                       │
│                                                              │
│  ┌────────────────────┐    ┌──────────────────────┐         │
│  │  email-oracle       │    │  neko browser         │        │
│  │  (Python/Node)      │───▶│  (chromium container)  │       │
│  │                     │    │  signup only — then    │        │
│  │  - JMAP client      │    │  stopped               │        │
│  │  - pin extraction   │    └──────────────────────┘         │
│  │  - attestation API  │                                     │
│  └────────┬───────────┘                                      │
│           │                                                  │
│  ┌────────▼───────────┐                                      │
│  │  dstack-KMS         │  key = derive_key("email/creds")    │
│  │  (sealed storage)   │  same app_id → same key on reboot   │
│  └────────────────────┘                                      │
│                                                              │
│  tappd.sock → TDX Quote on every response                    │
└──────────────────────────────────────────────────────────────┘
         │
         │  mTLS + TDX quote verification
         ▼
┌────────────────────────┐
│  Consumer dstack app   │  e.g. signup-agent, auth-agent
│  (separate CVM)        │  requests: "get me the pin from
│                        │   sender X, subject matching Y"
└────────────────────────┘
```

## 3. Components

### 3.1 Account Creator (one-shot, then discarded)

**Runtime**: neko browser (headless chromium) inside the CVM.

**Flow**:

1. Generate credentials inside TEE:
   - Username: `crypto.randomBytes(8).toString('hex')` → e.g. `a3f8c1d9@fastmail.com`
   - Password: `crypto.randomBytes(32).toString('base64url')` — 256-bit
2. Automate browser to complete signup on email provider
3. Disable all recovery options (remove recovery email, phone, backup codes)
4. Generate a scoped JMAP API token (read-only)
5. Encrypt and store credentials via `derive_key("email/creds")`
6. Stop neko browser container — it is never started again
7. Generate TDX attestation quote binding the new email address to report_data

**Provider choice**: Fastmail

| Reason | Detail |
|--------|--------|
| JMAP API | Modern, single-request query+fetch, RFC 8620/8621 |
| Scoped API tokens | Read-only tokens for pin extraction |
| 180+ domains | Random domain selection adds opacity |
| No phone required | Paid accounts skip SMS verification |
| Recovery removable | Can strip recovery email/phone after setup |
| Trial available | 30-day trial for testing (limited IMAP, but JMAP works) |

**Alternatives considered**:

- **Migadu**: Programmatic mailbox creation via REST API (no browser needed), standard IMAP, but no JMAP. Requires bringing your own domain. Strong fallback option.
- **Self-hosted Stalwart**: Full JMAP+IMAP, zero third-party trust, but significant ops burden and requires a domain + IP with clean mail reputation.

### 3.2 Email Oracle (long-running service)

**Runtime**: Python (uv + pyproject.toml) or Node.js inside the same CVM.

**Responsibilities**:
- Hold encrypted credentials (decrypt via dstack-KMS on boot)
- Poll or query inbox via JMAP
- Extract verification pins/codes from emails matching caller-specified filters
- Serve an attestation-authenticated API

**API**:

```
POST /pin
Authorization: Bearer <tee-derived-token>
X-TDX-Quote: <caller's quote for mutual attestation>

{
  "from": "noreply@service.com",
  "subject_contains": "verification",
  "max_age_seconds": 300,
  "extract_pattern": "\\b\\d{6}\\b"
}

→ 200 OK
{
  "pin": "482917",
  "email_id": "M123abc",
  "received_at": "2026-03-07T12:34:56Z",
  "tdx_quote": "<oracle's quote binding this response>"
}
```

**JMAP query** (executed inside TEE):

```python
{
  "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
  "methodCalls": [
    ["Email/query", {
      "accountId": ACCOUNT_ID,
      "filter": {
        "from": request.from_filter,
        "after": cutoff_timestamp
      },
      "sort": [{"property": "receivedAt", "isAscending": false}],
      "limit": 5
    }, "q"],
    ["Email/get", {
      "accountId": ACCOUNT_ID,
      "#ids": {"resultOf": "q", "name": "Email/query", "path": "/ids"},
      "properties": ["from", "subject", "receivedAt", "textBody", "bodyValues"],
      "fetchTextBodyValues": true
    }, "g"]
  ]
}
```

### 3.3 Cross-App Authentication

Two dstack apps cannot share derived keys (different `app_id`). Secret
delivery uses **mutual TDX attestation over TLS**:

```
Consumer App                          Email Oracle
     │                                     │
     ├─ Generate TDX quote ───────────────▶│
     │  (report_data = nonce)              │
     │                                     ├─ Verify quote:
     │                                     │   - DCAP signature valid?
     │                                     │   - MRTD matches allowed list?
     │                                     │   - RTMRs match expected code?
     │                                     │
     │◀── TDX quote + encrypted pin ──────┤
     │   (report_data = sha256(pin+nonce)) │
     │                                     │
     ├─ Verify oracle's quote              │
     ├─ Decrypt pin                        │
     └─ Use pin for signup/login           │
```

**Allowed consumer list**: The email oracle maintains an on-chain or
config-embedded allowlist of `(compose_hash, deployer_id)` tuples.
Only consumers whose MRTD/RTMRs match an allowed entry receive pins.

**Alternative (same compose file)**: If consumer and oracle are services
within the same `docker-compose.yaml`, they share the same `app_id` and
can use `derive_key("shared/secret")` for a symmetric key. Simpler but
couples deployment.

## 4. Threat Model

### 4.1 Trust Boundaries

```
┌─────────────────────────────────────────────────┐
│  TRUSTED                                        │
│                                                 │
│  - Code running inside TDX CVM                  │
│  - dstack-KMS MPC nodes (each in TEE)           │
│  - Intel TDX hardware (CPU package)             │
│  - On-chain AppAuth contract logic              │
│                                                 │
├─────────────────────────────────────────────────┤
│  UNTRUSTED                                      │
│                                                 │
│  - Cloud provider (Phala) — can see metadata,   │
│    encrypted traffic, cannot read TD memory     │
│  - dstack operator — cannot extract keys,       │
│    cannot deploy unauthorized code              │
│  - Network observers — see encrypted traffic    │
│  - Human deployers — no SSH, no console,        │
│    no memory inspection                         │
│                                                 │
├─────────────────────────────────────────────────┤
│  PARTIALLY TRUSTED                              │
│                                                 │
│  - Email provider (Fastmail) — CAN read email   │
│    contents at rest. Cannot access TEE memory   │
│    or extract stored credentials.               │
│    Mitigation: pins are short-lived, extracted   │
│    immediately, and the inbox is ephemeral.     │
│                                                 │
│  - Intel (CPU vendor) — theoretically could     │
│    extract fused keys with physical die access.  │
│    No demonstrated TDX key extraction attack.    │
│    Mitigated by MPC-distributed root key.       │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 4.2 Threat Matrix

| # | Threat | Attacker | Impact | Mitigation |
|---|--------|----------|--------|------------|
| T1 | Extract email credentials from TEE memory | Cloud provider / root on host | Full account takeover | TDX encrypts TD memory with per-TD AES-XTS 128-bit key. Hypervisor removed from trust boundary. Host reads cause page faults. |
| T2 | Deploy malicious code to extract credentials | Compromised developer | Credential exfiltration | AppAuth contract requires multi-sig approval for code upgrades. dstack-KMS only provisions keys to authorized compose hashes. |
| T3 | Recover email account via provider support | Social engineering attacker | Account takeover | All recovery options removed during setup. No phone, no recovery email, no backup codes. Provider cannot reset without recovery method. |
| T4 | Intercept pin in transit between TEE apps | Network observer / cloud provider | Pin theft | Mutual TDX attestation + TLS. Pin encrypted to consumer's TEE-derived public key. Network sees only ciphertext. |
| T5 | Replay a previously captured pin | Attacker with network access | Unauthorized login | Pins are single-use and short-lived (typically 5-10 min). Oracle tracks delivered pin IDs and rejects re-requests for same email_id. |
| T6 | Impersonate a consumer app to request pins | Rogue dstack app | Pin theft | Consumer must present valid TDX quote. Oracle verifies MRTD/RTMRs against allowlist. Unauthorized code produces wrong measurements. |
| T7 | Email provider reads inbox contents | Fastmail (insider/compelled) | Pin interception | Fastmail CAN read emails. Mitigation: pins are short-lived, oracle extracts within seconds, inbox is ephemeral. For higher assurance, use end-to-end encrypted provider or self-hosted mail. |
| T8 | TDX side-channel attack (TDXdown) | Co-tenant on same host | Key leakage via timing | Patched in TDX module 1.5.06. dstack pins TDX module version. OpenSSL/wolfSSL patched for nonce leakage. |
| T9 | TDX live migration TOCTOU (CVE-2025-30513) | Malicious host during migration | Full TD state exposure | Patched by Intel. dstack can disable live migration. Phala does not enable migration by default. |
| T10 | TEE crashes, credentials lost | Hardware failure | Permanent lockout from email | dstack-KMS derives keys deterministically from RootKey. On reboot, same `app_id` re-derives same keys. Encrypted disk persists across crashes. |
| T11 | dstack-KMS MPC compromise | Colluding MPC operators | Root key exposure, all app keys compromised | MPC threshold (e.g. 3-of-5) requires multiple independent compromises. Each MPC node runs in a TEE. Geographic and organizational distribution. |
| T12 | Sender spoofs verification email | Attacker sending fake pin emails | Consumer uses wrong pin | Oracle filters by exact sender address + subject pattern. DKIM/SPF validation by Fastmail rejects spoofed mail. Consumer specifies expected sender. |

### 4.3 What We Explicitly Do NOT Protect Against

- **Email provider reading email contents** (T7). Fastmail is not end-to-end
  encrypted. They can read pins. We accept this because: pins expire in
  minutes, the oracle extracts them in seconds, and the account is otherwise
  inaccessible to humans. For higher assurance, swap Fastmail for self-hosted
  Stalwart (eliminates this threat entirely).

- **Intel hardware backdoors**. If Intel has an undisclosed mechanism to
  extract TDX memory encryption keys from the CPU die, all bets are off.
  This is a shared assumption across the entire TEE ecosystem. Mitigated
  partially by MPC-distributed root key (compromising one CPU doesn't
  compromise the KMS root).

- **Email account suspension by provider**. Fastmail can suspend or delete
  the account. Mitigation: maintain payment, don't violate ToS, monitor
  account health from within the TEE. If suspended, the email address is
  lost but no credentials are exposed.

## 5. Credential Lifecycle

```
PHASE 1: GENESIS (one-shot, ~5 minutes)
═══════════════════════════════════════
  TEE boots → neko browser starts → navigate to signup
  → generate random username + password inside enclave
  → complete signup → disable recovery → create API token
  → seal credentials via derive_key("email/creds")
  → stop neko browser forever
  → emit TDX attestation binding email address

PHASE 2: OPERATION (long-running)
═════════════════════════════════
  TEE boots → decrypt credentials via derive_key("email/creds")
  → start JMAP client → listen for pin requests
  → on request: verify consumer TDX quote → query inbox
  → extract pin → return pin + oracle TDX quote
  → delete read emails (optional, reduces exposure window)

PHASE 3: KEY ROTATION (periodic)
════════════════════════════════
  (Same app_id, upgraded code authorized by AppAuth contract)
  → new code re-derives same keys → rotates API token
  → rotates email password → updates sealed store
  → old code version deauthorized on-chain

PHASE 4: END OF LIFE
════════════════════
  Deauthorize app on AppAuth contract
  → KMS stops provisioning keys
  → credentials become irrecoverable
  → email account abandoned (no human can access it either)
```

## 6. Implementation Plan

### Phase 1: Proof of Concept (local, no TEE)

Build the core without TEE to validate the email automation flow:

- [ ] **email-oracle service** — Python (uv/pyproject.toml), JMAP client
      that authenticates to Fastmail, queries inbox, extracts pins via regex
- [ ] **neko browser signup script** — Playwright or Puppeteer script that
      creates a Fastmail account and disables recovery options
- [ ] **credential store** — file-based encrypted store (AES-256-GCM with
      key from env var, simulating dstack-KMS `derive_key`)
- [ ] **pin extraction API** — HTTP server with `/pin` endpoint, no auth
      (mocked consumer for testing)
- [ ] **docker-compose.yaml** — neko browser + oracle service

### Phase 2: TEE Integration

- [ ] Replace file-based key with `dstack_sdk.TappdClient.derive_key("email/creds")`
- [ ] Add TDX quote generation on every `/pin` response
- [ ] Add consumer quote verification on every `/pin` request
- [ ] Compose hash pinning + AppAuth contract deployment
- [ ] dstack-compatible `docker-compose.yaml` with `tappd.sock` mount
- [ ] Attestation endpoint (`GET /attestation`) returning current TDX quote

### Phase 3: Cross-App Integration

- [ ] Define allowlist format for authorized consumer apps
- [ ] Implement mutual attestation handshake
- [ ] Build reference consumer (e.g. a signup-agent that uses the email
      oracle to complete email verification on a third-party service)
- [ ] On-chain AppAuth governance for code upgrades

## 7. Open Questions

1. **Provider selection**: Fastmail requires browser automation for signup.
   Migadu offers a REST API for mailbox creation (no browser needed) but
   requires your own domain and has no JMAP. Which is the better tradeoff?

2. **Same-compose vs cross-compose**: Should the email oracle and its
   consumers live in the same docker-compose (shared `app_id`, simpler
   key sharing) or separate CVMs (stronger isolation, harder key sharing)?

3. **Email retention**: Should the oracle delete emails after extracting
   pins? Reduces exposure window but loses audit trail.

4. **Payment for Fastmail**: How to pay for the account without human
   involvement? Virtual card provisioned inside TEE? Crypto payment if
   provider accepts it? Trial account with known limitations?

5. **Browser automation reliability**: Fastmail's signup flow may change
   without notice. How to handle breakage? Health check + alerting?
   Fallback to Migadu API?

6. **Pin delivery guarantee**: What if the pin email hasn't arrived yet
   when the consumer requests it? Polling with timeout? Webhook/push
   from JMAP (Fastmail supports JMAP push)?

## 8. References

| Resource | URL |
|----------|-----|
| DelegaTEE paper (USENIX 2018) | https://www.usenix.org/conference/usenixsecurity18/presentation/matetic |
| Setting Your Pet Rock Free (Nous) | https://nousresearch.com/setting-your-pet-rock-free/ |
| dstack KMS protocol | https://docs.phala.com/dstack/design-documents/key-management-protocol |
| dstack SDK (Python) | https://pypi.org/project/dstack-sdk/ |
| Fastmail JMAP API | https://www.fastmail.com/dev/ |
| JMAP spec (RFC 8620) | https://datatracker.ietf.org/doc/html/rfc8620 |
| JMAP Mail (RFC 8621) | https://datatracker.ietf.org/doc/html/rfc8621 |
| Migadu REST API | https://migadu.com/api/ |
| TDXdown attack | https://uzl-its.github.io/tdxdown/ |
| CVE-2025-30513 (TDX migration) | https://www.securityweek.com/google-intel-security-audit-reveals-severe-tdx-vulnerability-allowing-full-compromise/ |
| Loose SEAL (SGX sealing for TDX) | https://collective.flashbots.net/t/loose-seal-enabling-crash-tolerant-tdx-applications-by-utilizing-sgx-sealing-provider-sidecar/4243 |
| Replicatoor (secret migration) | https://collective.flashbots.net/t/replicatoor-upgrade-controlled-migration-module-for-dstack/4148 |
| amiller/teemail | https://github.com/amiller/teemail |
| Account-Link/github-zktls (email-login branch) | https://github.com/Account-Link/github-zktls/tree/email-login |
| Account-Link/neko_agent | https://github.com/Account-Link/neko_agent |
| Account-Link/oauth3-tee-proxy | https://github.com/Account-Link/oauth3-tee-proxy |
