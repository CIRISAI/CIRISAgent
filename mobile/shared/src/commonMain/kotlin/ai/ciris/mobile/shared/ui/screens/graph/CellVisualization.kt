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
// CellVisualization — Compose-dependent rendering of the cell
// =============================================================================
//
// Pure domain model + math lives in [CellVizModel.kt]. User-tunable config
// lives in [CellVizConfig.kt]. This file is the only one that depends on
// Compose, so it stays small-ish and every non-draw function we own can be
// unit-tested from commonTest against the model file.
//
// See FSD/CELL_VIZ_REDESIGN.md for the full design. Quick map of which
// steps are wired in here:
//
//   Step 3 (cell skeleton):   bus arcs, adapter ports, membrane openings
//   Step 4 (nucleus):         static nucleus + breathing
//   Step 5 (cytoplasm):       golden-angle motes with drift + birth halo
//   Step 6+ (events):         not yet — rhythmic bus shimmer, gratitude
//                              motes, deferral ripple, etc. land later.

// -----------------------------------------------------------------------------
// Bus segments — load-bearing, do not rearrange
// -----------------------------------------------------------------------------

/**
 * Fixed angle + color for a bus arc on the membrane. Angles are in
 * degrees, Compose convention (0° = east, clockwise).
 *
 * This data class depends on Compose via [Color], which is why it
 * lives here rather than in the pure-Kotlin [CellVizModel.kt].
 */
