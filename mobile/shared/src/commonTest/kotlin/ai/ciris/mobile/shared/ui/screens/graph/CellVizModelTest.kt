package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Unit tests for the pure helpers in CellVizModel.kt.
 *
 * Everything here is a pure function of its inputs — no Compose, no
 * dispatchers, no mocks. Tests use a seeded [Random] where randomness
 * matters so that assertions are deterministic.
 */
class CellVizModelTest {

    private val tolerance = 1e-4f

    // =========================================================================
    // smoothstep
    // =========================================================================

    @Test
    fun smoothstep_atZero_isZero() {
        assertEquals(0f, smoothstep(0f), tolerance)
    }

    @Test
    fun smoothstep_atOne_isOne() {
        assertEquals(1f, smoothstep(1f), tolerance)
    }

    @Test
    fun smoothstep_atHalf_isHalf() {
        assertEquals(0.5f, smoothstep(0.5f), tolerance)
    }

    @Test
    fun smoothstep_clampsBelowZero() {
        assertEquals(0f, smoothstep(-100f), tolerance)
    }

    @Test
    fun smoothstep_clampsAboveOne() {
        assertEquals(1f, smoothstep(100f), tolerance)
    }

    @Test
    fun smoothstep_isMonotonicOnUnitInterval() {
        // Sanity: smoothstep must not decrease as t increases across [0,1].
        var prev = smoothstep(0f)
        var i = 1
        while (i <= 10) {
            val cur = smoothstep(i / 10f)
            assertTrue(cur >= prev, "smoothstep not monotonic at i=$i")
            prev = cur
            i++
        }
    }

    // =========================================================================
    // halfSineEnvelope
    // =========================================================================

    @Test
    fun halfSineEnvelope_atZero_isZero() {
        assertEquals(0f, halfSineEnvelope(0f), tolerance)
    }

    @Test
    fun halfSineEnvelope_atOne_isZero() {
        assertEquals(0f, halfSineEnvelope(1f), tolerance)
    }

    @Test
    fun halfSineEnvelope_atHalf_peaksAtOne() {
        assertEquals(1f, halfSineEnvelope(0.5f), tolerance)
    }

    @Test
    fun halfSineEnvelope_clampsNegativePhase() {
        assertEquals(0f, halfSineEnvelope(-1f), tolerance)
    }

    @Test
    fun halfSineEnvelope_clampsPhaseAboveOne() {
        assertEquals(0f, halfSineEnvelope(2f), tolerance)
    }

    @Test
    fun halfSineEnvelope_nonNegativeAcrossUnitInterval() {
        var i = 0
        while (i <= 20) {
            val v = halfSineEnvelope(i / 20f)
            assertTrue(v >= 0f, "halfSineEnvelope must be non-negative; v=$v at i=$i")
            i++
        }
    }

    // =========================================================================
    // adapterBus
    // =========================================================================

    @Test
    fun adapterBus_api_routesToComm() {
        assertEquals(CellBus.COMM, adapterBus("api"))
    }

    @Test
    fun adapterBus_discord_routesToComm() {
        assertEquals(CellBus.COMM, adapterBus("discord"))
    }

    @Test
    fun adapterBus_weather_routesToTool() {
        assertEquals(CellBus.TOOL, adapterBus("weather"))
    }

    @Test
    fun adapterBus_cirisverify_routesToWise() {
        assertEquals(CellBus.WISE, adapterBus("cirisverify"))
    }

    @Test
    fun adapterBus_unknown_fallsBackToTool() {
        assertEquals(CellBus.TOOL, adapterBus("some_new_adapter_not_in_list"))
    }

    @Test
    fun adapterBus_isCaseInsensitive() {
        assertEquals(CellBus.COMM, adapterBus("API"))
        assertEquals(CellBus.COMM, adapterBus("Discord"))
        assertEquals(CellBus.WISE, adapterBus("CIRISVerify"))
    }

    // =========================================================================
    // portShapeFor
    // =========================================================================

    @Test
    fun portShapeFor_memory_isHex() {
        assertEquals(PortShape.HEX, portShapeFor(CellBus.MEMORY))
    }

