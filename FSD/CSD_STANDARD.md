# CIRIS Specification Document (CSD) — the standard

**Version**: 1.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2026-09-07
**Parent**: `FSD/MISSION_DRIVEN_DEVELOPMENT.md` (MDD)

## Abstract

A CSD is Mission Driven Development applied to **one feature**. MDD says every
architectural decision must demonstrate alignment with the mission through three
structural legs — LOGIC (how), SCHEMAS (what), PROTOCOLS (who) — resting on the
MISSION (why). A CSD writes those four down for a single user-facing surface, and
adds the one thing a feature has that an architecture does not: **a test that is
the same document as the spec.**

That last property is the reason this standard exists. Every UI flow in this
repository's gate has been hand-written imperative code against the client's test
server, and the failures have not been in the app — they have been in our encoding
of it (CIRISClient#39: `btn_menu` opens ADVANCED; `menu_logout` lives under
GOVERNANCE; the click succeeded, the wait timed out, nothing was broken). A CSD
states what a card is *and* how it is driven in one declarative form, so that the
spec cannot say one thing while the test checks another.

## 0. What a CSD is, in one sentence

> A CSD names the mission a surface serves, the tags and fields it is made of, the
> contracts it reads and writes, and a flow — in the UI DSL — that a machine
> executes to prove the surface does what the document says.

## 1. The four components, applied to a feature

| MDD component | question | what a CSD section contains |
|---|---|---|
| **MISSION** (the seat) | *why does this surface exist?* | §1 — one falsifiable paragraph: *"a user can now …"*, and which CIRIS principle it serves |
| **SCHEMAS** (what) | *what is it made of?* | §2 — the screens, the guaranteed test tags, the fields it collects or shows, what it writes |
| **PROTOCOLS** (who) | *what does it talk to?* | §3 — version floors, the endpoints each value comes from, who owns each half |
| **LOGIC** (how) | *how is it reached and driven?* | §4 — the flow, in the DSL, verbatim |
| — | *how do we know?* | §5 — the QA plan: platforms, how to run, results in UI and logs, acceptance |

MDD's **Constant Alignment** principle applies section by section: every tag in §2
must appear in a step in §4; every endpoint in §3 must be the source of something in
§2; every step in §4 must serve the sentence in §1. The checker (§7) enforces the
mechanical half of that; review enforces the rest.

## 2. The header

Identical to every FSD in this directory, plus two lines that make the document
addressable by machines:

```
**CSD**: CSD-001
**Flow**: tools/qa_runner/flows/delegation_card.yaml
**Client floor**: >=0.5.208
**Origin**: CIRISClient#45
```

