package ai.ciris.mobile.shared.ui.screens.graph

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

    /** Max gratitude motes in flight at once (step 6). */
    val maxGratitudeMotesInFlight: Int = 1,

    /** Minimum seconds between gratitude-mote emissions (step 6). */
    val gratitudeCooldownSec: Float = 3f,

    /** Maximum in-flight floating "caught" event bubbles on the UI layer. */
    val maxCaughtBubbles: Int = 12,

    /** Breathing period in seconds (step 4 — active-presence rhythm). */
    val breathePeriodSec: Float = 6f,

    /** Peak scale added on the breathe animation (0.008 = 0.8%). */
    val breatheScaleAmp: Float = 0.010f,

    /** Nucleus song period in seconds (step 4). */
    val nucleusSongPeriodSec: Float = 8f,
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
            maxGratitudeMotesInFlight = maxGratitudeMotesInFlight.coerceIn(0, 4),
            gratitudeCooldownSec      = gratitudeCooldownSec.coerceIn(0.5f, 60f),
            maxCaughtBubbles          = maxCaughtBubbles.coerceIn(0, 32),
            breathePeriodSec          = breathePeriodSec.coerceIn(2f, 30f),
            breatheScaleAmp           = breatheScaleAmp.coerceIn(0f, 0.03f),
            nucleusSongPeriodSec      = nucleusSongPeriodSec.coerceIn(2f, 30f),
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

    Canvas(modifier = modifier) {
        val centerX = size.width / 2f
        val centerY = size.height / 2f
        val membraneRadius = minOf(size.width, size.height) * cfg.membraneRadiusFraction

        drawMedium(isDarkMode, centerX, centerY)
        drawCellBodyAura(isDarkMode, centerX, centerY, membraneRadius * 1.05f)
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
        drawAdapterPorts(
            adaptersByBus = adaptersByBus,
            rotationDeg = rotationDeg,
            centerX = centerX, centerY = centerY,
            membraneRadius = membraneRadius,
            isDarkMode = isDarkMode,
            cfg = cfg,
        )
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
 */
private fun DrawScope.drawCellBodyAura(
    isDarkMode: Boolean,
    cx: Float,
    cy: Float,
    radius: Float,
) {
    val (inner, outer) = if (isDarkMode) {
        Color(0xFF3A2A1E).copy(alpha = 0.12f) to Color(0xFF0A0D14).copy(alpha = 0f)
    } else {
        Color(0xFFFFFAF3).copy(alpha = 0.50f) to Color(0xFFD9C7B3).copy(alpha = 0f)
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
