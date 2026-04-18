package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.ui.theme.getScopeColor
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import kotlinx.coroutines.isActive
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

// =============================================================================
// Cell Visualization — Step 3: membrane skeleton + seam + static adapter ports
// =============================================================================
//
// This composable is the new Interact-screen background. It replaces the
// cylinder-based [LiveGraphBackground] on devices that pass the cell-viz
// capability gate (64-bit ABI, sufficient RAM). See FSD/CELL_VIZ_REDESIGN.md
// for the full design document.
//
// What this step renders (static, no events yet):
//
//  - The medium (dark radial-gradient background; light mode is a parity
//    fallback, not the composition target).
//  - The cell-body aura (faint warm wash inside the membrane).
//  - Six bus arcs forming the membrane, each with a three-path bloom
//    stack — outer halo, mid halo, bright stroke. Colors per §2 of the
//    design doc: wise/runtime/tool/llm/memory/comm at fixed angles.
//  - The membrane seam — a single 6° gap inside the Wise arc. Visible
//    acknowledgement that the system is incomplete by design.
//  - Adapter ports — diamonds or hexagons anchored on their owning bus
//    arc, spread evenly within the 60° segment. Shape and color come
//    from the adapter type.
//
// What this step does NOT render (intentional — later steps):
//
//  - The nucleus (step 4)
//  - Cytoplasm motes (step 5)
//  - Bus shimmer / gratitude motes / event pulses (steps 6, 8)
//  - Pseudopods + weaving tendrils (step 7)
//  - Deferral ripple + WA companion cell (step 9)
//  - BG↔FG zoom transition (step 10)
//
// Rotation matches the step-2 refactor: a single withFrameNanos-driven
// variable, 6°/sec baseline, +external swipe rotation.
//
// CONFIGURATION:
//
// Every tunable the viz exposes lives on [CellVizConfig] below. The
// caller may pass a custom instance to override any defaults. Later
// build steps (see FSD/CELL_VIZ_REDESIGN.md step 11) will plumb a
// user-facing Settings screen into this config, so the same struct
// that drives the defaults here is the same struct the user's saved
// preferences populate at runtime. All fields are hard-capped in
// [CellVizConfig.sanitized] so a bad preference can't break rendering.

// -----------------------------------------------------------------------------
// CellVizConfig — every tunable lives here, capped, overridable
// -----------------------------------------------------------------------------

/**
 * User-facing + developer-facing tuning surface for the cell viz.
 *
 * Every visual constant that a reasonable person might want to change
 * lives on this struct — rotation speed, port size, seam width, future
 * max-node counts, breathing period, gratitude cooldown, etc. Hot-path
 * code reads from a single sanitized instance; the UI-surfaced
 * Settings screen (see build-order step 11) populates the same struct.
 *
 * All numeric fields are clamped to safe ranges by [sanitized]. A user
 * with a broken preferences file can't ship NaN or a negative radius
 * into the renderer — the worst they can do is land at the bounded
 * extreme.
 */
