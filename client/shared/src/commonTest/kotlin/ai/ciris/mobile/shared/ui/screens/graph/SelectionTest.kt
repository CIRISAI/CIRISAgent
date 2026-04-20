package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Pure tests for [hitTestSelection]. Matches the priority contract
 * documented in FSD/CELL_VIZ_REDESIGN.md §12.3:
 *
 *   1. AdapterPort
 *   2. CytoplasmMote
 *   3. NucleusCore
 *   4. NucleusShell
 *   5. BusArc
 *
 * Anything outside the membrane (+ slack) returns null.
 */
class SelectionTest {

    // Standard layout used by most tests — centred, 300 px membrane,
    // 100 px nucleus, zero rotation.
    private val layout = SelectionLayout(
        centerX = 500f,
        centerY = 500f,
        membraneRadius = 300f,
        nucleusRadius = 100f,
        rotationDeg = 0f,
    )

    // Seven H3ERE event types in shell-order (inner → outer).
    private val stages = listOf(
        "thought_start",
        "snapshot_and_context",
        "dma_results",
        "idma_result",
        "aspdma_result",
        "conscience_result",
        "action_result",
    )

    // =========================================================================
    // AdapterPort — highest priority
    // =========================================================================

    @Test
    fun `tap on adapter port returns AdapterPort even when over a bus arc`() {
        val port = SelectionPort(
            adapterId = "weather_abc",
            adapterType = "weather",
            bus = CellBus.TOOL,
            x = 800f, y = 500f,  // right of centre, on membrane
        )
        val hit = hitTestSelection(
            tapX = 800f, tapY = 500f,
            layout = layout,
            ports = listOf(port),
            motes = emptyList(),
            shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.AdapterPort)
        assertEquals("weather_abc", hit.adapterId)
        assertEquals(CellBus.TOOL, hit.bus)
    }

    @Test
    fun `tap 5 px from a port still hits the port (hit radius forgiving)`() {
        val port = SelectionPort("a", "api", CellBus.COMM, 300f, 500f)
        val hit = hitTestSelection(
            tapX = 305f, tapY = 500f,
            layout = layout.copy(portHitRadiusPx = 18f),
            ports = listOf(port),
            motes = emptyList(),
            shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.AdapterPort)
    }

    @Test
    fun `tap 30 px from a port misses the port`() {
        val port = SelectionPort("a", "api", CellBus.COMM, 300f, 500f)
        val hit = hitTestSelection(
            tapX = 330f, tapY = 500f,  // 30 px off
            layout = layout.copy(portHitRadiusPx = 18f),
            ports = listOf(port),
            motes = emptyList(),
            shellEventTypes = stages,
        )
        assertTrue(hit !is SelectionKind.AdapterPort, "port should have missed")
    }

    // =========================================================================
    // CytoplasmMote — beats NucleusCore/Shell when inside the nucleus
    // =========================================================================

    @Test
    fun `mote inside the nucleus region beats NucleusShell`() {
        // Place mote at centre+50 (well inside nucleus radius 100).
        val mote = SelectionMote("node-123", "LOCAL", 550f, 500f)
        val hit = hitTestSelection(
            tapX = 550f, tapY = 500f,
            layout = layout,
            ports = emptyList(),
            motes = listOf(mote),
            shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.CytoplasmMote)
        assertEquals("node-123", hit.nodeId)
    }

    @Test
    fun `mote tap hit radius is 8 px by default`() {
        val mote = SelectionMote("n", "LOCAL", 600f, 500f)
        val in8 = hitTestSelection(
            tapX = 607f, tapY = 500f,
            layout = layout, ports = emptyList(),
            motes = listOf(mote), shellEventTypes = stages,
        )
        val out12 = hitTestSelection(
            tapX = 612f, tapY = 500f,
            layout = layout, ports = emptyList(),
            motes = listOf(mote), shellEventTypes = stages,
        )
        assertTrue(in8 is SelectionKind.CytoplasmMote)
        assertTrue(out12 !is SelectionKind.CytoplasmMote)
    }

    // =========================================================================
    // NucleusCore — innermost band
    // =========================================================================

