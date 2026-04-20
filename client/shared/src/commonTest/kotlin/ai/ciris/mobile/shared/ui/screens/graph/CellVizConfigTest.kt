package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Unit tests for [CellVizConfig.sanitized] and [CellVizConfig.DEFAULT].
 *
 * Every numeric field has bounds; these tests verify both single-field
 * clamping and the interdependent-pair clamping (min ≤ max etc.).
 */
class CellVizConfigTest {

    // ----- Single-field clamping -------------------------------------------

    @Test
    fun sanitized_rotationDegPerSec_clampsBelowMin() {
        val cfg = CellVizConfig(rotationDegPerSec = -5f).sanitized()
        assertEquals(0f, cfg.rotationDegPerSec)
    }

    @Test
    fun sanitized_rotationDegPerSec_clampsAboveMax() {
        val cfg = CellVizConfig(rotationDegPerSec = 1000f).sanitized()
        assertEquals(45f, cfg.rotationDegPerSec)
    }

    @Test
    fun sanitized_membraneRadiusFraction_clampsBelowMin() {
        val cfg = CellVizConfig(membraneRadiusFraction = 0.01f).sanitized()
        assertEquals(0.15f, cfg.membraneRadiusFraction)
    }

    @Test
    fun sanitized_membraneRadiusFraction_clampsAboveMax() {
        val cfg = CellVizConfig(membraneRadiusFraction = 2f).sanitized()
        assertEquals(0.48f, cfg.membraneRadiusFraction)
    }

    @Test
    fun sanitized_busArcStrokeWidth_clamps() {
        assertEquals(1f, CellVizConfig(busArcStrokeWidth = 0f).sanitized().busArcStrokeWidth)
        assertEquals(12f, CellVizConfig(busArcStrokeWidth = 100f).sanitized().busArcStrokeWidth)
    }

    @Test
    fun sanitized_busArcMidHaloWidth_clamps() {
        assertEquals(2f, CellVizConfig(busArcMidHaloWidth = 0f).sanitized().busArcMidHaloWidth)
        assertEquals(24f, CellVizConfig(busArcMidHaloWidth = 100f).sanitized().busArcMidHaloWidth)
    }

    @Test
    fun sanitized_busArcOuterHaloWidth_clamps() {
        assertEquals(4f, CellVizConfig(busArcOuterHaloWidth = 0f).sanitized().busArcOuterHaloWidth)
        assertEquals(48f, CellVizConfig(busArcOuterHaloWidth = 100f).sanitized().busArcOuterHaloWidth)
    }

    @Test
    fun sanitized_openingGrowSec_clamps() {
        assertEquals(0.1f, CellVizConfig(openingGrowSec = 0f).sanitized().openingGrowSec)
        assertEquals(5f, CellVizConfig(openingGrowSec = 100f).sanitized().openingGrowSec)
    }

    @Test
    fun sanitized_openingShrinkSec_clamps() {
        assertEquals(0.1f, CellVizConfig(openingShrinkSec = 0f).sanitized().openingShrinkSec)
        assertEquals(5f, CellVizConfig(openingShrinkSec = 100f).sanitized().openingShrinkSec)
    }

    @Test
    fun sanitized_openingDriftMaxDegPerSec_clamps() {
        assertEquals(0f, CellVizConfig(openingDriftMaxDegPerSec = -1f).sanitized().openingDriftMaxDegPerSec)
        assertEquals(10f, CellVizConfig(openingDriftMaxDegPerSec = 100f).sanitized().openingDriftMaxDegPerSec)
    }

    @Test
    fun sanitized_portRadiusPx_clamps() {
        assertEquals(6f, CellVizConfig(portRadiusPx = 0f).sanitized().portRadiusPx)
        assertEquals(30f, CellVizConfig(portRadiusPx = 1000f).sanitized().portRadiusPx)
    }

    @Test
    fun sanitized_portSegmentMarginDeg_clamps() {
        assertEquals(0f, CellVizConfig(portSegmentMarginDeg = -5f).sanitized().portSegmentMarginDeg)
        assertEquals(20f, CellVizConfig(portSegmentMarginDeg = 1000f).sanitized().portSegmentMarginDeg)
    }

    @Test
    fun sanitized_portInactiveAlpha_clamps() {
        assertEquals(0.1f, CellVizConfig(portInactiveAlpha = 0f).sanitized().portInactiveAlpha)
        assertEquals(1f, CellVizConfig(portInactiveAlpha = 5f).sanitized().portInactiveAlpha)
    }

