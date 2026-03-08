# NDAI: Non-Disclosure through AI and Trusted Execution Environments

## Paper Metadata
- **arXiv:** 2502.07924
- **Date:** February 11, 2025
- **Authors:** Matt Stephenson (Pantera Capital), Andrew Miller (Teleport, Flashbots), Xyn Sun, Bhargav Annem (Caltech), Rohan Parikh (Nous Research, University of Chicago Booth)
- **Categories:** Theoretical Economics (econ.TH), Artificial Intelligence (cs.AI)

---

## Abstract

The paper addresses a fundamental economic challenge: inventors must reveal innovation details to secure funding, yet disclosure risks expropriation. The authors develop a game-theoretic model where a seller (inventor) and buyer (investor) bargain over information goods under hold-up threats. They propose using trusted execution environments (TEEs) combined with AI agents to eliminate this disclosure-expropriation paradox. When the invention value stays within TEE security thresholds, full disclosure becomes feasible with efficient transfers. Even when value exceeds security limits, partial disclosure improves outcomes compared to baseline scenarios. The framework remains robust when agents make random errors—budget caps and acceptance thresholds preserve efficiency gains across moderate error rates.

---

## 1. Introduction: The Disclosure Paradox

### 1.1 Why Patents and NDAs Often Fail

The paper opens with John Harrison's historical struggle to claim compensation for inventing the Marine Chronometer. Despite revolutionizing navigation, Harrison faced decades of bureaucratic obstruction after revealing his design. This illustrates Arrow (1971) and Nelson (1959)'s recognized tension: "an inventor must reveal information to capture its economic value but, by revealing it, risks losing the ability to appropriate it."

Legal protections like NDAs and patents constitute ex post enforcement—costly, uncertain, and imperfect. Monitoring intangible knowledge use remains difficult. The authors propose **ex interim enforcement** through TEEs: conditional disclosure prevents unauthorized use from arising beforehand, eliminating extensive monitoring burdens that plague traditional approaches.

### 1.2 Background and Related Work

The research builds on three literature streams:

1. **Information disclosure in contracting** (Crawford & Sobel, 1982; Okuno-Fujiwara, 1991)
2. **Hold-up problems and incomplete contracts** (Hart & Moore, 1988; Aghion & Howitt, 1992)
3. **Cryptographic and hardware-based solutions** departing from traditional legal instruments

The authors note connections to blockchain MEV (maximal extractable value) literature, where order flow information enables front-running—a parallel disclosure problem in decentralized systems.

#### Key Contributions

Five main contributions are outlined:

1. **Formalizing the disclosure-expropriation trade-off** through game-theoretic modeling
2. **TEE-based mechanism** resolving hold-up under sufficient security
3. **Security risk formalization** using threshold encryption, establishing scope conditions for protecting high-value secrets
4. **Robustness analysis** showing simple budget caps and acceptance thresholds preserve gains despite imperfect agents
5. **Policy implications** demonstrating how cryptographic safeguards can substitute for costly legal enforcement

### 1.3 Model Framework and Roadmap

The model assumes two parties must choose disclosure levels before learning if gains from trade exist. Higher disclosure increases trade probability but raises appropriation risk. The TEE approach reduces expropriation risk through secure environments rather than contractual solutions alone, making disclosure conditional on agreement.

**Paper Structure:**
- Section 2: Baseline disclosure game highlighting information withholding absent protective mechanisms
- Section 3: TEE setting with AI agents restoring efficient disclosure
- Section 4: Equilibrium characterization under TEE arrangement
- Section 5: Realistic AI agent error analysis
- Section 6: Policy implications and conclusions

---

## 2. A Baseline Model of Innovation Disclosure

### 2.1 Setup and Payoffs

#### Types and Disclosure

A seller possesses a divisible information good with value ω drawn uniformly from [0,1). The buyer cannot observe ω directly and relies on seller disclosure ω̂ ≤ ω. Without disclosure, the buyer lacks information to invest.

#### Outside Options

With no disclosure (ω̂ = 0), the buyer receives zero payoff. The seller obtains α₀ω, where α₀ ∈ (0,1], representing residual value from independent commercialization.

#### Payoffs from Trade vs. Expropriation

**If buyer invests** (paying price P):
- Seller: uₛ(ω; Invest) = P + α₀(ω - ω̂)
- Buyer: u_B(ω; Invest) = ω̂ - P

**If buyer expropriates** disclosed portion:
- Seller: uₛ(ω; Expropriate) = α₀(ω - ω̂)
- Buyer: u_B(ω; Expropriate) = ω̂

