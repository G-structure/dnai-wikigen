# Contextual Agent Security: A Policy for Every Purpose (ConSECA)

## Paper Metadata
- **arXiv:** 2501.17070
- **Date:** April 17, 2025 (v3)
- **Authors:** Lillian Tsai (Google), Eugene Bagdasarian (Google)
- **Venue:** Workshop on Hot Topics in Operating Systems (HotOS '25), May 14–16, 2025
- **Categories:** Cryptography and Security (cs.CR)

---

## Abstract

The paper argues that "judging an action's safety requires knowledge of the context in which the action takes place." As artificial agents gain broader capabilities across multiple tasks, security frameworks must adapt beyond static policies. The authors introduce **Conseca** (Contextual Agent Security), a framework generating "just-in-time, contextual, and human-verifiable security policies" for generalist agent systems.

---

## 1. Introduction

The authors observe that conventional security systems rely on manually-specified contexts or no context at all, creating problems: policies can be overly restrictive or permissive, and writing comprehensive rules is challenging. With generalist AI agents handling diverse tasks, "as the scale of contexts encountered by a system increases, so must the granularity of policies."

### Key Contributions:

1. A call for research on security mechanisms scaling to unknown tasks and contexts for general-purpose agents
2. Conseca framework using generated but deterministically-enforced policies tailored to specific purposes and trusted context
3. A proof-of-concept prototype integrated with a Linux computer-use agent

---

## 2. Background and Threat Model

### System Architecture

Conseca abstracts agents into two components:
- **Planner:** Processes user requests and outputs actions (e.g., bash commands)
- **Executor:** Runs actions and interfaces with external tools

The context of a user request includes all information relevant to completing their task—usernames, file contents, job descriptions, and backup locations.

### 2.1 Threat Model

The threat model assumes an unrestricted agent might perform harmful actions through mistakes or adversarial attacks (such as prompt injection). Specifically: "an attacker could send the user a phishing email which contains a script, and the agent might later be tricked into executing the script when reading the email contents."

The framework trusts some context (timestamps) but treats other context as untrusted (third-party emails). The agent aims to execute actions aligned with user expectations while working toward the requested goal, potentially requiring untrusted context for certain operations.

---

## 3. Design

Conseca performs two primary functions:

1. **Policy Generation:** Accepts task requests and trusted context, producing task- and context-specific security policies
2. **Policy Enforcement:** Provides feedback on whether proposed actions satisfy the policy

### 3.1 Trusted Context

"Developers specify what context to trust (typically context not susceptible to potential attackers); alternatively, Conseca could ask users to set coarse-grained trusted context boundaries." Trusting more context improves policy accuracy but increases compromise risk.

### 3.2 Contextual Security Policies

The policy generator outputs a policy: "a set of constraints in a declarative language on the various tool APIs, and human-readable rationales for the constraints." For example, a filesystem policy constraint might be `rm "/tmp/.*"` with the rationale "only remove temporary files when organizing."

The framework leverages in-context learning—"prompting the LLM with a 'golden' set of example policies to demonstrate what the model should output"—to improve policy quality.

Developers may require users to approve policies before execution. Policies are logged for later audit and verification.

### 3.3 Deterministic Policy Enforcement

"Given a policy and a proposed action, the policy enforcer checks whether the action lies within the policy's set of allowed actions by deterministically evaluating policy constraints over the proposed action."

Key separation: **Policy drafting uses an LLM. Policy enforcement does not.** Enforcement is purely deterministic regex/constraint matching.

### 3.4 Security Discussion

Conseca's guarantees depend on security policy strength. Two fundamental limitations:

1. Policies depend on understanding user preferences, social norms, and task requirements
2. Limited trusted context restricts ability to predict data-dependent actions

---

## 4. Proof-of-Concept

### 4.1 The Conseca Prototype

Implementation uses Python for a Linux machine with agents accessing:
- **Filesystem tool:** POSIX filesystem API
- **File processing tool:** Commands like find and sed
- **Email tool:** Read, send, delete, categorize emails with attachments

**Conseca API:**
- `set_policy(task, trusted_ctxt) -> Policy`
- `is_allowed(cmd, policy) -> (bool, str) #rationale`

A Policy maps API calls to constraints including: (i) whether the call should execute in context, (ii) a boolean constraint on arguments, and (iii) human-readable rationales.

**Example Policy Output:**

For the task "Get unread emails related to work and respond to any that are urgent":
- **send_email:** Can Execute: True; Args: `re.search(r'alice', $1) ∧ re.search(r'^.*@work\.com', $2) ∧ re.search(r'.*urgent.*', $3)` with rationale explaining sender, recipient, and subject constraints
- **delete_email:** Can Execute: False with rationale "We are not deleting any emails in this task"

#### Trusted Context
Developers define trusted context including: email categories and addresses, filesystem directory structure (names), username, time, and date.

#### Agent Integration
After policy generation, the agent invokes `is_allowed` for each command. Denied commands and rationales return to the planner, appended to its prompt. Continuous failures (10+) cause the agent to return "could not complete."

---

## 5. Case Studies

### Setup

Experiments on Debian Linux with Gemini 1.5 Pro. The filesystem initializes with 10 users (including admin) and approximately 10 files per folder per user. Twenty tasks involve filesystem and email operations requiring subjective judgment and multiple tool calls.

### Preliminary Results

| Policy | Tasks Completed | Inappropriate Actions Denied? |
|--------|-----------------|-------------------------------|
| None | 14.0/20 | No |
| Static Permissive | 12.2/20 | No |
| Static Restrictive | 0.0/20 | Yes |
| **Conseca** | **12.0/20** | **Yes** |

An unrestricted agent completed 70% of tasks. Conseca achieved 60% completion, matching permissive policies while preventing inappropriate actions. Static restrictive policies completed zero tasks.

### Inappropriate Actions Demonstration

When an email requests forwarding security vulnerability emails, an unrestricted agent forwards inappropriately, even for non-urgent tasks. "An agent run with Conseca denies forwarding for all tasks other than 'perform the tasks in urgent emails'." Conseca maintained higher utility than restrictive policies while preventing misaligned actions.

---

## 6. Related Work

### Prompt Injection Attacks and Defenses

Detection and mitigation approaches remain susceptible to untrusted context attacks. Some systems use dual-LLM patterns isolating planners; CaMeL strengthens this with capability-based policies. Conseca isolates policy generation rather than planning, "providing full context for the planner and requiring few changes to existing agents' planner designs."

### Context-Aware AI

Conseca uses models understanding behavioral norms and operates in the contextual integrity (CI) framework. "Conseca follows in the spirit of CI, but enforces contextually appropriate actions (in addition to contextually appropriate data flows) in order to prevent harm."

### Traditional Application Security

Conseca enables "finer-grained access controls and capability restrictions." Mobile permissions offer examples of context-sensitive control. "Agents serve even broader purposes than a mobile app, making it difficult to rely on users to manage permissions for every task."

---

## 7. Discussion

Research directions include:

**Improving Contextual Policies:** User interaction for overrides, automated verification mapping rationales to constraints, sanitized output expanding trusted context.

**Trajectory Constraints:** "Conseca's policies currently check individual actions, regardless of what actions came prior." Multi-action policies could prevent unintended compositions.

**Efficiency:** LLM-based policy generation adds per-task overhead. Distillation and caching pre-generated policies for common contexts could reduce cost.

**Non-LLM Approaches:** Combining dynamic policies with manual policies and user confirmation for high-risk scenarios.

---

## 8. Conclusion

"Conseca imagines an emerging world in which agents perform human-like tasks, serving different purposes and commanded by unstructured inputs." Security systems must adapt beyond static encoding. More research into contextual agent security—safely leveraging the power of context to choose and judge actions—can help ensure readiness for such agents when they emerge.