    @Test
    fun sanitized_maxMemoryMotes_clamps() {
        assertEquals(0, CellVizConfig(maxMemoryMotes = -5).sanitized().maxMemoryMotes)
        assertEquals(500, CellVizConfig(maxMemoryMotes = 10_000).sanitized().maxMemoryMotes)
    }

    @Test
    fun sanitized_memoryQueryPeriodSec_clamps() {
        assertEquals(3f, CellVizConfig(memoryQueryPeriodSec = 0f).sanitized().memoryQueryPeriodSec)
        assertEquals(300f, CellVizConfig(memoryQueryPeriodSec = 10_000f).sanitized().memoryQueryPeriodSec)
    }

    @Test
    fun sanitized_memoryLoadWindowHours_clamps() {
        assertEquals(1, CellVizConfig(memoryLoadWindowHours = 0).sanitized().memoryLoadWindowHours)
        assertEquals(168, CellVizConfig(memoryLoadWindowHours = 1000).sanitized().memoryLoadWindowHours)
    }

    @Test
    fun sanitized_moteRadiusPx_clamps() {
        assertEquals(0.5f, CellVizConfig(moteRadiusPx = 0f).sanitized().moteRadiusPx)
        assertEquals(12f, CellVizConfig(moteRadiusPx = 1000f).sanitized().moteRadiusPx)
    }

    @Test
    fun sanitized_moteDriftAmpPx_clamps() {
        assertEquals(0f, CellVizConfig(moteDriftAmpPx = -5f).sanitized().moteDriftAmpPx)
        assertEquals(20f, CellVizConfig(moteDriftAmpPx = 1000f).sanitized().moteDriftAmpPx)
    }

    @Test
    fun sanitized_moteDriftPeriodSec_clamps() {
        assertEquals(2f, CellVizConfig(moteDriftPeriodSec = 0f).sanitized().moteDriftPeriodSec)
        assertEquals(60f, CellVizConfig(moteDriftPeriodSec = 10_000f).sanitized().moteDriftPeriodSec)
    }

    @Test
    fun sanitized_moteBirthMs_clamps() {
        assertEquals(0L, CellVizConfig(moteBirthMs = -500L).sanitized().moteBirthMs)
        assertEquals(6000L, CellVizConfig(moteBirthMs = 100_000L).sanitized().moteBirthMs)
    }

    @Test
    fun sanitized_maxGratitudeMotesInFlight_clamps() {
        assertEquals(0, CellVizConfig(maxGratitudeMotesInFlight = -3).sanitized().maxGratitudeMotesInFlight)
        assertEquals(4, CellVizConfig(maxGratitudeMotesInFlight = 100).sanitized().maxGratitudeMotesInFlight)
    }

    @Test
    fun sanitized_gratitudeCooldownSec_clamps() {
        assertEquals(0.5f, CellVizConfig(gratitudeCooldownSec = 0f).sanitized().gratitudeCooldownSec)
        assertEquals(60f, CellVizConfig(gratitudeCooldownSec = 1000f).sanitized().gratitudeCooldownSec)
    }

    @Test
    fun sanitized_maxCaughtBubbles_clamps() {
        assertEquals(0, CellVizConfig(maxCaughtBubbles = -5).sanitized().maxCaughtBubbles)
        assertEquals(32, CellVizConfig(maxCaughtBubbles = 1000).sanitized().maxCaughtBubbles)
    }

    @Test
    fun sanitized_breathePeriodSec_clamps() {
        assertEquals(2f, CellVizConfig(breathePeriodSec = 0f).sanitized().breathePeriodSec)
        assertEquals(30f, CellVizConfig(breathePeriodSec = 1000f).sanitized().breathePeriodSec)
    }

    @Test
    fun sanitized_breatheScaleAmp_clamps() {
        assertEquals(0f, CellVizConfig(breatheScaleAmp = -0.1f).sanitized().breatheScaleAmp)
        assertEquals(0.06f, CellVizConfig(breatheScaleAmp = 1f).sanitized().breatheScaleAmp)
    }

    @Test
    fun sanitized_nucleusRadiusFraction_clamps() {
        assertEquals(0.10f, CellVizConfig(nucleusRadiusFraction = 0f).sanitized().nucleusRadiusFraction)
        assertEquals(0.60f, CellVizConfig(nucleusRadiusFraction = 2f).sanitized().nucleusRadiusFraction)
    }

    // ----- Interdependent pair clamping ------------------------------------