    @Test
    fun portShapeFor_wise_isHex() {
        assertEquals(PortShape.HEX, portShapeFor(CellBus.WISE))
    }

    @Test
    fun portShapeFor_comm_isDiamond() {
        assertEquals(PortShape.DIAMOND, portShapeFor(CellBus.COMM))
    }

    @Test
    fun portShapeFor_llm_isDiamond() {
        assertEquals(PortShape.DIAMOND, portShapeFor(CellBus.LLM))
    }

    @Test
    fun portShapeFor_tool_isDiamond() {
        assertEquals(PortShape.DIAMOND, portShapeFor(CellBus.TOOL))
    }

    @Test
    fun portShapeFor_runtime_isDiamond() {
        assertEquals(PortShape.DIAMOND, portShapeFor(CellBus.RUNTIME))
    }

    // =========================================================================
    // GOLDEN_ANGLE_DEG
    // =========================================================================

    @Test
    fun goldenAngleDeg_isApproximately137point508() {
        assertEquals(137.508f, GOLDEN_ANGLE_DEG, 0.01f)
    }

    // =========================================================================
    // MembraneOpening lifecycle helpers
    // =========================================================================

    private fun newOpening(
        bornAtMs: Long = 0L,
        birthCenterDeg: Float = 180f,
        targetWidthDeg: Float = 10f,
        driftDegPerSec: Float = 0f,
        growMs: Long = 1000L,
        stableMs: Long = 2000L,
        shrinkMs: Long = 1000L,
    ): MembraneOpening = MembraneOpening(
        id = 42L,
        birthCenterDeg = birthCenterDeg,
        targetWidthDeg = targetWidthDeg,
        driftDegPerSec = driftDegPerSec,
        bornAtMs = bornAtMs,
        growMs = growMs,
        stableMs = stableMs,
        shrinkMs = shrinkMs,
    )

    @Test
    fun currentWidthDeg_beforeBirth_isZero() {
        val op = newOpening(bornAtMs = 1000L)
        assertEquals(0f, op.currentWidthDeg(nowMs = 500L), tolerance)
    }

    @Test
    fun currentWidthDeg_atBirth_isZero() {
        // At exact birth, age=0, smoothstep(0)=0 → width=0
        val op = newOpening(bornAtMs = 1000L)
        assertEquals(0f, op.currentWidthDeg(nowMs = 1000L), tolerance)
    }

    @Test
    fun currentWidthDeg_midGrow_isSmoothstepOfProgress() {
        // age=500ms, growMs=1000 → t=0.5 → smoothstep(0.5)=0.5 → width=5
        val op = newOpening(targetWidthDeg = 10f, growMs = 1000L)
        assertEquals(5f, op.currentWidthDeg(nowMs = 500L), tolerance)
    }

    @Test
    fun currentWidthDeg_atStablePhase_isTargetWidth() {
        // age in [growMs, growMs+stableMs) → full targetWidth
        val op = newOpening(targetWidthDeg = 10f, growMs = 1000L, stableMs = 2000L)
        assertEquals(10f, op.currentWidthDeg(nowMs = 1500L), tolerance)
        assertEquals(10f, op.currentWidthDeg(nowMs = 2999L), tolerance)
    }

    @Test
    fun currentWidthDeg_midShrink_fadesToZero() {
        // grow=1000, stable=2000, shrink=1000 → lifetime=4000
        // at age=3500 (mid shrink) → (4000-3500)/1000 = 0.5 → smoothstep(0.5)=0.5 → width=5
        val op = newOpening(
            targetWidthDeg = 10f,
            growMs = 1000L,
            stableMs = 2000L,
            shrinkMs = 1000L,
        )
        assertEquals(5f, op.currentWidthDeg(nowMs = 3500L), tolerance)
    }

    @Test
    fun currentWidthDeg_afterDeath_isZero() {
        val op = newOpening(
            targetWidthDeg = 10f,
            growMs = 1000L,
            stableMs = 2000L,
            shrinkMs = 1000L,
        )
        // lifetime = 4000
        assertEquals(0f, op.currentWidthDeg(nowMs = 4000L), tolerance)
        assertEquals(0f, op.currentWidthDeg(nowMs = 99999L), tolerance)
    }