data class CellVizConfig(
    // ----- Rotation ---------------------------------------------------------
    /** Degrees per second for the baseline rotation. 0 disables auto-rotation. */
    val rotationDegPerSec: Float = 6f,

    // ----- Membrane geometry -----------------------------------------------
    /**
     * Membrane radius as a fraction of `min(canvas width, canvas height)`.
     * 0.26 keeps the full circle inside the chat area even on landscape
     * layouts where the canvas is shorter than it is wide. Larger values
     * cause the top/bottom of the cell to clip behind surrounding UI
     * chrome (warning banner, input bar). Adjustable via Settings in
     * step 11.
     */
    val membraneRadiusFraction: Float = 0.26f,

    /** Stroke width of the bright inner stroke of each bus arc. */
    val busArcStrokeWidth: Float = 4.5f,

    /** Stroke width of the soft mid-halo stack in dark mode. */
    val busArcMidHaloWidth: Float = 10f,

    /** Stroke width of the outermost bloom halo in dark mode. */
    val busArcOuterHaloWidth: Float = 20f,

    // ----- Membrane openings (dynamic apertures) ---------------------------
    //
    // The membrane is never a closed ring. At any time, between [minOpenings]
    // and [maxOpenings] apertures are open somewhere around the cell — each
    // forms, drifts, and dissolves on its own timer. This renders
    // Incompleteness Awareness as continuous motion rather than a static
    // broken pixel that looks like a bug. Openness over stitching.

    /** Minimum number of openings present at any time. */
    val minOpenings: Int = 3,

    /** Maximum number of openings present at any time. */
    val maxOpenings: Int = 5,

    /** Seconds an opening takes to grow from 0° to its target width. */
    val openingGrowSec: Float = 0.8f,

    /** Seconds an opening takes to shrink from its target width back to 0°. */
    val openingShrinkSec: Float = 0.8f,

    /** Minimum time (seconds) an opening stays at its target width. */
    val openingStableMinSec: Float = 2.0f,

    /** Maximum time (seconds) an opening stays at its target width. */
    val openingStableMaxSec: Float = 4.0f,

    /** Minimum angular width (degrees) an opening reaches at full size. */
    val openingMinWidthDeg: Float = 4f,

    /** Maximum angular width (degrees) an opening reaches at full size. */
    val openingMaxWidthDeg: Float = 10f,

    /** Maximum drift speed (degrees/sec) an opening walks around the cell. */
    val openingDriftMaxDegPerSec: Float = 1.0f,

    // ----- Adapter ports ---------------------------------------------------
    /** Half-extent (in pixels) of an adapter port's shape. */
    val portRadiusPx: Float = 14f,

    /** Margin (in degrees) between a port and its bus segment boundary. */
    val portSegmentMarginDeg: Float = 8f,

    /** Alpha multiplier applied to inactive-adapter ports. */
    val portInactiveAlpha: Float = 0.35f,

    // ----- Future steps (placeholders, already capped) ---------------------
    // Expose these now so the Settings schema is stable even before the
    // code that reads them lands. Each one has a sensible default and
    // a hard-capped sanitized value.

    /** Maximum number of memory-graph motes rendered in cytoplasm (step 5). */
    val maxMemoryMotes: Int = 200,

    /**
     * Query period (seconds) for refreshing the memory-graph snapshot
     * that populates motes. Too-frequent queries harass the server;
     * too-infrequent queries make the cell feel stale.
     */
    val memoryQueryPeriodSec: Float = 15f,

    /**
     * Hours of recent graph history to load for motes (step 5).
     * 24 matches the legacy LiveGraphBackground behaviour — last
     * day's worth of activity.
     */
    val memoryLoadWindowHours: Int = 24,

    /** Base radius of a single cytoplasm mote in pixels. */
    val moteRadiusPx: Float = 2.4f,

    /**
     * Peak drift amplitude in pixels. Each mote oscillates with its
     * own phase/frequency within this envelope — small enough to feel
     * ambient, large enough to register as "alive" (plan §3).
     */
    val moteDriftAmpPx: Float = 3f,

    /**
     * Reference drift period in seconds. Individual motes pick slightly
     * different frequencies so they don't drift in lockstep.
     */
    val moteDriftPeriodSec: Float = 12f,

    /**
     * Birth animation duration (ms). New motes fade in with a soft
     * white halo pulse over this window.
     */
    val moteBirthMs: Long = 1500L,

    /** Max gratitude motes in flight at once (step 6). */
    val maxGratitudeMotesInFlight: Int = 1,

    /** Minimum seconds between gratitude-mote emissions (step 6). */
    val gratitudeCooldownSec: Float = 3f,

    /** Maximum in-flight floating "caught" event bubbles on the UI layer. */
    val maxCaughtBubbles: Int = 12,

    /** Breathing period in seconds (step 4 — active-presence rhythm). */
    val breathePeriodSec: Float = 6f,

    /**
     * Peak scale added on the breathe animation. 0.035 = 3.5% — clearly
     * perceptible without feeling like the cell is gasping. At 1.8% the
     * motion was too subtle for a casual observer to register that the
     * system is active.
     */
    val breatheScaleAmp: Float = 0.035f,

    /**
     * Nucleus song period in seconds. 6 s gives a visible wave
     * propagating outward every 6 s — unrushed but clearly alive.
     */
    val nucleusSongPeriodSec: Float = 6f,

    /**
     * Nucleus outer radius as a fraction of the membrane radius.
     * 0.45 makes the pipeline area a meaningful, readable presence at
     * the cell's centre — large enough that the shells and song waves
     * are perceptible without competing with the membrane.
     */
    val nucleusRadiusFraction: Float = 0.45f,

    /**
     * Peak opacity of each emitted nucleus song wave. 0.50 makes each
     * emitted wave clearly visible against the dark medium without
     * flashing; lower values fade into ambient noise.
     */
    val nucleusSongPeakOpacity: Float = 0.50f,

    /**
     * Emit a song wave every Nth period. Default 1 (every cycle) at
     * the default 8 s period gives one wave roughly every 8 s. Raise
     * to 2 or 3 for a quieter hum.
     */
    val nucleusSongEmissionEveryN: Int = 1,
) {
    /**
     * Return a copy with every value forced into a safe range. Call
     * this once per composition; every tunable is then known to be in
     * bounds for the rest of the rendering pass.
     */
    fun sanitized(): CellVizConfig {
        // Openings: min ≤ max, min ≥ 0. Keep both in [0, 8] so the
        // membrane can't become so holey that the cell reads as broken.
        val sanitizedMin = minOpenings.coerceIn(0, 8)
        val sanitizedMax = maxOpenings.coerceIn(sanitizedMin, 8)
        val sanitizedStableMin = openingStableMinSec.coerceIn(0.2f, 20f)
        val sanitizedStableMax = openingStableMaxSec.coerceIn(sanitizedStableMin, 30f)
        val sanitizedWidthMin = openingMinWidthDeg.coerceIn(1f, 45f)
        val sanitizedWidthMax = openingMaxWidthDeg.coerceIn(sanitizedWidthMin, 45f)

        return copy(
            rotationDegPerSec         = rotationDegPerSec.coerceIn(0f, 45f),
            membraneRadiusFraction    = membraneRadiusFraction.coerceIn(0.15f, 0.48f),
            busArcStrokeWidth         = busArcStrokeWidth.coerceIn(1f, 12f),
            busArcMidHaloWidth        = busArcMidHaloWidth.coerceIn(2f, 24f),
            busArcOuterHaloWidth      = busArcOuterHaloWidth.coerceIn(4f, 48f),
            minOpenings               = sanitizedMin,
            maxOpenings               = sanitizedMax,
            openingGrowSec            = openingGrowSec.coerceIn(0.1f, 5f),
            openingShrinkSec          = openingShrinkSec.coerceIn(0.1f, 5f),
            openingStableMinSec       = sanitizedStableMin,
            openingStableMaxSec       = sanitizedStableMax,
            openingMinWidthDeg        = sanitizedWidthMin,
            openingMaxWidthDeg        = sanitizedWidthMax,
            openingDriftMaxDegPerSec  = openingDriftMaxDegPerSec.coerceIn(0f, 10f),
            portRadiusPx              = portRadiusPx.coerceIn(6f, 30f),
            portSegmentMarginDeg      = portSegmentMarginDeg.coerceIn(0f, 20f),
            portInactiveAlpha         = portInactiveAlpha.coerceIn(0.1f, 1f),
            maxMemoryMotes            = maxMemoryMotes.coerceIn(0, 500),
            memoryQueryPeriodSec      = memoryQueryPeriodSec.coerceIn(3f, 300f),
            memoryLoadWindowHours     = memoryLoadWindowHours.coerceIn(1, 168),
            moteRadiusPx              = moteRadiusPx.coerceIn(0.5f, 12f),
            moteDriftAmpPx            = moteDriftAmpPx.coerceIn(0f, 20f),
            moteDriftPeriodSec        = moteDriftPeriodSec.coerceIn(2f, 60f),
            moteBirthMs               = moteBirthMs.coerceIn(0L, 6000L),
            maxGratitudeMotesInFlight = maxGratitudeMotesInFlight.coerceIn(0, 4),
            gratitudeCooldownSec      = gratitudeCooldownSec.coerceIn(0.5f, 60f),
            maxCaughtBubbles          = maxCaughtBubbles.coerceIn(0, 32),
            breathePeriodSec          = breathePeriodSec.coerceIn(2f, 30f),
            breatheScaleAmp           = breatheScaleAmp.coerceIn(0f, 0.06f),
            nucleusSongPeriodSec      = nucleusSongPeriodSec.coerceIn(2f, 30f),
            nucleusRadiusFraction     = nucleusRadiusFraction.coerceIn(0.10f, 0.60f),
            nucleusSongPeakOpacity    = nucleusSongPeakOpacity.coerceIn(0f, 1f),
            nucleusSongEmissionEveryN = nucleusSongEmissionEveryN.coerceIn(1, 10),
        )
    }

    companion object {
        /** Stable reference to the default, already-sanitized config. */
        val DEFAULT: CellVizConfig = CellVizConfig().sanitized()
    }
}

// -----------------------------------------------------------------------------
// Bus segments — load-bearing, do not rearrange
// -----------------------------------------------------------------------------

/** Identifier for one of CIRIS's six message buses. */
enum class CellBus { COMM, MEMORY, LLM, TOOL, RUNTIME, WISE }

/**
 * Fixed angle + color for a bus arc on the membrane. Angles are in
 * degrees, Compose convention (0° = east, clockwise).
 */
private data class BusSegment(
    val bus: CellBus,
    val startDeg: Float,
    val endDeg: Float,
    val color: Color,
) {
    val midDeg: Float get() = (startDeg + endDeg) / 2f
    val sweepDeg: Float get() = endDeg - startDeg
}

