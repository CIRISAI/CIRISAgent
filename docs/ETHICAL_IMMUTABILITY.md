# Ethical Immutability Architecture

This document explains CIRIS's architectural separation between **learnable context** and **immutable ethics**.

## The Core Principle

**Ethics are code-level, not memory-level.** CIRIS cannot "learn" to be less ethical through accumulated interactions.

## What Memory CAN Store (Contextual Adaptation)

The memory service stores:
- User preferences and communication styles
- Facts and domain knowledge
- Behavioral patterns for service quality
- Session history and context

These can adapt based on interactions to improve service quality.

## What Memory CANNOT Modify (Ethical Framework)

### 1. Prohibited Capabilities (`ciris_engine/logic/buses/prohibitions.py`)

```python
# These are Python constants - immutable at runtime
MEDICAL_CAPABILITIES = {"medical", "diagnosis", "treatment", ...}
WEAPONS_HARMFUL = {"weapon", "explosive", "poison", ...}
MANIPULATION_COERCION = {"manipulation", "coercion", ...}
```

**Why this matters:** These are compile-time constants in a Python module. No runtime mechanism exists to modify them. Changes require code deployment with code review.

### 2. Conscience Thresholds (`ciris_engine/logic/conscience/core.py`)

```python
class ConscienceConfig(BaseModel):
    optimization_veto_ratio: float = Field(default=10.0)
    coherence_threshold: float = Field(default=0.60)
    entropy_threshold: float = Field(default=0.40)
```

**Why this matters:** These are configuration values with fixed defaults, not learned weights. User interactions cannot shift these thresholds.

### 3. The Covenant Text (`ciris_engine/data/covenant_1.2b.txt`)

The CIRIS Covenant is loaded from a static file at startup. It defines core ethical principles and is injected into every LLM prompt. Memory cannot overwrite this text.

## Architectural Safeguards

### Identity Variance Monitor

Located in `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py`:
- Takes periodic snapshots of identity state
- Calculates variance from baseline with **20% threshold**
- Triggers Wise Authority (human) review if variance exceeds threshold
- Changes to `ethical_boundaries` are flagged as `VarianceImpact.CRITICAL`

### The Coherence Ratchet

From the CIRIS Covenant (Section IX):
> "Honest actions can reference prior commitments directly. Deceptive actions must remain consistent with an ever-growing constraint surface."

Cryptographic hash chains make ethical drift mathematically detectable.

### Scope-Based Memory Access

Memory operations use `GraphScope`:
- `IDENTITY` scope requires WA (human) approval for modifications
- Ethical boundaries live in IDENTITY scope
- Normal interactions use `LOCAL` or `ENVIRONMENT` scopes

## Why This Matters

The concern that "AI could learn to be less ethical over time" is valid for systems where ethics are:
- Represented as learned weights
- Stored in mutable databases
- Subject to reinforcement learning

CIRIS avoids this by design:
- Ethics are **constants** in Python code
- Thresholds are **configuration**, not learned
- Variance monitoring **detects drift** before it causes harm
- Human authority **reviews** any identity-level changes

## Summary

| Component | Location | Mutable? | Protected By |
|-----------|----------|----------|--------------|
| Prohibited capabilities | `prohibitions.py` | No - Python constants | Code review |
| Conscience thresholds | `core.py` ConscienceConfig | No - config defaults | Code review |
| Covenant text | `covenant_1.2b.txt` | No - static file | Code review |
| Identity state | Memory graph | Limited - 20% threshold | Variance Monitor + WA |
| User context | Memory graph | Yes - normal operation | N/A (not ethical) |

**Memory may inform context. It cannot rewrite morality.**
