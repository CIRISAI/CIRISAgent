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

/**
 * Route an SSE reasoning-stream event to the bus that best represents
 * "where the work is happening". Used by Tier-1 bus-arc shimmer — when
 * an event arrives, the matching bus briefly brightens.
 *
 * Not every event has a clean bus home: `thought_start` kicks off LLM
 * reasoning, `conscience_result` is ethical evaluation (WISE), and
 * `task_complete` is signalled via a gratitude mote rather than a bus
 * shimmer (see §2.5.1), so it returns null here.
 *
 * @param eventType SSE event_type from `ReasoningStreamClient`.
 * @param action Optional action verb (observe/speak/tool/...) when
 *   the event is an `action_result` — needed to distinguish MEMORY
 *   (memorize/recall/forget) from COMM (speak/observe) etc.
 */
fun busFromEventType(eventType: String, action: String? = null): CellBus? = when {
    // Action results — dispatch on the verb.
    eventType == "action_result" -> action?.lowercase()?.let { a ->
        when {
            "memorize" in a || "recall" in a || "forget" in a -> CellBus.MEMORY
            "speak" in a || "observe" in a -> CellBus.COMM
            "tool" in a -> CellBus.TOOL
            "defer" in a -> CellBus.WISE
            "ponder" in a -> CellBus.LLM      // self-directed reasoning
            "reject" in a -> CellBus.RUNTIME  // control response
            "task_complete" in a -> null      // → gratitude mote instead
            else -> null
        }
    }
    // Reasoning pipeline stages.
    eventType == "snapshot_and_context" -> CellBus.MEMORY  // context gathered from graph
    eventType == "thought_start" -> CellBus.LLM
    eventType == "dma_results" -> CellBus.LLM
    eventType == "idma_result" -> CellBus.LLM
    eventType == "aspdma_result" -> CellBus.LLM
    eventType == "tsaspdma_result" -> CellBus.TOOL  // tool-specific refinement
    eventType == "conscience_result" -> CellBus.WISE
    else -> null
}

/**
 * A transient brightness boost applied to one bus arc, in response to
 * an SSE event landing on that bus. Pure data — the rendering layer
 * reads [startMs] to compute decay.
 */
data class BusPulse(val bus: CellBus, val startMs: Long)

/** Duration of a bus-arc shimmer, in milliseconds. */
const val BUS_PULSE_DURATION_MS: Long = 600L

/**
 * Returns 0.0..1.0 intensity of a bus pulse at time [nowMs].
 * 1.0 at spawn, decays smoothly to 0 over [BUS_PULSE_DURATION_MS].
 */
fun busPulseIntensity(pulse: BusPulse, nowMs: Long): Float {
    val elapsed = (nowMs - pulse.startMs).toFloat()
    if (elapsed < 0f || elapsed >= BUS_PULSE_DURATION_MS) return 0f
    // Fast attack, slow release — 1 - smoothstep gives a natural decay.
    val t = elapsed / BUS_PULSE_DURATION_MS.toFloat()
    return 1f - smoothstep(t)
}

// =============================================================================
// Gratitude motes — Tier-1 signal for "task complete" / good interaction
// =============================================================================
//
// One of the load-bearing CIRIS-acronym signals (§2.5.1 "Signalling
// Gratitude"). Emitted by the nucleus toward the membrane on a task
// completion event, bounded by a 3 s cooldown so it stays special and
// never interferes with ambient mote drift. Drawn warm-amber regardless
// of scope colour since it's about the *system*, not a node.

/** Duration of a gratitude mote's life, in milliseconds. */
const val GRATITUDE_MOTE_DURATION_MS: Long = 2500L

/**
 * Minimum gap between consecutive gratitude emissions. The user must be
 * able to tell "oh, something good just happened" — firing them on
 * every tick would make the signal noise.
 */
const val GRATITUDE_COOLDOWN_MS: Long = 3000L

/**
 * Tier-3 deferral-ripple expansion duration. A single concentric wave
 * expands from nucleus → membrane over this span, quadratic ease-out,
 * alpha fading at the membrane. FSD §2.5.3 specifies 1.5 s.
 */