### 2.2 The Breakdown Under Hold-Up

The equilibrium is straightforward: once the seller discloses any ω̂ > 0, the buyer can expropriate without paying. Anticipating this, sellers withhold disclosure (ω̂ = 0), resulting in:
- Seller payoff: α₀ω
- Buyer payoff: 0

This no-disclosure equilibrium eliminates potential gains from trade—the fundamental hold-up problem Arrow identified.

---

## 3. Building an Ironclad NDA: Trusted Execution and AI Agents

### 3.1 AI Delegation via Secure Hardware

Each player i delegates decisions to an agent A_i—a function mapping private inputs x_i, messages from other agents m_{j\i}, and error terms ε_i to actions a_i. Agents aim to maximize their principal's payoff subject to stochasticity captured by ε_i.

#### Secure Execution Environment

The agents run inside a trusted execution environment (TEE)—implemented via hardware like Intel SGX. Real TEEs permit arbitrary code execution while enforcing data secrecy.

#### TEE Functionality

All agents {A_i} combine into a single secure function **T** that:
1. Collects private inputs (x₁,...,xₙ) from n players
2. Mediates inter-agent messaging
3. Outputs final actions (a₁,...,aₙ)

If fully secure, no player learns about others' private inputs beyond final outputs.

### 3.2 Provisioning the TEE

To protect against TEE breaches, players use n distinct TEEs from different providers with (k,n)-threshold encryption. No subset smaller than k can reconstruct secret ω; breach detection is probabilistic.

#### Scope Conditions for Security

Let p = breach detection probability and C = breach penalty. Expected colluder gain from size-k expropriation is:

(1 - p^k)ω/k (benefit) vs. p^k·C (penalty)

This yields a security threshold:

**ω ≤ Φ(k,p,C) = [k(1-(1-p)^k)]/[(1-p)^k] · C**

A secret is safe if ω ≤ Φ. Larger k, higher p, or higher C increase maximum securable value.

---

## 4. Perfect Agents, Perfect Security: The Main Theorem

### 4.1 Mechanism and Timeline

1. Nature draws ω ~ U(0,1), observed only by seller
2. Both parties decide whether to delegate to TEE (else revert to baseline §2.2)
3. Buyer endows agent A_B with budget P̄; seller discloses ω̂ ≤ Φ to its agent
4. Inside TEE, agents bargain over ω̂ split: A_S reveals ω to A_B; they negotiate; A_B offers payment P̂ < P̄ (accept) or exits; A_S accepts or rejects
5. On mutual acceptance, ω transfers to buyer and P to seller; on exit, TEE deletes session

### 4.2 TEE Equilibrium with Congruent Agents

#### Bargaining Setup

Inside the TEE, agents solve a symmetric Nash bargaining problem over ω̂ split:

max_{u_S,u_B} (u_S - α₀ω̂) × (u_B - 0)

subject to: u_S + u_B = ω̂, u_S ≥ α₀ω̂, u_B ≥ 0

Nash bargaining solution yields:
- u*_S = α₀ω̂ + ½(ω̂ - α₀ω̂)
- u*_B = ½(ω̂ - α₀ω̂)

The seller captures fraction θ = (1 + α₀)/2 of ω̂.

#### Buyer's Budget Choice

Maximum securable disclosure is ω̂ = min{ω, Φ}. Budget should be:
**P̄ = min{ω, Φ}** to cover largest possible deal.

#### Seller's Disclosure Choice

Since seller utility increases with disclosure (bounded by Φ), equilibrium disclosure is:
**∀i: ω̂ᵢ = min{ωᵢ, Φ}**

### Theorem 1: TEE Mitigates Hold-Up

**Under TEE arrangement with perfectly aligned agents and security ω ≤ Φ:**
- Unique equilibrium: full disclosure (ω̂ = ω) and investment at P = θω
- Both parties strictly prefer this to no-TEE baseline (α₀ω, 0)

**Intuition:** The TEE prevents misappropriation, enabling the seller's agent to freely disclose ω. The buyer's agent then pays P = θω, accepted because it meets the seller's threshold. Both strictly benefit versus the expropriation-threatened baseline. No profitable deviations exist.

**For ω > Φ:** Seller discloses only Φ, earning θΦ > α₀ω (partial mitigation but not full elimination of hold-up).

---

## 5. Robustness to Agent Errors: How Good Do These Agents Need to Be?