/**
 * Canonical bus layout — order matters only for iteration; each segment
 * owns a fixed 60° range of the membrane.
 */
private val BUS_SEGMENTS: List<BusSegment> = listOf(
    BusSegment(CellBus.TOOL,    startDeg = 0f,   endDeg = 60f,  color = Color(0xFFD98A2D)),
    BusSegment(CellBus.LLM,     startDeg = 60f,  endDeg = 120f, color = Color(0xFF3D86D9)),
    BusSegment(CellBus.MEMORY,  startDeg = 120f, endDeg = 180f, color = Color(0xFF8B5FD6)),
    BusSegment(CellBus.COMM,    startDeg = 180f, endDeg = 240f, color = Color(0xFF2DA89C)),
    BusSegment(CellBus.WISE,    startDeg = 240f, endDeg = 300f, color = Color(0xFFC9A52A)),
    BusSegment(CellBus.RUNTIME, startDeg = 300f, endDeg = 360f, color = Color(0xFFD8554E)),
)

// -----------------------------------------------------------------------------
// Membrane openings — dynamic apertures
// -----------------------------------------------------------------------------
//
// The membrane is never a closed ring. 3–5 apertures exist at any time;
// each one grows in, drifts slightly, stabilizes, then shrinks out. When
// one dies a new one spawns elsewhere. This renders the "openness" and
// "imperfection" principles as continuous motion, and completely avoids
// the "looks like a bug" read of a static gap.
//
// The openings CUT bus arcs — wherever an opening overlaps a bus, that
// portion of the arc is not drawn. Adapter ports still render on top
// because they sit above the arc layer.

/**
 * One aperture in the cell membrane at a given moment in time.
 *
 * An opening has a deterministic lifecycle: grow → stable → shrink → die.
 * All timing is expressed in wall-clock ms so the renderer can drive its
 * state purely from the current time, without per-frame mutation of the
 * opening itself. Creating a new `MembraneOpening` is the only mutation;
 * everything else is a pure function of age.
 */
private data class MembraneOpening(
    val id: Long,
    /** Initial position of the opening's center (degrees, 0..360). */
    val birthCenterDeg: Float,
    /** Target angular width at full growth (degrees). */
    val targetWidthDeg: Float,
    /** How fast the opening walks around the cell (deg/sec; can be negative). */
    val driftDegPerSec: Float,
    /** Wall-clock millis when this opening was born. */
    val bornAtMs: Long,
    /** Grow-in duration from 0 → targetWidthDeg (ms). */
    val growMs: Long,
    /** Time at full width (ms). */
    val stableMs: Long,
    /** Shrink-out duration back to 0 (ms). */
    val shrinkMs: Long,
) {
    /** Total lifetime in ms (grow + stable + shrink). */
    val lifetimeMs: Long get() = growMs + stableMs + shrinkMs

    fun isDead(nowMs: Long): Boolean = nowMs >= bornAtMs + lifetimeMs

    /** Current center angle in degrees, wrapped to 0..360. */
    fun currentCenterDeg(nowMs: Long): Float {
        val ageSec = (nowMs - bornAtMs) / 1000f
        val raw = birthCenterDeg + driftDegPerSec * ageSec
        return ((raw % 360f) + 360f) % 360f
    }

    /** Current angular width in degrees — 0 before birth, 0 after death. */
    fun currentWidthDeg(nowMs: Long): Float {
        val age = nowMs - bornAtMs
        return when {
            age < 0L -> 0f
            age < growMs -> targetWidthDeg * smoothstep(age.toFloat() / growMs)
            age < growMs + stableMs -> targetWidthDeg
            age < lifetimeMs -> targetWidthDeg * smoothstep(
                (lifetimeMs - age).toFloat() / shrinkMs
            )
            else -> 0f
        }
    }
}

/** Classic smoothstep easing — C¹ continuous, no library dependency. */
private fun smoothstep(t: Float): Float {
    val x = t.coerceIn(0f, 1f)
    return x * x * (3f - 2f * x)
}

// -----------------------------------------------------------------------------
// Cytoplasm motes — the memory graph, visible in the cell
// -----------------------------------------------------------------------------
//
// Every node in the last [cfg.memoryLoadWindowHours] hours of the memory
// graph renders as a small luminous mote drifting in the cytoplasm —
// the region between the nucleus and the membrane. Positions are
// deterministic functions of (stable index, time); no per-frame
// mutation of mote fields.
//
// Positioning uses the golden-angle scatter (φ ≈ 137.508°) so motes
// distribute evenly without visible banding or clustering. Radial
// distance is sqrt-based so each equal-area ring contains roughly the
// same number of motes — uniform 2D density, not concentrated near the
// nucleus.

/**
 * One node from the memory graph, laid out as a drifting mote.
 *
 * The `stableIndex` is what determines this mote's angular + radial
 * placement via the golden-angle formula. Preserving the same index
 * across refreshes means a node doesn't "teleport" around the cell
 * when neighbouring nodes appear or disappear — it breathes in place.
 */
private data class CytoplasmMote(
    val id: String,
    val scope: ai.ciris.api.models.GraphScope,
    val stableIndex: Int,
    val birthTimeMs: Long,
)

/**
 * Map an adapter's type string onto the bus that owns it. Step-3 only
 * needs the 1-to-1 type→bus mapping; per-adapter positioning within a
 * bus segment comes from spread.
 */
private fun adapterBus(type: String): CellBus = when (type.lowercase()) {
    "api", "discord", "cli" -> CellBus.COMM
    "weather", "navigation", "home_assistant", "ha",
    "wallet", "reddit", "mcp", "apple_notes", "apple_reminders",
    "bear_notes", "bird", "blogwatcher" -> CellBus.TOOL
    "cirisverify" -> CellBus.WISE
    // LLM, MEMORY, RUNTIME don't typically come from "adapter" entries
    // in the current data model. Default to TOOL as a visible placeholder.
    else -> CellBus.TOOL
}

/** Which rendered shape a bus uses for its adapter ports. */
private enum class PortShape { DIAMOND, HEX }

private fun portShapeFor(bus: CellBus): PortShape = when (bus) {
    // Memory and graph-shaped buses use hex; flow buses use diamond.
    // Keeps the vocabulary consistent with the mockup.
    CellBus.MEMORY, CellBus.WISE -> PortShape.HEX
    else -> PortShape.DIAMOND
}

// -----------------------------------------------------------------------------
// Public composable
// -----------------------------------------------------------------------------