    @Test
    fun `tap at the centre returns NucleusCore`() {
        val hit = hitTestSelection(
            tapX = 500f, tapY = 500f,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertEquals(SelectionKind.NucleusCore, hit)
    }

    @Test
    fun `tap within 30 percent of nucleus radius returns NucleusCore`() {
        // nucleusRadius=100, core=<30 px from centre.
        val hit = hitTestSelection(
            tapX = 500f + 25f, tapY = 500f,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertEquals(SelectionKind.NucleusCore, hit)
    }

    // =========================================================================
    // NucleusShell — concentric bands inside the nucleus
    // =========================================================================

    @Test
    fun `tap in the middle nucleus radius lands on a middle shell`() {
        // nucleusRadius=100, tap at 50 px from centre — somewhere in
        // the middle of the 7 shells.
        val hit = hitTestSelection(
            tapX = 500f + 50f, tapY = 500f,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.NucleusShell)
        assertTrue(hit.stageIndex in 1..4, "expected middle shell, got ${hit.stageIndex}")
    }

    @Test
    fun `tap at nucleus outer edge returns the outermost shell`() {
        val hit = hitTestSelection(
            tapX = 500f + 95f, tapY = 500f,  // very close to nucleusR=100
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.NucleusShell)
        assertEquals(6, hit.stageIndex)
        assertEquals("action_result", hit.eventType)
    }

    @Test
    fun `shell tap returns event_type matching its index`() {
        val hit = hitTestSelection(
            tapX = 500f + 35f, tapY = 500f,  // just outside core
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.NucleusShell)
        assertEquals(stages[hit.stageIndex], hit.eventType)
    }

    // =========================================================================
    // BusArc — tap on or near the membrane line
    // =========================================================================

    @Test
    fun `tap on the membrane at 30 degrees returns the TOOL bus`() {
        // 30° below +x axis, at membrane radius.
        val angleRad = 30.0 * kotlin.math.PI / 180.0
        val x = layout.centerX + layout.membraneRadius * kotlin.math.cos(angleRad).toFloat()
        val y = layout.centerY + layout.membraneRadius * kotlin.math.sin(angleRad).toFloat()
        val hit = hitTestSelection(
            tapX = x, tapY = y,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.BusArc)
        assertEquals(CellBus.TOOL, hit.bus)
    }

    @Test
    fun `tap on the membrane at 90 degrees returns the LLM bus`() {
        // 90° = straight down from centre.
        val hit = hitTestSelection(
            tapX = layout.centerX,
            tapY = layout.centerY + layout.membraneRadius,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.BusArc)
        assertEquals(CellBus.LLM, hit.bus)
    }

    @Test
    fun `rotation shifts which bus a given angle hits`() {
        // With rotation=60° the TOOL segment moves to 60..120 in screen
        // space, so a tap at angle 90° (screen) corresponds to canonical
        // angle 30° → TOOL.
        val rotated = layout.copy(rotationDeg = 60f)
        val hit = hitTestSelection(
            tapX = rotated.centerX,
            tapY = rotated.centerY + rotated.membraneRadius,
            layout = rotated, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.BusArc)
        assertEquals(CellBus.TOOL, hit.bus)
    }

    @Test
    fun `tap slightly inside the membrane still hits the bus arc`() {
        val hit = hitTestSelection(
            tapX = layout.centerX + (layout.membraneRadius - 5f),
            tapY = layout.centerY,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertTrue(hit is SelectionKind.BusArc)
    }

    // =========================================================================
    // Out-of-bounds + deselection
    // =========================================================================

    @Test
    fun `tap far outside the membrane returns null`() {
        val hit = hitTestSelection(
            tapX = layout.centerX + layout.membraneRadius + 50f,
            tapY = layout.centerY,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertNull(hit)
    }

    @Test
    fun `tap in empty cytoplasm (no mote) returns null`() {
        // Between nucleus (r=100) and membrane (r=300), no mote there.
        val hit = hitTestSelection(
            tapX = layout.centerX + 200f, tapY = layout.centerY,
            layout = layout, ports = emptyList(),
            motes = emptyList(), shellEventTypes = stages,
        )
        assertNull(hit)
    }

    // =========================================================================
    // shellIndexForRadius unit tests
    // =========================================================================

    @Test
    fun `shellIndexForRadius returns 0 at the very centre`() {
        assertEquals(0, shellIndexForRadius(r = 5f, nucleusOuterR = 100f))
    }

    @Test
    fun `shellIndexForRadius returns 6 at outer edge`() {
        assertEquals(6, shellIndexForRadius(r = 99f, nucleusOuterR = 100f))
    }

    @Test
    fun `shellIndexForRadius is monotonic in radius`() {
        var last = -1
        for (r in 0..100 step 5) {
            val idx = shellIndexForRadius(r.toFloat(), 100f) ?: continue
            assertTrue(idx >= last, "non-monotonic: last=$last this=$idx at r=$r")
            last = idx
        }
    }

    // =========================================================================
    // busAtAngle sanity
    // =========================================================================

    @Test
    fun `busAtAngle covers all 6 buses across the ring`() {
        // Canonical angles sampled every 30°.
        val found = mutableSetOf<CellBus>()
        for (deg in 0..330 step 30) {
            val rad = deg.toDouble() * kotlin.math.PI / 180.0
            val dx = kotlin.math.cos(rad).toFloat()
            val dy = kotlin.math.sin(rad).toFloat()
            busAtAngle(rotationDeg = 0f, dx = dx, dy = dy)?.let { found.add(it) }
        }
        assertEquals(6, found.size, "expected all six buses, got $found")
    }
}
