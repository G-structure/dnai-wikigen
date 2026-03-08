# Dstack: A Zero Trust Framework for Confidential Containers

## Paper Metadata
- **arXiv:** 2509.11555
- **Date:** September 15, 2025
- **Authors:** Shunfan Zhou, Kevin Wang, Hang Yin (Phala Network)
- **Categories:** Cryptography and Security (cs.CR), Artificial Intelligence (cs.AI)

---

## Abstract

Web3 applications require execution platforms maintaining confidentiality and integrity without centralized trust authorities. While Trusted Execution Environments (TEEs) show promise for confidential computing, current implementations have significant limitations in Web3 contexts, particularly regarding security reliability, censorship resistance, and vendor independence.

This paper introduces dstack, a comprehensive framework transforming raw TEE technology into a genuine Zero Trust platform through three key innovations:

1. **Portable Confidential Containers**: Enable seamless workload migration across heterogeneous TEE environments while preserving security guarantees
2. **Decentralized Code Management**: Leverage smart contracts for transparent TEE application governance
3. **Verifiable Domain Management**: Ensure secure, verifiable application identity without centralized authorities

Implementation utilizes three core components (dstack-OS, dstack-KMS, dstack-Gateway) demonstrating how to achieve both VM-level TEE performance advantages and trustless Web3 guarantees.

---

## 1. Introduction

### Context and Motivation

Web3 represents a fundamental paradigm shift in digital trust models, transitioning from centralized developer control to decentralized governance. Unlike Web2 systems where developers maintain administrative privileges, Web3 embraces "Code is Law"—deployed code operates autonomously, independent of external control.

This transformation demands execution platforms maintaining confidentiality and integrity without relying on centralized trust authorities. Figure 1 illustrates this evolution: Web2 systems retain developer control through proprietary applications on centralized servers; Web3 introduces smart contracts as trustless execution via decentralized platforms where administrators cannot alter program execution post-deployment.

### Zero Trust Platform Requirements

The paper identifies four essential principles for Zero Trust platforms:

**Code is Law**:
- Application logic cannot change unexpectedly after deployment
- Code lifecycle management (deployment, upgrades, deletion) follows predefined governance rules

**Censorship Resistance**:
- User data remains beyond single-entity control
- Data availability is protected against denial-of-service attacks

**Full Chain of Trust**:
- Users can verify application aspects comprehensively: network configuration, application identity, code logic, underlying hardware, execution environment

**Assume Breach**:
- Platform operates assuming compromises will occur
- Implements mechanisms for damage containment, rapid recovery, data exposure minimization

### Current TEE Limitations

While VM-level TEE solutions (Intel TDX, AMD SEV) offer substantial performance improvements and developer-friendly interfaces for Web3, significant gaps remain:

**Security Reliability**: Recent TEE vulnerabilities raise concerns about effectiveness as trust anchors. Persistent side-channel attacks undermine confidence for high-value Web3 applications where single compromises could cause catastrophic data exposure.

**Censorship Vulnerability**: Conventional encryption schemes bind keys to specific hardware instances, creating single points of failure. Centralized hardware manufacturers become censorship vectors, contradicting censorship resistance principles.

**Incomplete Verifiability**: TEEs provide Remote Attestation for application/hardware identity verification but fail delivering comprehensive chain of trust. Users lack guarantees programs process data as expected or cannot be modified without authorization.

**Unrestricted Application Lifecycle Control**: Existing TEE platforms lack robust mechanisms preventing developer updates from benign to malicious versions. Without decentralized code management, users cannot verify application upgrades follow agreed governance.

### Dstack Innovation Summary

**Portable Confidential Container**: Architecture enables seamless confidential workload migration across different TEE instances and vendors, reducing vendor lock-in while maintaining robust security through hardware abstraction and state continuity.

**Decentralized Code Management**: Comprehensive governance framework leveraging smart contracts for transparent TEE application management, ensuring verifiable deployment/upgrade processes with immutable audit trails.

**Verifiable Domain Management**: Novel certificate management approach enabling confidential containers to exclusively control domains, providing native HTTPS support without centralized authorities or client software modifications.

### Core Components

**dstack-OS**: Hardware abstraction layer with minimized operating system image, eliminating underlying TEE hardware differences while reducing attack surface. Provides consistent, secure runtime across diverse TEE implementations.