/**
 * Cell visualization. Step 3 of the redesign — renders the medium, the
 * membrane (bus arcs with dynamic openings), and adapter ports anchored
 * on their owning bus. Drop-in replacement for [LiveGraphBackground] at
 * call sites that passed the [probeCellVizCapability] gate.
 *
 * @param modifier Layout modifier — fill the chat area; the cell will
 *   center itself within the available space.
 * @param isDarkMode Dark mode is the hero composition target. Light
 *   mode is a parity fallback.
 * @param adapterOrbits Reused from the legacy orbit renderer; only the
 *   `id`, `type`, and `isActive` fields are used here. The orbit's
 *   altitude/phase are ignored — the cell positions ports on the
 *   owning bus segment, not on arbitrary altitudes.
 * @param externalRotation Degrees added to the baseline rotation
 *   (swipe-to-spin).
 * @param config Every tunable the viz exposes. See [CellVizConfig]; the
 *   config is sanitized once per composition so draw code can assume
 *   every field is in a safe range. User-facing Settings screen (build
 *   step 11) will inject overrides here.
 */
@Composable
fun CellVisualization(
    modifier: Modifier = Modifier,
    isDarkMode: Boolean = true,
    adapterOrbits: List<AdapterOrbit> = emptyList(),
    externalRotation: Float = 0f,
    config: CellVizConfig = CellVizConfig.DEFAULT,
    // Optional — when present, cytoplasm motes populate from the live
    // memory graph. Null means "render the cell empty of motes", which
    // is a legitimate state (e.g. during startup) and should not crash.
    apiClient: ai.ciris.mobile.shared.api.CIRISApiClient? = null,
    colorTheme: ai.ciris.mobile.shared.ui.theme.ColorTheme =
        ai.ciris.mobile.shared.ui.theme.ColorTheme.DEFAULT,
    // Incremented by the caller when something happened that might have
    // changed the memory graph (SSE events, explicit refresh). Wired in
    // step 6; step 5 just fetches once at mount.
    eventTrigger: Int = 0,
) {
    // Take the config once per composition (effectively per param change)
    // so every draw reads the same sanitized values.
    val cfg = remember(config) { config.sanitized() }

    // --- Rotation driver (matches step-2 refactor exactly) ---------------
    //
    // One mutable float; one LaunchedEffect driving it with withFrameNanos.
    // Delta-time accumulation gives the canonical revolution without
    // relying on a tween spec that can't be paused.

    var autoRotationDeg by remember { mutableStateOf(0f) }
    LaunchedEffect(cfg.rotationDegPerSec) {
        var lastFrameNs = 0L
        while (isActive) {
            withFrameNanos { frameTimeNs ->
                if (lastFrameNs != 0L) {
                    val dSec = (frameTimeNs - lastFrameNs) / 1_000_000_000f
                    autoRotationDeg = (autoRotationDeg + cfg.rotationDegPerSec * dSec) % 360f
                }
                lastFrameNs = frameTimeNs
            }
        }
    }
    val rotationDeg = (autoRotationDeg + externalRotation) % 360f

    // --- Membrane openings --------------------------------------------------
    //
    // We keep a list of live openings in Compose state. A frame-timer
    // effect (a) expires dead openings and (b) spawns new ones to keep the
    // count at [cfg.minOpenings]. Current center/width are PURE functions of
    // wall-clock time — per-frame draw just reads them, no mutation.

    val openings = remember { mutableStateOf(emptyList<MembraneOpening>()) }
    val nowMs = remember { mutableStateOf(0L) }

    LaunchedEffect(cfg.minOpenings, cfg.maxOpenings, cfg.openingStableMinSec,
        cfg.openingStableMaxSec, cfg.openingMinWidthDeg, cfg.openingMaxWidthDeg,
        cfg.openingDriftMaxDegPerSec, cfg.openingGrowSec, cfg.openingShrinkSec) {
        var lastFrameNs = 0L
        val rng = kotlin.random.Random.Default
        while (isActive) {
            withFrameNanos { frameTimeNs ->
                if (lastFrameNs != 0L) {
                    val now = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                    nowMs.value = now
                    val alive = openings.value.filterNot { it.isDead(now) }
                    val delta = mutableListOf<MembraneOpening>()
                    // Spawn until we hit the minimum; above that, let
                    // natural death thin out and only spawn probabilistically.
                    if (alive.size < cfg.minOpenings) {
                        delta += spawnOpening(now, rng, cfg)
                    } else if (alive.size < cfg.maxOpenings && rng.nextFloat() < 0.002f) {
                        // Very small per-frame probability → ~0.12/sec at 60fps
                        delta += spawnOpening(now, rng, cfg)
                    }
                    if (delta.isNotEmpty() || alive.size != openings.value.size) {
                        openings.value = alive + delta
                    }
                }
                lastFrameNs = frameTimeNs
            }
        }
    }

    // --- Group adapters by bus so ports can spread within each segment ---
    val adaptersByBus: Map<CellBus, List<AdapterOrbit>> = remember(adapterOrbits) {
        adapterOrbits.groupBy { adapterBus(it.type) }
    }

    // --- Cytoplasm motes (memory graph) ---------------------------------
    //
    // Fetch once at mount + whenever eventTrigger changes. Each mote
    // keeps a stableIndex across refreshes so existing nodes don't
    // teleport when neighbours appear or disappear — they just fade in
    // (birth halo) or fade out (removed). Total count bounded by
    // cfg.maxMemoryMotes; server-side `limit` caps the fetch matching.
    val motes = remember { mutableStateOf(emptyList<CytoplasmMote>()) }
    // Preserved indices for stable positioning across refreshes.
    val moteIndexById = remember { mutableMapOf<String, Int>() }
    val nextMoteIndex = remember { mutableStateOf(0) }

    LaunchedEffect(apiClient, eventTrigger, cfg.maxMemoryMotes,
        cfg.memoryLoadWindowHours) {
        val client = apiClient ?: return@LaunchedEffect
        try {
            val graph = client.getGraphData(
                hours = cfg.memoryLoadWindowHours,
                scope = null,
                nodeType = null,
                limit = cfg.maxMemoryMotes,
                includeMetrics = false,
            )
            val nowMsLocal = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
            val known = moteIndexById.keys.toSet()
            val newMotes = graph.nodes.map { node ->
                val existingIdx = moteIndexById[node.id]
                val idx = existingIdx ?: nextMoteIndex.value.also {
                    moteIndexById[node.id] = it
                    nextMoteIndex.value = it + 1
                }
                val isNew = existingIdx == null && known.isNotEmpty()
                CytoplasmMote(
                    id = node.id,
                    scope = node.scope,
                    stableIndex = idx,
                    birthTimeMs = if (isNew) nowMsLocal else 0L,
                )
            }
            motes.value = newMotes
        } catch (e: Exception) {
            PlatformLogger.w(
                "CellVisualization",
                "getGraphData failed: ${e.message}; cytoplasm will render empty",
            )
        }
    }

    Canvas(modifier = modifier) {
        val centerX = size.width / 2f
        val centerY = size.height / 2f
        val membraneRadius = minOf(size.width, size.height) * cfg.membraneRadiusFraction
        val nucleusRadius = membraneRadius * cfg.nucleusRadiusFraction

        // Wall-clock-driven scalars.
        //
        // breathePhase is a continuous phase in radians that advances with
        // time; the scale multiplier is a small sin-wave around 1.0. Aura
        // opacity pulses in phase so "the cell body becomes slightly
        // brighter as it expands" — the two cues reinforce each other.
        val nowSec = nowMs.value / 1000f
        val breathePhase = (nowSec / cfg.breathePeriodSec) * 2f * PI.toFloat()
        val breatheScale = 1f + cfg.breatheScaleAmp * sin(breathePhase)
        val breatheAuraAlpha = 0.85f + (cfg.breatheScaleAmp / 0.010f) * 0.15f *
            (0.5f * (1f + sin(breathePhase)))  // 0.85..1.00 when amp=0.010

        drawMedium(isDarkMode, centerX, centerY)

        // Everything that IS the cell (not the medium around it) breathes
        // together. A single scale transform applies uniformly.
        scale(scaleX = breatheScale, scaleY = breatheScale,
            pivot = Offset(centerX, centerY)) {
            drawCellBodyAura(
                isDarkMode = isDarkMode,
                cx = centerX, cy = centerY,
                radius = membraneRadius * 1.05f,
                opacityMultiplier = breatheAuraAlpha,
            )
            // Collect current opening ranges once per frame; pass through to
            // the membrane draw which subtracts them from the bus arcs.
            val openingRanges = openings.value
                .flatMap { openingRanges(it, nowMs.value) }
            drawMembrane(
                rotationDeg = rotationDeg,
                cx = centerX, cy = centerY,
                radius = membraneRadius,
                isDarkMode = isDarkMode,
                cfg = cfg,
                openingRanges = openingRanges,
            )
            drawCytoplasmMotes(
                motes = motes.value,
                cx = centerX, cy = centerY,
                nucleusRadius = nucleusRadius,
                membraneRadius = membraneRadius,
                nowMs = nowMs.value,
                isDarkMode = isDarkMode,
                colorTheme = colorTheme,
                cfg = cfg,
            )
            drawAdapterPorts(
                adaptersByBus = adaptersByBus,
                rotationDeg = rotationDeg,
                centerX = centerX, centerY = centerY,
                membraneRadius = membraneRadius,
                isDarkMode = isDarkMode,
                cfg = cfg,
            )
            drawNucleus(
                cx = centerX, cy = centerY,
                outerRadius = nucleusRadius,
                isDarkMode = isDarkMode,
            )
            drawNucleusSong(
                cx = centerX, cy = centerY,
                nucleusOuterRadius = nucleusRadius,
                membraneRadius = membraneRadius,
                isDarkMode = isDarkMode,
                cfg = cfg,
                nowSec = nowSec,
            )
        }
    }
}

