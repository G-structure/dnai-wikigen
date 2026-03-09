# Wiki + Rob NDAI Hackathon Brief

> look at us finally getting around to building wikigen.me

A tactical brief for turning the NDAI paper into a strong, sponsor-aligned demo.

## Quick takeaways
- Build one crisp NDAI mechanism demo, not a generic agent platform.
- Use Phala Cloud / dstack for the TEE layer; do not self-host confidential infrastructure during a hackathon.
- Expose the paper's real control knobs in the product: buyer budget cap, seller reserve threshold, attestation, and bounded disclosure.
- If you need your own contract, Base Sepolia is the pragmatic path; Phala's Onchain KMS supports Ethereum or Base.
- Andrew Miller's repos are branch-heavy. Mine branches before assuming the default branch is the real work.

## Why this track is strong
Shape Rotator is a 2-week virtual hackathon focused on turning research papers into prototypes. The March 9-23, 2026 program lets builders choose from 14 IC3 papers, with paper authors presenting on day 1 and mentoring teams. Public materials also note a $10,000 prize pool and the possibility of being fast-tracked into a 14-week accelerator. Flashbots and Convent are listed among the partners, which makes a TEE-heavy, mechanism-design-heavy build unusually legible for this room. [1][2]
The important implication: judges are not looking for maximal infrastructure. They are looking for a clear translation of one paper into a believable product. NDAI is strong because the paper itself already contains a product-shaped mechanism: private information, bargaining, selective disclosure, AI agents, and TEEs. [3]
The best read on sponsor alignment is not gossip - it is the public source map. Flashbots' TEE materials and the dstack / Phala stack repeatedly emphasize attested execution, protected secrets, account delegation, and verifiable deployment. That is exactly the world NDAI lives in. [4][5][6][24]

## NDAI in plain English
The paper starts from the disclosure paradox. A seller has a valuable private idea or artifact, but the buyer has to see enough of it to value it. Once the buyer learns too much, the seller loses leverage and may be unable to get paid. In the no-protection baseline, that hold-up problem is so severe that the seller optimally discloses nothing. [3]
NDAI's move is to place the interaction inside Trusted Execution Environments and let AI agents bargain there. The seller can reveal information to a secure boundary rather than to the buyer directly. If the value of the information is below the mechanism's secure threshold, the paper shows full disclosure and investment can be sustained in equilibrium. If the information is too valuable for the security envelope, partial disclosure still improves outcomes. [3]
The paper also matters because it is honest about agent error. It explicitly recommends controls like a buyer budget cap and a seller-side acceptance threshold, and shows these make the mechanism more robust when the agents are noisy or imperfect. For the hackathon, that means your UI should surface these as first-class product knobs rather than burying them. [3]

## Recommended build: Attested Diligence Room
The main recommendation is an Attested Diligence Room for selling private technical information. Think: private code audit notes, a research memo, an exploitable bug report, an unreleased design, a dataset description, or a strategy document. The product goal is simple: let a buyer inspect enough to make a decision, while making the seller comfortable that disclosure only happens inside an attested boundary and only under explicit deal rules. [3][4][6]
A clean demo flow is:
- 1) Seller creates a room and uploads a private artifact or snapshot; sets a reserve price, an expiry, and a disclosure policy.
- 2) Buyer funds a small escrow and sets a max budget cap plus a query budget.
- 3) The app shows an attestation / verification page so both sides can see what code is actually running.
- 4) A buyer-side evaluator agent inside the TEE inspects the artifact and can only emit constrained outputs (for example: score bands, structured findings, a yes/no recommendation, or an offer within cap).
- 5) The seller threshold and buyer budget cap enforce the paper's robustness story.
- 6) If the buyer accepts, the payment path completes and the room reveals only the agreed output. If not, the session expires and the artifact never leaves the boundary.
This maps directly onto the paper and is easier to judge than a vague 'confidential agent marketplace'. [3]
One killer polish move: add a simple toggle that simulates buyer-agent error with and without a budget cap. That visual makes the paper feel real, because Figure 1 in the paper is specifically about robustness under error. [3]