    @Test
    fun currentCenterDeg_noDrift_staysAtBirthCenter() {
        val op = newOpening(birthCenterDeg = 180f, driftDegPerSec = 0f)
        assertEquals(180f, op.currentCenterDeg(nowMs = 5000L), tolerance)
    }

    @Test
    fun currentCenterDeg_withPositiveDrift_advances() {
        // drift=10deg/s, age=2s → advances 20 degrees from 100 → 120
        val op = newOpening(bornAtMs = 0L, birthCenterDeg = 100f, driftDegPerSec = 10f)
        assertEquals(120f, op.currentCenterDeg(nowMs = 2000L), tolerance)
    }

    @Test
    fun currentCenterDeg_wrapsPositivePast360() {
        // birth=350, drift=20deg/s, age=1s → raw=370 → wraps to 10
        val op = newOpening(bornAtMs = 0L, birthCenterDeg = 350f, driftDegPerSec = 20f)
        assertEquals(10f, op.currentCenterDeg(nowMs = 1000L), tolerance)
    }

    @Test
    fun currentCenterDeg_wrapsNegativePast0() {
        // birth=10, drift=-20deg/s, age=1s → raw=-10 → wraps to 350
        val op = newOpening(bornAtMs = 0L, birthCenterDeg = 10f, driftDegPerSec = -20f)
        assertEquals(350f, op.currentCenterDeg(nowMs = 1000L), tolerance)
    }

    @Test
    fun isDead_beforeLifetime_isFalse() {
        val op = newOpening(bornAtMs = 0L, growMs = 100L, stableMs = 100L, shrinkMs = 100L)
        // lifetime = 300ms
        assertFalse(op.isDead(nowMs = 299L))
    }

    @Test
    fun isDead_atLifetime_isTrue() {
        val op = newOpening(bornAtMs = 0L, growMs = 100L, stableMs = 100L, shrinkMs = 100L)
        assertTrue(op.isDead(nowMs = 300L))
    }

    @Test
    fun isDead_afterLifetime_isTrue() {
        val op = newOpening(bornAtMs = 0L, growMs = 100L, stableMs = 100L, shrinkMs = 100L)
        assertTrue(op.isDead(nowMs = 10_000L))
    }

    @Test
    fun lifetimeMs_isSumOfPhases() {
        val op = newOpening(growMs = 111L, stableMs = 222L, shrinkMs = 333L)
        assertEquals(666L, op.lifetimeMs)
    }

    // =========================================================================
    // openingRanges
    // =========================================================================

    @Test
    fun openingRanges_zeroWidth_returnsEmpty() {
        // An opening whose currentWidthDeg=0 (before birth) yields no ranges.
        val op = newOpening(bornAtMs = 1000L, targetWidthDeg = 10f)
        assertTrue(openingRanges(op, nowMs = 0L).isEmpty())
    }

    @Test
    fun openingRanges_nonWrapping_returnsSingleRange() {
        // center=180, width=10 (stable phase) → [175, 185]
        val op = newOpening(
            birthCenterDeg = 180f,
            targetWidthDeg = 10f,
            growMs = 100L,
            stableMs = 2000L,
            shrinkMs = 100L,
        )
        val ranges = openingRanges(op, nowMs = 500L) // stable phase
        assertEquals(1, ranges.size)
        assertEquals(175f, ranges[0].start, tolerance)
        assertEquals(185f, ranges[0].endInclusive, tolerance)
    }

    @Test
    fun openingRanges_wrappingPastZero_returnsTwoRanges() {
        // center=2, width=10 → half=5 → rawStart=-3, rawEnd=7
        // Expected: [0..7, 357..360]
        val op = newOpening(
            birthCenterDeg = 2f,
            targetWidthDeg = 10f,
            growMs = 100L,
            stableMs = 2000L,
            shrinkMs = 100L,
        )
        val ranges = openingRanges(op, nowMs = 500L)
        assertEquals(2, ranges.size)
        assertEquals(0f, ranges[0].start, tolerance)
        assertEquals(7f, ranges[0].endInclusive, tolerance)
        assertEquals(357f, ranges[1].start, tolerance)
        assertEquals(360f, ranges[1].endInclusive, tolerance)
    }

