package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.api.models.GraphScope
import kotlin.math.PI
import kotlin.math.sin

/*
 * Pure domain model + math for the cell visualization.
 *
 * This file intentionally does NOT depend on Compose — everything here
 * is testable from plain unit tests in commonTest. The companion file
 * [CellVisualization.kt] owns all Compose-dependent work (draw calls,
 * colours, coordinates).
 *
 * The `internal` visibility on helpers lets tests in the same module
 * reach in without making the API public.
 */

// =============================================================================
// Buses — which of the six CIRIS message buses a membrane arc represents
// =============================================================================

/**
 * Identifier for one of CIRIS's six message buses. The set and order
 * of values is load-bearing — see FSD/CELL_VIZ_REDESIGN.md §2.
 */
enum class CellBus { COMM, MEMORY, LLM, TOOL, RUNTIME, WISE }

/**
 * Which rendered shape a bus uses for its adapter ports.
 * - [DIAMOND]: flow-shaped buses (COMM, LLM, TOOL, RUNTIME)
 * - [HEX]: graph-shaped buses (MEMORY, WISE)
 */
internal enum class PortShape { DIAMOND, HEX }

internal fun portShapeFor(bus: CellBus): PortShape = when (bus) {
    CellBus.MEMORY, CellBus.WISE -> PortShape.HEX
    else -> PortShape.DIAMOND
}

/**
 * Map an adapter's type string onto the bus that owns it. Unknown
 * types default to TOOL so a new adapter still renders somewhere
 * visible (rather than silently vanishing).
 */
internal fun adapterBus(type: String): CellBus = when (type.lowercase()) {
    "api", "discord", "cli" -> CellBus.COMM
    "weather", "navigation", "home_assistant", "ha",
    "wallet", "reddit", "mcp", "apple_notes", "apple_reminders",
    "bear_notes", "bird", "blogwatcher" -> CellBus.TOOL
    "cirisverify" -> CellBus.WISE
    // LLM, MEMORY, RUNTIME don't typically surface as "adapter" entries
    // in the current data model. Default to TOOL.
    else -> CellBus.TOOL
}

// =============================================================================
// Membrane openings — dynamic apertures
// =============================================================================
//
// 3–5 apertures exist at any time; each one grows in, drifts slightly,
// stabilizes, then shrinks out. When one dies, a replacement spawns
// elsewhere. Renders "openness" and "imperfection" as continuous motion,
// completely avoiding the "looks like a bug" read of a static gap.
//
// The openings CUT bus arcs — wherever an opening overlaps a bus, that
// portion of the arc is not drawn. Adapter ports still render on top
// because they sit above the arc layer.

/**
 * One aperture in the cell membrane at a given moment in time.
 *
 * An opening has a deterministic lifecycle: grow → stable → shrink → die.
 * All timing is expressed in wall-clock ms so the renderer can drive
 * its state purely from the current time, without per-frame mutation
 * of the opening itself. Creating a new [MembraneOpening] is the only
 * mutation; everything else is a pure function of age.
 */
internal data class MembraneOpening(
    val id: Long,
    /** Initial position of the opening's center (degrees, 0..360). */
    val birthCenterDeg: Float,
    /** Target angular width at full growth (degrees). */
    val targetWidthDeg: Float,
    /** Opening walks around the cell at this rate (deg/sec; can be negative). */
    val driftDegPerSec: Float,
    /** Wall-clock millis when this opening was born. */
    val bornAtMs: Long,
    /** Grow-in duration from 0 → [targetWidthDeg] (ms). */
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

/**
 * Classic smoothstep easing — C¹ continuous, no library dependency.
 * Used for the grow-in and shrink-out envelopes of membrane openings
 * and for the mote birth animation.
 */
internal fun smoothstep(t: Float): Float {
    val x = t.coerceIn(0f, 1f)
    return x * x * (3f - 2f * x)
}

/**
 * Build a new opening with randomized width, drift, and stable
 * duration picked from the configured ranges. Spawn position is
 * uniform around the cell so openings don't cluster.
 *
 * `rng` is injectable so tests can pass a seeded [kotlin.random.Random]
 * and assert deterministic outputs.
 */
internal fun spawnOpening(
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
 * straddling the 0°/360° boundary returns two ranges; all others
 * return one. An opening with zero current width (freshly spawned or
 * just dying) returns an empty list.
 */
internal fun openingRanges(
    op: MembraneOpening,
    nowMs: Long,
): List<ClosedFloatingPointRange<Float>> {
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

/**
 * Subtract a list of opening ranges (absolute degrees, possibly
 * wrapping past 0/360) from a single bus-arc range.
 *
 * Returned sub-arcs are expressed as `(startDeg, sweepDeg)` pairs
 * ready for Compose's `drawArc`. The arc itself may wrap past 0/360
 * — in that case we decompose the arc into two non-wrapping halves
 * first, run the subtraction on each, and concatenate. Keeps the
 * inner math simple (closed intervals on [0,360]) at the cost of at
 * most one extra split.
 */
internal fun subtractRangesFromArc(
    arcStart: Float,
    arcEnd: Float,
    openings: List<ClosedFloatingPointRange<Float>>,
): List<Pair<Float, Float>> {
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
    return result.map { (s, e) -> s to (e - s) }
}

// =============================================================================
// Cytoplasm motes — memory graph as drifting luminous points
// =============================================================================

/**
 * One node from the memory graph, laid out as a drifting mote in the
 * cytoplasm (the region between the nucleus and the membrane).
 *
 * The [stableIndex] is what determines this mote's angular + radial
 * placement via the golden-angle formula. Preserving the same index
 * across refreshes means a node doesn't "teleport" around the cell
 * when neighbouring nodes appear or disappear — it breathes in place.
 */
internal data class CytoplasmMote(
    val id: String,
    val scope: GraphScope,
    val stableIndex: Int,
    val birthTimeMs: Long,
)

/**
 * Golden angle in degrees — 137.508° ≈ 360° × (1 − 1/φ) where φ is
 * the golden ratio. Placing points at integer multiples of this
 * angle gives the most visually uniform distribution on a disc —
 * no banding or clustering at any integer count.
 */
internal const val GOLDEN_ANGLE_DEG: Float = 137.50776f

/**
 * Spread N adapter ports evenly across a bus segment's arc with a
 * margin from each boundary. For N=1 the port sits at the segment
 * midpoint; for N≥2 the first port is at `startDeg + margin` and the
 * last at `endDeg - margin`.
 */
internal fun spreadAngle(
    segmentStartDeg: Float,
    segmentEndDeg: Float,
    index: Int,
    total: Int,
    marginDeg: Float,
): Float {
    val midDeg = (segmentStartDeg + segmentEndDeg) / 2f
    val sweepDeg = segmentEndDeg - segmentStartDeg
    val usable = sweepDeg - 2f * marginDeg
    return when {
        total <= 1 -> midDeg
        else       -> segmentStartDeg + marginDeg +
                      (index.toFloat() / (total - 1)) * usable
    }
}

// =============================================================================
// Shared math helpers
// =============================================================================

/**
 * Half-sine envelope: 0 at phase=0, peaks at 1 at phase=0.5, 0 at
 * phase=1. Useful for any primitive that should swell in and fade out
 * smoothly over a normalized cycle.
 */
internal fun halfSineEnvelope(phase: Float): Float {
    val p = phase.coerceIn(0f, 1f)
    return sin(p * PI.toFloat()).coerceAtLeast(0f)
}
