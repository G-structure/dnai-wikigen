# Oracle API Auth Scoping — TEE Service-to-Service Authentication

## Problem

The email oracle API (`/pin`, `/credentials/*`) is currently unauthenticated. Any process that can reach port 8000 can read email pins and manage credentials. In production, only the tinker-delegate service running inside the same CVM should be able to call it.

## Threat Model

| Threat | Impact | Current Mitigation |
|--------|--------|-------------------|
| External attacker hits oracle API | Full credential theft | None (port exposed) |
| Rogue container in CVM calls oracle | Unauthorized email access | None (flat network) |
| Oracle impersonated by attacker | Delegate sends creds to wrong service | None (no mutual auth) |
| Replay of captured auth token | Stale token reuse | None |

## Research Findings from 🔬

Eight concrete auth patterns found across the reference repos:

### Pattern 1: dstack `derive_key` / `getKey` — Shared Secret
**Source**: `🔬/amiller/dstack-tutorial/05-onchain-authorization/`, `🔬/amiller/dstack-examples/tutorial/02-kms-and-signing/`

Both oracle and delegate derive a key from the same dstack-KMS using the same path. The derived key is deterministic per (compose hash, path) — same CVM always gets the same key.

```
# Both services call:
client.getKey("/service-auth", "raw")  # JS
# or
client.derive_key("/service-auth", "raw")  # Python

# Result: identical 32-byte secret on both sides
# Use as: HMAC-SHA256 bearer token, or pre-shared key for mutual TLS
```

**Pros**: Zero config, no external dependencies, cryptographically tied to CVM identity
**Cons**: Requires both services to have dstack.sock mounted, symmetric (no sender/receiver distinction)

### Pattern 2: Domain Separation Proxy
**Source**: `🔬/amiller/dstack-openclaw/docker-compose-phala.yaml`

A proxy container has dstack.sock and gates access. The constrained container (agent) has no dstack.sock — it can only reach the outside world through the proxy. The proxy logs all interactions.

```yaml
# From openclaw:
dstack-proxy:
  volumes:
    - /var/run/dstack.sock:/var/run/dstack.sock:ro
    - proxy-socket:/var/run-proxy
claw-tee-dah:
  # NO dstack.sock — uses proxy socket instead
  volumes:
    - proxy-socket:/var/run:rw
```

**Pros**: Strong isolation, genesis transparency (all instructions logged)
**Cons**: Complex, overkill for our 2-service setup where both need dstack access

### Pattern 3: AppAuth Contract (On-Chain Authorization)
**Source**: `🔬/amiller/dstack-tutorial/08-extending-appauth/`, `🔬/amiller/devproof-apps-guide/`

An on-chain contract whitelists compose hashes and device keys. The KMS only derives keys for CVMs whose compose hash is registered in the AppAuth contract. This provides public auditability of what code is authorized.

```solidity
// AppAuth.sol (simplified)
function addComposeHash(bytes32 hash) external onlyOwner;
function isAuthorized(bytes32 composeHash, bytes32 deviceKey) external view returns (bool);
```

**Pros**: Public verifiability, governance-compatible, revocable
**Cons**: Requires deployed contract, gas costs, doesn't solve intra-CVM auth directly

### Pattern 4: Bearer Token from Derived Key
**Source**: Synthesized from patterns 1 + 3

Derive a service-specific key at boot, compute `HMAC-SHA256(derived_key, "oracle-auth")`, use as Bearer token. Both services derive the same key, so both can compute the same token.

```python
# At boot (both services):
key = dstack_client.derive_key("/tinker-delegate/service-auth")
token = hmac_sha256(key, b"oracle-api-v1")

# Delegate → Oracle request:
headers = {"Authorization": f"Bearer {token.hex()}"}

# Oracle validates:
expected = hmac_sha256(key, b"oracle-api-v1")
if not hmac.compare_digest(request_token, expected):
    raise 401
```

### Pattern 5: Compose Hash as Identity
**Source**: `🔬/amiller/devproof-audits-guide/`, `🔬/amiller/dstack-tutorial/08-extending-appauth/add_compose_hash.py`

The compose hash (SHA256 of the docker-compose file) uniquely identifies the set of services. When both services are in the same compose, they share an identity. The TDX quote includes this hash — external verifiers can confirm what code is running.

**Relevance**: Not directly an auth mechanism, but the foundation for Pattern 3 (AppAuth) and for external verification that the oracle is only callable by the delegate.

### Pattern 6: GroupAuth / Cross-Attestation
**Source**: `🔬/amiller/github-zktls-1--groupauth/`

Multiple CVMs attest to each other. Each CVM verifies the other's TDX quote before exchanging data. Useful for multi-CVM architectures.

**Relevance**: Overkill for single-CVM deployment. Would matter if oracle and delegate ran on separate CVMs.

### Pattern 7: Genesis Transparency Log
**Source**: `🔬/amiller/dstack-openclaw/`

All instructions (developer commands, config changes) are logged to an append-only genesis log at startup. This log is attested alongside the TDX quote. External auditors can verify that no secret instructions were given.

**Relevance**: Useful for auditability of the delegate's behavior, not directly for service auth.

### Pattern 8: Network Isolation (Docker Networks)
**Source**: All compose files in 🔬

Services on different Docker networks cannot reach each other. In the unified compose, oracle + delegate share `tee-net` (172.20.0.0/24). Neko is on the same network but doesn't need oracle API access.