    @Test
    fun openingRanges_wrappingPast360_returnsTwoRanges() {
        // center=358, width=10 → half=5 → rawStart=353, rawEnd=363
        // Expected: [353..360, 0..3]
        val op = newOpening(
            birthCenterDeg = 358f,
            targetWidthDeg = 10f,
            growMs = 100L,
            stableMs = 2000L,
            shrinkMs = 100L,
        )
        val ranges = openingRanges(op, nowMs = 500L)
        assertEquals(2, ranges.size)
        assertEquals(353f, ranges[0].start, tolerance)
        assertEquals(360f, ranges[0].endInclusive, tolerance)
        assertEquals(0f, ranges[1].start, tolerance)
        assertEquals(3f, ranges[1].endInclusive, tolerance)
    }

    // =========================================================================
    // subtractRangesFromArc
    // =========================================================================

    @Test
    fun subtractRangesFromArc_noOpenings_returnsWholeArc() {
        val result = subtractRangesFromArc(
            arcStart = 10f,
            arcEnd = 100f,
            openings = emptyList(),
        )
        assertEquals(1, result.size)
        assertEquals(10f, result[0].first, tolerance)
        assertEquals(90f, result[0].second, tolerance) // sweep
    }

    @Test
    fun subtractRangesFromArc_openingBeyondArc_doesNothing() {
        // Arc [10..50], opening [200..250] — no overlap.
        val result = subtractRangesFromArc(
            arcStart = 10f,
            arcEnd = 50f,
            openings = listOf(200f..250f),
        )
        assertEquals(1, result.size)
        assertEquals(10f, result[0].first, tolerance)
        assertEquals(40f, result[0].second, tolerance)
    }

    @Test
    fun subtractRangesFromArc_singleOverlappingOpening_splitsArc() {
        // Arc [0..100], opening [40..60] → expect [0..40] + [60..100]
        val result = subtractRangesFromArc(
            arcStart = 0f,
            arcEnd = 100f,
            openings = listOf(40f..60f),
        )
        assertEquals(2, result.size)
        assertEquals(0f, result[0].first, tolerance)
        assertEquals(40f, result[0].second, tolerance)
        assertEquals(60f, result[1].first, tolerance)
        assertEquals(40f, result[1].second, tolerance)
    }

    @Test
    fun subtractRangesFromArc_openingCoversWholeArc_returnsEmpty() {
        val result = subtractRangesFromArc(
            arcStart = 20f,
            arcEnd = 80f,
            openings = listOf(0f..360f),
        )
        assertTrue(result.isEmpty())
    }

    @Test
    fun subtractRangesFromArc_wrappingArc_decomposedCorrectly() {
        // Arc wraps past 0: start=350, end=10. Opening at [355..5] would
        // need decomposition. Using a simpler opening at [355..360]:
        // Decomposed arcs: [350..360] and [0..10]
        // Opening clipped per piece: [355..360] on piece 1, none on piece 2
        // Expected sub-arcs: [350..355] and [0..10]
        val result = subtractRangesFromArc(
            arcStart = 350f,
            arcEnd = 10f,
            openings = listOf(355f..360f),
        )
        assertEquals(2, result.size)
        assertEquals(350f, result[0].first, tolerance)
        assertEquals(5f, result[0].second, tolerance)
        assertEquals(0f, result[1].first, tolerance)
        assertEquals(10f, result[1].second, tolerance)
    }

    // =========================================================================
    // spawnOpening — deterministic with seeded Random
    // =========================================================================

    @Test
    fun spawnOpening_widthIsWithinConfigRange() {
        val cfg = CellVizConfig.DEFAULT.copy(
            openingMinWidthDeg = 4f,
            openingMaxWidthDeg = 10f,
        ).sanitized()
        val rng = Random(seed = 1337L)
        var i = 0
        while (i < 50) {
            val op = spawnOpening(nowMs = 1000L, rng = rng, cfg = cfg)
            assertTrue(op.targetWidthDeg >= cfg.openingMinWidthDeg,
                "width ${op.targetWidthDeg} < min ${cfg.openingMinWidthDeg}")
            assertTrue(op.targetWidthDeg <= cfg.openingMaxWidthDeg,
                "width ${op.targetWidthDeg} > max ${cfg.openingMaxWidthDeg}")
            i++
        }
    }

