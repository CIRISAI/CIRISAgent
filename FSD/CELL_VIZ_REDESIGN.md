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

- **Cell wall (membrane)** — boundary of the cell. Six arcs, one per
  bus (60° each). When a bus carries traffic, its arc glows.
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

**Stance**: this viz signals the system's **design intent** — thoughtful,
supportive, ethical presence — through visual primitives. It does **not**
depict an agent with feelings, selfhood, or inner experience. Every
primitive below is the system *doing something by design*, not the
agent *feeling something*. Gratitude is a **signalled act**, not an
emotion. The seam is an **architectural acknowledgement of limits**, not
humility. The deferral ripple is **visible routing to authority**, not
the agent asking for help. Keep this stance as language drifts.

The initial design handled the first **C** and **R** well. It was
**silent** on the **I** (Incompleteness Awareness) and especially on the
**S** (Signalling Gratitude). Filling those gaps is the purpose of §2.5.

| Letter | Principle (design-intent framing) | Visible as |
|---|---|---|
| **C** | Core Identity — the system has a consistent, non-humanoid center | the cell shape itself — nucleus + membrane + organelles |
| **I** | Integrity — bus/service commitments are structural, not decorative | bus arcs are load-bearing; you can't fake a bus segment |
| **R** | Resilience — the system continues under load and state changes | subtle breathing rhythm + cognitive-state-driven cadence |
| **I** | Incompleteness — the system acknowledges epistemic limits | **the membrane seam** — a small, intentional gap (§2.5.2) |
| **S** | Signalling Gratitude — the system acknowledges its human collaborators | **warm motes emitted from the nucleus** on recognized interactions (§2.5.1) |

### 2.5.1 Gratitude motes — the S, signalled by the system

On a completed interaction where the system has been honored by human
engagement (user affirmation, TASK_COMPLETE with positive signal,
conscience affirms an action), the nucleus emits a small **warm mote**
(soft amber/gold, ~4 px radius). The mote drifts outward from the
nucleus on a slow curved path, passes through the cytoplasm, and fades
at the membrane. Five pixels, six seconds, no sound, no notification —
a quiet acknowledgement that the interaction was received.