    @Test
    fun sanitized_minOpenings_clampsToZero_whenNegative() {
        val cfg = CellVizConfig(minOpenings = -2, maxOpenings = 4).sanitized()
        assertEquals(0, cfg.minOpenings)
    }

    @Test
    fun sanitized_maxOpenings_clampsToEight_whenTooHigh() {
        val cfg = CellVizConfig(minOpenings = 0, maxOpenings = 1000).sanitized()
        assertEquals(8, cfg.maxOpenings)
    }

    @Test
    fun sanitized_openings_minLessThanOrEqualToMax() {
        // A user-set min greater than max must be reconciled — max rises to meet min.
        val cfg = CellVizConfig(minOpenings = 6, maxOpenings = 2).sanitized()
        assertTrue(cfg.minOpenings <= cfg.maxOpenings,
            "minOpenings=${cfg.minOpenings} must be <= maxOpenings=${cfg.maxOpenings}")
        assertEquals(6, cfg.minOpenings)
        assertEquals(6, cfg.maxOpenings)
    }

    @Test
    fun sanitized_openingStable_minLessThanOrEqualToMax() {
        val cfg = CellVizConfig(
            openingStableMinSec = 8f,
            openingStableMaxSec = 3f,
        ).sanitized()
        assertTrue(cfg.openingStableMinSec <= cfg.openingStableMaxSec)
        assertEquals(8f, cfg.openingStableMinSec)
        assertEquals(8f, cfg.openingStableMaxSec)
    }

    @Test
    fun sanitized_openingStableMinSec_clampsToFloor() {
        val cfg = CellVizConfig(openingStableMinSec = 0f).sanitized()
        assertEquals(0.2f, cfg.openingStableMinSec)
    }

    @Test
    fun sanitized_openingStableMaxSec_clampsToCeiling() {
        val cfg = CellVizConfig(
            openingStableMinSec = 2f,
            openingStableMaxSec = 1000f,
        ).sanitized()
        assertEquals(30f, cfg.openingStableMaxSec)
    }

    @Test
    fun sanitized_openingWidth_minLessThanOrEqualToMax() {
        val cfg = CellVizConfig(
            openingMinWidthDeg = 20f,
            openingMaxWidthDeg = 5f,
        ).sanitized()
        assertTrue(cfg.openingMinWidthDeg <= cfg.openingMaxWidthDeg)
        assertEquals(20f, cfg.openingMinWidthDeg)
        assertEquals(20f, cfg.openingMaxWidthDeg)
    }

    @Test
    fun sanitized_openingMinWidthDeg_clampsToFloor() {
        val cfg = CellVizConfig(openingMinWidthDeg = 0f).sanitized()
        assertEquals(1f, cfg.openingMinWidthDeg)
    }

    @Test
    fun sanitized_openingMaxWidthDeg_clampsToCeiling() {
        val cfg = CellVizConfig(
            openingMinWidthDeg = 4f,
            openingMaxWidthDeg = 1000f,
        ).sanitized()
        assertEquals(45f, cfg.openingMaxWidthDeg)
    }

    // ----- DEFAULT + idempotence -------------------------------------------

    @Test
    fun default_isInsideAllBounds() {
        val d = CellVizConfig.DEFAULT
        assertTrue(d.rotationDegPerSec in 0f..45f)
        assertTrue(d.membraneRadiusFraction in 0.15f..0.48f)
        assertTrue(d.minOpenings in 0..8)
        assertTrue(d.maxOpenings in d.minOpenings..8)
        assertTrue(d.openingStableMinSec <= d.openingStableMaxSec)
        assertTrue(d.openingMinWidthDeg <= d.openingMaxWidthDeg)
        assertTrue(d.nucleusRadiusFraction in 0.10f..0.60f)
    }

    @Test
    fun default_isIdempotentUnderSanitize() {
        // sanitized() of an already-sanitized config must produce the same instance.
        val once = CellVizConfig.DEFAULT
        val twice = once.sanitized()
        assertEquals(once, twice)
    }

    @Test
    fun sanitized_isIdempotent_forArbitraryInputs() {
        val messy = CellVizConfig(
            rotationDegPerSec = 999f,
            minOpenings = 99,
            maxOpenings = -4,
            openingStableMinSec = 500f,
            openingStableMaxSec = 0.001f,
            openingMinWidthDeg = 1000f,
            openingMaxWidthDeg = 0f,
        )
        val once = messy.sanitized()
        val twice = once.sanitized()
        assertEquals(once, twice)
    }
}
