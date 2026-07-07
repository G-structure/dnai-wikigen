# Deployment Runbook

Last updated: 2026-03-17

This file records the live Base Sepolia contracts and the current Phala CVM state for the tinker delegate stack.

## Base Sepolia

### DiligenceRoom

- Contract: `DiligenceRoom`
- Address: `0xe51A3C5fd564c625C9D72D2283878Ab4296b3844`
- Network: Base Sepolia (`chainId = 84532`)
- BaseScan: `https://sepolia.basescan.org/address/0xe51A3C5fd564c625C9D72D2283878Ab4296b3844`
- Deployment tx: `0x9407f7989c11ac1161397c85aa41bf3752ebca8124e5ecb7fafe05c6dbd899e4`
- Deployment block: `38837040`
- Deployer / developer fee recipient: `0x111dB654eCD8756188e03746C1bcff74FD749791`
- Compiler: `solc 0.8.28`
- Optimizer runs: `200`
- Verification: passed on BaseScan
- Current on-chain `dealCount()`: `0`

#### Security changes made before deployment

The original escrow contract was not safe enough to deploy unchanged. The deployed version includes these hardening changes:

1. Settlement now uses pull payments.
   - `acceptDeal`, `rejectDeal`, and `expireDeal` credit balances into `pendingWithdrawals`.
   - Recipients withdraw via `withdraw()`.
   - A reverting seller, buyer, or developer can no longer brick settlement.

2. TEE result submission is budget-checked.
   - `submitResult()` now reverts with `ComputeCostOverBudget()` if `computeCost + fee > budgetCap`.
   - This prevents `rejectDeal()` and `expireDeal()` from becoming permanently uncallable.

3. Deal creation now validates critical inputs.
   - `expiry` must be in the future.
   - `artifactHash` must be non-zero.
   - `teeIdentity` must be non-zero.

#### Contract interface snapshot

- `createDeal(uint256 reservePrice, uint256 expiry, bytes32 artifactHash, address teeIdentity)`
- `fundDeal(uint256 dealId)` payable
- `submitResult(uint256 dealId, ScoreBand scoreBand, uint256 computeCost, bytes32 resultHash)`
- `acceptDeal(uint256 dealId, uint256 dealPayment)`
- `rejectDeal(uint256 dealId)`
- `expireDeal(uint256 dealId)`
- `withdraw()`
- `pendingWithdrawals(address account) -> uint256`
- `getDeal(uint256 dealId) -> Deal`

#### Test status at deploy time

- Command: `forge test --gas-report`
- Result: `39` tests passed, `0` failed
- Includes:
  - unit coverage for all lifecycle transitions
  - fuzz coverage for settlement conservation
  - adversarial test proving a reverting seller cannot block `acceptDeal`
  - budget safety test proving over-budget compute is rejected

### EmailOracleAuth

- Contract: `EmailOracleAuth`
- Address: `0xd21706E1AfF482F1d23664be5768ceaD63ccdBfF`
- Network: Base Sepolia (`chainId = 84532`)
- BaseScan: `https://sepolia.basescan.org/address/0xd21706E1AfF482F1d23664be5768ceaD63ccdBfF`
- Owner: `0x1804c8AB1F12E6bbf3894d4083f33e07309d1f38`
- Oracle upgrade delay: `172800` seconds (`2 days`)
- `allowAnyDevice()`: `true`
- `oracleCodeFrozen()`: `false`
- `consumerRegistryFrozen()`: `false`

#### Purpose

`EmailOracleAuth` governs two different trust domains:

1. Oracle boot authorization.
   - Which oracle compose hashes may boot and receive KMS material.

2. OTP consumer authorization.
   - Which consumer app IDs and compose hashes may request OTPs from the oracle.

#### Operational note

The oracle contract is still mutable. Before production freeze:

1. Register the final oracle compose hash.
2. Register the final approved consumer app ID and compose hash.
3. Call `freezeOracleCodeAuth()`.
4. Optionally call `freezeConsumerRegistry()`.

## Phala

### Current CVM

- CVM name: `tinker-email-oracle`
- CVM id: `cvm_j2kD1EZn`
- App id: `29d78795d77408a705d2c77c42d1bc10c59d0671`
- Status reported by Phala: `running`
- Compose hash: `97818b3dbac8227ea3016e26c16886083f2fe25592fc0f33900e037c6003acd6`
- Instance type: `tdx.medium`
- Node: `prod5`
- dstack OS: `0.5.7`
- Gateway base domain: `dstack-pha-prod5.phala.network`