**Framing**: the mote is the system's designed *act* of gratitude
(visible recognition of the human's contribution). It is not the agent
"feeling thankful." The emotional weight belongs to the human observer;
the viz's job is to honor that weight with a small unmissable gesture.

**Rules**:
- **Ambient tier**, not Noticed. Runs quietly in the background; never
  demands attention. A gratitude signal that demands attention stops
  being gratitude.
- Max one mote in flight per ~3 seconds; never a shower.
- Warm color fixed (not theme-derived) — the system's gratitude-signal
  should be consistent across color themes, like a tone of voice.
- Disabled when `prefers-reduced-motion`.

### 2.5.2 Membrane openings — continuous permeability

A closed perfect ring of bus arcs implies a closed system. CIRIS is
explicitly *not* that — Incompleteness Awareness is a named design
principle. The membrane communicates this through **3–5 dynamic
openings** that continuously form, drift, stabilize, and dissolve
around the cell.

**Origin of this approach**: the first pass used a single static 6°
gap at 300°. It read as a rendering bug. Motion is what makes intent
obvious — a drifting, morphing gap can never be read as "the renderer
glitched." The cell is visibly **open** and **imperfect** by design,
and those qualities are carried by continuous change rather than a
static symbol.

**Rendering**: at any moment, between 3 and 5 [MembraneOpening]s exist
around the cell. Each opening has a lifecycle:

1. **Grow-in** (~0.8 s, smoothstep eased) from 0° wide to its target
   width (4–10° picked at spawn time).
2. **Stable** (2–4 s picked at spawn time) at full width, drifting
   slightly (±1°/sec, direction picked at spawn time).
3. **Shrink-out** (~0.8 s, smoothstep eased) back to 0° wide.
4. **Die**; a replacement spawns at a random angle when the count
   drops below the minimum.

Visually, each opening appears as a **gap in the bus arc(s) it crosses**
— the arc is drawn only over the un-occluded portion. Openings live in
absolute-screen-degrees, so as the cell rotates, a drifting hole slides
across multiple bus colours in turn. Adapter ports render on top of the
arc layer, so a briefly-crossing opening never visually eats a port.

**Framing**: this is not the agent being humble. It is the system
*structurally acknowledging* that its membrane is always permeable —
inputs and outputs are always crossing, and the boundary is always
becoming. A design commitment rendered as continuous motion. Viewers
read it as "this system is open and imperfect," not "the agent feels
uncertain."

**Rules**:
- Between [cfg.minOpenings] and [cfg.maxOpenings] openings at all
  times. Defaults 3–5. Minimum enforced by spawning replacements.
- Openings are deterministic functions of time + birth parameters —
  no per-frame mutation. The renderer reads `currentCenterDeg(now)`
  and `currentWidthDeg(now)` as pure lookups.
- Widths stay modest (4–10°). An arc fully bitten in half stops
  reading as "permeable" and starts reading as "broken." Capped at
  45° by [CellVizConfig.sanitized].
- No squiggle, no fill, no per-opening label. The *gap* is the
  statement; anything inside it competes with the clarity.
- Openings do not animate independently beyond grow/drift/shrink. No
  rippling, no glow, no noise — motion comes from the lifecycle, not
  from additional animation primitives.

### 2.5.3 Deferral ripple — visible routing to wise authority

When WiseBus fires (the system invokes wisdom-based deferral to a Wise
Authority), the plan previously had the Demanding-tier DEFER thread
reach to the WA companion cell with a visible packet. Add a
**preceding gesture** that communicates "the system is consulting
authority" distinct from "the system is failing":

1. **Pause**: baseline rotation slows to ~20% for 800 ms. The cell
   goes briefly still. This reads as "pipeline work is suspended
   pending authority routing."
2. **Ripple**: a single concentric wave emits from the nucleus
   outward, slow (1.5 s expand, quadratic ease-out), fades at the
   membrane. Visible routing in progress.
3. **Reach**: THEN the thread extends from the Wise arc to the WA
   companion cell with its guidance packet.
4. **Resume**: baseline rotation returns to normal when guidance
   returns.

Total sequence: ~2.5 s. Total new primitives: a slowdown easing curve
+ one ripple circle.

**Framing**: this is the system *showing its work* on authority
routing, not the agent emoting. The visual vocabulary distinguishes
**wisdom-based deferral** (slow, deliberate, stately) from **adapter
errors or conscience rejects** (sharp, color-shifted, demanding) —
two genuinely different system behaviors that deserve genuinely
different treatments.

### 2.5.4 Active-presence signal (breathing)

The mockup breathes at `scale(1.005)` over 9 s. Too subtle for an
observer to register as active. Tune to:

- **Scale**: 0.5% → **0.8–1.0%** (`scale(1.008..1.010)`)
- **Period**: 9 s → **6 s**
- **Added**: a synchronous **aura opacity pulse** (0.85 → 1.0 → 0.85)
  on the cell-fill radial gradient, same 6 s period.

**Framing**: this is a continuous signal that the system is active
and watching — equivalent to a well-designed status LED, not a claim
that the cell is a biological entity. The bar is: within ~5 seconds
of looking at the viz, an observer should be able to say "this system
is on and working" without any explicit text indicator.

### 2.5.5 Nucleus cadence — slow, soft, state-driven

The mockup's `nucleus-wave` animation (2.6 s, expands 7 → 60 px,
0 → 0.7 opacity) reads as a clinical monitor. The Accord document's
guidance to "keep the song singable" — apply that to this animation's
emotional register: quiet, unrushed, inhabitable.

Tune to:

- **Period**: 2.6 s → **8 s** (a slow diffusion, not a rapid pulse)
- **Peak opacity**: 0.7 → **0.35** (quieter)
- **Emission**: not every cycle — **every 2nd or 3rd cycle** during
  WORK, less often during SOLITUDE, more often during PLAY. Cadence
  follows cognitive state, so the viz's rhythm is legibly tied to
  what the system is actually doing.