## Technical stack: shortest path to something real
TEE layer: use Phala Cloud's managed dstack path. dstack is built around confidential containers / confidential VMs, workload identity, per-app key derivation, and attestation. Phala's docs and examples are explicitly designed to get Docker apps running inside a CVM quickly, including local simulation for development and a deploy path for real hosted instances. [4][6][7][11]
Verification layer: make verification user-visible. Phala documents a 'verify your application' flow centered on quote verification, reportData, compose-hash, and genuine Intel TDX hardware, plus separate platform / KMS verification. For judges, a clean verification page or verification button is part of the product, not back-office plumbing. [9][10]
Contract layer: if you want your own escrow contract, use Base Sepolia and keep the state machine minimal. Phala's Onchain KMS supports Ethereum or Base, and Andrew's repos already use forge / cast patterns that make Foundry a natural fit. For a hackathon, you do not need a fancy settlement system; you need a contract with obvious states such as Created, Evaluated, Accepted, Rejected, and Expired. [8][16][17]
Model layer: the simplest trust model is calling OpenAI or Anthropic from inside the TEE and being explicit about that boundary. The strongest showpiece version is using a TEE-protected gateway such as RedPill, which documents full-gateway TEE protection and per-request attestation. That is optional, not required. [26][27]
### Getting Base Sepolia ETH

**Option A: Andrew Miller's GitHub Faucet (zkTLS-verified, gasless)**

