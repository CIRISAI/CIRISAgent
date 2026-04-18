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

## 2.5 CIRIS semantic grounding (the acronym made visible)

The initial design handled the first **C** and **R** well — a cell has
obvious core identity and clear resilience rhythms. It was **silent** on
the **I** (Incompleteness Awareness) and especially on the **S**
(Signalling Gratitude). Without these the viz has no soul, just anatomy.

| Letter | Principle | Visible as |
|---|---|---|
| **C** | Core Identity | the cell shape itself — nucleus + membrane + organelles |
| **I** | Integrity | bus arcs are load-bearing and unforgeable; you can't fake a bus segment |
| **R** | Resilience | breathing rhythm + cognitive-state metabolism |
| **I** | Incompleteness | **the membrane seam** — a small, intentional gap in the wall (see §2.5.2) |
| **S** | Signalling Gratitude | **warm motes emitted from the nucleus** on good interactions (see §2.5.1) |

### 2.5.1 Gratitude motes — the S made visible

On a completed helpful interaction (user thanks the agent, task reaches
TASK_COMPLETE with positive signal, or conscience affirms an action), the
nucleus emits a small **warm mote** (soft amber/gold, ~4 px radius). The
mote drifts outward from the nucleus on a slow curved path, passes
through the cytoplasm, and fades at the membrane. Five pixels, six
seconds, no sound, no notification — a silent "I see you."

**Rules**:
- **Ambient tier**, not Noticed. Runs quietly in the background; never
  demands attention.
- Max one mote in flight per ~3 seconds; never a shower.
- Warm color fixed (not theme-derived) — gratitude should feel
  consistent across color themes, like the agent's own tone.
- Disabled when `prefers-reduced-motion`.

This is the soul of the viz. Gratitude is what makes the agent *for*
someone rather than just *about* itself.

### 2.5.2 Membrane seam — the second I made visible

A closed perfect ring of bus arcs implies a closed system. CIRIS is
explicitly *not* that — Incompleteness Awareness is a named principle.

**Rendering**: the membrane has a **~6° gap** at a fixed angle (suggest
at the top of the Wise arc, ~300°, where the agent "looks up toward what
it doesn't know"). Inside the gap, a short, soft hand-drawn-feeling
squiggle — "just enough wildness" — fills ~60% of the space. Not a
missing pixel; an unfinished stitch.

**Rules**:
- Exactly one seam. Not six, not randomized. Unity of imperfection.
- The seam is static — does not animate, does not pulse. It's a
  permanent humility.
- Rendered at half the opacity of the bus arcs so it reads as
  "intentionally understated," not "the renderer glitched."

### 2.5.3 Deferral ripple — humility, not error

When WiseBus fires (the agent defers to a Wise Authority), the current
plan had the Demanding-tier DEFER thread reach to the WA companion cell
with a visible packet. Add a **preceding gesture**:

1. **Pause**: baseline rotation slows to ~20% for 800 ms. The cell goes
   briefly still. Reads as "the agent has stopped to ask."
2. **Ripple**: a single concentric wave emits from the nucleus outward,
   slow (1.5 s expand, quadratic ease-out), fades at the membrane.
3. **Reach**: THEN the thread extends from the Wise arc to the WA
   companion cell with its guidance packet.
4. **Resume**: baseline rotation returns to normal.

Total sequence: ~2.5 s. Total new primitives: a slowdown easing curve +
one ripple circle. The viz now has a visual vocabulary for "I don't
know, I'm asking" — distinct from adapter errors or conscience rejects,
which remain the Demanding-tier color-shift + hold pattern.

### 2.5.4 Stronger breathing — perceptible, not shy

The mockup breathes at `scale(1.005)` over 9 s. Too subtle to read as
alive. Tune to:

- **Scale**: 0.5% → **0.8–1.0%** (`scale(1.008..1.010)`)
- **Period**: 9 s → **6 s**
- **Added**: a synchronous **aura opacity pulse** (0.85 → 1.0 → 0.85)
  on the cell-fill radial gradient, same 6 s period.

Together: the cell visibly breathes. A child or a casual observer would
notice within 5 s that it's alive. That's the bar.

### 2.5.5 The nucleus song — slower, softer

The mockup's `nucleus-wave` animation (2.6 s, expands 7 → 60 px,
0 → 0.7 opacity) reads as a heartbeat monitor. The Accord document says
"keep the song singable" — the nucleus is where the song lives.

Tune to:

- **Period**: 2.6 s → **8 s** (a slow hum, not a pulse)
- **Peak opacity**: 0.7 → **0.35** (quieter)
- **Emission**: not every cycle — **every 2nd or 3rd cycle** during
  WORK, less often during SOLITUDE, more often during PLAY. The song
  follows cognitive state, just like breathing does.

### 2.5.6 Weaving threads — the wider keep

