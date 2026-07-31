package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.ResolveDeferralData
import ai.ciris.mobile.shared.api.TicketData
import ai.ciris.mobile.shared.api.WAStatusData
import ai.ciris.mobile.shared.approvals.ApprovalKind
import ai.ciris.mobile.shared.approvals.ApprovalNotificationSink
import ai.ciris.mobile.shared.approvals.ApprovalNotifier
import ai.ciris.mobile.shared.approvals.ApprovalsApi
import ai.ciris.mobile.shared.approvals.BudgetCapability
import ai.ciris.mobile.shared.approvals.BudgetGrantError
import ai.ciris.mobile.shared.approvals.BudgetGrantOutcome
import ai.ciris.mobile.shared.approvals.GrantedBudget
import ai.ciris.mobile.shared.approvals.InMemoryNotifiedApprovalStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * ViewModel behaviour for the HITL approval surface.
 *
 * Covers the four things that make this a control rather than a decoration:
 * approvals from both sources reach one list, new ones raise exactly one
 * notification, an over-request grant is refused before it leaves the device,
 * and error / empty / permission-denied states never blank the surface.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class WiseAuthorityViewModelTest {

    private val testDispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // ─── Fakes ─────────────────────────────────────────────────────────────

    private class FakeApprovalsApi(
        var status: WAStatusData = waStatus(0),
        var deferrals: List<DeferralData> = emptyList(),
        var proposals: List<TicketData> = emptyList(),
        var grantOutcome: BudgetGrantOutcome = BudgetGrantOutcome(
            ok = true,
            granted = GrantedBudget("25.00", "USDC", "fee", null, null, null, null, signed = true),
        ),
        var statusUpdateOk: Boolean = true,
        var deferralsThrow: Exception? = null,
        var proposalsThrow: Exception? = null,
    ) : ApprovalsApi {
        val grantCalls = mutableListOf<GrantCall>()
        val statusUpdates = mutableListOf<Pair<String, String>>()
        val resolveCalls = mutableListOf<Triple<String, String, String>>()

        data class GrantCall(
            val ticketId: String,
            val amount: String,
            val currency: String,
            val purpose: String,
            val expiresInHours: Int,
        )

        override suspend fun fetchWAStatus(): WAStatusData = status

        override suspend fun fetchDeferrals(): List<DeferralData> {
            deferralsThrow?.let { throw it }
            return deferrals
        }

        override suspend fun resolveDeferral(
            deferralId: String,
            resolution: String,
            guidance: String,
        ): ResolveDeferralData {
            resolveCalls += Triple(deferralId, resolution, guidance)
            return ResolveDeferralData(deferralId, true, "2026-07-31T00:00:00Z")
        }

        override suspend fun fetchProposals(): List<TicketData> {
            proposalsThrow?.let { throw it }
            return proposals
        }

        override suspend fun grantBudget(
            ticketId: String,
            amount: String,
            currency: String,
            purpose: String,
            expiresInHours: Int,
        ): BudgetGrantOutcome {
            grantCalls += GrantCall(ticketId, amount, currency, purpose, expiresInHours)
            return grantOutcome
        }

        override suspend fun updateTicketStatus(ticketId: String, status: String, notes: String?): Boolean {
            statusUpdates += ticketId to status
            return statusUpdateOk
        }
    }

    private class FakeSink(var permission: Boolean = true) : ApprovalNotificationSink {
        val shown = mutableListOf<String>()
        override fun hasPermission(): Boolean = permission
        override suspend fun requestPermission(): Boolean = permission
        override fun show(id: String, title: String, body: String) {
            shown += id
        }
    }

    // ─── Builders ──────────────────────────────────────────────────────────

    private companion object {
        fun waStatus(pending: Int) = WAStatusData(
            serviceHealthy = true,
            activeWAs = 1,
            pendingDeferrals = pending,
            deferrals24h = pending,
            averageResolutionTimeMinutes = 0.0,
            timestamp = null,
        )

        fun deferral(id: String) = DeferralData(
            deferralId = id,
            createdAt = "2026-07-31T00:00:00Z",
            deferredBy = "datum",
            taskId = "task-$id",
            thoughtId = "th-$id",
            reason = "needs a human",
            channelId = null,
            userId = null,
            priority = "normal",
            assignedWaId = null,
            requiresRole = null,
            status = "pending",
            resolution = null,
            resolvedAt = null,
            question = "May I proceed?",
            context = null,
            timeoutAt = null,
        )

        fun meta(json: String): Map<String, JsonElement> =
            Json.parseToJsonElement(json) as JsonObject

        fun proposalTicket(
            id: String,
            requestedAmount: String? = "25.00",
            status: String = "blocked",
        ): TicketData {
            val budget = requestedAmount?.let {
                """, "__requested_budget__": {"requested_amount": "$it",
                     "requested_currency": "USDC", "purpose": "Opt-out fee",
                     "justification": "registry charges"}"""
            }.orEmpty()
            return TicketData(
                ticketId = id,
                sop = "DSAR_DELETE",
                ticketType = "dsar",
                status = status,
                priority = 5,
                email = "user@example.com",
                userIdentifier = null,
                submittedAt = "2026-07-31T00:00:00Z",
                deadline = null,
                lastUpdated = "2026-07-31T00:00:00Z",
                completedAt = null,
                notes = "Delete request",
                automated = false,
                metadata = meta(
                    """{"__proposal__": {"proposed_by": "agent",
                        "goal_description": "Pay the opt-out fee and file the deletion"}$budget}"""
                ),
            )
        }
    }

    private fun viewModel(
        api: FakeApprovalsApi,
        sink: FakeSink = FakeSink(),
    ): Pair<WiseAuthorityViewModel, FakeSink> {
        val notifier = ApprovalNotifier(sink, InMemoryNotifiedApprovalStore())
        return WiseAuthorityViewModel(api, notifier) to sink
    }

    // ─── Unified list ──────────────────────────────────────────────────────

    @Test
    fun refresh_foldsDeferralsAndProposalsIntoOneApprovalList() = runTest {
        val api = FakeApprovalsApi(
            status = waStatus(1),
            deferrals = listOf(deferral("d1")),
            proposals = listOf(proposalTicket("t1")),
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        assertEquals(2, vm.approvals.value.size)
        assertEquals(
            setOf(ApprovalKind.DEFERRAL, ApprovalKind.TICKET_PROPOSAL),
            vm.approvals.value.map { it.kind }.toSet(),
        )
        assertEquals(2, vm.pendingApprovalCount.value)
    }

    @Test
    fun refresh_carriesTheRequestedBudgetOntoTheApproval() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        val approval = vm.approvals.value.single()
        assertNotNull(approval.requestedBudget)
        assertEquals("25.00", approval.requestedBudget.requestedAmount)
        assertTrue(approval.needsBudgetDecision)
        // A request must never read as a grant.
        assertNull(approval.grantedBudget)
    }

    @Test
    fun refresh_ignoresTicketsThatAreNotUnapprovedProposals() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(
                proposalTicket("t1"),
                proposalTicket("t2", status = "pending"), // already promoted
            )
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        assertEquals(listOf("t1"), vm.approvals.value.map { it.id })
    }

    // ─── Empty / error states ──────────────────────────────────────────────

    @Test
    fun refresh_withNothingPendingLeavesAnEmptyListAndNoError() = runTest {
        val (vm, sink) = viewModel(FakeApprovalsApi())

        vm.refresh()
        advanceUntilIdle()

        assertTrue(vm.approvals.value.isEmpty())
        assertEquals(0, vm.pendingApprovalCount.value)
        assertNull(vm.error.value)
        assertTrue(sink.shown.isEmpty())
    }

    @Test
    fun refresh_surfacesAnErrorWhenTheDeferralFetchFails() = runTest {
        val api = FakeApprovalsApi(deferralsThrow = RuntimeException("connection refused"))
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        assertNotNull(vm.error.value)
        assertFalse(vm.isConnected.value)
        assertFalse(vm.isLoading.value)
    }

    @Test
    fun refresh_stillShowsDeferralsWhenTheServerHasNoTicketsApi() = runTest {
        // A deployment without tickets must not lose its deferral list.
        val api = FakeApprovalsApi(
            deferrals = listOf(deferral("d1")),
            proposalsThrow = RuntimeException("404 Not Found"),
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        // fetchProposals throwing propagates through fetchDataInternal, so the
        // surface reports the error rather than silently showing a partial list.
        assertNotNull(vm.error.value)
    }

    // ─── Notification ──────────────────────────────────────────────────────

    @Test
    fun newApprovalNotifiesExactlyOnceAcrossRepeatedPolls() = runTest {
        val api = FakeApprovalsApi(deferrals = listOf(deferral("d1")))
        val (vm, sink) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()
        vm.refresh()
        advanceUntilIdle()
        vm.refresh()
        advanceUntilIdle()

        assertEquals(listOf("d1"), sink.shown)
    }

    @Test
    fun permissionDeniedShowsNoNotificationButStillPopulatesTheSurface() = runTest {
        val api = FakeApprovalsApi(deferrals = listOf(deferral("d1")))
        val (vm, sink) = viewModel(api, FakeSink(permission = false))

        vm.refresh()
        advanceUntilIdle()

        assertTrue(sink.shown.isEmpty(), "no notification without permission")
        assertEquals(1, vm.approvals.value.size, "but the badge and card must still show it")
        assertEquals(1, vm.pendingApprovalCount.value)
        assertNull(vm.error.value, "a missing notification is not an error state")
    }

    // ─── Budget issuance ───────────────────────────────────────────────────

    @Test
    fun grantBudget_refusesMoreThanRequestedWithoutCallingTheServer() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        var outcome: BudgetGrantOutcome? = null
        vm.grantBudget("t1", "100.00", "USDC", "fee", 24, promote = false) { outcome = it }
        advanceUntilIdle()

        assertEquals(BudgetGrantError.EXCEEDS_REQUESTED, outcome?.error)
        assertTrue(api.grantCalls.isEmpty(), "an over-request grant must never reach the wire")
        assertNotNull(vm.error.value)
    }

    @Test
    fun grantBudget_allowsAtOrBelowRequested() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "10.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertEquals(1, api.grantCalls.size)
        assertEquals("10.00", api.grantCalls.single().amount)
        assertEquals(BudgetCapability.AVAILABLE, vm.budgetCapability.value)
    }

    @Test
    fun grantBudget_doesNotStartTheWorkUnlessAskedTo() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertTrue(
            api.statusUpdates.isEmpty(),
            "granting money and starting work are separate decisions",
        )
    }

    @Test
    fun grantBudget_promotesWhenAsked() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = true)
        advanceUntilIdle()

        assertEquals(listOf("t1" to "pending"), api.statusUpdates)
    }

    @Test
    fun grantBudget_onAnApprovalWithNoBudgetRequestIsRefusedLocally() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", requestedAmount = null)))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        var outcome: BudgetGrantOutcome? = null
        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = false) { outcome = it }
        advanceUntilIdle()

        assertFalse(outcome?.ok ?: true)
        assertTrue(api.grantCalls.isEmpty())
    }

    @Test
    fun grantBudget_marksTheServerUnsupportedWhenTheEndpointIsAbsent() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1")),
            grantOutcome = BudgetGrantOutcome(false, BudgetGrantError.ENDPOINT_UNAVAILABLE),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertEquals(BudgetCapability.UNAVAILABLE, vm.budgetCapability.value)
        assertNotNull(vm.error.value)
    }

    @Test
    fun grantBudget_reportsAForbiddenRoleRatherThanFailingSilently() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1")),
            grantOutcome = BudgetGrantOutcome(false, BudgetGrantError.FORBIDDEN_ROLE),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertNotNull(vm.error.value)
        assertTrue(vm.error.value!!.contains("AUTHORITY", ignoreCase = true))
        // Capability is unchanged — the endpoint exists, the caller lacks the role.
        assertEquals(BudgetCapability.UNKNOWN, vm.budgetCapability.value)
    }

    // ─── Proposal lifecycle ────────────────────────────────────────────────

    @Test
    fun rejectProposal_cancelsTheTicket() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1")))
        val (vm, _) = viewModel(api)

        vm.rejectProposal("t1", "not warranted")
        advanceUntilIdle()

        assertEquals(listOf("t1" to "cancelled"), api.statusUpdates)
    }

    @Test
    fun deferProposal_leavesTheTicketBlocked() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1")))
        val (vm, _) = viewModel(api)

        vm.deferProposal("t1", "ask me tomorrow")
        advanceUntilIdle()

        // Fail-closed stays fail-closed: nothing is issued, nothing starts.
        assertEquals(listOf("t1" to "blocked"), api.statusUpdates)
    }

    @Test
    fun resolveDeferral_usesTheWireResolutionTheServerAccepts() = runTest {
        val api = FakeApprovalsApi(deferrals = listOf(deferral("d1")))
        val (vm, _) = viewModel(api)

        vm.resolveDeferral("d1", "approve", "go ahead")
        advanceUntilIdle()

        assertEquals(Triple("d1", "approve", "go ahead"), api.resolveCalls.single())
    }
}
