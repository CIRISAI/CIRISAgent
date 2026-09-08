# CSD-003 — Constitutional screen and the Accord cards

**CSD**: CSD-003
**Version**: 1.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2026-09-07
**Flow**: tools/qa_runner/flows/constitutional_card.yaml
**Client floor**: >0.5.212
**Origin**: CIRISClient#45
**Standard**: `FSD/CSD_STANDARD.md`

## 1. Mission (why)

**A user can now see whether the halt authority is armed, who holds the Accord,
and reach the ceremony and provisioning entry points — on one screen.** The
killswitch card is the reason this CSD is not optional: it is the surface of CC
4.2 *halt authority* ("no objective can outvote it"), one of the three claims
CIRISServer#536 names as load-bearing on the public /safety page. A safety surface
that silently fails to render is worse than one that is absent, because absence is
at least visible. Serves **Core Identity** and **Integrity**.

## 2. Surface (what)

### Screens

| screen | reached from | leaves to |
|---|---|---|
| `Constitutional` | `NavSurface.Constitutional` (ungated in #45) | `btn_constitutional_back` |

### Tags

| tag | kind | guaranteed by |
|---|---|---|
| `screen_constitutional` | screen root | CIRISClient#45 |
| `btn_constitutional_back` | navigation | CIRISClient#45 |
| `btn_constitutional_refresh` | action, live | CIRISClient#45 |
| `card_constitutional_overview` | panel | CIRISClient#45 |
| `card_accord_killswitch` | panel — **safety** | CIRISClient#45 |
| `card_accord_holders` | panel | CIRISClient#45 |
| `btn_open_accord_ceremony` | entry | CIRISClient#45 |
| `btn_open_provision_holder` | entry | CIRISClient#45 |

### Collects / shows

| field | source (§3) | required |
|---|---|---|
| overview — trust root, this node's holder record | trust-root + holder reads | shows |
| killswitch — halt status | halt-status read | shows |
| holders — the Accord holder set | holders read | shows |

### Writes

Nothing on this screen; both entries open ceremonies that do.

## 3. Contracts (who)

Confirmed against ciris-server 0.5.199's route table (the pinned wheel).

| value | endpoint / surface | owner |
|---|---|---|
| trust root | `/v1/trust-root` | CIRISServer |
| this node's holder record | `/v1/accord/holder` | CIRISServer |
| halt status (killswitch) | `/v1/accord/halt-status` | CIRISServer |
| holder set | `/v1/accord/holders` | CIRISServer |
| ceremony entry | `/v1/accord/provision` | CIRISServer |
| provision-holder entry | `/v1/accord/provision-holder` | CIRISServer |

## 4. Flow (how)

<!-- flow: tools/qa_runner/flows/constitutional_card.yaml -->
```yaml
flow: constitutional_card
title: Constitutional screen and its Accord cards
description: >-
  CIRISClient#45 implemented ConstitutionalScreen with the killswitch and holders
  cards. The killswitch card is the reason this flow is not optional: it is a
  safety surface, and a safety surface that silently fails to render is worse
  than one that is absent, because the absence is at least visible.
# CIRISClient#45 is unmerged (2026-09-08): no released client carries this surface.
# Bump to the release that ships #45 when it is cut; until then every released
# client is refused as "cannot start" rather than driven into "element not found".
client: ">0.5.212"

steps:
  - step_id: constitutional_screen
    title: The Constitutional screen composes its overview
    requires:
      screen: Constitutional
    expect:
      visible: [screen_constitutional, card_constitutional_overview, btn_constitutional_back]

  - step_id: accord_cards
    title: Killswitch and holders cards are both present
    expect:
      visible: [card_accord_killswitch, card_accord_holders]

  - step_id: accord_entry_points
    title: The ceremony and provision entry points are offered
    expect:
      visible: [btn_open_accord_ceremony, btn_open_provision_holder]

  - step_id: refresh_is_live
    title: Refresh runs without leaving the screen
    do:
      - click: btn_constitutional_refresh
    expect:
      screen: Constitutional
      visible: [card_accord_killswitch]
```

## 5. QA plan

### Platforms

All five.

### How to run

```
python -m tools.qa_runner.modules.web_ui flow --spec tools/qa_runner/flows/constitutional_card.yaml --platform <desktop|android|ios>
```

### Results — in the UI and in the log

Per step: a console line (`[OK]` with the held condition and duration, or `[FAIL]`
naming the phase — `requires` / `do` / `expect` — the predicate, and the tags on
screen and drivable now); a screenshot at `artifacts/shots/flow-constitutional_card-<step_id>.png`
rendered in the five-platform gallery; a row in `artifacts/flows/constitutional_card.json`.

### Acceptance

**Functional**
1. A person on the Constitutional screen can see the halt authority's status and
   the holder set, and can reach both ceremonies.

**Tests** (the flow)
* `constitutional_screen` — root, overview and back are on screen.
* `accord_cards` — killswitch **and** holders are on screen.
* `accord_entry_points` — both entries are on screen.
* `refresh_is_live` — refresh leaves the screen where it was, killswitch still present.

**Untested and must be established**
* **The killswitch card's content.** The flow proves the card composes; it does not
  prove it says *armed* when the authority is armed. That needs a `text:` predicate
  against `/v1/accord/halt-status` on a known fixture, and it is the single most
  important assertion this CSD does not yet make. Track with CIRISServer#536 (4.2).
* Either ceremony. Their own CSDs.
* ~~The hop to `Constitutional`.~~ The runner reaches it before the flow starts:
  `Constitutional` is a child of `LayerGlobalCommons` in the sidebar
  (EpistemicNav.kt), so the parent is reached first (`nav_epistemic_layer_global_commons`,
  which expands it) and then `nav_epistemic_constitutional`; `constitutional_screen`'s
  `requires` asserts arrival.