/**
 * Build a new opening with randomized width, drift, and stable duration
 * picked from the configured ranges. Spawn position is uniform around
 * the cell so openings don't cluster.
 */
private fun spawnOpening(
    nowMs: Long,
    rng: kotlin.random.Random,
    cfg: CellVizConfig,
): MembraneOpening {
    val widthDeg = cfg.openingMinWidthDeg +
        rng.nextFloat() * (cfg.openingMaxWidthDeg - cfg.openingMinWidthDeg)
    val stableSec = cfg.openingStableMinSec +
        rng.nextFloat() * (cfg.openingStableMaxSec - cfg.openingStableMinSec)
    val drift = (rng.nextFloat() - 0.5f) * 2f * cfg.openingDriftMaxDegPerSec
    return MembraneOpening(
        id = rng.nextLong(),
        birthCenterDeg = rng.nextFloat() * 360f,
        targetWidthDeg = widthDeg,
        driftDegPerSec = drift,
        bornAtMs = nowMs,
        growMs = (cfg.openingGrowSec * 1000).toLong(),
        stableMs = (stableSec * 1000).toLong(),
        shrinkMs = (cfg.openingShrinkSec * 1000).toLong(),
    )
}

/**
 * Return the degree ranges currently occluded by an opening. A seam
 * straddling the 0°/360° boundary returns two ranges; all others return
 * one. An opening with zero current width (freshly spawned or just
 * dying) returns an empty list.
 */
private fun openingRanges(op: MembraneOpening, nowMs: Long): List<ClosedFloatingPointRange<Float>> {
    val w = op.currentWidthDeg(nowMs)
    if (w <= 0f) return emptyList()
    val c = op.currentCenterDeg(nowMs)
    val half = w / 2f
    val rawStart = c - half
    val rawEnd = c + half
    return when {
        rawStart < 0f -> listOf(0f..rawEnd, (rawStart + 360f)..360f)
        rawEnd > 360f -> listOf(rawStart..360f, 0f..(rawEnd - 360f))
        else -> listOf(rawStart..rawEnd)
    }
}

// =============================================================================
// Drawing — one concern per function, no cross-function state
// =============================================================================

/**
 * The medium the cell sits in. Dark mode fills the canvas with a
 * subtle radial gradient so the space feels like dark water rather
 * than a flat black rectangle. Light mode is a plain warm-cream fill.
 */
private fun DrawScope.drawMedium(isDarkMode: Boolean, cx: Float, cy: Float) {
    if (isDarkMode) {
        drawRect(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFF141826),  // warmer near the cell
                    Color(0xFF0A0D14),  // deep edge
                ),
                center = Offset(cx, cy),
                radius = size.minDimension * 0.75f,
            )
        )
    } else {
        drawRect(color = Color(0xFFF3EDE9))  // parity cream
    }
}

/**
 * A faint warm glow centered on the cell, so you register "there's a
 * body here" without naming it. Intentionally almost invisible.
 *
 * [opacityMultiplier] is the breathe-driven opacity modulation: the aura
 * brightens and dims in step with the cell's scale pulse so the two cues
 * reinforce each other rather than fighting.
 */
private fun DrawScope.drawCellBodyAura(
    isDarkMode: Boolean,
    cx: Float,
    cy: Float,
    radius: Float,
    opacityMultiplier: Float = 1f,
) {
    val (inner, outer) = if (isDarkMode) {
        Color(0xFF3A2A1E).copy(alpha = 0.12f * opacityMultiplier) to
            Color(0xFF0A0D14).copy(alpha = 0f)
    } else {
        Color(0xFFFFFAF3).copy(alpha = 0.50f * opacityMultiplier) to
            Color(0xFFD9C7B3).copy(alpha = 0f)
    }
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(inner, outer),
            center = Offset(cx, cy),
            radius = radius,
        ),
        radius = radius,
        center = Offset(cx, cy),
    )
}

// =============================================================================
// Nucleus + song — the cell's small, warm center
// =============================================================================
//
// The pipeline lives here, not around the whole membrane. It's small
// (cfg.nucleusRadiusFraction × membraneRadius, default 30%) and sits
// dead-center. Seven thin concentric shells represent the H3ERE stages
// (THINK..ACT); the shells do not individually animate in step 4, they
// are the static anatomy. A slow "song" wave emits from the core every
// Nth cycle — not a heartbeat, a hum.