internal data class BusSegment(
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
 * owns a fixed 60° range of the membrane. Colours are load-bearing
 * (see FSD/CELL_VIZ_REDESIGN.md §2) and must not be made user-tunable.
 */
internal val BUS_SEGMENTS: List<BusSegment> = listOf(
    BusSegment(CellBus.TOOL,    startDeg = 0f,   endDeg = 60f,  color = Color(0xFFD98A2D)),
    BusSegment(CellBus.LLM,     startDeg = 60f,  endDeg = 120f, color = Color(0xFF3D86D9)),
    BusSegment(CellBus.MEMORY,  startDeg = 120f, endDeg = 180f, color = Color(0xFF8B5FD6)),
    BusSegment(CellBus.COMM,    startDeg = 180f, endDeg = 240f, color = Color(0xFF2DA89C)),
    BusSegment(CellBus.WISE,    startDeg = 240f, endDeg = 300f, color = Color(0xFFC9A52A)),
    BusSegment(CellBus.RUNTIME, startDeg = 300f, endDeg = 360f, color = Color(0xFFD8554E)),
)

// -----------------------------------------------------------------------------
// Nucleus styling
// -----------------------------------------------------------------------------

/** Warm amber the nucleus emits — fixed, not theme-derived. */
private val NUCLEUS_AMBER = Color(0xFFE3A64B)

/**
 * Radii of the 7 nucleus shells as fractions of the nucleus outer
 * radius. Picked to be readable but not crowded; each shell is
 * slightly thinner than the last as we move outward.
 */
private val NUCLEUS_SHELL_FRACTIONS = floatArrayOf(
    0.25f, 0.35f, 0.45f, 0.55f, 0.65f, 0.78f, 0.92f,
)

/** Shell opacities, matched index-by-index to [NUCLEUS_SHELL_FRACTIONS]. */
private val NUCLEUS_SHELL_OPACITIES = floatArrayOf(
    0.40f, 0.42f, 0.42f, 0.38f, 0.32f, 0.24f, 0.16f,
)

// =============================================================================
// Public composable
// =============================================================================

/**
 * Cell visualization. Renders the medium, membrane (bus arcs with
 * dynamic openings), cytoplasm motes, adapter ports, and nucleus.
 * Drop-in replacement for [LiveGraphBackground] at call sites that
 * passed the `probeCellVizCapability` gate.
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
 * @param config Every tunable the viz exposes. See [CellVizConfig];
 *   the config is sanitized once per composition so draw code can
 *   assume every field is in a safe range.
 * @param apiClient Optional — when present, cytoplasm motes populate
 *   from the live memory graph. Null means "render the cell empty of
 *   motes", which is a legitimate pre-login state.
 * @param colorTheme Used only to color memory motes via
 *   [getScopeColor]. Bus / adapter / nucleus colours are architectural.
 * @param eventTrigger Incremented by the caller when something happens
 *   that might have changed the memory graph. Step 5 fetches once at
 *   mount; step 6+ makes this reactive.
 */
@Composable
fun CellVisualization(
    modifier: Modifier = Modifier,
    isDarkMode: Boolean = true,
    adapterOrbits: List<AdapterOrbit> = emptyList(),
    externalRotation: Float = 0f,
    config: CellVizConfig = CellVizConfig.DEFAULT,
    apiClient: ai.ciris.mobile.shared.api.CIRISApiClient? = null,
    colorTheme: ai.ciris.mobile.shared.ui.theme.ColorTheme =
        ai.ciris.mobile.shared.ui.theme.ColorTheme.DEFAULT,
    eventTrigger: Int = 0,
    /**
     * Live CIRIS capacity (C/I_int/R/I_inc/S) for this agent's template.
     * Drives the ambient dials — nucleus opacity, bus crispness, breathing
     * steadiness, opening churn, mote warmth. Neutral default means the
     * cell renders as-designed until lens data arrives.
     */
    state: CellVizState = CellVizState.DEFAULT,
) {
    // Sanitize once per composition so draw code reads in-range values.
    val cfg = remember(config) { config.sanitized() }
    // Derive visual dials from CIRIS factors. Recomputed only when the
    // factors change (i.e. once per 15-min capacity refresh).
    val dials = remember(state) { derivedDials(state) }

    // Rotation driver: withFrameNanos accumulates delta-time. Single
    // source of truth for current angle; the membrane, ports, and any
    // future rotating element all derive from it.
    var autoRotationDeg by remember { mutableStateOf(0f) }
    LaunchedEffect(cfg.rotationDegPerSec) {
        var lastFrameNs = 0L
        while (isActive) {
            withFrameNanos { frameTimeNs ->
                if (lastFrameNs != 0L) {
                    val dSec = (frameTimeNs - lastFrameNs) / 1_000_000_000f
                    autoRotationDeg =
                        (autoRotationDeg + cfg.rotationDegPerSec * dSec) % 360f
                }
                lastFrameNs = frameTimeNs
            }
        }
    }
    val rotationDeg = (autoRotationDeg + externalRotation) % 360f

    // Membrane openings: frame-timer effect expires dead openings and
    // spawns new ones to stay within [cfg.minOpenings, cfg.maxOpenings].
    // Current center/width are PURE functions of wall-clock time — per-frame
    // draw just reads them, no mutation of opening fields.
    val openings = remember { mutableStateOf(emptyList<MembraneOpening>()) }
    val nowMs = remember { mutableStateOf(0L) }

    LaunchedEffect(
        cfg.minOpenings, cfg.maxOpenings,
        cfg.openingStableMinSec, cfg.openingStableMaxSec,
        cfg.openingMinWidthDeg, cfg.openingMaxWidthDeg,
        cfg.openingDriftMaxDegPerSec, cfg.openingGrowSec, cfg.openingShrinkSec,
        dials.openingBias,
    ) {
        var lastFrameNs = 0L
        val rng = kotlin.random.Random.Default
        // Humility factor (I_inc) biases the effective target opening count
        // toward maxOpenings when high, toward minOpenings when low. An
        // agent that defers more reads visually as "more porous."
        val targetCount = (cfg.minOpenings +
            (cfg.maxOpenings - cfg.minOpenings) * dials.openingBias)
            .toInt()
            .coerceIn(cfg.minOpenings, cfg.maxOpenings)
        while (isActive) {
            withFrameNanos { frameTimeNs ->
                if (lastFrameNs != 0L) {
                    val now = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                    nowMs.value = now
                    val alive = openings.value.filterNot { it.isDead(now) }
                    val delta = mutableListOf<MembraneOpening>()
                    if (alive.size < cfg.minOpenings) {
                        delta += spawnOpening(now, rng, cfg)
                    } else if (alive.size < targetCount && rng.nextFloat() < 0.002f) {
                        // ~0.12/sec at 60fps; gentle top-up toward bias target.
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

    // Group adapters by bus so ports can spread within each segment.
    val adaptersByBus: Map<CellBus, List<AdapterOrbit>> = remember(adapterOrbits) {
        adapterOrbits.groupBy { adapterBus(it.type) }
    }

    // Cytoplasm motes (memory graph). Fetch on mount + eventTrigger change.
    // stableIndex preserved across refreshes so motes don't teleport.
    val motes = remember { mutableStateOf(emptyList<CytoplasmMote>()) }
    val moteIndexById = remember { mutableMapOf<String, Int>() }
    val nextMoteIndex = remember { mutableStateOf(0) }

    LaunchedEffect(
        apiClient, eventTrigger, cfg.maxMemoryMotes, cfg.memoryLoadWindowHours,
    ) {
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
            val wasPopulated = moteIndexById.isNotEmpty()
            val newMotes = graph.nodes.map { node ->
                val existingIdx = moteIndexById[node.id]
                val idx = existingIdx ?: nextMoteIndex.value.also {
                    moteIndexById[node.id] = it
                    nextMoteIndex.value = it + 1
                }
                val isNew = existingIdx == null && wasPopulated
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

        // Breathing: whole-cell scale + aura opacity pulse, both driven
        // by the same sin-wave phase so the two cues reinforce.
        //
        // Reliability factor (R) modulates breath amplitude. High R =
        // metronomic breath at the default amplitude; low R = dampened
        // breath that feels shallow (reads as reduced vitality). We do
        // NOT inject jitter — the viz goal is to signal drift, not fake
        // agent distress.
        val nowSec = nowMs.value / 1000f
        val breathePhase = (nowSec / cfg.breathePeriodSec) * 2f * PI.toFloat()
        val breatheAmp = cfg.breatheScaleAmp * dials.breathSteadiness
        val breatheScale = 1f + breatheAmp * sin(breathePhase)
        val breatheAuraAlpha = 0.85f + (breatheAmp / 0.010f) * 0.15f *
            (0.5f * (1f + sin(breathePhase)))

        drawMedium(isDarkMode, centerX, centerY)

        // Everything inside the cell scales uniformly; medium does not.
        scale(
            scaleX = breatheScale, scaleY = breatheScale,
            pivot = Offset(centerX, centerY),
        ) {
            drawCellBodyAura(
                isDarkMode = isDarkMode,
                cx = centerX, cy = centerY,
                radius = membraneRadius * 1.05f,
                opacityMultiplier = breatheAuraAlpha,
            )
            val openingAngleRanges = openings.value
                .flatMap { openingRanges(it, nowMs.value) }
            drawMembrane(
                rotationDeg = rotationDeg,
                cx = centerX, cy = centerY,
                radius = membraneRadius,
                isDarkMode = isDarkMode,
                cfg = cfg,
                openingRanges = openingAngleRanges,
                crispness = dials.busCrispness,
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
                warmth = dials.moteWarmth,
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
                opacityScale = dials.nucleusOpacity,
            )

            // The nucleus "song" (slow pulse wave from the core through
            // the cytoplasm) was removed after repeated tuning attempts
            // failed to make it reliably read as *moving* against the
            // dense mote cloud. Rhythmic signalling is now carried by
            // breathing + the per-event pulses landing in step 6.
        }
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
 * body here" without naming it. [opacityMultiplier] is the breathe-
 * driven opacity modulation — the aura brightens and dims in step
 * with the cell's scale pulse so the two cues reinforce.
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

/**
 * The membrane — six bus arcs, minus wherever a membrane opening is
 * currently punched through them. In dark mode each arc renders as a
 * three-path bloom stack (outer halo, mid halo, bright stroke); light
 * mode is a single stroke to keep the diagrammatic feel.
 */
private fun DrawScope.drawMembrane(
    rotationDeg: Float,
    cx: Float,
    cy: Float,
    radius: Float,
    isDarkMode: Boolean,
    cfg: CellVizConfig,
    openingRanges: List<ClosedFloatingPointRange<Float>>,
    /**
     * `dials.busCrispness` in [0.7, 1.0]. Low integrity (I_int < 1.0) fades
     * the bright center stroke — bus arcs stay readable but lose sharpness,
     * which reads as "chain not fully verified" without looking broken.
     */
    crispness: Float = 1f,
) {
    BUS_SEGMENTS.forEach { seg ->
        val segStart = (seg.startDeg + rotationDeg) % 360f
        val segEnd   = (seg.endDeg   + rotationDeg) % 360f
        val subArcs = subtractRangesFromArc(segStart, segEnd, openingRanges)

        subArcs.forEach { (subStart, subSweep) ->
            if (subSweep <= 0.5f) return@forEach
            if (isDarkMode) {
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = 0.22f), cfg.busArcOuterHaloWidth)
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = 0.35f), cfg.busArcMidHaloWidth)
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = crispness), cfg.busArcStrokeWidth)
            } else {
                drawBusArc(cx, cy, radius, subStart, subSweep,
                    seg.color.copy(alpha = crispness), cfg.busArcStrokeWidth * 0.75f)
            }
        }
    }
}

/** One arc stroke at a given angle/width/color. */
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
 * arc. Within a bus segment, ports spread evenly with a margin from
 * each segment boundary so a single-adapter bus sits centered and a
 * multi-adapter bus spreads without touching its neighbours.
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
            val angleDeg = spreadAngle(
                segmentStartDeg = seg.startDeg,
                segmentEndDeg = seg.endDeg,
                index = index,
                total = adapters.size,
                marginDeg = cfg.portSegmentMarginDeg,
            )
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

/** Draw one adapter port — shape + optional halo in dark mode. */
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
        drawCircle(color = color.copy(alpha = 0.18f * alpha),
            radius = radius * 2.0f, center = center)
        drawCircle(color = color.copy(alpha = 0.32f * alpha),
            radius = radius * 1.25f, center = center)
    }

    drawPath(path = shapePath, color = color.copy(alpha = alpha))
    drawPath(
        path = shapePath,
        color = (if (isDarkMode) Color.White else Color.Black).copy(alpha = 0.35f * alpha),
        style = Stroke(width = 1.3f),
    )
}

/**
 * Nucleus — warm amber fill + 7 concentric shells + soft core.
 *
 * Colours are deliberately amber-only (no pure white) so the centre
 * doesn't read as eye-searing against the indigo-black dark medium.
 * The shells are the H3ERE pipeline stages as anatomy; individual
 * shell activation on events lands in step 6.
 */
private fun DrawScope.drawNucleus(
    cx: Float,
    cy: Float,
    outerRadius: Float,
    isDarkMode: Boolean,
    /**
     * `dials.nucleusOpacity` in [0.55, 1.0]. Low Consistency (C < 1.0) fades
     * the nucleus — identity is the literal core, so contradictions register
     * as a dimmer centre. Floored well above 0 so the nucleus never vanishes.
     */
    opacityScale: Float = 1f,
) {
    if (outerRadius <= 1f) return
    val center = Offset(cx, cy)

    val fillInner = NUCLEUS_AMBER.copy(alpha = (if (isDarkMode) 0.38f else 0.25f) * opacityScale)
    val fillMid   = NUCLEUS_AMBER.copy(alpha = (if (isDarkMode) 0.22f else 0.15f) * opacityScale)
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

    NUCLEUS_SHELL_FRACTIONS.forEachIndexed { i, frac ->
        drawCircle(
            color = NUCLEUS_AMBER.copy(alpha = NUCLEUS_SHELL_OPACITIES[i] * opacityScale),
            radius = outerRadius * frac,
            center = center,
            style = Stroke(width = 0.9f),
        )
    }

    val coreRadius = outerRadius * 0.10f
    drawCircle(
        color = NUCLEUS_AMBER.copy(alpha = (if (isDarkMode) 0.35f else 0.25f) * opacityScale),
        radius = coreRadius * 2.2f,
        center = center,
    )
    drawCircle(
        color = NUCLEUS_AMBER.copy(alpha = (if (isDarkMode) 0.70f else 0.55f) * opacityScale),
        radius = coreRadius,
        center = center,
    )
}

/**
 * Draw the cytoplasm motes — memory graph nodes as small luminous
 * points drifting between the nucleus and the membrane.
 *
 * Positioning formula per mote (deterministic, no stored state):
 *   baseAngleDeg  = stableIndex × GOLDEN_ANGLE_DEG mod 360
 *   baseRadialFrac = sqrt((stableIndex + 0.5) / totalCount)
 *   radial        = lerp(nucleusRadius × 1.10, membraneRadius × 0.92, frac)
 *   drift         = per-mote sin/cos using phases derived from index
 *
 * Newly-born motes fade in over [CellVizConfig.moteBirthMs] with a
 * brief white halo, then settle into ambient rendering.
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
    /**
     * `dials.moteWarmth` in [0.2, 1.0]. Driven by the Steering factor (S —
     * ethical faculties passing). High warmth = motes glow as designed
     * (gratitude signal present); low warmth = haloes dim, cytoplasm reads
     * cooler. No color replacement — scope semantics stay intact.
     */
    warmth: Float = 1f,
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

        // Base position: golden-angle scatter + sqrt radial
        val angleDeg = ((idx.toFloat() * GOLDEN_ANGLE_DEG) % 360f + 360f) % 360f
        val radialFrac = kotlin.math.sqrt((idx + 0.5f) / totalCount.toFloat())
            .coerceIn(0f, 1f)
        val r = innerRadial + (outerRadial - innerRadial) * radialFrac
        val angleRad = angleDeg.toDouble() * PI / 180.0
        val bx = cx + r * cos(angleRad).toFloat()
        val by = cy + r * sin(angleRad).toFloat()

        // Per-mote drift — deterministic from index, no RNG in hot path
        val phaseX = (idx * 0.7531f) % (2f * PI.toFloat())
        val phaseY = (idx * 1.2847f) % (2f * PI.toFloat())
        val wX = driftOmega * (0.85f + 0.30f * ((idx * 31) % 17) / 17f)
        val wY = driftOmega * (0.80f + 0.40f * ((idx * 53) % 19) / 19f)
        val dx = sin(nowSec * wX + phaseX) * cfg.moteDriftAmpPx
        val dy = cos(nowSec * wY + phaseY) * cfg.moteDriftAmpPx

        val pos = Offset(bx + dx, by + dy)

        // Birth animation
        val birthAge = if (mote.birthTimeMs > 0L)
            nowMs - mote.birthTimeMs
        else Long.MAX_VALUE
        val birthProgress = if (cfg.moteBirthMs > 0L)
            (birthAge.toFloat() / cfg.moteBirthMs).coerceIn(0f, 1f)
        else 1f
        val birthScale = smoothstep(birthProgress)

        val moteColor = colorTheme.getScopeColor(mote.scope)
        val coreRadius = cfg.moteRadiusPx * birthScale
        if (coreRadius < 0.4f) return@forEach

        if (isDarkMode) {
            // Two-circle halo so motes read like distant stars. Halo
            // brightness is modulated by `warmth` — gratitude present =
            // full glow; faculty failures = motes dim to their cores.
            drawCircle(
                color = moteColor.copy(alpha = 0.22f * birthScale * warmth),
                radius = coreRadius * 2.5f,
                center = pos,
            )
            drawCircle(
                color = moteColor.copy(alpha = 0.38f * birthScale * warmth),
                radius = coreRadius * 1.6f,
                center = pos,
            )
        }
        drawCircle(
            color = moteColor.copy(
                alpha = (if (isDarkMode) 0.95f else 0.70f) * birthScale
            ),
            radius = coreRadius,
            center = pos,
        )

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

// -----------------------------------------------------------------------------
// Geometry helpers — Compose-dependent
// -----------------------------------------------------------------------------

/** Convert a polar (radius, degrees) coord to an Offset in screen space. */
private fun polar(cx: Float, cy: Float, r: Float, deg: Float): Offset {
    val rad = deg.toDouble() * PI / 180.0
    return Offset(cx + r * cos(rad).toFloat(), cy + r * sin(rad).toFloat())
}

/**
 * A diamond aligned so its long axis points radially outward from the
 * cell's center. [adapterRotationDeg] is the angle from center to the
 * port's position.
 */
private fun diamondPath(center: Offset, radius: Float, adapterRotationDeg: Float): Path {
    val rad = adapterRotationDeg.toDouble() * PI / 180.0
    val outward = Offset(cos(rad).toFloat(), sin(rad).toFloat())
    val tangent = Offset(-outward.y, outward.x)
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

/** A regular hexagon with one flat oriented tangent to the membrane. */
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