    @Test
    fun spawnOpening_stableDurationIsWithinConfigRange() {
        val cfg = CellVizConfig.DEFAULT.copy(
            openingStableMinSec = 2f,
            openingStableMaxSec = 4f,
        ).sanitized()
        val rng = Random(seed = 99L)
        val expectedMinMs = (cfg.openingStableMinSec * 1000).toLong()
        val expectedMaxMs = (cfg.openingStableMaxSec * 1000).toLong()
        var i = 0
        while (i < 50) {
            val op = spawnOpening(nowMs = 0L, rng = rng, cfg = cfg)
            assertTrue(op.stableMs >= expectedMinMs,
                "stableMs ${op.stableMs} < $expectedMinMs")
            assertTrue(op.stableMs <= expectedMaxMs,
                "stableMs ${op.stableMs} > $expectedMaxMs")
            i++
        }
    }

    @Test
    fun spawnOpening_driftIsWithinConfigRange() {
        val cfg = CellVizConfig.DEFAULT.copy(
            openingDriftMaxDegPerSec = 1f,
        ).sanitized()
        val rng = Random(seed = 7L)
        var i = 0
        while (i < 50) {
            val op = spawnOpening(nowMs = 0L, rng = rng, cfg = cfg)
            assertTrue(op.driftDegPerSec >= -cfg.openingDriftMaxDegPerSec,
                "drift ${op.driftDegPerSec} < -${cfg.openingDriftMaxDegPerSec}")
            assertTrue(op.driftDegPerSec <= cfg.openingDriftMaxDegPerSec,
                "drift ${op.driftDegPerSec} > ${cfg.openingDriftMaxDegPerSec}")
            i++
        }
    }

    @Test
    fun spawnOpening_centerDegIsWithin0to360() {
        val cfg = CellVizConfig.DEFAULT
        val rng = Random(seed = 4242L)
        var i = 0
        while (i < 50) {
            val op = spawnOpening(nowMs = 0L, rng = rng, cfg = cfg)
            assertTrue(op.birthCenterDeg >= 0f,
                "birthCenterDeg ${op.birthCenterDeg} < 0")
            assertTrue(op.birthCenterDeg < 360f,
                "birthCenterDeg ${op.birthCenterDeg} >= 360")
            i++
        }
    }

    @Test
    fun spawnOpening_bornAtMs_matchesNowMs() {
        val op = spawnOpening(nowMs = 12345L, rng = Random(1L), cfg = CellVizConfig.DEFAULT)
        assertEquals(12345L, op.bornAtMs)
    }

    @Test
    fun spawnOpening_growAndShrinkMs_matchConfig() {
        val cfg = CellVizConfig.DEFAULT.copy(
            openingGrowSec = 0.8f,
            openingShrinkSec = 1.2f,
        ).sanitized()
        val op = spawnOpening(nowMs = 0L, rng = Random(1L), cfg = cfg)
        assertEquals(800L, op.growMs)
        assertEquals(1200L, op.shrinkMs)
    }

    // =========================================================================
    // spreadAngle
    // =========================================================================

    @Test
    fun spreadAngle_total1_returnsMidpoint() {
        // segment [0..60], total=1, margin=anything → midpoint=30
        assertEquals(30f, spreadAngle(0f, 60f, index = 0, total = 1, marginDeg = 5f), tolerance)
    }

    @Test
    fun spreadAngle_total1_atAnyIndex_returnsMidpoint() {
        // total<=1 branch ignores index.
        assertEquals(30f, spreadAngle(0f, 60f, index = 0, total = 0, marginDeg = 5f), tolerance)
    }

    @Test
    fun spreadAngle_total2_firstAtStartPlusMargin() {
        // segment [0..60], total=2, margin=5
        // index=0 → 0 + 5 + 0 = 5
        assertEquals(5f, spreadAngle(0f, 60f, index = 0, total = 2, marginDeg = 5f), tolerance)
    }

