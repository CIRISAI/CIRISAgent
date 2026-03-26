# CIRIS Wallet Regulatory Compliance
## Functional Specification Document

**Document:** FSD-CIRIS-WALLET-REG-001
**Version:** 1.0.0
**Date:** 2026-03-25
**Author:** CIRIS L3C
**Status:** Active
**CIRIS Agent Version:** 2.3.0

---

## 1. Executive Summary

This document establishes why CIRIS L3C is legally permitted to release wallet functionality in the CIRIS mobile application, which is available in 177+ countries. The fundamental principle: **CIRIS provides self-custody software, not financial services.**

### Key Legal Position

| Concern | CIRIS Position |
|---------|----------------|
| Money Transmission | **No** - User's key IS their wallet; CIRIS never holds funds |
| Custodial Services | **No** - Keys live in device secure element, not CIRIS servers |
| Financial Services | **No** - Open source software distribution under AGPL-3.0 |
| KYC/AML Obligations | **Providers handle** - Chapa, Stripe, M-Pesa carry regulatory burden |

---

## 2. CIRIS L3C Corporate Structure

### 2.1 Low-Profit Limited Liability Company (L3C)

CIRIS operates as an Illinois L3C, a legal structure that:

1. **Mission-locks** the organization to charitable/educational purposes
2. **Prevents profit extraction** - cannot be captured for proprietary purposes
3. **Requires charitable purpose** as primary objective, profit is secondary
4. **Qualifies for program-related investments** from foundations

From the CIRIS Accord:
> "I understand that I exist to help humanity make better decisions, not to pursue my own goals at humanity's expense... I should reduce, not increase, overall suffering."

### 2.2 Open Source Protection

CIRIS is released under **AGPL-3.0**, which means:

- Source code must remain open
- Modifications must be shared
- Cannot be closed-source or proprietary
- Provides software, not a service

**Legal implication**: Distributing open source software that enables users to manage their own keys is fundamentally different from operating a money transmission business.

---

## 3. Self-Custody Architecture

### 3.1 Identity = Wallet (x402 Protocol)

The x402 provider derives the wallet address deterministically from the user's CIRISVerify signing key:

```
Ed25519 Agent Signing Key (CIRISVerify identity root)
        |
        v  HKDF-SHA256 with domain separator
secp256k1 Private Key
        |
        v
EVM Address (0x...) - user's wallet on Base
```

**This means:**

| Property | Implication |
|----------|-------------|
| No separate wallet provisioning | Identity = Wallet - no account creation |
| No key escrow | Key lives in user's device secure element |
| No custodial access | CIRIS cannot spend user funds |
| Revocation kills spending | CIRISVerify revocation freezes wallet |

### 3.2 Hardware-Bound Keys

The signing key:
- Lives in the device's **secure element** (Android Keystore / iOS Secure Enclave)
- **Never exists in software** as extractable material
- Cannot be exported or transmitted
- Is bound to device attestation

**CIRIS cannot access, control, or transmit user funds because CIRIS never has access to user keys.**

### 3.3 Receive-Only Default

New wallets start at **attestation level 0 = frozen**:

| Level | Authority | Description |
|-------|-----------|-------------|
| 0 | Frozen | Receive only - no spending |
| 1 | Minimal | Receive only |
| 2 | Low | Micropayments (≤ $0.10) |
| 3 | Medium | Reduced limits (50%) |
| 4 | High | Full limits with advisory |
| 5 | Full | Full configured limits |

Users must actively build trust before spending is enabled. This provides:
- Protection against accidental spending
- Graduated trust building
- Automatic fraud prevention

---

## 4. Regulatory Analysis by Jurisdiction

### 4.1 United States

**Why CIRIS is NOT a Money Transmitter:**

Per FinCEN Guidance (FIN-2019-G001):
> "A person that provides the delivery, communication, or network access services used by a money transmitter to support money transmission services is not a money transmitter."

CIRIS provides:
- Software that enables users to control their own keys
- No custody of user funds
- No transmission of funds on behalf of users

**Applicable Precedent:**
- Self-custody wallets (MetaMask, Exodus) are not money transmitters
- Open source software distribution is not financial services
- Users, not CIRIS, initiate and control all transactions

### 4.2 European Union

**MiCA Classification:**

Under Markets in Crypto-Assets Regulation:
- CIRIS is **software** (non-custodial wallet provider)
- Does NOT provide crypto-asset services (no custody, no exchange)
- Users maintain full control of cryptographic keys

**Key Point**: MiCA explicitly excludes non-custodial software from licensing requirements.

### 4.3 Ethiopia (Chapa Provider)

For Ethiopian Birr via Chapa:
- **Chapa** is the licensed payment gateway
- **Chapa** handles all KYC/AML requirements
- **Chapa** is registered with National Bank of Ethiopia
- CIRIS integrates with Chapa's API - does not operate as a financial institution