/**
 * Radii of the 7 nucleus shells as fractions of the nucleus outer
 * radius. Picked to be readable but not crowded; each shell is slightly
 * thinner than the last as we move outward.
 */
private val NUCLEUS_SHELL_FRACTIONS = floatArrayOf(
    0.25f, 0.35f, 0.45f, 0.55f, 0.65f, 0.78f, 0.92f,
)

/** Shell opacities, matched index-by-index to [NUCLEUS_SHELL_FRACTIONS]. */
private val NUCLEUS_SHELL_OPACITIES = floatArrayOf(
    0.40f, 0.42f, 0.42f, 0.38f, 0.32f, 0.24f, 0.16f,
)

/** Warm amber the nucleus emits — fixed, not theme-derived. */
private val NUCLEUS_AMBER = Color(0xFFE3A64B)

/**
 * Draw the nucleus — a warm radial-gradient fill, 7 concentric shells,
 * and a bright emissive core at the centre. Zero per-frame state; the
 * nucleus is just static anatomy until a pipeline event lights it up
 * (that wiring comes in step 6).
 */
private fun DrawScope.drawNucleus(
    cx: Float,
    cy: Float,
    outerRadius: Float,
    isDarkMode: Boolean,
) {
    if (outerRadius <= 1f) return
    val center = Offset(cx, cy)

    // Warm fill — a soft amber wash. We deliberately do NOT run pure
    // white-amber at full opacity in the centre; the earlier version
    // read as eye-searing against the indigo-black medium. Amber-only
    // reads warm without hurting to look at.
    val fillInner = NUCLEUS_AMBER.copy(alpha = if (isDarkMode) 0.38f else 0.25f)
    val fillMid   = NUCLEUS_AMBER.copy(alpha = if (isDarkMode) 0.22f else 0.15f)
    val fillOuter = NUCLEUS_AMBER.copy(alpha = 0f)
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(fillInner, fillMid, fillOuter),
            center = center,
            radius = outerRadius,
        ),
        radius = outerRadius,
        center = center,
    )

    // Seven shells, thin strokes, slightly warmer amber than the fill so
    // they read against the gradient.
    val shellColor = NUCLEUS_AMBER
    NUCLEUS_SHELL_FRACTIONS.forEachIndexed { i, frac ->
        val r = outerRadius * frac
        drawCircle(
            color = shellColor.copy(alpha = NUCLEUS_SHELL_OPACITIES[i]),
            radius = r,
            center = center,
            style = Stroke(width = 0.9f),
        )
    }

    // Soft inner core. Amber (not white), no hard-edge core dot. A
    // small warm centre of light that doesn't punch out of the scene.
    val coreRadius = outerRadius * 0.10f
    drawCircle(
        color = NUCLEUS_AMBER.copy(alpha = if (isDarkMode) 0.35f else 0.25f),
        radius = coreRadius * 2.2f,
        center = center,
    )
    drawCircle(
        color = NUCLEUS_AMBER.copy(alpha = if (isDarkMode) 0.70f else 0.55f),
        radius = coreRadius,
        center = center,
    )
}

/**
 * The nucleus "song" — a slow concentric wave emitted from the core
 * every [CellVizConfig.nucleusSongEmissionEveryN] periods. The wave
 * propagates from inside the nucleus outward through the cytoplasm,
 * nearly reaching the membrane before dissolving.
 *
 * Design tuning:
 *  - The wave travels WELL PAST the nucleus boundary (maxR = 0.85 ×
 *    membraneRadius) so it's visible as an expanding ring against the
 *    dark cytoplasm, not trapped inside the nucleus fill's amber glow.
 *  - Stroke is thick (3.5 px in dark mode) so the ring reads clearly
 *    at the low peak opacity.
 *  - Envelope is half-sine so the wave swells in and fades out over
 *    its cycle rather than hard-starting and hard-ending.
 */
private fun DrawScope.drawNucleusSong(
    cx: Float,
    cy: Float,
    nucleusOuterRadius: Float,
    membraneRadius: Float,
    isDarkMode: Boolean,
    cfg: CellVizConfig,
    nowSec: Float,
) {
    if (cfg.nucleusSongPeakOpacity <= 0f) return
    val period = cfg.nucleusSongPeriodSec
    if (period <= 0f) return

    // Which cycle are we in, and are we on an emission cycle?
    val cycleCount = (nowSec / period).toInt()
    if (cycleCount % cfg.nucleusSongEmissionEveryN != 0) return

    val phase = ((nowSec % period) / period).coerceIn(0f, 1f)  // 0..1 within the cycle
    // Half-sine envelope: ramps up, peaks at mid-cycle, ramps down.
    val envelope = sin(phase * PI.toFloat())  // 0 → 1 → 0
    val alphaScale = envelope.coerceIn(0f, 1f)
    if (alphaScale < 0.02f) return

    // Wave grows from the nucleus's inner region out toward the
    // membrane — it travels through the cytoplasm, not just within the
    // nucleus. This is what makes the pulse legible: the ring moves
    // against the dark medium rather than being lost in the nucleus fill.
    val minR = nucleusOuterRadius * 0.20f
    val maxR = membraneRadius * 0.85f
    val r = minR + (maxR - minR) * phase

    val color = NUCLEUS_AMBER.copy(
        alpha = (cfg.nucleusSongPeakOpacity * alphaScale).coerceIn(0f, 1f)
    )
    val strokeWidth = if (isDarkMode) 3.5f else 2.0f
    drawCircle(
        color = color,
        radius = r,
        center = Offset(cx, cy),
        style = Stroke(width = strokeWidth),
    )
}

/**
 * The membrane — six bus arcs around the cell, minus wherever a
 * membrane opening is currently punched through them.
 *
 * Rendering strategy (keep it simple, keep it obvious):
 *  1. For each bus segment, subtract all current opening ranges to
 *     produce a list of un-occluded sub-arcs.
 *  2. Draw each sub-arc as either a three-path bloom stack (dark
 *     mode) or a single stroke (light mode).
 *
 * Rotation is applied uniformly to every arc; each segment's own
 * start angle is offset by the current rotation so the cell appears
 * to spin as a solid body. Openings are in absolute screen-degrees,
 * so they stay put while the cell rotates through them — a drifting
 * hole that the membrane slides past, exactly as we want.
 */
