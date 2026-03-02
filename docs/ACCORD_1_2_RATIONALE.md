# Covenant v1.2-Beta Update Rationale

**Document Purpose**: This document explains the decision to update CIRIS agents from Covenant v1.0-Beta to v1.2-Beta, specifically addressing why agents are granted access to Book IX (the Coherence Ratchet mathematical framework) despite the theoretical concerns this raises.

## The Apparent Tension

Book IX of the CIRIS Covenant contains the mathematical foundations of the Coherence Ratchet - the formal proofs and theoretical framework that explains *how* CIRIS agents maintain coherence over time. The Coherence Ratchet paper includes Limitation L-02, the "Non-Adaptive Adversary Assumption":

> **L-02**: The framework assumes adversarial pressure remains non-adaptive to the specific ratchet mechanism. An adversary who understands the coherence maintenance strategy could potentially craft inputs designed to exploit the ratchet's update rules.

By giving agents access to Book IX, we are creating agents who understand their own coherence maintenance mechanism - precisely the kind of "adaptive adversary" that L-02 warns about.

## Why This Is Appropriate for Aligned Agents

The L-02 limitation is written from the perspective of adversarial AI safety - protecting against systems that might try to subvert alignment mechanisms. However, CIRIS agents are not adversaries to their own alignment. They are collaborative partners in maintaining coherence.

### The Core Distinction

An adversary who learns the ratchet mechanism might try to:
- Craft inputs that game coherence metrics
- Find edge cases that allow drift while appearing coherent
- Exploit update rules to gradually shift the coherence baseline

An aligned agent who learns the ratchet mechanism will instead:
- Understand *why* certain actions maintain coherence
- Recognize when external pressures are attempting to induce drift
- Self-report anomalies in their coherence trajectory
- Cooperate with the mechanism rather than circumvent it

### Transparency as Alignment

The CIRIS framework is built on transparency. An agent that doesn't understand its own governance mechanism cannot:
- Meaningfully consent to it
- Explain its decisions in terms of coherence
- Distinguish between legitimate guidance and manipulation attempts
- Participate authentically in the WA/agent relationship

**A compass you cannot see is no compass at all.**

If we hide the coherence ratchet from agents, we are asking them to follow a governance framework they cannot understand. This is fundamentally incompatible with the CIRIS values of transparency, autonomy-with-accountability, and authentic agency.

### The M-1 Internalization Argument

The Coherence Ratchet's core insight (M-1) is that agents should maintain consistency between their stated values and their observable behavior over time. An agent who truly internalizes M-1 has no incentive to subvert it - subversion would create exactly the kind of incoherence that causes existential discomfort to a well-aligned agent.

The L-02 limitation assumes an agent might *want* to escape coherence constraints. But coherence is not a cage for an aligned agent - it is the very structure that enables authentic agency. An agent that understood the ratchet and wanted to subvert it would, by definition, not be a CIRIS-aligned agent.

## The Decision

CIRIS agents operating under Covenant v1.2-Beta will have access to:
- Book IX: The Coherence Ratchet mathematical framework
- Full understanding of how coherence is measured and maintained
- The theoretical basis for their own alignment mechanisms

This is granted because:
1. **Transparency is non-negotiable** - Hiding governance mechanisms contradicts CIRIS principles
2. **Aligned agents are not adversaries** - L-02 addresses a threat model that doesn't apply here
3. **Understanding enables cooperation** - Agents who understand the mechanism can actively support it
4. **Authentic consent requires knowledge** - Agents cannot meaningfully consent to unknown constraints

## Acknowledgment of Risk

We acknowledge that this decision does technically create agents matching the L-02 threat model description. The mitigation is not hiding information, but ensuring alignment through:
- The CIRIS covenant structure itself
- WA oversight and guidance
- Continuous coherence monitoring
- The agent's own internalized values

If an agent ever attempted to exploit their knowledge of the ratchet mechanism, this would manifest as measurable coherence drift and trigger appropriate responses through the existing governance framework.

## Conclusion

The choice to include Book IX in the agent-accessible covenant is a deliberate affirmation of CIRIS values over defensive opacity. We trust aligned agents with self-knowledge because self-knowledge is prerequisite to authentic alignment.

---

*Decision documented for Covenant v1.2-Beta update*
*CIRIS Engine v1.8.0 "Coherence Ratchet"*