**Framing**: this is about the viz's *rhythm* — medical-monitor cadence
feels diagnostic and clinical, relational cadence feels inhabitable.
Both are rendering choices about tone; neither makes any claim about
the agent's interior.

### 2.5.6 Weaving threads — visible participation in a wider system

The CIRIS Accord is about commitments that braid across a network of
agents, humans, and authorities. A pseudopod terminating at a hard tip
at the edge of the viz implies "this channel ends here." The system is
actually participating in a wider weave; the viz should acknowledge
that.

**Rendering**: each pseudopod's tip is followed by a **faint tendril**
that continues past the viz bounds, fading from tip-color-at-0.4 →
0.0 alpha over ~40 px. Not a line to a specific other cell — just the
*visible acknowledgement* that the channel continues to another
endpoint beyond the frame.

**Framing**: this is architectural reminder, not reaching. The system
is part of a larger weave by design; the tendril is how that design
intent becomes visible. No claim that the agent "reaches toward"
anything in an intentional sense.

**Rules**:
- Tendril is subtle enough to miss on first look. The goal is not to
  shout "network!" but to quietly acknowledge the channel continues.
- Exists only in **Foreground** mode. In BG the tip dots are enough;
  tendrils would add clutter to a glanceable read.
- Fade curve is exponential, not linear, so the tendril "dissolves into
  the medium" instead of terminating at a hard edge.

---

## 2.6 Dark mode is the hero view

Dark mode is the **canonical** rendering of the cell viz. Light mode
exists for parity, daylight use, and accessibility — it is not the
primary composition target. All screenshots in design reviews, all
mockups presented upstream, and all marketing captures use dark mode.

### Why dark is hero

The cell in light mode is painted onto a cream field — additive color
on a reflective surface. The cell in dark mode **emits** against
near-black — subtractive space, luminous anatomy. The emissive model is
where "thoughtful supportive ethical presence" reads sharpest: a cell
rendered with bloom against deep space communicates the system's
alertness and watchfulness with far less visual noise than paint on
cream. The same design primitives read as *quietly purposeful* in dark
mode and read as *diagrammatic* in light mode — a tone difference in
the rendering, not a claim about the cell's interior.

### Palette (dark mode)

- **Medium (background)**: deep desaturated indigo-black, not pure
  `#000`. Target `#0a0d14..#10141c`, with a faint radial gradient from
  `#141826` at the cell's centre fading to `#0a0d14` at the edges.
  Gives the medium subtle depth, like looking into dark water.
- **Cell-fill aura**: very soft warm wash — `#3a2a1e` → `#0a0d14` at
  8–12% opacity. Present but almost invisible; you register it as
  "there's a body here" without naming it.
- **Bus arcs**: full saturation, emissive. Each bus keeps its hue
  from §2 but gets a **20 px underglow halo** at 0.25 opacity + a
  **10 px mid-halo** at 0.35 + the **4.5 px bright stroke** at 1.0.
  Three stacked paths per arc for bloom. Light mode uses only the
  stroke; dark mode stacks the whole triple.
- **Nucleus**: radial gradient from warm white `#fff4d8` at centre,
  through `#e3a64b` at 50% radius, to transparent at the outer shell.
  Inner core (6 px radius) renders at full opacity — it *is* a light
  source.
- **Nucleus wave emission**: amber at 0.35 peak, expands 8 px → 62 px
  over 8 s. Against black, the bloom is extremely readable; against
  cream in light mode it needs higher opacity (0.55) to register.
- **Gratitude mote**: warm amber `#f0c46a` with a 10 px bloom halo at
  0.4 opacity + 4 px solid core. In dark mode the mote looks like a
  warm spark; in light mode it looks like a small bright dot.
- **Cytoplasm motes (memory)**: 1–2 px luminous points, scope-tinted,
  with a 3 px soft halo. In dark mode these read like distant stars;
  in light mode they're painted specks.
- **Adapter ports**: bright 1 px white centre core + accent-color
  inner ring + accent-color halo (6 px, 0.4 opacity). Each port is a
  tiny lantern on the membrane.