    @Test
    fun spreadAngle_total2_lastAtEndMinusMargin() {
        // segment [0..60], total=2, margin=5
        // index=1 → 0 + 5 + 1.0 * (60 - 10) = 55 = end - margin
        assertEquals(55f, spreadAngle(0f, 60f, index = 1, total = 2, marginDeg = 5f), tolerance)
    }

    @Test
    fun spreadAngle_total3_spreadsEvenly() {
        // segment [0..60], total=3, margin=5, usable=50
        // i=0 → 5; i=1 → 5 + 0.5 * 50 = 30; i=2 → 5 + 1.0 * 50 = 55
        assertEquals(5f, spreadAngle(0f, 60f, index = 0, total = 3, marginDeg = 5f), tolerance)
        assertEquals(30f, spreadAngle(0f, 60f, index = 1, total = 3, marginDeg = 5f), tolerance)
        assertEquals(55f, spreadAngle(0f, 60f, index = 2, total = 3, marginDeg = 5f), tolerance)
    }

    @Test
    fun spreadAngle_resultsStayWithinSegment_forFullSpread() {
        // With reasonable margin, every port must fall inside [start+margin, end-margin].
        val start = 100f
        val end = 200f
        val margin = 8f
        val total = 5
        var i = 0
        while (i < total) {
            val a = spreadAngle(start, end, i, total, margin)
            assertTrue(a >= start + margin - 1e-3f,
                "port $i at $a is before start+margin (${start + margin})")
            assertTrue(a <= end - margin + 1e-3f,
                "port $i at $a is past end-margin (${end - margin})")
            i++
        }
    }

    // =========================================================================
    // CellBus sanity — the ordering is load-bearing
    // =========================================================================

    @Test
    fun cellBus_containsExpectedValues() {
        val values = CellBus.values().toList()
        assertContains(values, CellBus.COMM)
        assertContains(values, CellBus.MEMORY)
        assertContains(values, CellBus.LLM)
        assertContains(values, CellBus.TOOL)
        assertContains(values, CellBus.RUNTIME)
        assertContains(values, CellBus.WISE)
        assertEquals(6, values.size)
    }

    // =========================================================================
    // busFromEventType — Tier-1 event routing
    // =========================================================================

    @Test
    fun `pipeline stages route to their owning bus`() {
        assertEquals(CellBus.LLM, busFromEventType("thought_start"))
        assertEquals(CellBus.LLM, busFromEventType("dma_results"))
        assertEquals(CellBus.LLM, busFromEventType("idma_result"))
        assertEquals(CellBus.LLM, busFromEventType("aspdma_result"))
        assertEquals(CellBus.TOOL, busFromEventType("tsaspdma_result"))
        assertEquals(CellBus.WISE, busFromEventType("conscience_result"))
        assertEquals(CellBus.MEMORY, busFromEventType("snapshot_and_context"))
    }

    @Test
    fun `action_result routes on verb, not event_type alone`() {
        assertEquals(
            CellBus.MEMORY,
            busFromEventType("action_result", action = "memorize"),
        )
        assertEquals(
            CellBus.MEMORY,
            busFromEventType("action_result", action = "RECALL"),
        )
        assertEquals(
            CellBus.MEMORY,
            busFromEventType("action_result", action = "forget"),
        )
        assertEquals(
            CellBus.COMM,
            busFromEventType("action_result", action = "speak"),
        )
        assertEquals(
            CellBus.COMM,
            busFromEventType("action_result", action = "observe"),
        )
        assertEquals(
            CellBus.TOOL,
            busFromEventType("action_result", action = "tool"),
        )
        assertEquals(
            CellBus.WISE,
            busFromEventType("action_result", action = "defer"),
        )
        assertEquals(
            CellBus.LLM,
            busFromEventType("action_result", action = "ponder"),
        )
        assertEquals(
            CellBus.RUNTIME,
            busFromEventType("action_result", action = "reject"),
        )
    }

    @Test
    fun `task_complete returns null so it fires a gratitude mote instead`() {
        assertEquals(
            null,
            busFromEventType("action_result", action = "task_complete"),
        )
    }