Contract: [`0x72cd70d28284dD215257f73e1C5aD8e28847215B`](https://sepolia.basescan.org/address/0x72cd70d28284dD215257f73e1C5aD8e28847215B) on Base Sepolia. Claims 0.001 ETH per GitHub user per 24 hours. No gas needed — you can claim via a GitHub Issue.

```bash
# 1. Fork the repo
gh repo fork amiller/github-zktls

# 2. Run the identity workflow (MUST use v1.0.3 tag or you get WrongCommit revert)
gh workflow run github-identity.yml --ref v1.0.3 \
  -f recipient_address=0xYOUR_ETH_ADDRESS \
  -f faucet_address=0x72cd70d28284dD215257f73e1C5aD8e28847215B

# 3. Download attestation bundle
gh run list --workflow=github-identity.yml
gh run download RUN_ID -n identity-proof

# 4. Generate ZK proof
docker run --rm -v $(pwd):/work zkproof generate /work/bundle.json /work/proof
```

Then either submit directly with `cast send` or use the **gasless path**: open an issue on `amiller/github-zktls` with title `[CLAIM]` and paste `proof/claim.json` in a ```json code block. A relayer submits the tx for you.

See full details: `🔬/amiller/github-zktls-1/docs/faucet.md`

**Option B: Standard faucets**
- Alchemy Base Sepolia faucet (requires free account)
- Coinbase Developer Platform faucet
- QuickNode Base Sepolia faucet

**Option C: Direct with `/cast-wallet`**
```bash
# Generate a wallet and import to Foundry keystore
# Then fund it from any faucet above
```

Stretch layer: GitHub-zkTLS, Teleport / oauth3, and OpenClaw-style patterns are optional spice. They are not the MVP. Use them only after the core NDAI mechanism works end to end. [17][18][19][21][22][23]

## What to read first
Tier 0 - Read before coding:
- NDAI paper. Focus on the model, the secure-threshold story, and the section on agent error. [3]
- Official dstack repo, official dstack examples, and the Phala overview / deploy / verify docs. This tells you what is actually easy vs hard. [4][6][7][9][10][11]

Tier 1 - Read for hacker leverage:
- amiller/dstack-tutorial for the 'DevProof / unruggable app' framing. [13]
- amiller/devproof-audits-guide because it tells you what outsiders should be able to verify about a TEE app. That is exactly what judges will ask. [15]
- amiller/devproof-apps-guide because it includes starter-kit patterns and deploy commands, including Base-oriented deployment paths. [16]
- amiller/dstack-examples, but do not stop at main. Prioritize branches such as oracle-demo, minecraft-demo, and any branch that looks like a live integration test. [14]

Tier 2 - Read for optional edge:
- amiller/github-zktls-1. This is useful if you want seller identity proofs, repo ownership proofs, or a verifiable pre-screening step. Important branches include sealed-box, env-confinement, groupauth, packed-inputs, email-login, and feature/prediction-market-oracle. [17]
- Account-Link / Teleport and oauth3-skill. These show how to delegate web2 account capabilities or secrets into a TEE without handing them to the agent in plaintext. [18][19]
- jameslbarnes/hermes as a concrete dstack deployment example with attestation and secret handling. [20]
- amiller/oauth3-openclaw and amiller/dstack-openclaw if you want to study human-approved secret use, policy enforcement, or self-attesting agent patterns. Relevant branches in oauth3-openclaw include feat/conseca-policy-engine, feat/phala-deploy-gate, feat/ses-compartment, and feat/tiktok-plugin. [21][22]
- amiller/skill-verifier if you want an 'inspection certificate' style stretch feature. [23]

High-signal rule: Andrew's GitHub is branch-heavy. The default branch is often only part of the story. [12][14][17][21]

## 72-hour execution plan
Hour 0-6: decide the exact artifact being sold (private memo, code report, etc.), write the deal states, and choose the narrowest possible output shape for the evaluator agent. Then fork an official dstack example and get the local simulator or fast deploy path running. [7][11]
Hour 6-24: build the room creation flow, private upload path, a stub evaluator inside the TEE, and a fake or stubbed escrow state machine. Do not touch optional identity proofs yet.
Hour 24-48: deploy to Phala Cloud, wire in real attestation / verification, and replace the stubbed escrow with a tiny Base Sepolia contract if needed. Add seller reserve threshold and buyer budget cap to the UI. [8][9][10]
Hour 48-72: polish the demo story. Add one visual that makes the economics legible - for example, an error slider that shows why the cap matters. Only after this should you consider GitHub-zkTLS, oauth3, or RedPill as stretch features. [3][17][18][26]

## How to pitch it
The winning sentence is: 'We turned the NDAI paper into an attested deal room for private technical information, where disclosure happens only inside a verifiable TEE and economic controls from the paper - reserve price, budget cap, and bounded disclosure - are exposed directly in the product.'
Good talking points for judges:
- This is not 'TEE for TEE's sake'; the TEE is the enforcement boundary for a mechanism-design problem in the paper. [3]
- The seller's reserve threshold and the buyer's budget cap are not random UX features; they come directly from the paper's robustness story about agent error. [3]
- We used the most practical currently-deployable privacy primitive for a hackathon. The paper itself discusses TEEs as the practical route today, with MPC / FHE / ZK-style techniques as complements rather than prerequisites. [3]
- dstack / Phala gives us a clean deployment and verification path that judges can actually inspect. [4][5][6][9][10]
If somebody asks 'why not just use FHE / ZK?', the best answer is: because the goal here is to ship the market mechanism now. The paper explicitly positions TEEs as the practical implementation route, and dstack gives you public attestation, key management, and governance hooks without needing to invent a brand-new cryptosystem first. [3][5][6]

## Local operating notes
Rob (and Wiki) should treat the Convent / Flashbots(x) orbit as a live operating environment, not just a networking list. The practical goal is to have a crisp live demo early, then use that artifact to get help and attention.
Friends to know: Andrew Miller, SxySyn, James B, Tina Zen, Dmarz, Vinny, Alexis, and Evan.
The highest-leverage posture is simple: show a running thing, ask one concrete technical question at a time, and keep the ask narrow. People are much more likely to help when they can react to a live artifact instead of an abstract vision.

## NDAI paper concepts -> product primitives
| Paper concept | Product primitive | Why it matters |
|---|---|---|
| Disclosure paradox | Confidential diligence room | Seller reveals to the TEE, not to the buyer directly. |
| Secure threshold (Phi) | Disclosure / query cap | Lets you explain why full vs partial disclosure is a product choice. |
| Bargaining share / price | Offer engine + reserve | Shows this is a market mechanism, not just a private chatbot. |
| Buyer error | Budget cap | Prevents runaway overpayment in bad model states. |
| Seller protection | Acceptance threshold | Stops lowball acceptance from bad agent outputs. |

## Source map
- [1] Encode Club - Shape Rotator Virtual Hackathon: https://www.encodeclub.com/programmes/shape-rotator-virtual-hackathon
- [2] Encode Club LinkedIn announcement (dates, partners, accelerator details): https://www.linkedin.com/posts/encode-club_announcing-shape-rotator-virtual-hackathon-activity-7427757784684879873-yeKP
- [3] Negotiating Disclosure Agreements with AI - arXiv:2502.07924: https://arxiv.org/abs/2502.07924
- [4] Dstack GitHub repository: https://github.com/Dstack-TEE/dstack
- [5] dstack paper - arXiv:2509.11555: https://arxiv.org/abs/2509.11555
- [6] Phala docs - dstack overview: https://docs.phala.com/dstack/overview
- [7] Phala docs - deploy your first CVM / Cloud deploy: https://docs.phala.com/phala-cloud/phala-cloud-cli/start-from-cloud-cli
- [8] Phala docs - Cloud vs Onchain KMS (Ethereum or Base): https://docs.phala.com/phala-cloud/key-management/cloud-vs-onchain-kms
- [9] Phala docs - Verify your application: https://docs.phala.com/phala-cloud/attestation/verify-your-application
- [10] Phala docs - Verify the platform / KMS: https://docs.phala.com/phala-cloud/attestation/verify-the-platform
- [11] Official dstack examples: https://github.com/Dstack-TEE/dstack-examples
- [12] Andrew Miller GitHub profile: https://github.com/amiller
- [13] amiller/dstack-tutorial: https://github.com/amiller/dstack-tutorial
- [14] amiller/dstack-examples: https://github.com/amiller/dstack-examples
- [15] amiller/devproof-audits-guide: https://github.com/amiller/devproof-audits-guide
- [16] amiller/devproof-apps-guide: https://github.com/amiller/devproof-apps-guide
- [17] amiller/github-zktls-1: https://github.com/amiller/github-zktls-1
- [18] Account-Link / Teleport repo: https://github.com/Account-Link/teleport-gramine-rs
- [19] Account-Link / oauth3-skill: https://github.com/Account-Link/oauth3-skill
- [20] jameslbarnes/hermes: https://github.com/jameslbarnes/hermes
- [21] amiller/oauth3-openclaw: https://github.com/amiller/oauth3-openclaw
- [22] amiller/dstack-openclaw: https://github.com/amiller/dstack-openclaw
- [23] amiller/skill-verifier: https://github.com/amiller/skill-verifier
- [24] Flashbots Collective - TEE Wiki: https://collective.flashbots.net/t/tee-wiki/2019
- [25] Flashbots Collective - Flashwares viii: dstack meets on-chain PCCS and ZK SNARK proofs of attestations: https://collective.flashbots.net/t/flashwares-viii-dstack-meets-on-chain-pccs-and-zk-snark-proofs-of-attestations/3877
- [26] RedPill AI - TEE-protected gateway: https://docs.redpill.ai/privacy/tee-protection
- [27] RedPill AI - confidential AI FAQ / attestation: https://docs.redpill.ai/privacy/confidential-ai/faqs