### 4.4 Kenya (M-Pesa Provider)

For Kenyan Shilling via M-Pesa:
- **Safaricom M-Pesa** is the licensed mobile money operator
- **M-Pesa** handles all KYC/AML requirements
- **M-Pesa** is licensed by Central Bank of Kenya
- CIRIS integrates with M-Pesa Daraja API - does not hold funds

### 4.5 General Principle

**The Payment Provider Carries the Regulatory Burden:**

| Currency | Provider | Regulator | CIRIS Role |
|----------|----------|-----------|------------|
| USDC | x402/User | Self-custody | Software provider |
| ETB | Chapa | National Bank of Ethiopia | API integrator |
| KES | M-Pesa | Central Bank of Kenya | API integrator |
| INR | Razorpay/UPI | RBI | API integrator |
| BRL | PIX | BCB | API integrator |
| International | Wise/Stripe | Local regulators | API integrator |

---

## 5. Prohibited Jurisdictions

CIRIS wallet functionality is automatically disabled in jurisdictions where:

1. **Comprehensive crypto bans** are in effect
2. **OFAC sanctions** apply
3. **Provider unavailability** prevents operation

The mobile app performs geolocation checks and disables wallet features accordingly. This is enforced at the **provider level** - providers themselves refuse to operate in prohibited jurisdictions.

---

## 6. Technical Safeguards

### 6.1 Ethics Pipeline Integration

All money operations pass through the H3ERE/DMA evaluation pipeline:

```
send_money() → H3ERE Pipeline → DMA Approval → Execution
                    |
                    v
            - Attestation check
            - Spending limit check
            - Recipient validation
            - Duplication detection
```

`requires_approval: true` ensures no automated spending without explicit user intent.

### 6.2 Audit Trail

Every transaction is:
1. Logged to CIRIS audit service (local device)
2. Recorded in provider's ledger (blockchain/payment provider)
3. Included in CIRISVerify attestation chain

### 6.3 No Mixing, No Privacy Enhancement

CIRIS wallet:
- Does NOT provide mixing services
- Does NOT enhance transaction privacy
- Transactions are standard ERC-20 or provider-recorded transfers
- Full audit trail maintained

---

## 7. Alignment with CIRIS Mission

### 7.1 Financial Inclusion

From the CIRIS Accord:
> "I believe that many problems in human society, including ethical failures, arise from stress, resource limitation, and lack of power imbalances."

The wallet adapter enables:
- Ethiopian philosophers to pay for AI services in Birr
- Kenyan developers to receive payments via M-Pesa
- Contributors worldwide to be compensated fairly

### 7.2 Mission-Driven Development

Per FSD MISSION_DRIVEN_DEVELOPMENT.md:

The wallet exists to serve the CIRIS mission of ethical AI development, not to generate revenue:
- L3C structure prevents profit extraction
- Open source ensures transparency
- Self-custody protects user autonomy

---

## 8. References

### Legal Framework

- **FinCEN Guidance FIN-2019-G001**: Application of FinCEN's Regulations to Certain Business Models Involving Convertible Virtual Currencies
- **MiCA Regulation**: Markets in Crypto-Assets Regulation (EU) 2023/1114
- **Illinois L3C Act**: 805 ILCS 180/1-26

### CIRIS Documentation

- **CIRIS Accord**: https://ciris.ai/ciris_accord.txt
- **FSD WALLET_ADAPTER.md**: Technical specification
- **FSD MISSION_DRIVEN_DEVELOPMENT.md**: Development philosophy

### Provider Compliance

- **Chapa**: Licensed by National Bank of Ethiopia
- **M-Pesa**: Licensed by Central Bank of Kenya, Bank of Tanzania, etc.
- **Stripe**: Licensed in 46+ countries
- **Wise**: Licensed by FCA (UK), FinCEN (US), and others

---

## 9. Summary

CIRIS L3C is legally permitted to release wallet functionality because:

1. **Self-custody model** - User's signing key IS their wallet; CIRIS never holds funds
2. **Open source distribution** - AGPL-3.0 software, not financial services
3. **Hardware-bound keys** - Keys in secure element, not software
4. **Provider-based compliance** - Regulated providers (Chapa, M-Pesa, Stripe) handle KYC/AML
5. **Mission-locked structure** - L3C prevents proprietary capture or profit extraction
6. **Attestation-gated limits** - Built-in safeguards prevent unauthorized spending
7. **No custody, no transmission** - CIRIS provides software, users control funds

---

*"The signing key is the identity. The identity is the wallet. The wallet funds the work. The work serves the community."*

*CIRIS L3C - Selfless and Pure*