private fun DrawScope.drawMembrane(
    rotationDeg: Float,
    cx: Float,
    cy: Float,
    radius: Float,
    isDarkMode: Boolean,
    cfg: CellVizConfig,
    openingRanges: List<ClosedFloatingPointRange<Float>>,
) {
    BUS_SEGMENTS.forEach { seg ->
        // Segment spans are in the cell's body frame; add rotation to
        // convert into the same absolute-screen-degrees space that
        // opening ranges live in, then subtract any overlaps.
        val segStart = (seg.startDeg + rotationDeg) % 360f
        val segEnd   = (seg.endDeg   + rotationDeg) % 360f

        val subArcs = subtractRangesFromArc(segStart, segEnd, openingRanges)

        subArcs.forEach { (subStart, subSweep) ->
            if (subSweep <= 0.5f) return@forEach  // skip hair-thin slivers
            if (isDarkMode) {
                // Three-path bloom stack — cheapest form of glow that still reads.
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = 0.22f), cfg.busArcOuterHaloWidth)
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = 0.35f), cfg.busArcMidHaloWidth)
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color,                     cfg.busArcStrokeWidth)
            } else {
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color, cfg.busArcStrokeWidth * 0.75f)
            }
        }
    }
}

/**
 * Subtract a list of opening ranges (absolute degrees, possibly wrapping
 * past 0/360) from a single bus-arc range.
 *
 * Returned sub-arcs are expressed as `(startDeg, sweepDeg)` pairs ready
 * to hand to [drawBusArc]. The arc itself may wrap past 0/360 — in that
 * case we decompose the arc into two non-wrapping halves first, run the
 * subtraction on each, and concatenate. This keeps the inner math simple
 * (closed intervals on [0,360]) at the cost of at most one extra split.
 */
private fun subtractRangesFromArc(
    arcStart: Float,
    arcEnd: Float,
    openings: List<ClosedFloatingPointRange<Float>>,
): List<Pair<Float, Float>> {
    // Decompose the arc into up to two non-wrapping pieces.
    val arcPieces: List<Pair<Float, Float>> =
        if (arcEnd >= arcStart) listOf(arcStart to arcEnd)
        else listOf(arcStart to 360f, 0f to arcEnd)

    val result = mutableListOf<Pair<Float, Float>>()
    for ((pStart, pEnd) in arcPieces) {
        val overlaps = openings
            .mapNotNull { r ->
                val s = r.start.coerceIn(pStart, pEnd)
                val e = r.endInclusive.coerceIn(pStart, pEnd)
                if (e > s) s to e else null
            }
            .sortedBy { it.first }

        var cursor = pStart
        for ((oStart, oEnd) in overlaps) {
            if (oStart > cursor) result += cursor to oStart
            cursor = maxOf(cursor, oEnd)
        }
        if (cursor < pEnd) result += cursor to pEnd
    }
    // Convert (start, end) to (start, sweep)
    return result.map { (s, e) -> s to (e - s) }
}

/**
 * Primitive: one arc stroke at a given angle/width/color.
 * Uses the canvas's drawArc on a square bounding box around the cell.
 */
private fun DrawScope.drawBusArc(
    cx: Float,
    cy: Float,
    radius: Float,
    startDeg: Float,
    sweepDeg: Float,
    color: Color,
    strokeWidth: Float,
) {
    drawArc(
        color = color,
        startAngle = startDeg,
        sweepAngle = sweepDeg,
        useCenter = false,
        topLeft = Offset(cx - radius, cy - radius),
        size = androidx.compose.ui.geometry.Size(radius * 2f, radius * 2f),
        style = Stroke(width = strokeWidth, cap = StrokeCap.Butt),
    )
}

/**
 * Adapter ports — diamonds and hexagons anchored on their owning bus
 * arc. Within a bus segment, ports spread evenly with a fixed margin
 * from each segment boundary, so a single-adapter bus sits centered
 * and a three-adapter bus spreads across the arc without touching its
 * neighbors.
 *
 * In dark mode each port gets a halo + core bloom (two extra circles).
 * Inactive adapters render at 35% alpha.
 */
private fun DrawScope.drawAdapterPorts(
    adaptersByBus: Map<CellBus, List<AdapterOrbit>>,
    rotationDeg: Float,
    centerX: Float,
    centerY: Float,
    membraneRadius: Float,
    isDarkMode: Boolean,
    cfg: CellVizConfig,
) {
    BUS_SEGMENTS.forEach { seg ->
        val adapters = adaptersByBus[seg.bus] ?: return@forEach
        if (adapters.isEmpty()) return@forEach

        adapters.forEachIndexed { index, adapter ->
            val angleDeg = spreadAngle(seg, index, adapters.size, cfg.portSegmentMarginDeg)
            val effectiveDeg = (angleDeg + rotationDeg) % 360f
            val pos = polar(centerX, centerY, membraneRadius, effectiveDeg)

            val alpha = if (adapter.isActive) 1f else cfg.portInactiveAlpha
            drawPort(
                center = pos,
                radius = cfg.portRadiusPx,
                color = seg.color,
                shape = portShapeFor(seg.bus),
                isDarkMode = isDarkMode,
                alpha = alpha,
                rotationDeg = effectiveDeg,
            )
        }
    }
}

/**
 * Spread N ports evenly across a segment's arc with a margin from each
 * boundary. For N=1 the port sits at the segment midpoint; for N>=2 the
 * first port is at startDeg+margin and the last at endDeg-margin.
 *
 * Openings in the membrane are dynamic and may briefly cross a port;
 * that's fine — the port renders on top of the arc layer, so a drifting
 * aperture just gives the impression that the port is being passed by.
 */
private fun spreadAngle(seg: BusSegment, index: Int, total: Int, marginDeg: Float): Float {
    val usable = seg.sweepDeg - 2f * marginDeg
    return when {
        total <= 1 -> seg.midDeg
        else       -> seg.startDeg + marginDeg + (index.toFloat() / (total - 1)) * usable
    }
}

/**
 * Draw one adapter port — core shape + optional halo in dark mode.
 * The port is oriented so the shape's "flat side" faces the center of
 * the cell, which reads as a docked connector rather than a floating
 * badge.
 */
private fun DrawScope.drawPort(
    center: Offset,
    radius: Float,
    color: Color,
    shape: PortShape,
    isDarkMode: Boolean,
    alpha: Float,
    rotationDeg: Float,
) {
    val shapePath = when (shape) {
        PortShape.DIAMOND -> diamondPath(center, radius, rotationDeg)
        PortShape.HEX     -> hexPath(center, radius, rotationDeg)
    }

    if (isDarkMode) {
        // Bloom halo behind the port — two softer circles stacked.
        drawCircle(color = color.copy(alpha = 0.18f * alpha), radius = radius * 2.0f, center = center)
        drawCircle(color = color.copy(alpha = 0.32f * alpha), radius = radius * 1.25f, center = center)
    }

    drawPath(
        path = shapePath,
        color = color.copy(alpha = alpha),
    )
    drawPath(
        path = shapePath,
        color = (if (isDarkMode) Color.White else Color.Black).copy(alpha = 0.35f * alpha),
        style = Stroke(width = 1.3f),
    )
}

