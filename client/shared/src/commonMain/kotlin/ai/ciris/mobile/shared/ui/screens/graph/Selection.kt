package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.sqrt

/*
 * FG selection model. Pure Kotlin — no Compose imports — so the hit
 * tester is fully unit-testable from commonTest.
 *
 * Selection is only possible in FG mode (see FSD §12). BG stays a
 * passive glance surface. Each selectable element carries just enough
 * payload for the ViewModel to drive a live detail panel — we don't
 * embed the actual runtime data here, just the *key* needed to fetch
 * it.
 */

/** One selectable element in the cell viz. */
sealed interface SelectionKind {
    /** A diamond/hex port sitting on a bus arc. */
    data class AdapterPort(
        val adapterId: String,
        val adapterType: String,
        val bus: CellBus,
    ) : SelectionKind

    /**
     * A bus-arc segment on the membrane. Tapping an arc that has a
     * port on it should prefer the port (hit-tester priority).
     */
    data class BusArc(val bus: CellBus) : SelectionKind

    /** One of the 7 concentric nucleus shells (0 = innermost). */
    data class NucleusShell(
        val stageIndex: Int,
        /** SSE event_type this shell maps to, e.g. "thought_start". */
        val eventType: String,
    ) : SelectionKind

    /** The nucleus core — the amber centre. Selects the whole agent. */
    data object NucleusCore : SelectionKind

    /** A memory-graph mote drifting in the cytoplasm. */
    data class CytoplasmMote(
        val nodeId: String,
        /** Scope string ("LOCAL" / "IDENTITY" / "ENVIRONMENT" / "COMMUNITY"). */
        val scope: String,
    ) : SelectionKind

    /**
     * A signal channel from a specific port. Functionally aliases to
     * [AdapterPort] — the hit tester never returns this on a direct
     * tap; the ViewModel may coerce `AdapterPort` → `SignalChannel`
     * when the user's intent is to see channel traffic specifically.
     */
    data class SignalChannel(val adapterId: String, val bus: CellBus) : SelectionKind

    /** A gratitude mote in-flight. */
    data class GratitudeMote(
        val startMs: Long,
        /** When the SSE payload carried a task id, use it for surgical detail fetch. */
        val taskId: String? = null,
    ) : SelectionKind
}

// =============================================================================
// Hit-testing — pure geometry, no Compose
// =============================================================================

/**
 * Layout inputs the hit tester needs. All distances are in pixels in
 * the viz's own coordinate space (same coordinates the draw code uses).
 */
data class SelectionLayout(
    val centerX: Float,
    val centerY: Float,
    val membraneRadius: Float,
    val nucleusRadius: Float,
    /** Current rotation applied to bus arcs / ports, in degrees. */
    val rotationDeg: Float,
    /** Membrane-port hit radius in px (a bit larger than the drawn shape). */
    val portHitRadiusPx: Float = 18f,
    /** Membrane arc hit thickness in px on either side of the arc line. */
    val busArcHitThicknessPx: Float = 12f,
    /** Mote hit radius in px. */
    val moteHitRadiusPx: Float = 8f,
)

/**
 * One cytoplasm mote's position for hit testing. Kept as a tiny POJO
 * rather than re-reading [CytoplasmMote] so the tester stays free of
 * drift-math (caller already has screen-space positions).
 */
data class SelectionMote(
    val nodeId: String,
    val scope: String,
    val x: Float,
    val y: Float,
)

/**
 * One adapter port's position for hit testing.
 */
data class SelectionPort(
    val adapterId: String,
    val adapterType: String,
    val bus: CellBus,
    val x: Float,
    val y: Float,
)

/**
 * Test a pointer tap against the visible elements. Priority order
 * (highest first) — the FIRST match wins:
 *
 *   1. AdapterPort (diamond/hex on membrane)   — small, precise target
 *   2. CytoplasmMote                            — small, inside the membrane
 *   3. NucleusCore                              — innermost shell region
 *   4. NucleusShell (0..6)                      — concentric rings
 *   5. BusArc                                   — large, outermost
 *
 * If the tap is outside the membrane + a small grace margin, returns
 * null (deselect). The BusArc match uses membrane-hit thickness so a
 * tap *on* the ring hits it, rather than requiring pixel-accurate aim.
 */
