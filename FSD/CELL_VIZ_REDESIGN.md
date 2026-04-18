# Cell Visualization Redesign — Interact Screen

**Status**: In progress. Steps 1 + 2 of 10 complete on `feature/cell-viz-redesign`.
**Branch base**: `release/2.5.3`
**Context window**: Drafted while the live session was still hot. Treat as the
canonical handoff document — anything not captured here is lost when the
conversation is compacted.

---

## 1. Motivation

The current Interact screen renders a rotating 3D cylinder (memory graph
nodes + H3ERE pipeline scaffolding rings + adapter orbit satellites). It is
visually striking but does not *represent* what the agent is. It is a
decoration around a chat window.

The agent actually has:

- **6 message buses** (nervous system pathways)
- **22 services** (organs with specific functions)
- **A memory graph** (what it knows)
- **An H3ERE pipeline** (its cycle of thought)
- **Adapters** as gates to the outside world
- **Tools** as things the agent can do
- **Comms channels** — concurrent conversations (Discord users, HA sensors,
  API callers). This is the dimension the current UI collapses entirely.
- **Cognitive state** (WAKEUP/WORK/PLAY/SOLITUDE/DREAM/SHUTDOWN)
- **Real situation** (time, weather, location, system resource pressure)

The redesign expresses all of the above as a single living thing — a **cell**
suspended in a medium — with every visible element carrying meaning.

### Hard constraint: 32-bit ARM

CIRIS deploys in Ethiopia on low-end Android phones (many still 32-bit). The
old cylinder runs acceptably there. A canvas-heavy cell viz will not.

**Resolution**: gate the new viz behind 64-bit + ≥4 GB RAM. Devices below
that bar keep rendering the legacy `LiveGraphBackground` unchanged, as an
orphaned code path. No compromises in the new design to accommodate the
low-end.

Users can also force the classic path via a Settings toggle regardless of
device capability (accessibility / motion sensitivity / regression isolation).

---

## 2. Design — The Cell

Looking through a microscope at a single cell in its medium:

- **Cell wall (membrane)** — boundary of the being. Six arcs, one per bus
  (60° each). When a bus carries traffic, its arc glows.
- **Nucleus** (center) — the H3ERE pipeline. Seven concentric shells,
  THINK to ACT innermost to outermost. Small (~60 px). Pulses when a
  thought cycles. Much smaller than the current rings; thinking is local.
- **Cytoplasm** (between nucleus and wall) — memory graph as drifting
  motes. Golden-angle scatter, not cylindrical. Clustered by scope.
- **Organelles** — 22 services as distinct small shapes (hex/circle/
  square/triangle/diamond/pentagon) fixed inside the cell.
- **Adapter ports** — embedded in the cell wall at their owning bus's
  segment. Diamond / hexagon shapes, read-and-tap sized. Replace floating
  orbit satellites entirely.
- **Pseudopods** — communication channels. Each open channel extends a
  bezier thread from the CommunicationBus segment outward to a tip dot
  (correspondent). Fans out on tap to individual threads when clustered.
- **Medium** — environment as ambient tint. Time-of-day, weather, system
  pressure shape the background.
- **Cognitive state** — cell metabolism. WORK = gentle drift; PLAY =
  faster, warmer; SOLITUDE = thins/slows; DREAM = violet, strange;
  SHUTDOWN = contraction + fade.
- **WiseAuthority** — a smaller companion cell off-axis; a thread reaches
  to it when WiseBus fires; a visible packet travels back on guidance.

### Bus ring assignment (load-bearing, do not rearrange)

| Bus | Arc | Color | Rationale |
|---|---|---|---|
| Wise | 240–300° | `#c9a52a` amber | top-left, elder/consultation direction |
| Runtime | 300–360° | `#d8554e` red | top-right, autonomic / brainstem |
| Tool | 0–60° | `#d98a2d` orange | right, "hand" / action surface |
| LLM | 60–120° | `#3d86d9` blue | bottom-right, cortex / reasoning inflow |
| Memory | 120–180° | `#8b5fd6` purple | bottom, accreted past |
| Communication | 180–240° | `#2da89c` teal | bottom-left, where most pseudopods reach |

### Two interaction modes (ZUI pattern)

- **Background (default)**: cell lives under the chat; messages flow over
  it; chronological layout, bubbles on top. Nothing is tappable except
  the VIZ FG button. Ambient + noticed events only. Labels hidden.
- **Foreground**: cell expands to fullscreen, chat drawer. Every element
  tappable. Pseudopods open channel detail, adapter ports open adapter
  detail, clusters fan out. Labels visible with stroke-first halo. Only
  mode where Demanding-tier events and cluster fan-out render in full.

---

## 3. Events — three tiers, one primitive each

Research on glanceable/ambient displays (severity-tiered treatment) maps to
our event taxonomy:

| Tier | CIRIS events | Visual primitive | Duration |
|---|---|---|---|
| **Ambient** | bus traffic | alpha shimmer on bus arc, amplitude 0.6→1.0 | continuous while active |
| **Noticed** | new memory mote, pipeline tick, channel open | one 600ms beat — fade-in + single halo pulse | 600ms |
| **Demanding** | DEFER to WA, adapter error, conscience reject | color shift + hold until acknowledged | persistent |