### Current endpoints

- Oracle API: `https://29d78795d77408a705d2c77c42d1bc10c59d0671-8000.dstack-pha-prod5.phala.network`
- Delegate API: `https://29d78795d77408a705d2c77c42d1bc10c59d0671-8080.dstack-pha-prod5.phala.network`
- Chrome CDP: `https://29d78795d77408a705d2c77c42d1bc10c59d0671-9222.dstack-pha-prod5.phala.network`
- Neko UI: `https://29d78795d77408a705d2c77c42d1bc10c59d0671-52000.dstack-pha-prod5.phala.network`

### Current images

- Oracle image: `ttl.sh/therealwiki-tinker-oracle-20260313-8b76c1d@sha256:6d521ae4da405250adbab51a8597ac83fdff4addfe930921293ccadad6d12352`
- Delegate image: `ttl.sh/therealwiki-tinker-delegate-20260313-8b76c1d-r6@sha256:6563c94382f82dc43dfe4de1f615189c8c3a6806061bb366c0efd0403017e115`
- Delegate browser sidecar: `mcr.microsoft.com/playwright:v1.58.0-noble`

### Current live state

- Oracle API is live and healthy at the public `:8000` endpoint.
- The delegate stack now boots with registry images instead of local `build:` contexts.
- The delegate service no longer needs to crash the whole CVM if bootstrap fails; `/health` exposes runtime bootstrap status.

### Important current blocker

The remaining blocker is Tinker auth automation, not Phala deployment.

On March 17, 2026, direct tests showed:

1. A headed local Chrome session reaches the Tinker `magic-code` page with a `gmail.com` control.
2. The deployed delegate path, which currently uses a headless Playwright browser server, is blocked with:
   - `Access blocked, please contact support.`
3. The Tinker auth page now ships explicit bot-check machinery:
   - hidden `signals` / bot token handling in the server-rendered form
   - `Fingerprint`
   - `BotCheckClient`
   - `BotCheckTokenInput`

This means the previous assumption that `cock.email` alone explained the failure is stale. The email domain is not the primary blocker now; the deployed browser posture is.

### What remains to finish fully automatic bootstrap

1. Replace the current headless Playwright sidecar with a headed browser path that survives Phala packaging.
2. Re-validate signup against the live Tinker auth flow from inside the CVM.
3. Once signup succeeds, verify:
   - OTP retrieval from the email oracle
   - onboarding completion
   - API key creation and encrypted storage at `/data/tinker_api_key.enc`
4. Freeze docs around the new browser requirement and stop claiming `cock.email` alone is sufficient.

## Commands used

### Test and build

```bash
cd "⚙️/tinker-delegate/contracts"
set -a; . ../../../.env; set +a
forge build
forge test --gas-report
```

### Deploy DiligenceRoom

```bash
cd "⚙️/tinker-delegate/contracts"
set -a; . ../../../.env; set +a
forge script script/DiligenceRoom.s.sol \
  --rpc-url "$BASE_SEPOLIA_RPC_URL" \
  --account "$FOUNDRY_KEYSTORE_ACCOUNT" \
  --password "$FOUNDRY_PASSWORD" \
  --broadcast \
  --verify \
  --etherscan-api-key "$ETHERSCAN_API_KEY" \
  --slow \
  --non-interactive
```

### Useful verification reads

```bash
cast call 0xe51A3C5fd564c625C9D72D2283878Ab4296b3844 "developer()(address)" --rpc-url "$BASE_SEPOLIA_RPC_URL"
cast call 0xe51A3C5fd564c625C9D72D2283878Ab4296b3844 "dealCount()(uint256)" --rpc-url "$BASE_SEPOLIA_RPC_URL"

cast call 0xd21706E1AfF482F1d23664be5768ceaD63ccdBfF "owner()(address)" --rpc-url "$BASE_SEPOLIA_RPC_URL"
cast call 0xd21706E1AfF482F1d23664be5768ceaD63ccdBfF "ORACLE_UPGRADE_DELAY()(uint256)" --rpc-url "$BASE_SEPOLIA_RPC_URL"
cast call 0xd21706E1AfF482F1d23664be5768ceaD63ccdBfF "allowAnyDevice()(bool)" --rpc-url "$BASE_SEPOLIA_RPC_URL"
```