fun hitTestSelection(
    tapX: Float,
    tapY: Float,
    layout: SelectionLayout,
    ports: List<SelectionPort>,
    motes: List<SelectionMote>,
    /**
     * The 7 H3ERE pipeline event types in shell order (innermost →
     * outermost). Matches `PipelineStage.STAGE_DEFINITIONS`.
     */
    shellEventTypes: List<String>,
): SelectionKind? {
    // 1. Adapter ports — circular hit test in world coordinates.
    for (p in ports) {
        if (distanceSq(tapX, tapY, p.x, p.y) <=
            layout.portHitRadiusPx * layout.portHitRadiusPx) {
            return SelectionKind.AdapterPort(
                adapterId = p.adapterId,
                adapterType = p.adapterType,
                bus = p.bus,
            )
        }
    }

    // 2. Cytoplasm motes — circular hit test.
    for (m in motes) {
        if (distanceSq(tapX, tapY, m.x, m.y) <=
            layout.moteHitRadiusPx * layout.moteHitRadiusPx) {
            return SelectionKind.CytoplasmMote(nodeId = m.nodeId, scope = m.scope)
        }
    }

    val dx = tapX - layout.centerX
    val dy = tapY - layout.centerY
    val r = sqrt(dx * dx + dy * dy)

    // Outside the membrane (+ a small slack for mistaps on the edge).
    val outerSlack = 6f
    if (r > layout.membraneRadius + outerSlack) return null

    // 3. Nucleus core — anything inside the innermost shell boundary.
    val innermostShellR = layout.nucleusRadius * NUCLEUS_SHELL_CORE_FRACTION
    if (r <= innermostShellR) return SelectionKind.NucleusCore

    // 4. Nucleus shell — map radial distance inside the nucleus to
    //    the 7 shell bands, returning the matching stage index.
    if (r <= layout.nucleusRadius) {
        val shellIndex = shellIndexForRadius(r, layout.nucleusRadius)
        if (shellIndex != null && shellIndex < shellEventTypes.size) {
            return SelectionKind.NucleusShell(
                stageIndex = shellIndex,
                eventType = shellEventTypes[shellIndex],
            )
        }
    }

    // 5. Bus arc — tap close to the membrane line (inside or outside).
    if (r >= layout.membraneRadius - layout.busArcHitThicknessPx &&
        r <= layout.membraneRadius + layout.busArcHitThicknessPx) {
        val bus = busAtAngle(layout.rotationDeg, dx, dy)
        if (bus != null) return SelectionKind.BusArc(bus)
    }

    // Anything else inside the cell (cytoplasm but not on a mote) is
    // intentionally un-selectable — empty space is empty space.
    return null
}

/** Radius fraction of the nucleus treated as "core" — innermost shell center. */
private const val NUCLEUS_SHELL_CORE_FRACTION = 0.30f

/**
 * Return the shell index (0..6) a radial distance falls into, given
 * the nucleus outer radius. Boundaries match [NUCLEUS_SHELL_FRACTIONS]
 * in the draw code but widened slightly so tap targets overlap.
 */
internal fun shellIndexForRadius(r: Float, nucleusOuterR: Float): Int? {
    if (nucleusOuterR <= 0f || r <= 0f) return null
    val frac = (r / nucleusOuterR).coerceIn(0f, 1f)
    // 7 shells at fractions 0.25, 0.35, 0.45, 0.55, 0.65, 0.78, 0.92.
    // Midpoint boundaries between consecutive shells, with the first
    // shell's band ending at 0.30 (the core's top boundary).
    val boundaries = floatArrayOf(0.30f, 0.40f, 0.50f, 0.60f, 0.71f, 0.85f, 1.01f)
    for (i in boundaries.indices) {
        if (frac <= boundaries[i]) return i
    }
    return null
}

/**
 * Identify which bus arc's 60° segment the tap fell inside, accounting
 * for the current ring rotation. Returns null if the computed angle
 * doesn't map to any segment (shouldn't happen for a full ring, but
 * guards against fp edge cases).
 */
internal fun busAtAngle(rotationDeg: Float, dx: Float, dy: Float): CellBus? {
    // Compose convention: 0° = east (+x), angles increase clockwise
    // (in standard math orientation, +y points down on screen).
    var deg = (atan2(dy.toDouble(), dx.toDouble()) * 180.0 / PI).toFloat()
    if (deg < 0f) deg += 360f
    // Undo the rotation so we can test against BUS_SEGMENTS' canonical
    // start/end angles (which are the un-rotated layout).
    var canonical = ((deg - rotationDeg) % 360f + 360f) % 360f
    // Each bus owns 60°; slot index = canonical / 60.
    val slot = (canonical / 60f).toInt().coerceIn(0, 5)
    return when (slot) {
        0 -> CellBus.TOOL       // 0–60°
        1 -> CellBus.LLM        // 60–120°
        2 -> CellBus.MEMORY     // 120–180°
        3 -> CellBus.COMM       // 180–240°
        4 -> CellBus.WISE       // 240–300°
        5 -> CellBus.RUNTIME    // 300–360°
        else -> null
    }
}

/** Squared distance, avoiding a sqrt when only the comparison is needed. */
internal fun distanceSq(ax: Float, ay: Float, bx: Float, by: Float): Float {
    val dx = ax - bx
    val dy = ay - by
    return dx * dx + dy * dy
}