**Relevance**: Defense in depth — restrict which containers can even reach the oracle port.

## Recommended Approach

**Primary: Pattern 4 (Bearer Token from Derived Key)** — simple, zero-config, cryptographically strong.

**Defense in depth: Pattern 8 (Network Isolation)** — oracle only listens on internal interface.

### Implementation Plan

#### Phase 1: Derived Key Bearer Auth (P0 — must have for TEE deploy)

```
Effort: ~2 hours
Files:  oracle/auth.py (new), oracle/api.py (middleware), delegate/oracle_client.py (header)
```

1. **Shared auth module** (can live in both services or as a small shared package):
   ```python
   import hmac, hashlib
   from dstack_sdk import DstackClient

   DOMAIN = b"tinker-delegate/oracle-api/v1"

   async def derive_service_token() -> bytes:
       """Derive a deterministic auth token from dstack KMS."""
       client = DstackClient()
       key_result = await client.derive_key("/tinker-delegate/service-auth")
       return hmac.new(key_result.key, DOMAIN, hashlib.sha256).digest()
   ```

2. **Oracle middleware** — validate Bearer token on all non-health endpoints:
   ```python
   @app.middleware("http")
   async def verify_service_auth(request, call_next):
       if request.url.path == "/health":
           return await call_next(request)
       if not DSTACK_ENABLED:
           return await call_next(request)  # skip in local dev
       token = request.headers.get("Authorization", "").removeprefix("Bearer ")
       expected = (await derive_service_token()).hex()
       if not hmac.compare_digest(token, expected):
           return JSONResponse(status_code=401, content={"error": "unauthorized"})
       return await call_next(request)
   ```

3. **Delegate client** — attach token to all oracle requests:
   ```python
   class OracleClient:
       async def _headers(self) -> dict:
           if not self.dstack_enabled:
               return {}
           token = await derive_service_token()
           return {"Authorization": f"Bearer {token.hex()}"}
   ```

#### Phase 2: Network Hardening (P1 — should have)

```
Effort: ~30 minutes
Files:  docker-compose.all.yaml, docker-compose.all.dstack.yaml
```

- Oracle binds API to `172.20.0.4` only (not 0.0.0.0) in dstack mode
- Remove oracle port mapping in dstack overlay (no external access)
- Neko doesn't need oracle access — consider separate network if more services join

#### Phase 3: AppAuth Contract Integration (P2 — nice to have)

```
Effort: ~1 day
Files:  contracts/src/AppAuth.sol, deployment script
```

- Deploy AppAuth contract on Base Sepolia
- Register compose hash at CVM deploy time
- KMS only derives keys for authorized compose hashes
- DiligenceRoom.sol can verify the TEE identity against AppAuth
- External auditors can verify what code had oracle access

### Sequence Diagram — Auth Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  dstack   │     │ delegate │     │  oracle  │
│   KMS     │     │          │     │          │
└────┬──────┘     └────┬─────┘     └────┬─────┘
     │                 │                │
     │◄── derive_key ──┤                │
     │    ("/service-  │                │
     │     auth")      │                │
     ├── key_bytes ───►│                │
     │                 │                │
     │                 │── POST /pin ──►│
     │                 │  Bearer: hmac  │
     │                 │                │
     │                 │                ├── derive_key ──►│
     │                 │                │◄── key_bytes ──│
     │                 │                │
     │                 │                ├── verify hmac
     │                 │                │   (same key,
     │                 │                │    same domain)
     │                 │                │
     │                 │◄── 200 OK ────┤
     │                 │   {pin: "..."}│
```

### Local Dev Bypass

In local dev (`DSTACK_ENABLED=false`), auth is skipped entirely. The oracle accepts all requests. This is safe because:
- Local dev runs on developer's machine (no multi-tenant threat)
- No dstack.sock available, so derive_key would fail
- Tests can run without TEE infrastructure

To test auth locally, use the dstack simulator (`/phala-simulator`):
```bash
# Start simulator
docker run -p 8090:8090 phalanetwork/dstack-simulator:latest

# Set env
export DSTACK_SIMULATOR_ENDPOINT=http://localhost:8090

# Both services will derive the same key from the simulator
```

## Open Questions

1. **Key rotation**: Should the derived key rotate? Currently it's static per compose hash. If the compose changes (code update), the key changes automatically. This may be sufficient.

2. **Rate limiting**: Should oracle rate-limit even authenticated requests? The delegate shouldn't make more than ~10 requests per deal. A rate limit of 100/min would catch runaway loops.

3. **Audit log**: Should oracle log all authenticated requests? Useful for post-mortem analysis of deal evaluations. Could write to a volume that's included in attestation.

4. **Mutual auth**: Does the delegate need to verify the oracle's identity? Currently unidirectional (delegate proves identity to oracle). If oracle is compromised, it could return fake pins. Mutual TLS from derived keys would solve this but adds complexity.

5. **Multi-CVM split**: If oracle and delegate eventually run on separate CVMs, Pattern 6 (GroupAuth / cross-attestation) would be needed instead of shared derive_key. Worth designing the auth interface to be swappable.

## What Can Wait

- **AppAuth contract** — governance for a system that doesn't run yet. Implement after the first successful E2E deal.
- **Mutual TLS** — single-CVM deployment means the network is trusted. Add if we split to multi-CVM.
- **Genesis transparency log** — nice for auditability but not blocking for the auth story.
- **Rate limiting** — add after the first real workload reveals actual request patterns.