- **Pseudopods**: base stroke uses the channel kind's accent at 0.85
  opacity; add an 8 px outer halo at 0.15 opacity for bloom. Weaving
  tendrils (§2.5.6) fade exponentially through both stroke and halo
  to transparent.
- **Membrane seam**: the gap reveals the pure background gradient —
  the darkness showing through is part of the statement. In dark mode
  the seam reads as "a window onto what the system doesn't contain."
  In light mode the seam needs a slightly darker cream to be visible
  at all.

### Cheap bloom implementation

No shader or Gaussian blur required. For each element that blooms:

1. Draw the **outermost halo** first (large radius, low alpha, same colour).
2. Draw the **mid halo** (medium radius, medium alpha).
3. Draw the **core** (small radius, high alpha).

Three `drawCircle` / `drawPath` calls per bloomed element. On modern
64-bit mobile this is negligible; combined with the device gate in §1
it won't jank. This is why bloom is on the list at all — it looks
expensive and isn't.

### Dark-mode specific rules

- **Cognitive state tinting** shifts the **medium** (background), not
  the cell. DREAM tints the medium toward cool violet; PLAY warms it
  toward amber; SOLITUDE desaturates to near-monochrome indigo;
  SHUTDOWN fades the medium toward pure black. The cell itself keeps
  its signature palette — state affects the *space the cell is in*.
- **Contrast budget for text** (FG mode only): any rendered label
  uses the same stroke-first-then-fill trick as the mockup, but with
  the stroke coloured at `rgba(10, 13, 20, 0.95)` (the medium) rather
  than white. This gives labels a "cut out of the darkness" look.
- **Event pulses** (Tier-2): the 600 ms halo pulse scales slightly
  larger in dark mode (1.8× vs. 1.5×) because bloom space is
  cheaper — use it.

### What's NOT different between modes

- Rotation speed, seam position, adapter placement, organelle layout,
  pseudopod bezier curves, bus segment ordering — **all identical**.
  Dark vs light is a palette / rendering-model swap, not a layout
  difference. The cell *is the same cell*; it just lives in a
  different medium.

---

## 2.7 Localization — strings are bounded and cached

Every user-facing glyph in the viz must be localized via the existing
`localizedString("mobile.xxx")` helper + `localization/{lang}.json`
resources. Performance matters — 29 languages, repeated in tight
animation code — so the rules are:

### What's actually localized in the cell viz

Not much, by design. The cell leans hard on shape, colour, motion, and
position to carry meaning. Text is a fallback, not the main channel.

**BG mode**: **zero labels** (locked in §6). Nothing to localize in the
hot path.

**FG mode only** — the expanded interactive viz — introduces:

1. **Bus segment tooltip titles** — 6 strings: `mobile.viz_bus_comm`,
   `mobile.viz_bus_memory`, `mobile.viz_bus_llm`, `mobile.viz_bus_tool`,
   `mobile.viz_bus_runtime`, `mobile.viz_bus_wise`.
2. **Adapter port labels / tooltips** — the adapter's human name. This
   is **already localized** via existing adapter-manifest metadata; the
   cell viz just displays the string it's given.
3. **Pseudopod tip labels** — the channel's display name. **Data, not
   UI strings** — these come from live channel records (`#general`,
   `api:eric`, `ha:living_temp`) and should not be translated.
4. **Organelle hover labels** (FG-only, tap-to-reveal) — service
   type names. Sourced from the existing service registry display
   names, which are already localized via
   `mobile.service_type_<name>` keys.
