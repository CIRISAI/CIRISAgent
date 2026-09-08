# CSD-002 — Environment page (Local Community layer)

**CSD**: CSD-002
**Version**: 1.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2026-09-07
**Flow**: tools/qa_runner/flows/environment_card.yaml
**Client floor**: >0.5.212
**Origin**: CIRISClient#45
**Standard**: `FSD/CSD_STANDARD.md`

## 1. Mission (why)

**A user can now open the environment graph their local community is embedded in,
from that community's own hub, and get back.** Before #45 `Screen.EnvironmentInfo`
existed and nothing reached it. Serves **Integrity** — a cohort that can see its
environment can reason about it — and the plain rule that an entry with no exit is
a trap.

## 2. Surface (what)

### Screens

| screen | reached from | leaves to |
|---|---|---|
| `LayerLocalCommunity` | the Local Community layer hub | — |
| `EnvironmentInfo` | `btn_open_environment` on `card_local_community_environment` | back → `LayerLocalCommunity` (wired in #45; **tag not named**) |

### Tags

| tag | kind | guaranteed by |
|---|---|---|
| `card_local_community_environment` | card on the hub | CIRISClient#45 |
| `btn_open_environment` | entry | CIRISClient#45 |

### Collects / shows

| field | source (§3) | required |
|---|---|---|
| environment graph | environment read | shows |

### Writes

Nothing.

## 3. Contracts (who)

| value | endpoint / surface | owner |
|---|---|---|
| environment graph | **unconfirmed** — `NavSurface.EnvironmentGraph` was added in #45; the read it drives is not named there | CIRISClient |

## 4. Flow (how)

This CSD is the worked example of the standard's §3.4 last rule. #45 wired
back-navigation from `EnvironmentInfo` to `LayerLocalCommunity` but did not name the
tag. The return step is written out **in a comment in the flow file** with the tag
left blank, and the question is on #45. It is not guessed, because a guessed tag
succeeds at the click and fails twenty seconds later on an element that was never
going to render.

<!-- flow: tools/qa_runner/flows/environment_card.yaml -->
```yaml
flow: environment_card
title: Environment page from the Local Community layer hub
description: >-
  CIRISClient#45 made Screen.EnvironmentInfo reachable from the LOCAL_COMMUNITY
  layer hub and wired its back navigation. Both directions are asserted: an
  entry that cannot be left is a trap, and it is the half that usually ships
  broken because nobody drives it twice.
# CIRISClient#45 is unmerged (2026-09-08): no released client carries this surface.
# Bump to the release that ships #45 when it is cut; until then every released
# client is refused as "cannot start" rather than driven into "element not found".
client: ">0.5.212"

steps:
  - step_id: local_community_hub
    title: The Local Community hub shows the environment card
    requires:
      screen: LayerLocalCommunity
    expect:
      visible: [card_local_community_environment, btn_open_environment]

  - step_id: open_environment
    title: Opening the card reaches the Environment page
    do:
      - click: btn_open_environment
    expect:
      screen: EnvironmentInfo

  # THE RETURN LEG IS NOT WRITTEN YET, DELIBERATELY. CIRISClient#45 says back
  # navigation from EnvironmentInfo to LayerLocalCommunity was wired, but it does
  # not name the tag, and this file must not contain a tag nobody has confirmed.
  # Guessing one is the exact defect CIRISClient#39 was opened about: the click
  # would succeed against something, and the flow would fail twenty seconds later
  # on an element that was never going to render. Asked on #45; the step lands
  # here, unchanged in shape, the moment the tag is named:
  #
  #   - step_id: back_to_local_community
  #     title: Back returns to the Local Community hub, not to the root
  #     do:
  #       - click: <the back tag>
  #     expect:
  #       screen: LayerLocalCommunity
  #       visible: [card_local_community_environment]
```

## 5. QA plan

### Platforms

All five.

### How to run

```
python -m tools.qa_runner.modules.web_ui flow --spec tools/qa_runner/flows/environment_card.yaml --platform <desktop|android|ios>
```

### Results — in the UI and in the log

Per step: a console line (`[OK]` with the held condition and duration, or `[FAIL]`
naming the phase — `requires` / `do` / `expect` — the predicate, and the tags on
screen and drivable now); a screenshot at `artifacts/shots/flow-environment_card-<step_id>.png`
rendered in the five-platform gallery; a row in `artifacts/flows/environment_card.json`.

### Acceptance

**Functional**
1. From the Local Community hub a person can open the Environment page.
2. From the Environment page a person can return to the Local Community hub — not
   to the root, and not to a different layer.

**Tests** (the flow)
* `local_community_hub` — the card and its entry are on screen.
* `open_environment` — the entry reaches `EnvironmentInfo`.

**Untested and must be established**
* **Functional 2, entirely.** The return leg is the half that ships broken (back
  wired to the default destination rather than the hub it was opened from) and it
  is the half this flow cannot yet drive. It lands the moment the tag is named.
* What the page shows. No `text:` predicate until the graph's read is named.