### Explicitly cut from the mockup

- `tendril-flow` dashed-line animation on active pseudopods (too busy)
- `breathe` scale animation on the whole cell (rotation + gradient is enough)
- Overly large mote drift (reduce `±10px` → `±3px`)
- "SWIPE TO SPIN" hint on the canvas (moved to the help/legend dialog)

---

## 4. Rationale for key choices

**Why non-anthropic?** Giving the agent a face or body-shape invites users
to pattern-match it to a person, then feel confused when it does non-person
things. A cell is clearly alive and clearly not a person. Matches CIRIS's
stance as an ethical AI platform that is *a being, not a mirror of a human*.

**Why shrink the pipeline?** Thinking is a temporary local event; memory
and body are durable. The current design makes the pipeline the frame
around everything, visually implying it's the most permanent feature. A
tiny pulsing nucleus matches the physical truth: a short event inside a
larger living thing.

**Why buses as the membrane?** Only six services in CIRIS use the bus
registry pattern. They are genuinely the connective tissue — the places
where multi-provider plurality exists. Making them the boundary of the
cell asserts their architectural role visually.

**Why hide labels in BG mode?** Glanceable-display research: labels
clutter when they're not the focal task. In BG the user is chatting; the
pseudopod shape + tip dot already says "something lives here." Labels
are an FG feature, unlocked when the user chooses to inspect.

**Why `withFrameNanos` over tween?** Single source of rotation truth lets
the upcoming swipe momentum, reduce-motion gate, spin-apart pause, and
velocity decay all compose from one variable. Tweens are keyframe-based
and can't cleanly pause or integrate delta-time velocity.

---

## 5. Build order (10 steps)

Each step is a standalone commit. Steps 1–2 done; 3–10 pending.

1. **Device capability gate + user override.** ✅
   - `CellVizCapability` expect/actual. Android: 64-bit + ≥4 GB. iOS:
     ≥3 GB. Desktop: always capable.
   - Settings toggle "Use classic visualization" (forceClassicViz key).
   - Plumbed: SettingsVM → CIRISApp → InteractScreen.forceClassicViz.
   - Gate formula: `useCellViz = capable && !forceClassicViz`.
   - Both branches of the gate currently render `LiveGraphBackground`
     (scaffold only — no visible change).
2. **Rotation source refactor.** ✅
   - `infiniteTransition.animateFloat` tween → `withFrameNanos` driver,
     6°/sec baseline (matches old 60s/rev exactly).
   - Single `var autoRotationY` can be reused by cell viz.
   - `autoTiltX` and `birthPulse` stay as tweens.
3. **Cell skeleton — membrane + static adapter ports.** *(next)*
   - New `CellVisualization` composable, selected when `useCellViz=true`.
   - Draw 6 bus arcs (static, inactive color).
   - Anchor adapter ports at their owning bus's arc segment by type.
   - First visible change.
4. **Shrink pipeline to nucleus.** Move H3ERE rings to center, reduce
   radius to ~60 px. Same pulse logic.
5. **Cytoplasm motes.** Replace cylindrical node layout with 2D
   golden-angle scatter + small-amplitude drift.
6. **Tier-1 events: bus-arc shimmer + bus-pulse on SSE.** Route SSE
   event types to bus segments (memory→MemoryBus, llm→LLMBus, etc.).
7. **Pseudopods** for comms channels. BG: no labels. FG: labels with
   stroke-first halo. Bezier from Communication arc to tip node.
8. **Tier-2 events**: new-mote halo, pipeline shell pulse, channel-open
   animation. 600ms each, one primitive.
9. **Tier-3: DEFER thread to WA companion cell.** The one bespoke
   event animation.
10. **BG↔FG zoom transition.** 400ms morph; the one "sexy" animation
    the user triggers.

---

## 6. Decisions that stay (don't re-litigate)

- **Cell metaphor over jellyfish, coral, plant, hive, constellation.**
  Cell is intuitive (middle-school vocabulary), non-anthropic,
  volumetric, matches the egg silhouette already present.
- **Server is source of truth.** Client holds only live events + what
  the user explicitly pinned (caught bubbles). Bounded memory. Ethiopia
  constraint informed this, but it's now the design.
- **No force-directed graph layout** inside the cell. Deterministic
  golden-angle scatter for organelles, random-seeded drift for motes.
  Force simulation code stays for the non-Interact graph screen.
- **Simple is better.** The baseline scene is rich; events are restrained.
  One animation primitive per severity tier.
- **BG mode hides labels.** Full stop. Not collision-avoidance, not
  fading — *hidden*. Labels are an FG feature.

---

## 7. Stateful bubble-as-carrier pattern (applies across the rework)

Pattern already landed, keep:
- `ReasoningEvent.Emoji.payload: String?` — hard-capped at
  `PAYLOAD_MAX_CHARS=160` at SSE parse time.
