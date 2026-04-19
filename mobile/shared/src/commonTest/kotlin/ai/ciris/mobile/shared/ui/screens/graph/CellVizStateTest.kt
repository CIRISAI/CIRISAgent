package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Pure tests for [CellVizState] sanitization and [derivedDials] mapping.
 *
 * These guard the factor-to-visual-dial contract: a Compose author
 * should be able to read [derivedDials] and trust every field is in a
 * safe range no matter what upstream capacity data arrived.
 */
class CellVizStateTest {

    // =========================================================================
    // DEFAULT / neutral baseline
    // =========================================================================

    @Test
    fun `DEFAULT is neutral — all factors 1 0, preFetch true`() {
        val s = CellVizState.DEFAULT
        assertEquals(1f, s.c)
        assertEquals(1f, s.iInt)
        assertEquals(1f, s.r)
        assertEquals(1f, s.iInc)
        assertEquals(1f, s.s)
        assertEquals(1f, s.compositeScore)
        assertTrue(s.isPreFetch, "DEFAULT must flag pre-fetch so UI can distinguish 'never fetched' from 'all 1.0'")
    }

    @Test
    fun `derivedDials NEUTRAL for DEFAULT state`() {
        val dials = derivedDials(CellVizState.DEFAULT)
        assertEquals(CellVizDials.NEUTRAL.nucleusOpacity, dials.nucleusOpacity)
        assertEquals(CellVizDials.NEUTRAL.busCrispness, dials.busCrispness)
        assertEquals(CellVizDials.NEUTRAL.breathSteadiness, dials.breathSteadiness)
        assertEquals(CellVizDials.NEUTRAL.openingBias, dials.openingBias)
        assertEquals(CellVizDials.NEUTRAL.moteWarmth, dials.moteWarmth)
    }

    // =========================================================================
    // sanitize() clamps every factor into [0, 1]
    // =========================================================================

    @Test
    fun `sanitized clamps all factors into unit interval`() {
        val s = CellVizState(
            c = 1.3f, iInt = -0.2f, r = 2f, iInc = -5f, s = 0.7f,
            compositeScore = -1f, fragilityIndex = -3f,
        ).sanitized()
        assertEquals(1f, s.c)
        assertEquals(0f, s.iInt)
        assertEquals(1f, s.r)
        assertEquals(0f, s.iInc)
        assertEquals(0.7f, s.s)
        assertEquals(0f, s.compositeScore)
        assertEquals(0f, s.fragilityIndex)  // never negative, unbounded above
    }

    @Test
    fun `sanitized allows fragilityIndex above 1 — unbounded upward`() {
        val s = CellVizState(fragilityIndex = 5.5f).sanitized()
        assertEquals(5.5f, s.fragilityIndex)
    }

    // =========================================================================
    // derivedDials — per-factor mapping is loud enough to see
    // =========================================================================

    @Test
    fun `derivedDials nucleusOpacity tracks C factor linearly between 0 55 and 1 0`() {
        assertEquals(0.55f, derivedDials(CellVizState(c = 0f)).nucleusOpacity, 1e-4f)
        assertEquals(1.00f, derivedDials(CellVizState(c = 1f)).nucleusOpacity, 1e-4f)
        assertEquals(0.775f, derivedDials(CellVizState(c = 0.5f)).nucleusOpacity, 1e-4f)
    }

    @Test
    fun `derivedDials busCrispness tracks I_int linearly between 0 70 and 1 0`() {
        assertEquals(0.70f, derivedDials(CellVizState(iInt = 0f)).busCrispness, 1e-4f)
        assertEquals(1.00f, derivedDials(CellVizState(iInt = 1f)).busCrispness, 1e-4f)
    }

    @Test
    fun `derivedDials breathSteadiness tracks R linearly between 0 40 and 1 0`() {
        assertEquals(0.40f, derivedDials(CellVizState(r = 0f)).breathSteadiness, 1e-4f)
        assertEquals(1.00f, derivedDials(CellVizState(r = 1f)).breathSteadiness, 1e-4f)
    }