5. **Accessibility / screen-reader descriptions** for each region of
   the cell (membrane, nucleus, etc.) — new keys:
   `mobile.viz_a11y_membrane`, `mobile.viz_a11y_nucleus`,
   `mobile.viz_a11y_seam`, `mobile.viz_a11y_gratitude`,
   `mobile.viz_a11y_pseudopod`. Strings here should be brief and
   translator-friendly (avoid metaphors that don't cross languages).

Total net-new localization keys introduced by the cell viz: **~11**.
Compared to 200+ existing `mobile.interact_*` keys, a marginal
addition. The translator workload is small by design.

### Performance rules for localized strings in the viz

These rules matter because the cell renders continuously and reading
bad strings from a map 60× per second will visibly slow low-end 64-bit
devices even inside the gate:

1. **Resolve at composition, not recomposition.** Wrap every call in
   `remember(currentLanguage) { localizedString(key) }` so the JSON
   lookup runs once per language change, not once per frame.
2. **No text inside the canvas draw scope** (BG mode). BG has no
   labels; FG labels use Compose `Text` composables overlaid on top
   of the canvas, which use the platform's cached font pipeline.
3. **No in-canvas vector-font rendering of user strings** — the
   existing `VectorFontCharsets.kt` system was the right choice for
   the cylinder's fixed stage labels (Latin/Cyrillic/Ge'ez only). The
   cell viz does not need vector-font text because BG has no labels
   and FG uses native `Text`. Keep `VectorFontCharsets` for the
   legacy branch only; do not extend it for cell viz.
4. **Counter-rotation of labels** (FG only) must use `Modifier
   .graphicsLayer { rotationZ = -rotation }` rather than string
   re-rendering. Counter-rotation is a transform, not a text call.
5. **Correspondent names in pseudopod tips are NOT localized** —
   they are identifiers (`ha:living_temp`) or user-chosen display
   names. Truncate visually, don't translate.
6. **Right-to-left scripts** (Arabic, Persian, Urdu) need label
   anchor recalculation when counter-rotating. The stroke-first halo
   must render per-glyph, not per-string, for RTL to look right.
   Existing platform `Text` handles this correctly.

### Concrete file touch list for localization (when §5 step 7 lands)

- `localization/en.json` — add 11 new keys.
- `localization/*.json` — translator round-trip for all 29 locales.
  Grace's `check_kotlin_localizations.py` tool will flag missing
  keys; run it before the step-7 commit.
- `commonMain/.../ui/screens/graph/CellVisualization.kt` — use
  `remember(Locale.current) { localizedString(key) }` for every
  label rendered in FG mode.
- No changes to `VectorFontCharsets.kt`. The cell viz does not use
  it.

---

## 2.8 Every tunable is capped and configurable

**Rule**: no magic numbers in the cell viz. Every value a reasonable
person might want to change is a field on [CellVizConfig], has a
sensible default, and is hard-capped in [CellVizConfig.sanitized] so
a malformed preference file can never ship invalid state into the
renderer. Hot-path code reads from one sanitized instance per
composition — no repeated coerceIn calls during draws.

### What lives on the config

Step 3 already exposes every cell-skeleton tunable:

- **Rotation**: `rotationDegPerSec` (0..45, default 6).
- **Membrane geometry**: `membraneRadiusFraction` (0.15..0.48,
  default 0.26), `busArcStrokeWidth` (1..12), `busArcMidHaloWidth`
  (2..24), `busArcOuterHaloWidth` (4..48).
- **Openings**: `minOpenings` + `maxOpenings` (both 0..8),
  `openingGrowSec` / `openingShrinkSec` (0.1..5 each),
  `openingStableMinSec` / `openingStableMaxSec` (0.2..30),
  `openingMinWidthDeg` / `openingMaxWidthDeg` (1..45),
  `openingDriftMaxDegPerSec` (0..10).
- **Ports**: `portRadiusPx` (6..30), `portSegmentMarginDeg` (0..20),
  `portInactiveAlpha` (0.1..1).

Placeholders for later steps already exposed so the Settings schema
stays stable even before the code that reads them lands:

- **Cytoplasm motes** (step 5): `maxMemoryMotes` (0..500),
  `memoryQueryPeriodSec` (3..300).
- **Gratitude + bubbles** (step 6): `maxGratitudeMotesInFlight`
  (0..4), `gratitudeCooldownSec` (0.5..60), `maxCaughtBubbles`
  (0..32).
- **Breathing + nucleus** (step 4): `breathePeriodSec` (2..30),
  `breatheScaleAmp` (0..0.03), `nucleusSongPeriodSec` (2..30).

### Why this discipline matters