    @Test
    fun `unknown event types return null`() {
        assertEquals(null, busFromEventType("mystery_event"))
        assertEquals(null, busFromEventType("action_result", action = "warp_speed"))
        // Missing action on action_result shouldn't misroute to a bus.
        assertEquals(null, busFromEventType("action_result", action = null))
    }

    @Test
    fun `action casing does not affect routing`() {
        assertEquals(
            CellBus.COMM,
            busFromEventType("action_result", action = "SPEAK"),
        )
        assertEquals(
            CellBus.COMM,
            busFromEventType("action_result", action = "Speak"),
        )
    }

    @Test
    fun `action substring matching handles decorated names`() {
        // ActionType.fromEmoji(...) may produce names like "SPEAK" or the
        // event may carry "action.speak" / "speak_action" — the helper
        // uses substring match so any of those land on the same bus.
        assertEquals(
            CellBus.COMM,
            busFromEventType("action_result", action = "action.speak"),
        )
        assertEquals(
            CellBus.TOOL,
            busFromEventType("action_result", action = "tool_use"),
        )
    }

    // =========================================================================
    // busPulseIntensity — decay curve for shimmer
    // =========================================================================

    @Test
    fun `busPulseIntensity is 1_0 at spawn and 0 past duration`() {
        val pulse = BusPulse(CellBus.LLM, startMs = 1_000L)
        assertEquals(1f, busPulseIntensity(pulse, nowMs = 1_000L), 1e-4f)
        // At exactly the duration boundary, intensity is 0.
        assertEquals(
            0f,
            busPulseIntensity(pulse, nowMs = 1_000L + BUS_PULSE_DURATION_MS),
            1e-4f,
        )
        assertEquals(
            0f,
            busPulseIntensity(pulse, nowMs = 1_000L + BUS_PULSE_DURATION_MS + 500L),
            1e-4f,
        )
    }

    @Test
    fun `busPulseIntensity decays monotonically inside the pulse window`() {
        val pulse = BusPulse(CellBus.MEMORY, startMs = 0L)
        var last = Float.POSITIVE_INFINITY
        for (t in 0L until BUS_PULSE_DURATION_MS step 30L) {
            val intensity = busPulseIntensity(pulse, nowMs = t)
            assertTrue(
                intensity <= last + 1e-4f,
                "non-monotonic at t=$t: prev=$last this=$intensity",
            )
            assertTrue(intensity >= 0f && intensity <= 1f, "out of range at t=$t")
            last = intensity
        }
    }

    @Test
    fun `busPulseIntensity handles negative elapsed time gracefully`() {
        // If clocks skew or a pulse is scheduled in the future, don't
        // return a nonsense value or throw.
        val pulse = BusPulse(CellBus.WISE, startMs = 1_000L)
        assertEquals(0f, busPulseIntensity(pulse, nowMs = 500L), 1e-4f)
    }

    @Test
    fun `BUS_PULSE_DURATION_MS is a perceptually tuned constant`() {
        // Locking this down as a contract — 600ms is the design-doc
        // duration; changing it moves the "shimmer feels snappy vs
        // sluggish" dial and should be a deliberate decision, not a
        // drive-by edit.
        assertEquals(600L, BUS_PULSE_DURATION_MS)
    }

    // =========================================================================
    // Gratitude motes — kinematics + cooldown
    // =========================================================================

    @Test
    fun `gratitude mote returns null outside its life window`() {
        val pulse = GratitudePulse(startMs = 1_000L, angleDeg = 42f)
        assertEquals(null, gratitudeMoteFrame(pulse, nowMs = 999L))
        assertEquals(null, gratitudeMoteFrame(pulse, nowMs = 1_000L + pulse.durationMs))
        assertEquals(null, gratitudeMoteFrame(pulse, nowMs = 1_000L + pulse.durationMs + 500L))
    }

    @Test
    fun `gratitude mote alpha peaks at the end of the attack phase`() {
        val pulse = GratitudePulse(startMs = 0L, angleDeg = 0f)
        // Attack is the first 15% of life.
        val attackEndMs = (pulse.durationMs * 0.15f).toLong()
        val peak = gratitudeMoteFrame(pulse, nowMs = attackEndMs)!!
        assertTrue(peak.alpha > 0.95f, "expected alpha near 1 at attack end, got ${peak.alpha}")

        val justBefore = gratitudeMoteFrame(pulse, nowMs = attackEndMs / 2L)!!
        assertTrue(
            justBefore.alpha < peak.alpha,
            "alpha should ramp up during attack, got ${justBefore.alpha} then ${peak.alpha}",
        )
    }

