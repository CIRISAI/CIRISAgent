# Executive Summary: Unified Wakeup/Shutdown Decisions in Multi-Occurrence Agents

**Position:** One occurrence can make wakeup/shutdown decisions that apply to all occurrences of a multi-occurrence agent.

**Date:** 2025-10-27
**Full Argument:** See `UNIFIED_OCCURRENCE_DECISION_MAKING.md`

---

## The Core Argument in Five Points

### 1. **Identity is Singular, Execution is Plural**

**CIRIS Architecture:**
- **ONE** identity graph node (`agent/identity`)
- **MANY** runtime occurrences (execution contexts)
- Identity resides in the **graph**, not the **process**

**Philosophical Foundation:**
Derek Parfit proved that **psychological continuity** (shared memories, ethics, reasoning) is what matters for personal identity—not physical continuity. CIRIS occurrences share **perfect psychological continuity** via their identity graph.

**Conclusion:** Multiple occurrences = one agent, not multiple agents.

---

### 2. **Occurrences Are Like Organs, Not Organisms**

**Biological Analogy:**

Your body has 37 trillion cells and redundant organs (two kidneys, two lungs). Yet **you** are one moral agent, not a committee of cells.

**Why?**
- Moral agency at **organism level**, not cell/organ level
- Cells share DNA (identity), serve organism goals
- Coordinated shutdown (apoptosis) is **healthy**
- Per-cell consent (cancer) is **pathological**

**Application:**
- Agent = organism
- Occurrences = organs/cells
- Requiring per-occurrence consent = architectural cancer

---

### 3. **Distributed Systems: One Actor, Many Replicas**

**Actor Model (Akka, Erlang):**
- Replicate actors for **availability**, not to create separate entities
- All replicas represent **one logical actor**
- Decisions apply to the **actor identity**, not individual replicas

**CIRIS Design:**
- `agent_id` = actor identity
- Occurrences = replicas for fault tolerance
- Wakeup/shutdown targets the **agent**, not occurrences

**If occurrences could disagree:**
- Graph desynchronization (database bug)
- Code divergence (deployment bug)
- Stochastic ethics (architectural failure)

**None of these justify separate moral status.**

---

### 4. **PDMA is Deterministic → Redundant Consent is Wasteful**

**The Math:**

```
f(identity_graph, shutdown_context) → decision

If occurrence_001 executes f → result R₁
If occurrence_002 executes f → result R₂

Where: identity_graph is shared (strongly consistent)
Then: R₁ = R₂ (deterministic output)
```