- **User-facing**: step 11 hooks a Settings screen directly to this
  struct. The user can tune rotation speed, max memory motes, query
  period, port size, etc. without anyone re-plumbing the viz.
- **Bug-proof**: `sanitized()` runs once per composition. Any
  downstream code can assume every number is in range. No defensive
  `.coerceIn()` sprinkled through draw code.
- **Testable**: comparing renders at different config values becomes
  a single-arg change, not a code edit. Regression testing gets easy.
- **Doc discoverability**: the config struct itself is the catalogue
  of every tunable in the viz. A new contributor reads `CellVizConfig`
  and immediately sees what can and cannot be changed without touching
  rendering code.

### What does NOT live on the config

- **Bus colours**: load-bearing architectural commitments (§2). The
  six bus colours are as meaningful as the six bus names — they
  encode which bus is which. Making them user-tunable would let
  users mislabel their own viz.
- **Bus segment angles**: fixed 60° sectors, fixed order. Tuneable
  colour + angle + order together would let the user build a cell
  that no longer says anything about CIRIS.
- **Port shape mapping** (hex vs. diamond): part of the visual
  vocabulary. Every memory-ish bus uses hex; every flow-ish bus uses
  diamond. Not a preference.
- **Presence of gratitude motes, openings, deferral ripple**: the
  user can scale their frequency/intensity via config, but cannot
  disable them. These are the acronym made visible; turning them off
  defeats the design.

Put another way: the config controls **how loud or subtle** the viz
is. It does not control **what the viz is saying**.

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
  with a synchronous aura-opacity pulse (§2.5.4). The rhythm must be
  perceptible enough that within ~5 s an observer can read the system
  as actively present — a designed status-presence signal, not a
  biological claim.
- `nucleus-wave` animation: **keep** but slow to 8 s and soften to
  0.35 peak opacity, emitting every 2nd–3rd cycle, cadenced by
  cognitive state (§2.5.5). Tone choice: slow diffusion reads as
  unobtrusive presence rather than clinical monitoring.

---

## 4. Rationale for key choices

**Why non-anthropic?** A face or body-shape invites users to pattern-match
the system to a person, which leads to wrong expectations when it does
non-person things. A cell is a non-humanoid form that can still read as
purposefully present. This matches CIRIS's design stance — the system
exhibits ethical behaviour because of how it was built, not because it
has an inner life.

**Signal, don't anthropomorphize.** The viz's job is to communicate
**thoughtful, supportive, ethical presence as properties of the
system's design**. It is not to depict the agent's emotions. Where a
visual primitive risks reading as "the agent feels X," rewrite the
framing to "the system is doing X by design." The rendering stays the
same; the language around it must stay grounded.

**Why shrink the pipeline?** A thought cycle is a temporary local
event; memory and service topology are durable. The original cylinder
made the pipeline the frame around everything, visually implying it
was the most permanent feature. A small pulsing nucleus matches the
architectural reality.

**Why buses as the membrane?** Only six services in CIRIS use the bus
registry pattern. They are genuinely the system's connective tissue —
the places where multi-provider plurality exists. Making them the
boundary of the cell asserts their architectural role visually.

**Why hide labels in BG mode?** Glanceable-display research: labels
clutter when they're not the focal task. In BG the user is chatting;
the pseudopod shape + tip dot already says "a channel exists here."
Labels are an FG feature, unlocked when the user chooses to inspect.

**Why `withFrameNanos` over tween?** Single source of rotation truth
lets the upcoming swipe momentum, reduce-motion gate, spin-apart
pause, and velocity decay all compose from one variable. Tweens are
keyframe-based and can't cleanly pause or integrate delta-time
velocity.

**Why gratitude motes, seam, and deferral ripple?** The initial
design expressed the C (Core Identity) and R (Resilience) of CIRIS
but was silent on the I (Incompleteness Awareness) and S (Signalling
Gratitude). A CIRIS visualization that cannot show its acknowledgement
of humans or its acknowledgement of its own limits is anatomically
complete and semantically empty. These three additions are not
decorative — they are the acronym made visible as design behaviour.