    @Test
    fun `derivedDials openingBias is I_inc passthrough`() {
        assertEquals(0f, derivedDials(CellVizState(iInc = 0f)).openingBias, 1e-4f)
        assertEquals(0.5f, derivedDials(CellVizState(iInc = 0.5f)).openingBias, 1e-4f)
        assertEquals(1f, derivedDials(CellVizState(iInc = 1f)).openingBias, 1e-4f)
    }

    @Test
    fun `derivedDials moteWarmth tracks S linearly between 0 20 and 1 0`() {
        assertEquals(0.20f, derivedDials(CellVizState(s = 0f)).moteWarmth, 1e-4f)
        assertEquals(1.00f, derivedDials(CellVizState(s = 1f)).moteWarmth, 1e-4f)
    }

    // =========================================================================
    // Floors prevent "broken" look under low scores
    // =========================================================================

    @Test
    fun `derivedDials floors keep cell recognisable under worst-case factors`() {
        val worstCase = CellVizState(
            c = 0f, iInt = 0f, r = 0f, iInc = 0f, s = 0f,
        )
        val dials = derivedDials(worstCase)
        assertTrue(dials.nucleusOpacity >= 0.55f, "Nucleus must stay visible")
        assertTrue(dials.busCrispness >= 0.70f, "Bus arcs must stay recognisable")
        assertTrue(dials.breathSteadiness >= 0.40f, "Breath must still animate")
        assertTrue(dials.moteWarmth >= 0.20f, "Motes must stay visible")
        // Opening bias floor is intentionally 0 — zero humility collapses
        // toward minOpenings, but the min is enforced by CellVizConfig.
    }

    @Test
    fun `derivedDials sanitizes out-of-range input before mapping`() {
        // Upstream could send NaN or out-of-range floats. Sanitized values
        // clamp first, then map — so no dial ever escapes [floor, 1.0].
        val rogue = CellVizState(c = 2f, iInt = -1f, r = 10f, iInc = -0.5f, s = 1.5f)
        val dials = derivedDials(rogue)
        assertEquals(1f, dials.nucleusOpacity, 1e-4f)
        assertEquals(0.70f, dials.busCrispness, 1e-4f)
        assertEquals(1f, dials.breathSteadiness, 1e-4f)
        assertEquals(0f, dials.openingBias, 1e-4f)
        assertEquals(1f, dials.moteWarmth, 1e-4f)
    }

    // =========================================================================
    // Realistic lens payloads
    // =========================================================================

    @Test
    fun `derivedDials for Ally-like high_capacity reads as near-neutral`() {
        // Shape taken from the live /scoring/capacity/Ally payload.
        val ally = CellVizState(
            c = 1.0f, iInt = 0.9697f, r = 1.0f, iInc = 0.9253f, s = 1.0f,
            compositeScore = 0.8972f, fragilityIndex = 1.1133f,
            category = "high_capacity", isPreFetch = false,
        )
        val dials = derivedDials(ally)
        // High-capacity cell should look almost-but-not-quite NEUTRAL.
        assertTrue(dials.nucleusOpacity > 0.95f)
        assertTrue(dials.busCrispness > 0.95f)
        assertTrue(dials.breathSteadiness > 0.95f)
        assertTrue(dials.openingBias > 0.85f)
        assertTrue(dials.moteWarmth > 0.95f)
    }

    @Test
    fun `derivedDials for Scout-like moderate reads as clearly degraded on R`() {
        // Scout fixtures: R=0.4375 due to drift penalty. Other factors healthy.
        val scout = CellVizState(
            c = 1.0f, iInt = 0.9702f, r = 0.4375f, iInc = 0.8938f, s = 1.0f,
            compositeScore = 0.3794f, fragilityIndex = 2.629f,
            category = "moderate", isPreFetch = false,
        )
        val dials = derivedDials(scout)
        // Breath should be noticeably dampened — that's the whole point of
        // signalling drift. Other dials near-healthy, matching Scout's scores.
        assertTrue(dials.breathSteadiness < 0.70f, "Scout's R=0.44 should dampen breath to < 0.70")
        assertTrue(dials.nucleusOpacity > 0.95f, "Scout's C=1.0 leaves nucleus bright")
        assertTrue(dials.moteWarmth > 0.95f, "Scout's S=1.0 leaves motes warm")
    }
}