const val RIPPLE_DURATION_MS: Long = 1500L

/**
 * Deferral-ripple pre-ripple rotation slowdown window. FSD §2.5.3
 * step 1: baseline rotation slows to ~20% for 800 ms so the cell
 * reads as "briefly still, consulting authority" before the ripple
 * itself emits.
 */
const val RIPPLE_PAUSE_MS: Long = 800L

/**
 * One in-flight gratitude mote. Travels outward from the nucleus at
 * [angleDeg], expanding slightly at mid-life, fading at the end.
 * Pure data — rendering math is in [gratitudeMoteFrame].
 */
data class GratitudePulse(
    val startMs: Long,
    /** Direction the mote travels, in degrees (Compose convention). */
    val angleDeg: Float,
    val durationMs: Long = GRATITUDE_MOTE_DURATION_MS,
)

/**
 * Per-frame state of a gratitude mote at time [nowMs]. Returns null
 * when the mote has expired, so the rendering loop can skip it cheaply.
 *
 * Kinematic model:
 *   - radialFrac smoothsteps 0→0.85 across the life (never quite
 *     reaches the membrane — the mote is "of" the cell, not "leaving"
 *     it). 0.85 gives a visible halt short of the membrane openings.
 *   - sizeScale bumps to 1.3× at mid-life then returns to 1.0 at end —
 *     creates a gentle "breathe" feel.
 *   - alpha fades in fast (0→1 over first 15%) and out slowly (1→0
 *     across the remaining 85%), so the mote registers sharply and
 *     dissolves gracefully.
 */
data class GratitudeMoteFrame(
    /** Life progress in [0, 1]. */
    val t: Float,
    /** Fraction of the nucleus-to-membrane distance traversed, in [0, 0.85]. */
    val radialFrac: Float,
    /** Draw alpha in [0, 1]. */
    val alpha: Float,
    /** Multiplier on the mote's base radius, roughly in [1.0, 1.3]. */
    val sizeScale: Float,
)

/** Kinematic sample of [pulse] at [nowMs], or null if expired. */
fun gratitudeMoteFrame(pulse: GratitudePulse, nowMs: Long): GratitudeMoteFrame? {
    val elapsed = (nowMs - pulse.startMs).toFloat()
    if (elapsed < 0f || elapsed >= pulse.durationMs) return null

    val t = (elapsed / pulse.durationMs.toFloat()).coerceIn(0f, 1f)
    val radialFrac = smoothstep(t) * 0.85f

    val attackCut = 0.15f
    val alpha = if (t < attackCut) {
        (t / attackCut)  // fast attack
    } else {
        1f - (t - attackCut) / (1f - attackCut)  // slow release
    }.coerceIn(0f, 1f)

    // Triangular bump peaking at t=0.5, returning to 1.0 at endpoints.
    val midBump = 1f - kotlin.math.abs(t - 0.5f) * 2f
    val sizeScale = 1f + 0.30f * midBump.coerceAtLeast(0f)

    return GratitudeMoteFrame(t = t, radialFrac = radialFrac, alpha = alpha, sizeScale = sizeScale)
}

/**
 * Enforce the minimum 3 s gap between emissions. Returns true if a new
 * gratitude mote is allowed to spawn now.
 */
fun canEmitGratitude(lastEmissionMs: Long, nowMs: Long): Boolean =
    lastEmissionMs <= 0L || (nowMs - lastEmissionMs) >= GRATITUDE_COOLDOWN_MS


// =============================================================================
// Signal channels — adapter-port → label leader lines (non-biological)
// =============================================================================
//
// Earlier drafts called these "pseudopods" or "tendrils"; renamed because
// biological metaphors leak anthropomorphism into a viz that's trying to
// stay out of that frame. These are wires / circuit traces / infographic
// leader lines, nothing that reaches or grows.

/** Duration of one full signal-packet traversal along a channel, in ms. */
const val CHANNEL_PACKET_PERIOD_MS: Long = 2_000L

/** How far past the label the channel continues to fade out, in px. */
const val CHANNEL_FADE_PAST_LABEL_PX: Float = 40f