    @Test
    fun `gratitude mote alpha fades back to zero at life end`() {
        val pulse = GratitudePulse(startMs = 0L, angleDeg = 0f)
        val lateFrame = gratitudeMoteFrame(pulse, nowMs = (pulse.durationMs * 0.99f).toLong())!!
        assertTrue(lateFrame.alpha < 0.1f, "expected alpha near 0 near end, got ${lateFrame.alpha}")
    }

    @Test
    fun `gratitude mote travels outward monotonically`() {
        val pulse = GratitudePulse(startMs = 0L, angleDeg = 90f)
        var lastRadial = -1f
        for (t in 0L..pulse.durationMs step 50L) {
            val frame = gratitudeMoteFrame(pulse, nowMs = t) ?: break
            assertTrue(
                frame.radialFrac >= lastRadial - 1e-4f,
                "radialFrac must not move backwards: t=$t last=$lastRadial this=${frame.radialFrac}",
            )
            assertTrue(frame.radialFrac in 0f..0.85f, "radialFrac out of [0, 0.85]: ${frame.radialFrac}")
            lastRadial = frame.radialFrac
        }
    }

    @Test
    fun `gratitude mote stops short of the membrane so it never overlaps bus arcs`() {
        val pulse = GratitudePulse(startMs = 0L, angleDeg = 0f)
        // At the very end of its travel the mote should cap at 0.85, not 1.0.
        val endFrame = gratitudeMoteFrame(pulse, nowMs = (pulse.durationMs * 0.99f).toLong())!!
        assertTrue(endFrame.radialFrac <= 0.85f + 1e-3f, "got ${endFrame.radialFrac}")
    }

    @Test
    fun `gratitude mote size bumps mid-life then returns`() {
        val pulse = GratitudePulse(startMs = 0L, angleDeg = 0f)
        val start = gratitudeMoteFrame(pulse, nowMs = 0L)!!
        val mid = gratitudeMoteFrame(pulse, nowMs = pulse.durationMs / 2L)!!
        val late = gratitudeMoteFrame(pulse, nowMs = (pulse.durationMs * 0.95f).toLong())!!
        assertTrue(mid.sizeScale > start.sizeScale, "size should grow past start")
        assertTrue(mid.sizeScale > late.sizeScale, "size should fall after mid-life")
        assertTrue(mid.sizeScale in 1.2f..1.31f, "bump in expected range: ${mid.sizeScale}")
    }

    // -------------------------------------------------------------------------
    // Cooldown gate — canEmitGratitude
    // -------------------------------------------------------------------------

    @Test
    fun `canEmitGratitude allows first emission with no history`() {
        assertTrue(canEmitGratitude(lastEmissionMs = 0L, nowMs = 100L))
    }

    @Test
    fun `canEmitGratitude blocks emissions within the cooldown window`() {
        val last = 10_000L
        assertTrue(!canEmitGratitude(last, nowMs = last + 1L))
        assertTrue(!canEmitGratitude(last, nowMs = last + 1_500L))
        assertTrue(!canEmitGratitude(last, nowMs = last + GRATITUDE_COOLDOWN_MS - 1L))
    }

    @Test
    fun `canEmitGratitude allows emission exactly at the cooldown boundary`() {
        val last = 10_000L
        assertTrue(canEmitGratitude(last, nowMs = last + GRATITUDE_COOLDOWN_MS))
    }

    @Test
    fun `gratitude constants lock down their design-doc values`() {
        // 2500 ms life + 3000 ms cooldown were chosen so a task completion
        // reliably signals as a discrete event (short enough to fade before
        // the next one lands, long enough to register). Drifting these
        // drifts the feel; make the change deliberate.
        assertEquals(2_500L, GRATITUDE_MOTE_DURATION_MS)
        assertEquals(3_000L, GRATITUDE_COOLDOWN_MS)
    }
}