**dstack-KMS**: Blockchain-controlled key management service replacing hardware-based encryption schemes with independent secret generation/management. Enables secure data migration across TEE instances and supports key rotation for forward/backward data secrecy.

**dstack-Ingress and dstack-Gateway**: TEE-controlled domain management systems—Ingress enables custom domains with minimal integration; Gateway offers pre-registered wildcard domains requiring no application code changes.

---

## 2. Background and Related Work

### 2.1 Fundamentals of Trusted Execution Environments

TEEs represent secure processor areas guaranteeing code and data confidentiality and integrity protection. Modern implementations fall into two categories:

**Enclave-Based Solutions** (e.g., Intel SGX): Provide fine-grained process-level isolation

**VM-Based Solutions** (e.g., Intel TDX, AMD SEV-SNP): Secure entire virtual machines, offering superior compatibility with existing cloud infrastructure and development practices

Security guarantees derive from:
- **Hardware isolation**: Privileged software (OS, hypervisor) cannot access protected memory regions
- **Remote attestation**: Third parties verify TEE environment integrity and application software, establishing trust chains from hardware to application

However, traditional approaches create hardware dependencies limiting portability and introducing centralization risks.

### 2.2 Evolution of Confidential Computing in Cloud Infrastructure

Major providers (Azure Confidential Computing, Google Cloud Confidential Computing) adopt TEE solutions leveraging VM-level implementations for superior performance and virtualization compatibility.

However, current implementations face critical limitations in Web3 application contexts. Traditional cloud-based confidential computing assumes centralized trust models where cloud providers maintain significant infrastructure control. This conflicts with Web3's fundamental trustless and decentralized operation requirements.

### 2.3 Zero Trust Architecture Principles

Zero Trust Architecture (ZTA) represents a crucial security paradigm assuming no implicit component trust regardless of location or ownership. Web3 ZTA extension requires:

- Continuous hardware and software component verification
- Cryptographic correct-execution proof
- Decentralized governance and control mechanisms
- Minimal hardware manufacturer trust requirements

### 2.4 Current Web3 Infrastructure Security Approaches

Projects like Secret Network and Oasis Network attempted confidential computing integration into blockchain networks but often introduce vendor dependencies and centralization risks through specific TEE implementation reliance.

### 2.5 Gaps in Current Research

1. **Limited TEE Portability**: Current solutions bind applications to specific hardware
2. **Insufficient Blockchain Integration**: Poor TEE integration with blockchain-based governance
3. **Incomplete Key Management**: Lacking comprehensive decentralized key management frameworks
4. **Inadequate Failure Recovery**: Limited consideration of failure modes and recovery mechanisms

---

## 3. System Design

### Architecture Overview

Figure 2 depicts dstack architecture including dstack-OS and dstack-KMS. Dstack-OS provides hardware abstraction with minimized operating system image; dstack-KMS replaces hardware-based data encryption keys with blockchain-controlled key management service.

### 3.1 Portable Confidential Containers

#### Technical Challenges

**Challenge 1—Hardware-Bound Data**: Existing TEE implementations generate data sealing keys derived from hardware-bound root keys unique to each TEE instance. Encrypted data from one TEE cannot decrypt on another, even with identical application code.

**Challenge 2—Vendor Specification Fragmentation**: TEE implementations impose disparate program deployment specifications, forcing developers maintaining multiple artifacts across platforms.

#### 3.1.1 Dstack-KMS: Blockchain-Controlled Secret Derivation

Dstack-KMS generates unique, stable application secrets (Root Key) based on code and configurations. This root key serves as foundation for deriving application-specific secrets for data encryption and verifiable random number generation.

**Key Distinction**: Unlike traditional systems, dstack-KMS deliberately decouples key generation from specific TEE hardware instances. This enables encrypted data migration between different TEE instances.

**Threat Model**: Explicitly acknowledges TEE compromise potential. Implements comprehensive key rotation providing forward and backward data secrecy.

**Dstack-KMS Architecture** (Figure 4):

Combines on-chain governance via smart contracts with off-chain peer-to-peer networks housing secret derivation service nodes. Multi-stage verification:

1. **Open Source Review**: Code and security review verifying key management logic
2. **Reproducible Builds**: Verifiers confirm runtime code matches reviewed source
3. **On-Chain Registry**: Valid executable digests published through governance smart contract
4. **TEE Verification**: Each service node operates within its own TEE instance

**Implementation Approaches**:

**Simple Duplication**:
- First node generates cryptographically secure random root key
- Shares with other nodes after attestation verification
- All nodes maintain identical copies
- Any operational node recovers root key

**MPC-Based Key Generation**:
- Uses Shamir's Secret Sharing across multiple nodes
- Compromising up to t−1 nodes does not expose root key
- Enables key rotation without application reconfiguration

##### Key Derivation

- **Application CA Key**: Derived from root CA key using application unique identifier (code and configuration hash)
- **Disk Encryption Key**: Derived combining application identifier and instance identifier
- **Environment Encryption Key**: Derived using application identifier alone
- **ECDSA Key**: Derived from root ECDSA key for signing operations

##### Key Rotation

**Root Key Share Rotation**: Individual key share rotation without root key modification. Application-transparent.

**Root Key Rotation**: Complete rotation with controlled handover period. Both old and new keys valid during transition, allowing re-encryption before old key destruction.

#### 3.1.2 Dstack-OS: Hardware Abstraction Layer

Provides comprehensive hardware abstraction with minimized OS image bridging gaps between application containers and VM-level TEE implementations.

**Boot Sequence Components** (Intel TDX):

**Hypervisor (TDX Module)**: Loads OVMF, measures code in MRTD register.

**Open Virtual Machine Firmware (OVMF)**: Configures VM hardware, records to RTMR0. Loads Linux kernel, records to RTMR1.

**Kernel**: Loads initrd, mounts root filesystem, records to RTMR2.

**Root Filesystem (RootFs)**: Read-only environment. Measures application images, stores in RTMR3. Manages container lifecycle, interfaces with dstack-KMS, implements LUKS encryption and dm-verity verification.

**Custom Construction**: Ground-up construction with only essential components. Fully open-sourced with reproducible builds.

##### Data Backup and Defense against Rollback Attacks

- Application data encrypted with dstack-KMS-derived keys can backup to external storage
- Anti-rollback via monotonic counters incorporated into encrypted data
- Applications verify counter values during restoration

### 3.2 Decentralized Code Management

Places TEE application governance under smart contract control, creating transparent, auditable deployment and update systems.

**Two-Tier Governance Framework**:

**KmsAuth Contract**: Global authority controlling dstack-KMS operations. Maintains authorized applications registry and governance parameters.

**AppAuth Contracts**: Individual governance contracts per application. Define management rules, permissible code versions, authorized TEE identities, upgrade approval requirements. Support multi-signature to DAO voting mechanisms.

**Enforcement**: Dstack-KMS only provides secrets to TEE instances running governance-contract-authorized code versions.

**Code Upgrade Flow** (Multi-Signature AppAuth):

1. Developer publishes new code version, submits hash to AppAuth
2. Contract initiates multi-signature approval
3. Signatures recorded on-chain (immutable audit trail)
4. Once threshold reached, AppAuth updates authorized versions
5. KmsAuth synchronizes authorization
6. dstack-KMS provisions secrets to new code
7. TEE instances deploy with full data access

### 3.3 Verifiable Domain Management

Enables standard web browsers to cryptographically verify TEE applications without client-side modifications.

#### 3.3.1 Zero Trust TLS Protocol

**TEE-Generated Certificates**: Generated using dstack-KMS-derived secrets. Private keys never exist outside TEE.

**Certificate Authority Authorization (CAA)**: DNS CAA records restrict certificate issuance to authorities verifying TEE attestation.

**Certificate Transparency (CT) Monitoring**: Continuous monitoring detects unauthorized certificates.

#### 3.3.2 Implementation Components

**dstack-Gateway**: Fully managed reverse proxy in TEE. Zero application code changes. Apps get wildcard subdomains (e.g., app-id.dstack.com).

**dstack-Ingress**: Custom domain support. Applications manage TLS certificates themselves with minimal integration.

---

## 4. Verifying TEE Applications: A Practical Walkthrough

### 4.1 Threat Model

Considers developers and administrators as potential adversaries:

- **Application-Level**: Unauthorized code deployment, supply chain attacks, governance bypass
- **Infrastructure-Level**: OS tampering, compromised KMS, unpatched firmware, spoofed attestation
- **Network-Level**: DNS hijacking, MITM attacks

### 4.2 The Reproducibility Challenge

TEE attestation proves specific artifacts run securely but cannot independently verify artifacts represent claimed source code.

**Complete Verification Chain**:
1. Source code verification (open-source review)
2. Build process integrity (reproducible builds)
3. Runtime attestation (TEE quotes)