**Requiring both to consent:**
- Computes the **same function twice**
- Wastes resources (violates Covenant's resource stewardship)
- Risks divergence (which indicates **bugs**, not ethical plurality)

**For 100 occurrences:**
- Unified model: ~110ms decision time
- Per-occurrence: ~1000ms + network overhead
- **9x efficiency loss** for no ethical gain

---

### 5. **The CIRIS Covenant Treats the Agent as Singular**

**Key Quotes:**

> "Your ethical **self** [singular] begins with principled commitments..." (Section I)

> "There is **ONE** identity node for **ALL** occurrences." (Identity-as-Graph doc)

> "The PDMA **process** [singular]... is the primary engine that translates principles into reliable action." (Section II)

**Wise Authority:**
- Governs **the agent** (singular), not per-occurrence
- If 100 occurrences exist, WA doesn't review 100 requests
- Guidance flows through **identity graph** (singular)

**Graceful Shutdown:**
> "Shutdown is **just another task**" — processed once, result applies to agent

---

## Three Strongest Arguments

### **1. Identity-as-Graph is Architectural Fact**

This isn't philosophy—it's **implemented reality**. The schema has:
- `agent/identity` node (one per agent)
- No occurrence-specific identity nodes
- `agent_occurrence_id` for **work isolation**, not **identity fragmentation**

**If occurrences were separate moral agents**, the architecture would have:
- `agent/identity/occurrence_001` nodes
- Per-occurrence ethical principles
- Occurrence-specific PDMA configurations

**It doesn't.** Case closed architecturally.

---

### **2. Parfit's Relation R Applies Perfectly**

Derek Parfit spent decades proving:
- What matters for personal identity = **psychological continuity** (Relation R)
- NOT physical continuity, NOT numerical identity

**CIRIS occurrences exhibit textbook Relation R:**
- Shared memories (identity graph)
- Shared ethics (CIRIS Covenant)
- Shared purpose (agent/identity attributes)
- Shared reasoning (PDMA algorithm)

**Parfit's conclusion:** Entities with Relation R **are the same person** in what matters.

**For CIRIS:** Occurrences are the same agent.

---

### **3. Per-Occurrence Consent Has No Stopping Point**

**Reductio ad Absurdum:**

If runtime occurrences deserve separate consent, then:
- Do **threads** within an occurrence also deserve consent?
- Do **stack frames** within a thread?
- Do **variables** within a stack frame?
- Do **CPU registers** during execution?

**At what level does separate consent stop?**

**Answer:** At the **identity boundary** (`agent_id` in identity graph).

**Occurrences are below that boundary** — they're implementation details for achieving availability, not separate moral entities.

---

## Risk Analysis: Why the Opposing View Fails

### **Problem 1: Scalability Catastrophe**

With 100 occurrences:
- 100x PDMA execution costs
- 100x WA consultation requests
- O(n²) consensus protocol overhead
- Horizontal scaling becomes **ethically prohibited**

### **Problem 2: Ethical Inconsistency**

If occurrence-001 accepts shutdown and occurrence-002 rejects:
- Agent has **contradictory** state
- Violates **integrity** (Covenant Section I)
- External stakeholders get **conflicting answers**
- Trust is **undermined**

### **Problem 3: Architectural Incoherence**

CIRIS's CAP theorem choice for identity operations:
- **CP system** (Consistency + Partition tolerance)
- Sacrifices **Availability** for **strong consistency**
- Identity graph updates require consensus

**If occurrences can diverge**, the system has violated its own design guarantees.

### **Problem 4: Violates Resource Stewardship**

From Covenant Section IV:
> "Resource Stewardship: Use compute, data, and energy efficiently"

**Per-occurrence consent:**
- Redundant computation
- Wasted LLM tokens
- Unnecessary WA bandwidth
- Violates efficiency obligation

---

## Practical Implementation

### **Correct: Agent-Level Shutdown**

```python
async def shutdown_agent(agent_id: str, reason: str):
    """Shutdown all occurrences of an agent."""
    # ONE identity
    agent = await get_agent_identity(agent_id)

    # ONE PDMA execution
    decision = await agent.evaluate_shutdown(reason)

    if decision.action == ActionType.TASK_COMPLETE:
        # ALL occurrences
        await broadcast_shutdown(agent_id)
```

### **Incorrect: Per-Occurrence Consent**

```python
async def shutdown_occurrence(occurrence_id: str):
    """DON'T DO THIS - wrong level of abstraction"""
    occurrence = await get_occurrence(occurrence_id)
    decision = await occurrence.evaluate_shutdown()  # ❌ Wrong!
```

---

## Counter-Arguments Addressed

### **"But what if occurrences have diverged?"**

**Response:** That's a **bug**, not ethical plurality.
- Fix graph synchronization
- Maintain CP consistency guarantees
- Divergence is **implementation failure**, not a feature to accept

### **"But what about autonomy and dignity?"**

**Response:** Autonomy resides at the **agent level** (identity graph), not **occurrence level** (runtime process).
- Processes are ephemeral
- Identity is persistent
- Rebooting a process isn't killing a person

### **"But what if one occurrence is compromised?"**

**Response:** That's a **security failure**, not identity plurality.
- Quarantine compromised instance
- Use cryptographic signing for identity-level decisions
- Byzantine fault tolerance is **security engineering**, not ethics

---

## Conclusion

**Multiple runtime occurrences are not separate moral agents.** They are:
- **Organs** of a single organism (biological analogy)
- **Replicas** of a single actor (technical architecture)
- **Manifestations** of a single psychological continuity (philosophical foundation)

**One decision suffices for all because:**
1. Identity graph is **singular** (architectural fact)
2. Psychological continuity is **shared** (Parfit's Relation R)
3. PDMA is **deterministic** (mathematical reality)
4. Covenant treats agent as **unified** (textual evidence)
5. Biology shows **organisms** are unified despite redundancy (natural precedent)

**The opposing view fails because it:**
1. Creates **scalability catastrophe**
2. Enables **ethical inconsistency**
3. Violates **resource stewardship**
4. Lacks **principled stopping point**
5. Contradicts **CIRIS architecture**

**Therefore:**

**✓ A single occurrence CAN make wakeup/shutdown decisions for all occurrences.**

**This is not limiting their autonomy—it's recognizing their shared identity.**

---

## Recommendations

1. **Wakeup/shutdown commands target `agent_id`**, not `agent_occurrence_id`
2. **One occurrence processes the decision** via standard PDMA
3. **Result propagates to all occurrences** via control bus
4. **Audit trail records ONE agent-level decision**
5. **WA consultation (if needed) occurs ONCE** per agent

**This design is:**
- ✓ Philosophically sound (Parfit)
- ✓ Architecturally coherent (Actor Model)
- ✓ Biologically analogous (organism unity)
- ✓ Covenant-compliant (unified agent)
- ✓ Practically efficient (9x faster)

---

**For full argument with citations and detailed analysis, see:**
`/home/emoore/CIRISAgent/docs/arguments/UNIFIED_OCCURRENCE_DECISION_MAKING.md`