Real AI agents are imperfect. The framework remains robust when agents make random errors if mechanisms constrain downside risk. Budget caps prevent unbounded overpayment; acceptance thresholds reject insufficient offers.

### Illustrative Example

Suppose A_B aims to pay P(ω) = θω but incurs random error e_b (mean zero). If e_b is sufficiently negative, the offered payment falls below θω, triggering rejection and no trade. Positive errors are capped at budget P̄. Over many realizations:

**ΠB = (baseline payoff) - (loss from underpayment rejections) + (budget-cap savings)**

Three regions emerge:
1. **No-Trade Region** (e_b < 0): seller rejects low offers
2. **Under-Budget Region** (0 ≤ e_b ≤ θ - θω): payment follows formula exactly
3. **Budget-Capped Region** (θ(1-ω) < e_b ≤ 2θ): payment capped at θ

### Corollary 1: Robustness to Agent Errors

Positive error thresholds (E^max_s, E^max_b) exist below which each player's ex ante payoff under the TEE mechanism exceeds their baseline (no-TEE) payoff. The mechanism remains robust across moderate error magnitudes.

**Figure 1** illustrates: with θ = 0.6, the buyer's payoff without budget cap crosses zero at E_b = 0.4; with a cap, it remains positive until E_b = 0.6—budget caps extend error tolerance by 50%.

### Key Implication

Even substantial agent deviations preserve TEE arrangement benefits for reasonable error rates. Simple design features make the mechanism resilient to imperfect AI.

---

## 6. Conclusion and Policy Implications

### 6.1 Policy Recommendations

**Three main policy opportunities emerge:**

1. **Promote secure hardware adoption**: Governments could incentivize broader TEE deployment through standards certification and research funding.

2. **Support secure collaboration infrastructure**: Public institutions could provide/subsidize TEE platforms for safer partnerships between inventors, investors, and R&D labs, accelerating technology diffusion.

3. **Clarify liability frameworks**: Where TEEs lack full reliability, stronger breach liability rules complement hardware solutions, offering robust protection without stifling innovation.

**Central takeaway:** Cryptographic/hardware solutions powerfully supplement legal frameworks, transforming disclosure "from a perilous gamble to a routine, secure transaction," addressing Arrow's information paradox.

### 6.2 Limitations and Extensions

**Key limitations:**

1. **Hardware trust assumptions**: Assumes TEEs are fully secure; side-channel attacks could undermine secrecy. Real implementations need supplementary measures.

2. **Agent error correlation**: Model treats agent errors as independent. Systematic errors on complex inventions might require re-examination.

3. **Adoption frictions**: Institutional inertia, user mistrust of "black-box" solutions, or high costs could slow real-world TEE deployment.

Future work should incorporate these frictions and explore repeated interactions, reputation effects, and multi-buyer competition.

### 6.3 Summary

The paper demonstrates that trusted execution environments combined with AI agents can restore efficient innovation disclosure. By delegating decision-making to secure programs verifying invention quality without unconditional revelation, sellers confidentially disclose, extract fair compensation, and avoid hold-up. Robustness to agent errors—via budget caps and acceptance thresholds—means the mechanism preserves core benefits even with imperfect automation.

This framework provides an "ironclad NDA" substituting cryptographic assurances for uncertain legal enforcement. As trusted hardware and AI advance, a new paradigm of secure information exchange becomes feasible, expanding innovation frontiers without expropriation threats.

---

## Appendices

### Appendix A: Alternate Cryptographic Techniques

#### A.1 Partial Revelation Using Zero-Knowledge Proofs (ZKP) or Fully Homomorphic Encryption (FHE)

These primitives permit proving specific properties without full disclosure. However, two drawbacks emerge:

**Adverse Selection:** Buyers cannot know all relevant properties they should verify. The authors note: "intuitively, knowing x itself (e.g. if it is an elephant or a forklift) better enables a buyer to home in on the relevant properties to be proven."

**Externalities from Partial Revelation:** Even knowing a property holds becomes valuable information. Historical examples (Manhattan Project nuclear enrichment) show that achieving specific thresholds guided competitors. Partial revelation risks leaking strategic information.

#### A.2 Full Revelation Using Secure Multi-Party Computation (MPC) or Indistinguishability Obfuscation (iO)

**Secure Multi-Party Computation:** Uses threshold signatures where information splits across multiple signers; no single party can expropriate. Requires managing collusion risk and threshold-signer bargaining power.

**Indistinguishability Obfuscation:** Theoretically perfect—would allow agents to operate within obfuscated programs without leaking properties. However, iO remains largely theoretical today, lacking efficient practical constructions. TEEs offer superior practicality.

