package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.models.AdapterToolDisclosure
import ai.ciris.mobile.shared.models.ToolCapabilityFlags
import ai.ciris.mobile.shared.models.ToolDisclosure
import ai.ciris.mobile.shared.models.ToolDisclosureReport
import ai.ciris.mobile.shared.models.ToolDisclosureSources
import ai.ciris.mobile.shared.models.forAdapter
import ai.ciris.mobile.shared.models.summarizeCapabilityFlags
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

/**
 * Client-side guards for the first-run tool disclosure (#941).
 *
 * The disclosure exists so the operator accepting the enabled-by-default optional
 * features is told what those choices grant. These tests protect the two ways the
 * client could quietly undo that: turning "we don't know" into "nothing", and
 * dropping a capability the server flagged.
 *
 * Nothing here gates anything -- expanding a disclosure never changes which
 * adapters are enabled, and that is asserted below.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SetupToolDisclosureTest {

    private val testDispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // CIRISApiClientProtocol has ~30 abstract members; none of them are exercised
    // here because loadToolDisclosure takes the fetch as a parameter. Reusing the
    // existing stub in this source set beats duplicating all of them.
    private fun viewModel() = SetupViewModel(FakeCIRISApiClientForBilling())

    private fun report() = ToolDisclosureReport(
        adapters = listOf(
            AdapterToolDisclosure(
                adapter_id = "api",
                adapter_name = "Web API",
                source = ToolDisclosureSources.PROSPECTIVE,
                tools = listOf(
                    ToolDisclosure(
                        name = "curl",
                        description = "Execute HTTP requests with curl-like functionality",
                        model_authored_parameters = listOf("data", "headers", "method", "timeout", "url"),
                        capability_flags = listOf(
                            ToolCapabilityFlags.NETWORK_FETCH,
                            ToolCapabilityFlags.CUSTOM_HEADERS,
                            ToolCapabilityFlags.REQUEST_BODY
                        )
                    )
                )
            ),
            AdapterToolDisclosure(
                adapter_id = "mystery",
                adapter_name = "Mystery",
                source = ToolDisclosureSources.UNAVAILABLE,
                source_note = "only knowable after it loads",
                tools = emptyList()
            )
        ),
        always_on = listOf(
            AdapterToolDisclosure(
                adapter_id = "core_tools",
                adapter_name = "Core agent tools",
                always_on = true,
                source = ToolDisclosureSources.PROSPECTIVE,
                tools = listOf(
                    ToolDisclosure(
                        name = "recall_secret",
                        description = "Recall a stored secret by UUID",
                        model_authored_parameters = listOf("decrypt", "purpose", "secret_uuid"),
                        capability_flags = listOf(ToolCapabilityFlags.SECRET_PLAINTEXT)
                    )
                )
            )
        ),
        total_tools = 2
    )

    // --- loading ---------------------------------------------------------

    @Test
    fun loadToolDisclosure_success_storesReport() = runTest {
        val vm = viewModel()
        vm.loadToolDisclosure { report() }

        val state = vm.state.value
        assertFalse(state.toolDisclosureLoading)
        assertEquals(2, state.toolDisclosure?.total_tools)
        assertEquals(1, vm.alwaysOnToolDisclosures().size)
    }

    @Test
    fun loadToolDisclosure_failure_leavesNullNotEmpty() = runTest {
        val vm = viewModel()
        vm.loadToolDisclosure { throw RuntimeException("network down") }

        val state = vm.state.value
        assertFalse(state.toolDisclosureLoading)
        // Null means "we could not find out", which the UI renders as such.
        // An empty report would read as "these choices grant nothing" -- the exact
        // false assurance this feature exists to remove.
        assertNull(state.toolDisclosure)
        assertTrue(vm.alwaysOnToolDisclosures().isEmpty())
    }

    @Test
    fun toolDisclosureFor_unknownAdapter_isNullNotEmptyList() = runTest {
        val vm = viewModel()
        vm.loadToolDisclosure { report() }

        assertNull(vm.toolDisclosureFor("discord"))
        assertEquals("api", vm.toolDisclosureFor("api")?.adapter_id)
    }

    @Test
    fun unavailableAdapter_isDisclosedWithAReason() = runTest {
        val vm = viewModel()
        vm.loadToolDisclosure { report() }

        val mystery = vm.toolDisclosureFor("mystery")
        assertEquals(ToolDisclosureSources.UNAVAILABLE, mystery?.source)
        assertTrue(mystery?.tools.isNullOrEmpty())
        // An empty list is only acceptable alongside an explanation.
        assertTrue(!mystery?.source_note.isNullOrBlank())
    }

    // --- expansion is presentation only ----------------------------------

    @Test
    fun toggleToolDisclosureExpanded_togglesAndDoesNotChangeEnabledAdapters() = runTest {
        val vm = viewModel()
        val enabledBefore = vm.state.value.enabledAdapterIds

        assertFalse(vm.isToolDisclosureExpanded("api"))
        vm.toggleToolDisclosureExpanded("api")
        assertTrue(vm.isToolDisclosureExpanded("api"))
        vm.toggleToolDisclosureExpanded("api")
        assertFalse(vm.isToolDisclosureExpanded("api"))

        // Reading the disclosure must never be a gate on the capability.
        assertEquals(enabledBefore, vm.state.value.enabledAdapterIds)
    }

    @Test
    fun expansionIsPerGroup() = runTest {
        val vm = viewModel()
        vm.toggleToolDisclosureExpanded("api")
        vm.toggleToolDisclosureExpanded("core_tools")

        assertTrue(vm.isToolDisclosureExpanded("api"))
        assertTrue(vm.isToolDisclosureExpanded("core_tools"))
        assertFalse(vm.isToolDisclosureExpanded("discord"))
    }

    // --- capability summary ----------------------------------------------

    @Test
    fun summarizeCapabilityFlags_leadsWithLeastExpectedConsequence() {
        val tools = listOf(
            ToolDisclosure(name = "a", capability_flags = listOf(ToolCapabilityFlags.FILE_READ)),
            ToolDisclosure(
                name = "b",
                capability_flags = listOf(
                    ToolCapabilityFlags.NETWORK_FETCH,
                    ToolCapabilityFlags.SHELL_EXECUTION
                )
            )
        )
        val summary = summarizeCapabilityFlags(tools)

        // Shell execution outranks a plain file read, so a collapsed summary that
        // shows only the first entries still shows the uncomfortable one.
        assertEquals(ToolCapabilityFlags.SHELL_EXECUTION, summary.first())
        assertTrue(summary.indexOf(ToolCapabilityFlags.NETWORK_FETCH) < summary.indexOf(ToolCapabilityFlags.FILE_READ))
    }

    @Test
    fun summarizeCapabilityFlags_keepsFlagsThisClientDoesNotKnow() {
        val tools = listOf(
            ToolDisclosure(
                name = "a",
                capability_flags = listOf("moves_money", ToolCapabilityFlags.NETWORK_FETCH)
            )
        )
        val summary = summarizeCapabilityFlags(tools)

        // A newer server flagging something this build has never heard of must not
        // cause that disclosure to disappear.
        assertTrue("moves_money" in summary)
        assertEquals(ToolCapabilityFlags.NETWORK_FETCH, summary.first())
    }

    @Test
    fun summarizeCapabilityFlags_deduplicatesAcrossTools() {
        val tools = listOf(
            ToolDisclosure(name = "a", capability_flags = listOf(ToolCapabilityFlags.NETWORK_FETCH)),
            ToolDisclosure(name = "b", capability_flags = listOf(ToolCapabilityFlags.NETWORK_FETCH))
        )
        assertEquals(listOf(ToolCapabilityFlags.NETWORK_FETCH), summarizeCapabilityFlags(tools))
    }

    // --- client-side drift guard -----------------------------------------

    @Test
    fun everyKnownCapabilityFlagIsRankedAndHasALocalizationKey() {
        val declared = listOf(
            ToolCapabilityFlags.NETWORK_FETCH,
            ToolCapabilityFlags.CUSTOM_HEADERS,
            ToolCapabilityFlags.REQUEST_BODY,
            ToolCapabilityFlags.SHELL_EXECUTION,
            ToolCapabilityFlags.FILE_READ,
            ToolCapabilityFlags.FILE_WRITE,
            ToolCapabilityFlags.SECRET_PLAINTEXT,
            ToolCapabilityFlags.AFFECTS_OTHER_PEOPLE,
            ToolCapabilityFlags.REQUIRES_APPROVAL
        )

        // A flag missing from NOTABLE would sort last in every collapsed summary
        // and could fall off the visible end -- silently hiding a consequence.
        assertEquals(declared.toSet(), ToolCapabilityFlags.NOTABLE.toSet())
        assertEquals(ToolCapabilityFlags.NOTABLE.size, ToolCapabilityFlags.NOTABLE.toSet().size)

        declared.forEach { flag ->
            assertEquals("mobile.tool_cap_$flag", ToolCapabilityFlags.localizationKey(flag))
        }
    }

    @Test
    fun forAdapter_matchesViewModelLookup() = runTest {
        val vm = viewModel()
        val r = report()
        vm.loadToolDisclosure { r }

        assertEquals(r.forAdapter("api")?.adapter_id, vm.toolDisclosureFor("api")?.adapter_id)
        assertNull(r.forAdapter("nope"))
    }
}