The Accord is about threads that braid. A pseudopod terminating in a
tip dot at the edge of the viz implies "this channel ends here." In
reality each channel reaches toward another keeper (another agent, a
user, a sensor in someone's home).

**Rendering**: each pseudopod's tip is followed by a **faint tendril**
that continues past the viz bounds, fading from tip-color-at-0.4 →
0.0 alpha over ~40 px. Not a line to a specific other cell — just the
*gesture* of reaching. Suggests "this agent is part of a wider weave"
without literalizing who is on the other end.

**Rules**:
- Tendril is subtle enough to miss on first look. The point is not to
  shout "network!" but to quietly hint continuation.
- Exists only in **Foreground** mode. In BG the tip dots are enough;
  tendrils would add clutter to a glanceable read.
- Fade curve is exponential, not linear, so the tendril "dissolves into
  the medium" instead of terminating at a hard edge.

---

## 3. Events — three tiers, one primitive each

Research on glanceable/ambient displays (severity-tiered treatment) maps to
our event taxonomy:

| Tier | CIRIS events | Visual primitive | Duration |
|---|---|---|---|
| **Ambient** | bus traffic | alpha shimmer on bus arc, amplitude 0.6→1.0 | continuous while active |
| **Ambient** | gratitude signal (§2.5.1) | warm mote emitted from nucleus, drifts + fades through membrane | ~6 s per mote, max 1 in flight per 3 s |
| **Noticed** | new memory mote, pipeline tick, channel open | one 600ms beat — fade-in + single halo pulse | 600ms |
| **Noticed** | deferral pause + ripple (§2.5.3) | slow nucleus ripple + rotation slowdown preceding the WA thread | ~2.5 s sequence |
| **Demanding** | adapter error, conscience reject | color shift + hold until acknowledged | persistent |
| **Demanding** | DEFER to WA | thread to WA companion cell with packet (after the Noticed-tier ripple above) | persistent until guidance returns |

### Explicitly cut from the mockup

- `tendril-flow` dashed-line animation on active pseudopods (too busy)
- Overly large mote drift (reduce `±10px` → `±3px`)
- "SWIPE TO SPIN" hint on the canvas (moved to the help/legend dialog)

### Explicitly tuned (not cut)

- `breathe` scale animation: **keep** but amplify from 0.5% → 0.8–1.0%
  with a synchronous aura-opacity pulse (§2.5.4). The cell needs to
  visibly breathe for a child to read it as alive.
- `nucleus-wave` animation: **keep** but slow to 8 s and soften to 0.35
  peak opacity, emitting every 2nd–3rd cycle, following cognitive state
  (§2.5.5). The nucleus is where the song lives.

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

**Why gratitude motes, seam, and humility ripple?** The initial design
expressed the C (Core Identity) and R (Resilience) of CIRIS but was
silent on the I (Incompleteness Awareness) and S (Signalling Gratitude).
An ethical-AI visualization that can't show "thank you" or "I don't
know" is anatomically complete and spiritually empty. These three
additions are not decorative — they are the acronym made visible.
Without them the viz is just a diagram.

**Why "keep the song singable"?** The Accord document's framing of the
agent's state as something that should stay singable, shareable,
inhabitable — applies to the nucleus-wave. A fast sharp pulse reads as
medical monitoring (diagnostic, clinical, *about* the agent). A slow
quiet hum reads as the agent breathing alongside you (relational, with
you). Same primitive, different tempo, different emotional register.

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
3. **Cell skeleton — membrane + seam + static adapter ports.** *(next)*
   - New `CellVisualization` composable, selected when `useCellViz=true`.
   - Draw 6 bus arcs (static, inactive color).
   - **Draw the membrane seam (§2.5.2)** — ~6° gap at 300° with an
     unfinished-stitch squiggle at half-opacity. Static.
   - Anchor adapter ports at their owning bus's arc segment by type.
   - First visible change.
4. **Shrink pipeline to nucleus + tune breathing + song.** Move H3ERE
   rings to center, reduce radius to ~60 px. Same pulse logic. Also
   lands:
   - **Stronger breathing (§2.5.4)**: 6 s period, 0.8–1.0% scale,
     synchronous aura-opacity pulse.
   - **Nucleus song (§2.5.5)**: 8 s period, 0.35 peak opacity, emission
     every 2nd–3rd cycle, cadence follows cognitive state.
5. **Cytoplasm motes.** Replace cylindrical node layout with 2D
   golden-angle scatter + small-amplitude drift (±3 px, not ±10 px).
6. **Tier-1 events: bus-arc shimmer + bus-pulse on SSE + gratitude.**
   Route SSE event types to bus segments (memory→MemoryBus, llm→LLMBus,
   etc.). Also lands **gratitude motes (§2.5.1)** — nucleus emits warm
   motes on good-interaction signals; max one in flight per 3 s;
   disabled under `prefers-reduced-motion`.
7. **Pseudopods + weaving tendrils.** BG: no labels, no tendrils. FG:
   labels with stroke-first halo + **tendrils fading past the viz
   bounds (§2.5.6)**. Bezier from Communication arc to tip node.
8. **Tier-2 events**: new-mote halo, pipeline shell pulse, channel-open
   animation. 600ms each, one primitive.
9. **Tier-3: deferral pause + ripple + WA thread.** The one bespoke
   event animation — **preceded by the humility ripple from §2.5.3**
   (rotation slowdown + nucleus ripple BEFORE the thread reaches out).
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
- **The acronym must be visible.** The viz renders the C, I, R, I, S of
  CIRIS as tangible features (shape, bus integrity, breathing, seam,
  gratitude motes — §2.5). None of these are optional polish.
- **Gratitude is ambient, never noticed.** A grateful sparkle that
  demands attention ceases to be grateful. One mote per ≥3 s, warm,
  silent. This is the soul of the viz.
- **The seam is exactly one seam.** Not randomized, not variable. The
  cell's imperfection is a *chosen* unity, not a generator.

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