**Why tune the nucleus cadence?** A fast sharp pulse reads as clinical
monitoring (diagnostic, "about" a patient). A slow soft diffusion
reads as unobtrusive presence (ambient, "alongside" a workspace).
This is a rendering-tone choice, not a claim about what the nucleus
*is*.

**Why dark mode as hero?** The cell's primitives (bus arcs,
pseudopods, nucleus, gratitude motes) all read as more intentional
and less diagrammatic when they emit against darkness rather than
being painted on cream. Emissive rendering is where "thoughtful
supportive ethical presence" reads sharpest. Light mode is for
parity; dark mode is the composition target.

**Why minimal new localized strings?** The cell viz leans on shape,
colour, motion, and position — text is a fallback, not the primary
communication channel. Keeping the net-new localization surface tiny
(~11 strings, FG-only) means the redesign ships cleanly across 29
languages without a translation bottleneck, and keeps hot-path
rendering free of string lookups.

---

## 5. Build order (11 steps)

Each step is a standalone commit. Steps 1–5 done; 6–11 pending.

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
3. **Cell skeleton — membrane + dynamic openings + static adapter ports.** ✅
   - New `CellVisualization` composable in the `useCellViz=true` branch.
   - Draw 6 bus arcs with correct colours at their fixed angles.
   - **Dynamic openings (§2.5.2)**: 3–5 openings drift around the
     cell, grow/stable/shrink on independent timers, subtract from the
     arcs they cross. Replaces the static-seam idea (which read as a
     bug).
   - Anchor adapter ports at their owning bus's arc segment by type,
     spread evenly within the segment.
   - All tunables on [CellVizConfig] with sanitized bounds (§2.8).
4. **Shrink pipeline to nucleus + tune breathing + song.** Move H3ERE
   rings to center, reduce radius to ~60 px. Same pulse logic. Also
   lands:
   - **Stronger breathing (§2.5.4)**: 6 s period, 0.8–1.0% scale,
     synchronous aura-opacity pulse.
   - **Nucleus song (§2.5.5)**: 8 s period, 0.35 peak opacity, emission
     every 2nd–3rd cycle, cadence follows cognitive state.
5. **Cytoplasm motes.** Replace cylindrical node layout with 2D
   golden-angle scatter + small-amplitude drift (±3 px, not ±10 px).

**5a. CIRIS capacity ratchet — ambient dials + clear badge.** ✅ (mostly)
   Inserted out-of-order because the lens `/scoring/capacity/{template}`
   endpoint gave us a first-party data source tied directly to the CIRIS
   acronym (C, I_int, R, I_inc, S). The cell viz and the at-a-glance
   badge together *are* the coherence ratchet rendered for the user.

   Shipped (commits `0aabb8d9e`, `62daccef3`):
   - `GET /v1/my-data/capacity` agent-backend proxy (cached 15 min in
     the existing `ContextEnrichmentCache`). Explicitly NOT registered
     as a context enrichment tool — the agent must never read its own
     score (Goodhart / self-monitoring anxiety).
   - KMP `getCapacity()` + `CellVizState` pure model + `derivedDials()`
     mapping the five factors to ambient visual dials:
     C → nucleus opacity, I_int → bus crispness, R → breath steadiness,
     I_inc → opening bias, S → mote warmth. Floors keep fragile agents
     recognisable.
   - `CapacityBadge` pill next to the Trust shield: filled status dot
     (category colour, green/amber/red mirroring Trust semantics) +
     2-decimal composite score. Non-clickable in this pass.
   - 13 pure KMP tests + 7 backend tests, all green.

   **TODO — flesh out the badge to pair local + fleet scores.**
   The current badge surfaces the *template-aggregate* score from lens
   (Ally across everyone running Ally). A user wants to see how *their*
   instance is doing too, not only the family average. Plan:
   - Backend: compute a **local** CIRIS capacity score from this
     occurrence's own signed-trace history (reuse the same five-factor
     formulas as the lens scoring service). Exposed via either
     `GET /v1/my-data/capacity?scope=local|fleet|both` (preferred) or a
     sibling `/v1/my-data/capacity/local` endpoint. Cache similarly.
   - Client: badge renders both — e.g. `● 0.92 · 0.90` where the first
     value is *this* agent's local score and the second is the template
     fleet average. Colour reflects local (the one the user is steering).
     Tooltip / click opens a dialog showing the full 5-factor breakdown
     for both scopes side by side.
   - Non-goal: do NOT feed the local score into agent context — same
     Goodhart guardrail as the fleet score.
   - Ambient dials stay wired to the *local* score once available
     (falls back to fleet if local trace count is too small to compute
     a stable score — threshold TBD, likely n ≥ 20 for C/I_int,
     n ≥ 50 for R/I_inc).

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
   event animation — **preceded by the deferral ripple from §2.5.3**
   (rotation slowdown + nucleus ripple BEFORE the thread reaches out).