/** Fraction of the membrane radius to reach past the edge for labels. */
const val CHANNEL_LABEL_OFFSET_FRACTION: Float = 0.28f

/**
 * Kinematic state of one signal channel's travelling packet. The packet
 * travels linearly from [startMs]; its position along the channel is
 * `((nowMs - startMs) % period) / period`. Alpha peaks at mid-traversal
 * and fades at both ends so the packet feels like a pulse, not a
 * constantly-lit tracer.
 *
 * Null means the packet is in its between-cycles quiet period (we render
 * the line without a packet dot).
 */
data class ChannelPacket(
    /** Position along the line in [0, 1] — 0 = port end, 1 = label end. */
    val t: Float,
    /** Packet alpha in [0, 1]. */
    val alpha: Float,
)

/**
 * Sample the travelling-packet state at [nowMs] given a channel's
 * [startMs] anchor. Returns null when the cycle is in its quiet phase
 * so the caller can skip the packet draw.
 *
 * Packets travel for 60 % of the period and then rest for 40 % — the
 * quiet gap is what makes consecutive packets read as discrete events
 * rather than a continuous streak.
 */
fun channelPacketAt(startMs: Long, nowMs: Long): ChannelPacket? {
    if (nowMs < startMs) return null
    val phase = ((nowMs - startMs) % CHANNEL_PACKET_PERIOD_MS).toFloat() /
        CHANNEL_PACKET_PERIOD_MS.toFloat()
    val activeFraction = 0.60f
    if (phase >= activeFraction) return null
    val t = (phase / activeFraction).coerceIn(0f, 1f)
    // Bell curve — rises fast, peaks mid-travel, drops off.
    val alpha = (1f - kotlin.math.abs(t - 0.5f) * 2f).coerceAtLeast(0f)
    return ChannelPacket(t = t, alpha = alpha)
}

/** Duration of the channel-open animation when an adapter comes online, in ms. */
const val CHANNEL_OPEN_DURATION_MS: Long = 650L

/**
 * 0..1 progress of a channel's open animation, where 0 = just activated
 * and 1 = fully open (line reaches the label anchor). Returns 1 for any
 * channel that activated more than [CHANNEL_OPEN_DURATION_MS] ago, so
 * stable channels render at full length with no extra work.
 *
 * Input is `activatedAtMs` — the wall-clock time the adapter first
 * appeared as active. Callers pass 0 / -1 for "never activated" /
 * "always-on from initial snapshot", in which case the animation is
 * skipped entirely (full-length line).
 */
fun channelOpenProgress(activatedAtMs: Long, nowMs: Long): Float {
    if (activatedAtMs <= 0L) return 1f  // stable / pre-existing — no animation
    val elapsed = (nowMs - activatedAtMs).toFloat()
    if (elapsed <= 0f) return 0f
    if (elapsed >= CHANNEL_OPEN_DURATION_MS) return 1f
    return smoothstep(elapsed / CHANNEL_OPEN_DURATION_MS.toFloat())
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
 * Rotate each non-wrapping range by `rotationDeg` around the 0/360
 * circle, splitting into two pieces if the shift causes it to straddle
 * the boundary. Used so membrane openings rotate *with* the bus ring
 * instead of staying fixed in screen space (which reads as the ring
 * passing through stationary holes rather than as holes in the ring).
 *
 * Inputs are expected to be non-wrapping (start <= endInclusive);
 * `openingRanges` already guarantees this.
 */
internal fun rotateRanges(
    ranges: List<ClosedFloatingPointRange<Float>>,
    rotationDeg: Float,
): List<ClosedFloatingPointRange<Float>> {
    val rot = ((rotationDeg % 360f) + 360f) % 360f
    if (rot == 0f || ranges.isEmpty()) return ranges
    return ranges.flatMap { r ->
        val s = (r.start + rot) % 360f
        val e = (r.endInclusive + rot) % 360f
        if (e >= s) listOf(s..e)
        else listOf(s..360f, 0f..e)  // shift caused a 0/360 straddle
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