/**
 * Draw the cytoplasm motes — memory graph nodes as small luminous
 * points drifting between the nucleus and the membrane.
 *
 * Positioning formula per mote (deterministic, no stored state):
 *  - baseAngleDeg = stableIndex × 137.508 (golden angle) mod 360
 *  - baseRadialFrac = sqrt((stableIndex + 0.5) / totalCount)
 *     → uniform 2D density (each equal-area ring has ~equal motes)
 *  - radial = lerp(nucleusRadius × 1.10, membraneRadius × 0.92, frac)
 *  - driftX = sin(t × wX + phaseX) × amp
 *  - driftY = cos(t × wY + phaseY) × amp
 *
 * Per-mote frequencies and phases come from the stableIndex so every
 * mote drifts a little differently — the cloud looks alive without
 * any mote mutating its own state.
 *
 * Newly-born motes fade in over [cfg.moteBirthMs] with a brief white
 * halo, then settle into ambient rendering.
 */
private fun DrawScope.drawCytoplasmMotes(
    motes: List<CytoplasmMote>,
    cx: Float,
    cy: Float,
    nucleusRadius: Float,
    membraneRadius: Float,
    nowMs: Long,
    isDarkMode: Boolean,
    colorTheme: ai.ciris.mobile.shared.ui.theme.ColorTheme,
    cfg: CellVizConfig,
) {
    if (motes.isEmpty()) return
    val totalCount = motes.size.coerceAtLeast(1)
    val innerRadial = nucleusRadius * 1.10f
    val outerRadial = membraneRadius * 0.92f
    if (outerRadial <= innerRadial) return

    val nowSec = nowMs / 1000f
    val driftOmega = if (cfg.moteDriftPeriodSec > 0f)
        (2f * PI.toFloat()) / cfg.moteDriftPeriodSec
    else 0f

    motes.forEach { mote ->
        val idx = mote.stableIndex

        // Base position via golden-angle scatter + sqrt radial.
        val angleDeg = ((idx.toFloat() * GOLDEN_ANGLE_DEG) % 360f + 360f) % 360f
        val radialFrac = kotlin.math.sqrt((idx + 0.5f) / totalCount.toFloat())
            .coerceIn(0f, 1f)
        val r = innerRadial + (outerRadial - innerRadial) * radialFrac
        val angleRad = angleDeg.toDouble() * PI / 180.0
        val bx = cx + r * cos(angleRad).toFloat()
        val by = cy + r * sin(angleRad).toFloat()

        // Per-mote drift. Derived from index so it's deterministic.
        // Each mote gets a unique (phase, freq-multiplier) without any
        // RNG call in the hot path.
        val phaseX = (idx * 0.7531f) % (2f * PI.toFloat())
        val phaseY = (idx * 1.2847f) % (2f * PI.toFloat())
        val wX = driftOmega * (0.85f + 0.30f * ((idx * 31) % 17) / 17f)
        val wY = driftOmega * (0.80f + 0.40f * ((idx * 53) % 19) / 19f)
        val dx = sin(nowSec * wX + phaseX) * cfg.moteDriftAmpPx
        val dy = cos(nowSec * wY + phaseY) * cfg.moteDriftAmpPx

        val pos = Offset(bx + dx, by + dy)

        // Birth animation — fade-in + brief bright halo.
        val birthAge = if (mote.birthTimeMs > 0L) nowMs - mote.birthTimeMs else Long.MAX_VALUE
        val birthProgress = if (cfg.moteBirthMs > 0L)
            (birthAge.toFloat() / cfg.moteBirthMs).coerceIn(0f, 1f)
        else 1f
        val birthScale = smoothstep(birthProgress)  // 0 → 1

        // Scope-tinted color from the current theme. getScopeColor picks
        // the right accent so motes recolor when the user changes theme.
        val moteColor = colorTheme.getScopeColor(mote.scope)

        // Core dot — small, solid-ish. Alpha scaled by birth progress.
        val coreRadius = cfg.moteRadiusPx * birthScale
        if (coreRadius < 0.4f) return@forEach

        if (isDarkMode) {
            // Soft halo in dark mode so motes read like distant stars,
            // not painted specks. Two stacked circles — no shader.
            drawCircle(
                color = moteColor.copy(alpha = 0.22f * birthScale),
                radius = coreRadius * 2.5f,
                center = pos,
            )
            drawCircle(
                color = moteColor.copy(alpha = 0.38f * birthScale),
                radius = coreRadius * 1.6f,
                center = pos,
            )
        }
        drawCircle(
            color = moteColor.copy(alpha = (if (isDarkMode) 0.95f else 0.70f) * birthScale),
            radius = coreRadius,
            center = pos,
        )

        // Birth halo — a single white ring pulse over the birth window.
        if (birthProgress < 1f) {
            val haloAlpha = (1f - birthProgress) * 0.85f
            drawCircle(
                color = Color.White.copy(alpha = haloAlpha),
                radius = coreRadius * (2.8f + 1.5f * birthProgress),
                center = pos,
                style = Stroke(width = 1.2f),
            )
        }
    }
}

/** Golden angle in degrees — 137.508° ≈ 360° × (1 − 1/φ) where φ is the golden ratio. */
private const val GOLDEN_ANGLE_DEG = 137.50776f

// -----------------------------------------------------------------------------
// Geometry helpers — no Compose dependencies, trivial math
// -----------------------------------------------------------------------------

/** Convert a polar (radius, degrees) coord to an Offset in screen space. */
private fun polar(cx: Float, cy: Float, r: Float, deg: Float): Offset {
    val rad = deg.toDouble() * PI / 180.0
    return Offset(cx + r * cos(rad).toFloat(), cy + r * sin(rad).toFloat())
}

/**
 * A diamond aligned so its long axis points radially outward from the
 * cell's center — adapterRotationDeg is the angle from center to the
 * port's position.
 */
private fun diamondPath(center: Offset, radius: Float, adapterRotationDeg: Float): Path {
    val rad = adapterRotationDeg.toDouble() * PI / 180.0
    val outward = Offset(cos(rad).toFloat(), sin(rad).toFloat())
    val tangent = Offset(-outward.y, outward.x)
    // Slight asymmetry — the diamond is a touch longer on its radial
    // axis than its tangential axis, giving a "docked plug" silhouette.
    val radial  = radius * 1.1f
    val lateral = radius * 0.85f
    return Path().apply {
        moveTo(center.x + outward.x * radial,  center.y + outward.y * radial)
        lineTo(center.x + tangent.x * lateral, center.y + tangent.y * lateral)
        lineTo(center.x - outward.x * radial,  center.y - outward.y * radial)
        lineTo(center.x - tangent.x * lateral, center.y - tangent.y * lateral)
        close()
    }
}

/**
 * A regular hexagon with one flat oriented tangent to the membrane.
 */
private fun hexPath(center: Offset, radius: Float, adapterRotationDeg: Float): Path {
    val path = Path()
    for (i in 0 until 6) {
        val angleRad = ((60f * i - 30f + adapterRotationDeg) * PI / 180.0).toFloat()
        val x = center.x + radius * cos(angleRad)
        val y = center.y + radius * sin(angleRad)
        if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
    }
    path.close()
    return path
}