**Conclusion:** TEEs combine hardware-enforced security guarantees, market availability (Intel SGX), and straightforward all-or-nothing payoff enforcement, making them conceptually and practically superior to alternatives.

### Appendix B: Strategic Subtleties

#### B.1 Errors in Surplus Split

Agents could achieve full surplus but misdistribute payment (P̃ ≠ P*(ω̂)). Such errors matter only conditional on successful trade and remain second-order for determining whether TEE dominates baseline—both parties tolerate such errors as long as total surplus is preserved.

#### B.2 Budget Constraints as Commitment

Budget constraints can function as credible commitment devices. If a buyer agent's budget is sufficiently lower than the Nash bargaining split, it prevents the seller from capturing full bargaining surplus. However, this works only under specific conditions where α₀ω̂ < budget, and requires careful distribution analysis to verify seller participation remains incentive-compatible.

#### B.3 Efficient Overpayment in the TEE

When the buyer adds a constant buffer d > 0 to offset negative errors (P̂(ω) = θω + d), two competing effects emerge:

1. **Gain from newly accepted deals**: Buffer d creates acceptance region [−d, 0) previously rejected, generating gain ≈ (1−θ)d/(8θ)

2. **Cost from overpayment in pre-accepted region**: Extra payment d in region [0, θ−θω] costs ≈ d/8

Net derivative: ∂ΠB/∂d|_{d=0} = (1−2θ)/(8θ)

This is positive when θ < 1/2, indicating overpayment buffers improve buyer surplus when the seller holds sufficient bargaining power.

### Appendix C: Derived Equilibrium Under Agent Errors

#### C.1 Seller's Disclosure Error

The seller's agent A_S receives full ω but may underdisclose due to execution error ε_S ≥ 0 (cannot disclose more than possessed). Strategic underdisclosure never occurs because it reduces bargaining surplus and the seller's payoff. Disclosed value: ω̃ = ω − ε_S.

**Conclusion:** Disclosure errors reduce surplus but don't affect seller incentive to use the TEE. Errors treated as purely execution-based.

#### C.2 Buyer's Overpayment Error

The buyer's agent aims to pay P̂(ω) = θω but incurs error e_b ~ U[−E_b, E_b]. Trading occurs only when e_b ≥ 0 (otherwise seller rejects underpayment).

**Three regions:**
1. **No-Trade Region** (e_b < 0): u_B = 0
2. **Under-Budget** (0 ≤ e_b ≤ θ−θω): u_B = ω − (θω + e_b)
3. **Budget-Capped** (θ−θω < e_b ≤ E_b): u_B = ω − θ (payment capped)

**Maximum Error Threshold:** There exists E^max_b such that ΠB remains positive above baseline when E_b < E^max_b. Budget caps expand this tolerance range.

#### C.3 Summary of Agent Error Impact

Even with substantial agent imprecision, budget constraints and acceptance thresholds preserve efficiency gains. The mechanism remains strictly superior to baseline across moderate error ranges, suggesting that imperfect AI systems suffice for practical implementation.

### Appendix D: Extended Model of TEE Security

#### D.1 Back-of-the-Envelope Estimate for Maximum Securable Value

The framework models security using threshold encryption across k distinct TEE providers. For realistic parameters:

- **Detection probability p**: Higher p increases Φ (stronger security)
- **Breach penalty C**: Reflects financial/reputational consequences; larger C increases Φ
- **Threshold k**: More providers increase Φ but raise coordination costs
- **Maximum secure value Φ**: Scales approximately as Φ ∝ p^k · C under typical settings

Empirical security analyses suggest TEE arrangements can protect innovations worth millions in value under plausible parameter choices, making the approach practical for substantial innovation transactions.

---

## References

- Arrow (1971, 1972) — Information economics
- Nelson (1959) — Innovation disclosure
- Hart & Moore (1988) — Incomplete contracts
- Aghion & Howitt (1992) — Growth theory
- Crawford & Sobel (1982) — Strategic information transmission
- Okuno-Fujiwara (1991) — Disclosure games
- Anton & Yao (1994, 2002) — Innovation disclosure
- Scotchmer (1999) — Innovation incentives
- Morgan (2015), Contigiani & Hsu (2019) — IP strategy
- Daian et al. (2020), Roughgarden (2020), Capponi et al. (2023) — Blockchain/MEV
- Costan & Devadas (2016) — Trusted execution environments