- `extractPayload(eventType, eventJson)` pulls one compact line per
  event type.
- `BubbleEmoji.payload` lives for the bubble's 2s flight window.
- `catchBubble(id)` promotes an in-flight bubble into the `caughtBubbles`
  list (MAX_CAUGHT_BUBBLES = 12, ~1.9 KB worst case).
- `CaughtBubblesPanel` renders the pinned list in the top-right.

In the cell design this pattern re-homes: pseudopods can carry an
ephemeral payload per event, and tapping a pseudopod promotes the event
to a pinned drawer. Same memory budget.

---

## 8. Experiments that will be replaced (commit sequence housekeeping)

The current branch contains experimental code from a prior round that
won't survive into the final cell viz:

- `LiveGraphBackground.adapterOrbits` rendering (`drawAdapterOrbits`,
  `AdapterOrbit`, `orbitFor`) — obsolete. Adapter ports in cell viz
  replace it. Legacy branch already strips these args; new viz will
  not use the helpers. Can delete once step 7 lands.
- `cognitiveState` param + state-posture modulation in
  `LiveGraphBackground` — was an experiment against the cylinder.
  The cell will carry state differently (metabolism analogy, not
  per-frame angle multiplier). Preserve the *idea* in step 8/9
  discussions; delete the code when cell viz stabilizes.
- Desktop-first `desktop-up` orchestration in
  `tools/qa_runner/modules/web_ui/__main__.py` — useful, keep. Not
  part of cell viz but a repeatable path to get a clean logged-in
  desktop with admin credentials.

---

## 9. Bugs fixed along the way (independent of cell viz)

These are unrelated wins that surfaced during the investigation and
should ship with the redesign branch:

- **`_try_refresh_adapter_location` never matched running adapters.**
  It indexed `loaded_adapters` by bare type name (`"weather"`) but
  keys are `{type}_{hash}`. Fixed to scan instances by
  `adapter_type`. Was silently breaking weather/navigation adapter
  location-refresh after `/v1/setup/location` calls.
  → `ciris_engine/logic/adapters/api/routes/setup/location.py:341`
- **Weather only supported NOAA (US-only) + OWM (needs API key).**
  Added Open-Meteo fallback — free, no key, worldwide. Context
  enrichment now populates for international users (Ethiopia
  deployment now works out of the box).
  → `ciris_adapters/weather/service.py:590+`
- **`ServerManager` didn't accept `SETUP` cognitive state as "ready"
  in first-run mode.** Caused the desktop-up flow to time out waiting
  for WORK. Fixed by adding `is_setup` branch in first-run mode.
  → `tools/qa_runner/modules/web_ui/server_manager.py:339`

---

## 10. Files in play (branch scope)

### New
- `mobile/shared/src/commonMain/.../platform/CellVizCapability.kt`
- `mobile/shared/src/androidMain/.../CellVizCapability.android.kt`
- `mobile/shared/src/iosMain/.../CellVizCapability.ios.kt`
- `mobile/shared/src/desktopMain/.../CellVizCapability.desktop.kt`
- `FSD/CELL_VIZ_REDESIGN.md` (this file)
- `FSD/cell_viz_mockups/viz_cell_mockup.html`, `FSD/cell_viz_mockups/viz_interact_mockup.html` (reference mockups)

### Modified
- `mobile/androidApp/.../MainActivity.kt` — `initCellVizProbe`
- `mobile/shared/.../CIRISApp.kt` — plumb `forceClassicViz`
- `mobile/shared/.../viewmodels/SettingsViewModel.kt` — forceClassicViz flow
- `mobile/shared/.../ui/screens/SettingsScreen.kt` — toggle UI
- `mobile/shared/.../ui/screens/InteractScreen.kt` — gate + help gestures section
- `mobile/shared/.../ui/screens/graph/LiveGraphBackground.kt` — rotation refactor
- `mobile/shared/.../viewmodels/InteractViewModel.kt` — bubble payload / caught
- `mobile/shared/.../api/ReasoningStreamClient.kt` — extractPayload
- `ciris_adapters/weather/service.py` — Open-Meteo fallback
- `ciris_engine/logic/adapters/api/routes/setup/location.py` — refresh fix
- `tools/qa_runner/modules/web_ui/__main__.py` — `desktop-up` command
- `tools/qa_runner/modules/web_ui/server_manager.py` — SETUP-state readiness

### Out of scope — do not include
- Local FFI library workaround (`libciris_verify_ffi.so.linux-x86_64.bak`)
  — macOS dev machine artifact only.
- Ad-hoc screenshots in repo root.

---

## 11. How to resume

```bash
git checkout feature/cell-viz-redesign
python3 -m tools.qa_runner.modules.web_ui desktop-up --mock-llm
# Backend + desktop come up fresh; admin/qa_test_password_12345
```

After login, the gate logs on boot:
```
[InteractScreen] cell-viz gate: useCellViz=<bool> (capable=<bool>,
    forceClassic=<bool>, ram=<N>GB, reason=<...>)
```

Resume at **Step 3: Cell skeleton**. Everything prior is committed and
verified baseline-unchanged.