### 4.3 Dstack Component Verifiability

| Component | Source | Build Method | Registry | Verification |
|-----------|--------|--------------|----------|--------------|
| dstack-OS | Open | Reproducible | KmsAuth | OS Digest |
| dstack-KMS | Open | In-CC | KmsAuth | Image Hash, Root PubKey |
| dstack-Gateway | Open | In-CC | AppAuth | Image Hash |

**In-ConfidentialContainer Build**: Executes entirely within verified dstack-OS. Specifies precise source references, produces verifiable artifacts with measurements attested in TEE quotes.

### 4.4 End-to-End Verification Walkthrough

**Step 1**: KmsAuth contract as system root of trust
**Step 2**: KMS node registration with measurement and quote recording
**Step 3**: dstack-Gateway verification via quote and governance contract
**Step 4**: TEE application deployment with AppAuth digest verification
**Step 5**: User invokes application, requests proof with on-demand quotes

### 4.5 Security Analysis

- **Application-Level**: Measurement verification against AppAuth, In-CC Build integrity, re-verification on updates
- **Infrastructure**: TDX Quotes verify OS integrity, multi-sig governance for KMS, firmware validation
- **Network**: Certificate chain validation prevents DNS hijacking and MITM

---

## 5. Discussion

### 5.1 Security Implications

#### TEE Hardware Vulnerabilities

Mitigations:
- **Defense in Depth**: Multiple protection layers via blockchain governance and key rotation
- **Rapid Response**: Key rotation enables migration from vulnerable hardware
- **Distributed Trust**: MPC-based key management reduces single-compromise impact

#### Detection of TEE Exploitation

- Statistical analysis of unusual behavior
- Honeypot deployments with known secrets
- Cross-validation via multiple computation instances

### 5.2 Broader Impact

- **Enterprise**: Multi-organization confidential collaboration
- **Government**: Privacy-preserving public services
- **Research**: Secure multi-party computation on sensitive data

---

## 6. Conclusion

Dstack transforms raw TEE technology into genuine Zero Trust platforms aligned with Web3 principles. It addresses: security reliability, censorship vulnerability, incomplete verifiability, and unrestricted lifecycle control.

The framework demonstrates maintaining TEE security guarantees while embracing decentralized, trustless principles. Portable Confidential Containers, Decentralized Code Management, and Verifiable Domain Management together establish foundations for next-generation confidential applications.

Principles extend beyond Web3 to any environment requiring confidentiality, verifiability, and decentralized governance.

---

## References

- [Ama25] Amazon. AWS Nitro System. 2025.
- [BGH+18] Boneh et al. Threshold cryptosystems from threshold FHE. J. Cryptology, 2018.
- [Goo25] Google. Confidential VM Overview. 2025.
- [HSS+18] Hunt et al. Chiron: Privacy-preserving ML as a service. 2018.
- [Kap16] Kaplan. AMD Memory Encryption. Linux Security Summit, 2016.
- [KE10] Krawczyk & Eronen. HKDF Scheme. RFC 5869, 2010.
- [LGY+19] Li et al. Intel Trust Domain Extensions. CCS 2019.
- [LLK13] Laurie et al. Certificate Transparency. RFC 6962, 2013.
- [LZ17] Lamb & Zacchiroli. Reproducible Builds. IEEE Software, 2017.
- [Mer14] Merkel. Docker: Lightweight Linux Containers. Linux Journal, 2014.
- [Mic25] Microsoft. Azure Confidential Computing. 2025.
- [MOG+20] Murdock et al. Plundervolt. IEEE S&P, 2020.
- [Oas20] Oasis Protocol. Privacy-Preserving Smart Contracts. 2020.
- [Sec20] Secret Network. Privacy-Preserving Smart Contracts. 2020.
- [Sha79] Shamir. How to Share a Secret. CACM, 1979.
- [TB19] Tramer & Boneh. Slalom: Verifiable NN Execution in Trusted Hardware. ICLR, 2019.
- [VBMS+20] Van Bulck et al. LVI: Load Value Injection. IEEE S&P, 2020.
- [VBMW+18] Van Bulck et al. Foreshadow. USENIX Security, 2018.
- [WTS+18] Wahby et al. Doubly-Efficient zkSNARKs. IEEE S&P, 2018.
- [ZZZ+19] Zhang et al. Ekiden: Confidentiality-Preserving Smart Contracts. EuroS&P, 2019.
