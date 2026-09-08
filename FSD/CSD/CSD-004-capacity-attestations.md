# CSD-004 — Federation capacity attestations (Health & Reputation)

**CSD**: CSD-004
**Version**: 1.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2026-09-07
**Flow**: tools/qa_runner/flows/capacity_attestations.yaml
**Client floor**: >=0.5.208
**Origin**: CIRISClient#45
**Standard**: `FSD/CSD_STANDARD.md`

## 1. Mission (why)

**A user can now see live federation capacity attestations on Health & Reputation,
where before #45 a gate placeholder stood in for them.** The distinction is the
whole feature: a placeholder that looks like data is the metric-dishonesty MDD's
anti-Goodhart measures name. Serves **Incompleteness** — show what is measured,
and only what is measured.

## 2. Surface (what)

### Screens

| screen | reached from | leaves to |
|---|---|---|
| `HealthReputation` | the Health & Reputation nav entry | — |

### Tags

| tag | kind | guaranteed by |
|---|---|---|
| `card_federation_capacity_attestations` | card | CIRISClient#45 |
| `federation_capacity_live` | the **live** marker — absent on the old gate | CIRISClient#45 |

### Collects / shows

| field | source (§3) | required |
|---|---|---|
| capacity attestations | capacity read | shows |

### Writes

Nothing.

## 3. Contracts (who)

| value | endpoint / surface | owner |
|---|---|---|
| capacity attestations | **unconfirmed** — `CapacityAttestation` is a type in ciris-server 0.5.199 and the pruned gate `LENSCORE_CAPACITY` says the lens read API on `:4243` serves it; the path is not named in #45 | CIRISServer / CIRISLensCore |

## 4. Flow (how)

<!-- flow: tools/qa_runner/flows/capacity_attestations.yaml -->
```yaml
flow: capacity_attestations
title: Federation capacity attestations on Health & Reputation
description: >-
  CIRISClient#45 replaced FederationAttestationsGate with a live section. The
  point of the change is that the data is real, so the assertion is on
  `federation_capacity_live` and not merely on the card: a gate placeholder
  would satisfy the card tag alone.
client: ">=0.5.208"

steps:
  - step_id: attestations_section
    title: The capacity attestations section is live, not gated
    requires:
      screen: HealthReputation
    expect:
      visible: [card_federation_capacity_attestations, federation_capacity_live]
```

## 5. QA plan

### Platforms

All five.

### How to run

```
python -m tools.qa_runner.modules.web_ui flow --spec tools/qa_runner/flows/capacity_attestations.yaml --platform <desktop|android|ios>
```

### Results — in the UI and in the log

Per step: a console line (`[OK]` with the held condition and duration, or `[FAIL]`
naming the phase — `requires` / `do` / `expect` — the predicate, and the tags on
screen and drivable now); a screenshot at `artifacts/shots/flow-capacity_attestations-<step_id>.png`
rendered in the five-platform gallery; a row in `artifacts/flows/capacity_attestations.json`.

### Acceptance

**Functional**
1. A person on Health & Reputation sees capacity attestations that are live data,
   not a gate.

**Tests** (the flow)
* `attestations_section` — the card **and** `federation_capacity_live` are on screen.
  The second tag is the assertion; the card alone would be satisfied by the gate
  this feature replaced.

**Untested and must be established**
* That the numbers are right. `federation_capacity_live` proves the section is the
  live one; it does not compare what it shows against the read. That needs the path
  in §3 named, then a `text:` predicate against a fixture.
