# CSD-001 — Delegation card and screen (Family layer)

**CSD**: CSD-001
**Version**: 1.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2026-09-07
**Flow**: tools/qa_runner/flows/delegation_card.yaml
**Client floor**: unreleased
**Origin**: CIRISClient#45
**Standard**: `FSD/CSD_STANDARD.md`

## 1. Mission (why)

**A user can now see who they have delegated trust to, who has delegated to them,
and reach the ceremony that changes either — from the Family layer, in three
panels, without inferring any of it from the graph.** Delegation is how a person
extends trust through a family without surrendering it; the Family layer is the
first cohort scope above self, and until #45 its delegations were data with no
surface. Serves **Resilience** (trust that survives a device) and **Integrity**
(the grant you hold is the grant you can see).

## 2. Surface (what)

### Screens

| screen | reached from | leaves to |
|---|---|---|
| `LayerFamily` | the Family layer hub | — |
| `Delegation` | `btn_open_delegations` on `card_family_delegations` | `btn_delegation_back` → `LayerFamily` |

### Tags

| tag | kind | guaranteed by |
|---|---|---|
| `card_family_delegations` | card on the hub | CIRISClient#45 |
| `btn_open_delegations` | entry | CIRISClient#45 |
| `screen_delegation` | screen root | CIRISClient#45 |
| `btn_delegation_back` | navigation | CIRISClient#45 |
| `btn_delegation_refresh` | action, live | CIRISClient#45 |
| `card_delegation_overview` | panel | CIRISClient#45 |
| `card_delegation_inbound` | panel | CIRISClient#45 |
| `card_delegation_outbound` | panel | CIRISClient#45 |
| `btn_delegation_manage_grants` | entry to the grant ceremony | CIRISClient#45 |

### Collects / shows

| field | source (§3) | required |
|---|---|---|
| overview — counts and standing | delegation read | shows |
| inbound — who delegated to this key | delegation read | shows |
| outbound — who this key delegated to | delegation read | shows |

### Writes

Nothing on this screen. `btn_delegation_manage_grants` opens the ceremony that
does; that ceremony is its own surface and is **not** asserted here.

## 3. Contracts (who)

| value | endpoint / surface | owner |
|---|---|---|
| delegation read (all three panels) | **unconfirmed** — persist's `delegates_to` relation shipped (the pruned gate `PERSIST_DELEGATES_TO` in #45 says so), but ciris-server 0.5.199 exposes no `/v1/delegat*` route; the client reads it through its substrate binding. Asked on #45 which. | CIRISClient / CIRISPersist |
| grant ceremony | **unconfirmed** — `/v1/federation/peers/{key_id}/trust` is the plausible write; not asserted | CIRISServer |

## 4. Flow (how)

<!-- flow: tools/qa_runner/flows/delegation_card.yaml -->
```yaml
flow: delegation_card
title: Delegation card and screen on the Family layer
description: >-
  CIRISClient#45 wired DelegationScreen and reached it from the Family layer hub.
  This drives the whole surface: the card is present on the hub, it opens, the
  screen composes its three panels, refresh is live, and back returns to the hub.
# CIRISClient#45 is unmerged (2026-09-08): NO release carries this surface, so the
# flow is refused as "cannot start" rather than driven into "element not found".
# Replace with ">=<release>" when #45 ships. A numeric floor was tried first and
# stopped refusing on the next client cut (0.5.213), turning these into binding
# verdicts against a client that still lacks the screens.
client: "unreleased"

steps:
  - step_id: family_hub
    title: The Family layer hub shows the delegations card
    description: >-
      Entry precondition, stated rather than assumed. If the flow is not here the
      failure is "this flow cannot start", not "a delegation element is broken" —
      which is the distinction CIRISClient#39 was opened about.
    requires:
      screen: LayerFamily
    expect:
      visible: [card_family_delegations, btn_open_delegations]

  - step_id: open_delegation
    title: Opening the card reaches the Delegation screen
    do:
      - click: btn_open_delegations
    expect:
      screen: Delegation
      visible: [screen_delegation, btn_delegation_back]

  - step_id: delegation_panels
    title: The screen composes overview, inbound and outbound
    description: >-
      Asserted as three separate tags rather than one screen check: a screen that
      renders its shell and none of its content still answers /screen correctly.
    expect:
      visible:
        - card_delegation_overview
        - card_delegation_inbound
        - card_delegation_outbound
        - btn_delegation_manage_grants

  - step_id: refresh_is_live
    title: Refresh runs without leaving the screen
    description: >-
      The screen is described as live/interactive, so refresh must be a real
      action. Asserting we are still on Delegation afterwards is what separates
      "it refreshed" from "it navigated away or crashed to a fallback".
    do:
      - click: btn_delegation_refresh
    expect:
      screen: Delegation
      visible: [card_delegation_overview]

  - step_id: back_to_family
    title: Back returns to the Family layer hub
    do:
      - click: btn_delegation_back
    expect:
      screen: LayerFamily
      visible: [card_family_delegations]
      absent: [screen_delegation]
```

## 5. QA plan

### Platforms

All five. The card is common-code; nothing in it is platform-conditional.

### How to run

```
python -m tools.qa_runner.modules.web_ui flow --spec tools/qa_runner/flows/delegation_card.yaml --platform <desktop|android|ios>
```

### Results — in the UI and in the log

Per step: a console line (`[OK]` with the held condition and duration, or `[FAIL]`
naming the phase — `requires` / `do` / `expect` — the predicate, and the tags on
screen and drivable now); a screenshot at `artifacts/shots/flow-delegation_card-<step_id>.png`
rendered in the five-platform gallery; a row in `artifacts/flows/delegation_card.json`.

### Acceptance

**Functional**
1. From the Family layer hub a person can open Delegation, see three populated
   panels, refresh, and return to the hub they came from.

**Tests** (the flow)
* `family_hub` — the card and its entry are on screen on the hub.
* `open_delegation` — the entry reaches `Delegation`, whose root and back control
  are on screen.
* `delegation_panels` — three panels **and** the grant entry are on screen, asserted
  as four tags, because a shell that renders no panel still answers `/screen`.
* `refresh_is_live` — refresh leaves the screen where it was, with the overview
  still present.
* `back_to_family` — back lands on `LayerFamily` **and** `screen_delegation` is gone.

**Untested and must be established**
* Panel *contents*. The flow asserts the panels compose; it does not assert what
  they say. A `text:` predicate needs a known fixture (a node with one inbound and
  one outbound grant) before it can be written honestly.
* The grant ceremony behind `btn_delegation_manage_grants`. Its own CSD.
* ~~The navigation hop **to** `LayerFamily`.~~ The runner reaches it through the
  sidebar before the flow starts — `nav_epistemic_layer_family`, which is the
  client's own rule (EpistemicSidebar.kt `navTag`: surface id `layer-family`,
  EpistemicNav.kt), not a guess — and `family_hub`'s `requires` asserts arrival.