`Flow` is the executable half. `Client floor` is the version the flow was written
against — a floor, not a pin (CIRISClient#39): running the flow on an older client is
**refused loudly**, because a tag that does not exist yet fails as *element not
found*, which is indistinguishable from a broken app.

## 3. The UI DSL

The DSL is not ours. CIRISClient specified it in answer to #39, and it is
deliberately a *narrowing* of the `interactive_config` language this repository
already carries in 83 adapter steps — one way to say each thing, not a second
language beside the first. A CSD uses the **test direction** of that form:

```yaml
flow: delegation_card              # id; must match the CSD's Flow line
title: …
client: ">=0.5.208"                # version-legible floor
steps:
  - step_id: open_delegation       # unique within the flow
    title: Opening the card reaches the Delegation screen
    requires:                      # LINKS — what must be true BEFORE
      screen: LayerFamily
      visible: [btn_open_delegations]
    do:                            # the interactions, in order
      - click: btn_open_delegations
    expect:                        # what must be true AFTER
      screen: Delegation
      visible: [screen_delegation, btn_delegation_back]
```

### 3.1 The HyperCard reading

CIRISClient's answer mapped the form onto title / contents / sources / links /
outputs. The same mapping holds for a CSD, and it is why §2 and §4 are separate
sections of one document rather than two documents:

| HyperCard | CSD section | DSL key |
|---|---|---|
| title | §2 screen name | `title` |
| contents | §2 tags and fields | `expect.visible` |
| sources | §3 endpoints | (named in §3; the flow asserts their *effect*) |
| links | §4 preconditions | `requires` |
| outputs | §2 "writes" | `expect` after the writing step |

### 3.2 Conditions — `requires` and `expect`

| key | meaning | why it is strict |
|---|---|---|
| `screen: Name` | `/screen` answers exactly this | a screen that renders its shell and none of its content still answers `/screen` — so `screen` alone is never enough |
| `visible: [tags]` | every tag is **on screen** | *on screen*, not *composed*: `/tree` lists everything ever composed (registry-never-forgets), and confusing the two is how the harness scrolled 300px of a 3142px form and reported success |
| `absent: [tags]` | no tag is on screen | the half of navigation nobody drives twice: *back* must make the previous screen's controls go away |
| `text: {tag: substr}` | the element's text contains it | for live surfaces, the difference between "the card rendered" and "the card rendered a placeholder" |

### 3.3 Actions — `do`

`click: tag` · `input: {tag: text}` · `scroll_to: tag` · `wait: tag`. Exactly one
verb per entry. `scroll_to` is rarely needed in a spec: the runner scrolls on its own
when an element is composed but off screen, and prints what each scroll did
(`down:300 moved 0→300 of 3142`) so an accepted-but-inert scroll is legible.

### 3.4 Rules — each is a load error, not a convention

* **Unknown keys fail the load.** A spec with a typo'd key would otherwise assert
  nothing and pass. This harness has produced that vacuous-green shape three times
  (the absent-screen check in #1151, `without_ai_recorded`, the `lsof` teardown);
  a fourth by misspelling `visible` is not acceptable.
* **A step with neither `do` nor `expect` is refused** — it is a comment pretending
  to be a test.
* **`step_id` is unique within a flow**, so a failure names one step.
* **Absent means false.** There is no `optional: true` beside `required: false`; a
  key is present or it is not. (`optional_step: true` exists for a step that may
  legitimately not apply on a build; it still asserts everything when its
  preconditions hold, and it is reported as SKIPPED — loudly — when they do not.)
* **A tag nobody has confirmed does not go in a flow.** If the client's PR names a
  behaviour but not its tag, the step is written out in a comment in the flow file
  with the tag left as `<the back tag>`, and the question is asked on the PR. A
  guessed tag is the #39 defect in its purest form. `CSD-002` demonstrates this.

## 4. One artifact, two readers

The flow block in §4 of a CSD is **byte-identical** to the file named on its `Flow`
line. That is not a convention; `tools/dev/check_csd.py` diffs them and fails CI on
any difference, in both directions:

* every CSD names a flow file that exists, and embeds it exactly;
* every flow file under `tools/qa_runner/flows/` is embedded by exactly one CSD.

The consequence is the property CIRISClient asked for in #39: *a screen reorder
cannot land without its flow moving in the same PR* — and now, without its
specification moving too. A CSD that describes yesterday's screen fails CI today.

## 5. The QA plan (§5 of every CSD)

A CSD's QA section is short because the flow is most of it. It states:

1. **Platforms.** Which of the five the flow must pass on. A card that exists on
   all five is asserted on all five; the gate runs the same YAML on each.
2. **How to run**, exactly:
   ```
   python -m tools.qa_runner.modules.web_ui flow --spec tools/qa_runner/flows/<flow>.yaml --platform <p>
   ```
3. **Results — in the UI and in the log.** For every step the runner emits:
   * a console line — `[OK]` with the condition that held and the duration, or
     `[FAIL]` naming **which phase** (`requires` / `do` / `expect`), **which
     predicate**, and the tags **on screen and drivable now**;
   * a screenshot, `artifacts/shots/flow-<flow>-<step_id>.png`, rendered in the
     five-platform gallery beside the platform tiles;
   * a row in `artifacts/flows/<flow>.json` (status, phase, detail, duration,
     screenshot path, drivable set).
   A precondition failure is reported as one. *"This flow cannot start here"* and
   *"this element is broken"* are different bugs with different owners.
4. **Acceptance**, in the house shape: **Functional** (what a person can do),
   **Tests** (what the flow asserts), and **Untested and must be established** —
   the honest list of what the flow does *not* prove. A CSD with an empty last list
   is suspect.

## 6. Writing a new CSD

1. Copy the template below into `FSD/CSD/CSD-NNN-<slug>.md` (next free number;
   the index at `FSD/CSD/README.md` is the registry).
2. Write §1 first. If the mission sentence cannot be written as *"a user can now
   …"*, the surface is not a feature yet.
3. Fill §2 from the client PR's tag list. **Do not add tags the PR does not name.**
4. Fill §3's sources from the substrate: the endpoint, or the literal word
   `unconfirmed` with who is being asked. Never a guess.
5. Write the flow in `tools/qa_runner/flows/<flow>.yaml`, then embed it in §4
   (`python tools/dev/check_csd.py --embed CSD-NNN` does the paste).
6. Run it against a build that has the surface. Put what it did *not* prove in §5.
7. `python tools/dev/check_csd.py` must pass before the PR opens.

### Template

```markdown
# CSD-NNN — <surface name>

**CSD**: CSD-NNN
**Version**: 1.0
**Status**: Active
**Date**: YYYY-MM-DD
**Flow**: tools/qa_runner/flows/<flow>.yaml
**Client floor**: >=X.Y.Z
**Origin**: CIRISClient#NN

## 1. Mission (why)
A user can now …  Serves: <principle>.

## 2. Surface (what)
### Screens
### Tags
| tag | kind | guaranteed by |
### Collects / shows
| field | source (§3) | required |
### Writes

## 3. Contracts (who)
| value | endpoint / surface | owner |

## 4. Flow (how)
<!-- flow: tools/qa_runner/flows/<flow>.yaml -->
```yaml
…
```

## 5. QA plan
Platforms · How to run · Results · Acceptance (Functional / Tests / Untested)
```

## 7. The checker — `tools/dev/check_csd.py`

Stdlib-only, wired into `build.yml` beside `check_evidence.py`. It fails on:

| check | why |
|---|---|
| a CSD's `Flow` line names a file that does not exist | the spec has no test |
| the embedded block differs from the file | the spec and the test disagree — the exact drift #39 is about |
| a flow file with no CSD, or with two | a test with no spec, or two specs for one test |
| the flow's `flow:` id differs from the CSD's filename slug | a CSD titled for one surface driving another |
| `Client floor` absent or unparseable | the flow cannot refuse an older client loudly |
| a §3 source that is neither a path nor the word `unconfirmed` | a guessed endpoint is worse than a named unknown |
| any CSD not listed in `FSD/CSD/README.md` | the registry is the registry |

`--embed CSD-NNN` rewrites the block from the file, so "keep them identical" is a
command rather than a chore.

## 8. What a CSD is not

* Not a design document. A CSD describes a surface that exists, in a client build
  that can be named. Design lives in an FSD; a CSD follows the PR that shipped it.
* Not a substitute for the client's own tests. The client guarantees the tags; the
  CSD asserts the *composition* — which tag is reachable from which, on which
  screen, after which click. That is precisely the knowledge #39 found nobody was
  writing down.
* Not a place for tags nobody has confirmed. See §3.4.

## 9. First set

`CSD-001` … `CSD-004` cover the four surfaces CIRISClient#45 unlocked. They are the
worked examples; the index is `FSD/CSD/README.md`.