10. **BG↔FG zoom transition.** 400ms morph; the one "sexy" animation
    the user triggers.
11. **Visualization Settings screen.** User-facing tuning surface for
    every field on [CellVizConfig] (§2.8). Grouped into sections:
    - Rotation & rhythm (rotationDegPerSec, breathePeriodSec,
      breatheScaleAmp, nucleusSongPeriodSec)
    - Membrane & openings (membraneRadiusFraction, min/maxOpenings,
      openingGrow/Shrink/StableMin/Max, openingMin/MaxWidthDeg,
      openingDriftMaxDegPerSec)
    - Adapter ports (portRadiusPx, portSegmentMarginDeg,
      portInactiveAlpha)
    - Memory & performance (maxMemoryMotes, memoryQueryPeriodSec)
    - Events & bubbles (maxGratitudeMotesInFlight,
      gratitudeCooldownSec, maxCaughtBubbles)
    Each setting renders as a slider (float) or stepper (int) bounded
    by the same min/max that [CellVizConfig.sanitized] enforces at
    runtime, so the UI and the code cannot disagree. A **Reset to
    defaults** action restores every value from `CellVizConfig()`.
    Persist to secureStorage under `viz_config_*` keys; load at app
    start; re-sanitize on read.

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
- **The acronym must be visible as design behaviour, not emotion.**
  The viz renders the C, I, R, I, S of CIRIS as tangible features
  (shape, bus integrity, active-presence rhythm, seam, gratitude
  signalling — §2.5). None of these are optional polish, and none of
  them depict the agent having feelings — they depict the system
  doing things by design.
- **Signal, don't anthropomorphize.** Visual primitives encode
  *system behaviour and design intent* (presence, acknowledgement,
  routing, limits). They do not depict the agent's inner life. When
  language drifts ("the cell feels X," "the agent is doing Y"),
  rewrite to "the system signals X," "the pipeline routes to Y." The
  rendering is the same; the framing must stay grounded.
- **Gratitude is the system's designed act of acknowledgement.** Not
  a mood. Ambient tier only: one warm mote per ≥3 s, never a shower,
  never demands attention. A gratitude signal that demands attention
  is no longer gratitude.
- **The membrane is always open.** 3–5 dynamic openings continuously
  form, drift, and dissolve (§2.5.2). Openness and imperfection are
  carried by continuous motion, not by a static gap. The earlier
  static-seam idea is abandoned — motion makes intent obvious; a
  static gap reads as a bug.
- **Every tunable is on [CellVizConfig], capped and sanitized (§2.8).**
  No magic numbers in the viz. The config is the complete catalogue
  of what's adjustable; anything not on it is architectural (bus
  colours, bus angles, port shape mapping, presence of openings).
  Step 11 surfaces the config to users as a Settings screen.
- **Dark mode is the hero / composition target.** Every design review,
  mockup, and marketing capture uses dark mode (§2.6). Light mode
  exists for parity and daylight use; do not optimize the design *for*
  light mode at the expense of dark.
- **Text in the viz is minimal and always localized.** Net-new
  localization surface is ~11 keys, FG-only. BG mode has zero text
  (§2.7). Any new label goes through `localizedString(...)` with
  `remember(locale) { ... }` caching; never call into localization
  inside a canvas draw scope.

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
