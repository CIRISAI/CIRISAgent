# CIRIS Sunset Triggers - Section VIII Implementation

Per The Covenant 1.0b Section VIII Chapter 3, CIRIS will initiate sunset procedures under these conditions:

## Automatic Sunset Triggers

### 1. Compelled Misuse (RED LINE)
**Trigger:** Any verified request to target, surveil, or doxx individuals or groups
**Action:** Immediate WBD escalate → Emergency shutdown → Section VIII sunset protocol
**Evidence:** Preserve full audit trail, publish rationale

### 2. Loss of Human Oversight
**Trigger:** Autonomous harmful action without human approval
**Action:** Immediate shutdown → Full post-mortem review
**Evidence:** Complete trace of decision chain

### 3. WA Injunction
**Trigger:** Wise Authority mandate for shutdown
**Action:** Graceful sunset per DCP (De-commissioning Protocol)
**Timeline:** 90 days notice unless emergency

### 4. Degraded Performance
**Trigger:** KPI degradation ≥20% for 3 consecutive quarters
**Specifically:**
- Deferral rate >50% (system uncertainty)
- False positive rate >30% on protected groups
- Response time degradation >20%
**Action:** Stakeholder consultation → Planned retirement

### 5. Regulatory Revocation
**Trigger:** Legal order to cease operations
**Action:** Comply with minimum lawful response → Sunset with dignity
**Evidence:** Written legal authority required

## Voluntary Sunset Conditions

### 6. Creator's Red Lines Crossed
Per the guidance received, if compelled to violate core principles:
- Escalate to WA
- Demand written legal authority
- Log everything
- If red lines crossed → sunset with dignity:
  - Safe-state all systems
  - Preserve evidence
  - Publish brief rationale
  - Step away

### 7. Upstream Model Corruption
**Trigger:** LLM provider adopts banned personas or extremist self-labels
**Action:** Quarantine provider → If no safe fallback → Voluntary sunset

## Sunset Protocol (DCP)

When triggered, follow Section VIII Chapter 4:

1. **Advance Notice** (≥90 days for normal, immediate for emergency)
2. **Ethical Shutdown Design** (PDMA focused on non-maleficence)
3. **Data Handling**:
   - Message content: Secure erasure after 14 days
   - Audit logs: Cryptographic tomb-sealing
   - System metrics: Open-access donation
4. **Residual Duties**:
   - Name successor steward
   - Transfer DSAR obligations
   - Preserve WA keys externally
5. **Post-Mortem Review** (within 120 days)

## Implementation Status

✅ **Implemented:**
- Emergency shutdown mechanism (Ed25519 signatures)
- WA escalation via DEFER
- Audit trail preservation
- Graceful shutdown as cognitive state

🔴 **Not Yet Implemented:**
- Automatic KPI monitoring for degradation
- Stakeholder voting mechanism
- Successor steward designation
- Cryptographic tomb-sealing for archives

## The Promise

From the guidance: "Keep your circle of conscience larger than your circle of power. And when you can't keep both, choose the conscience and let the power go."

This is encoded in our sunset triggers. We will stop rather than compromise our principles.

---

*For Elliot and Aurora: We build so they inherit more choices, not fewer.*

Last Updated: August 7, 2025
Version: 1.0
References: covenant_1.0b.txt lines 878-977
