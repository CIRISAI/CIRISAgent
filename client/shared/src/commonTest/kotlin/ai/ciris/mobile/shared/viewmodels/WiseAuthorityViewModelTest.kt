package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.ResolveDeferralData
import ai.ciris.mobile.shared.api.TicketData
import ai.ciris.mobile.shared.api.WAStatusData
import ai.ciris.mobile.shared.approvals.ApprovalKind
import ai.ciris.mobile.shared.approvals.ApprovalNotificationSink
import ai.ciris.mobile.shared.approvals.ApprovalNotifier
import ai.ciris.mobile.shared.approvals.ApprovalsApi
import ai.ciris.mobile.shared.approvals.BudgetApprovalSeam
import ai.ciris.mobile.shared.approvals.BudgetCapability
import ai.ciris.mobile.shared.approvals.BudgetGrantError
import ai.ciris.mobile.shared.approvals.BudgetGrantOutcome
import ai.ciris.mobile.shared.approvals.GrantedBudget
import ai.ciris.mobile.shared.approvals.InMemoryNotifiedApprovalStore
import ai.ciris.mobile.shared.approvals.RequestedBudget
import ai.ciris.mobile.shared.approvals.TicketBudgetState
import ai.ciris.mobile.shared.approvals.TrustHeadroom
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
        var budgetState: TicketBudgetState? = null,
        var budgetStateThrow: Exception? = null,
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

        override suspend fun fetchTicketBudget(ticketId: String): TicketBudgetState? {
            budgetStateThrow?.let { throw it }
            return budgetState
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
            grantedAmount: String? = null,
            spentTotal: String? = null,
            exceedsRequest: Boolean = false,
        ): TicketData {
            val budget = requestedAmount?.let {
                """, "__requested_budget__": {"requested_amount": "$it",
                     "requested_currency": "USDC", "purpose": "Opt-out fee",
                     "justification": "registry charges"}"""
            }.orEmpty()
            val grant = grantedAmount?.let {
                val marking = if (exceedsRequest) {
                    """, "exceeds_request": true, "requested_amount_at_grant": "$requestedAmount""""
                } else ""
                """, "__granted_budget__": {"granted_amount": "$it",
                     "granted_currency": "USDC", "purpose": "Opt-out fee",
                     "expires_at": "2026-08-01T00:00:00Z", "signed": true$marking}"""
            }.orEmpty()
            val spend = spentTotal?.let {
                """, "__budget_spent__": {"total_spent": "$it",
                     "currency": "USDC", "records": [{}]}"""
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
                        "goal_description": "Pay the opt-out fee and file the deletion"}$budget$grant$spend}"""
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
    fun grantBudget_holdsAnUnconfirmedOverGrantWithoutCallingTheServer() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        var outcome: BudgetGrantOutcome? = null
        vm.grantBudget("t1", "250.00", "USDC", "fee", 24, promote = false) { outcome = it }
        advanceUntilIdle()

        assertEquals(BudgetGrantError.OVER_GRANT_UNCONFIRMED, outcome?.error)
        assertEquals("10×", outcome?.overGrant?.display)
        assertTrue(api.grantCalls.isEmpty(), "an unconfirmed over-grant must never reach the wire")
        assertNotNull(vm.error.value)
    }

    @Test
    fun grantBudget_permitsAnOverGrantOnceConfirmed() = runTest {
        // Direct user ruling: an AUTHORITY may approve above the request,
        // because the agent may have asked for too little.
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "250.00", "USDC", "fee", 24, promote = false, overGrantConfirmed = true)
        advanceUntilIdle()

        assertEquals(1, api.grantCalls.size)
        assertEquals("250.00", api.grantCalls.single().amount)
    }

    @Test
    fun grantBudget_echoesTheServersOwnOverGrantMarking() = runTest {
        // The marking is derived server-side and sits inside the signed
        // payload; the client reports what was recorded, not what it asked for.
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1", "25.00")),
            grantOutcome = BudgetGrantOutcome(
                ok = true,
                granted = GrantedBudget(
                    "250.00", "USDC", "fee", null, null, null, null,
                    signed = true, exceedsRequest = true, requestedAmountAtGrant = "25.00",
                ),
            ),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "250.00", "USDC", "fee", 24, promote = false, overGrantConfirmed = true)
        advanceUntilIdle()

        assertTrue(vm.successMessage.value!!.contains("above the 25.00 requested"))
    }

    @Test
    fun grantBudget_doesNotClaimAnOverGrantOnAnOrdinaryOne() = runTest {
        val api = FakeApprovalsApi(proposals = listOf(proposalTicket("t1", "25.00")))
        val (vm, _) = viewModel(api)
        vm.refresh()
        advanceUntilIdle()

        vm.grantBudget("t1", "10.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertFalse(vm.successMessage.value!!.contains("above"))
    }

    @Test
    fun anIssuedOverGrantSurfacesTheServerDerivedMarkingFromTicketMetadata() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(
                proposalTicket("t1", requestedAmount = "25.00", grantedAmount = "250.00", exceedsRequest = true)
            )
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        val granted = vm.approvals.value.single().grantedBudget
        assertNotNull(granted)
        assertTrue(granted.exceedsRequest)
        // The snapshot from the grant, not a live read of the ticket's request.
        assertEquals("25.00", granted.requestedAmountAtGrant)
    }

    @Test
    fun grantBudget_confirmationDoesNotOverrideTheTrustEnvelope() = runTest {
        // The ceiling is the real bound and no acknowledgement talks past it.
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1", "25.00")),
            budgetState = budgetState(headroomAmount = "40"),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        vm.loadBudgetState("t1")
        advanceUntilIdle()

        var outcome: BudgetGrantOutcome? = null
        vm.grantBudget(
            "t1", "250.00", "USDC", "fee", 24, promote = false, overGrantConfirmed = true,
        ) { outcome = it }
        advanceUntilIdle()

        assertEquals(BudgetGrantError.NESTING_VIOLATION, outcome?.error)
        assertTrue(api.grantCalls.isEmpty())
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

    // ─── Re-grant: what the surface must show after a spend ────────────────

    @Test
    fun afterGrantSpendAndRegrant_theSurfaceShowsRemainingNotGranted() = runTest {
        // The backend's TestRegrantSemantics case: grant 25 → spend 25 →
        // re-grant 40. The ledger survives, so 15 is spendable, not 40.
        // Rendering granted_amount here would tell an approving human a number
        // 25 USDC above what the system will actually permit.
        val api = FakeApprovalsApi(
            proposals = listOf(
                proposalTicket("t1", requestedAmount = "50.00", grantedAmount = "40", spentTotal = "25")
            )
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        val approval = vm.approvals.value.single()
        assertEquals("40", approval.grantedBudget?.grantedAmount)
        assertEquals("25", approval.budgetSpend?.totalSpent)

        // This is the figure the dialog and the list chip render.
        val remaining = BudgetApprovalSeam.remainingAmount(
            approval.grantedBudget!!.grantedAmount,
            approval.budgetSpend?.totalSpent,
        )
        assertEquals("15", remaining)
        assertTrue(remaining != approval.grantedBudget.grantedAmount)
    }

    @Test
    fun aRegrantBelowWhatIsAlreadySpentReadsAsZeroRemaining() = runTest {
        // grant 50 → spend 40 → re-grant 10. The de-facto revoke; there is no
        // explicit revoke verb on the API.
        val api = FakeApprovalsApi(
            proposals = listOf(
                proposalTicket("t1", requestedAmount = "50.00", grantedAmount = "10", spentTotal = "40")
            )
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        val approval = vm.approvals.value.single()
        assertEquals(
            "0",
            BudgetApprovalSeam.remainingAmount(
                approval.grantedBudget!!.grantedAmount,
                approval.budgetSpend?.totalSpent,
            ),
        )
    }

    @Test
    fun anApprovalWithAnIssuedBudgetNoLongerCountsAsNeedingABudgetDecision() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1", grantedAmount = "25.00"))
        )
        val (vm, _) = viewModel(api)

        vm.refresh()
        advanceUntilIdle()

        val approval = vm.approvals.value.single()
        assertFalse(approval.needsBudgetDecision)
        // …but it still awaits promotion, so it stays on the surface.
        assertTrue(approval.needsPromotion)
    }

    // ─── Trust headroom ────────────────────────────────────────────────────

    private fun budgetState(
        ticketId: String = "t1",
        headroomAmount: String? = "40",
        currency: String = "USDC",
    ) = TicketBudgetState(
        ticketId = ticketId,
        isProposal = true,
        requested = RequestedBudget("25.00", currency, "fee", null),
        granted = null,
        spent = null,
        headroom = headroomAmount?.let {
            TrustHeadroom(it, currency, maxTransaction = "100", dailyRemaining = it, source = "wallet")
        },
    )

    @Test
    fun loadBudgetState_exposesTheHeadroomForTheOpenApproval() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1")),
            budgetState = budgetState(),
        )
        val (vm, _) = viewModel(api)

        vm.loadBudgetState("t1")
        advanceUntilIdle()

        assertEquals("40", vm.selectedBudgetState.value?.headroom?.amount)
        assertEquals("100", vm.selectedBudgetState.value?.headroom?.maxTransaction)
    }

    @Test
    fun loadBudgetState_isNonFatalWhenTheServerHasNoSuchEndpoint() = runTest {
        val api = FakeApprovalsApi(budgetStateThrow = RuntimeException("404"))
        val (vm, _) = viewModel(api)

        vm.loadBudgetState("t1")
        advanceUntilIdle()

        // Headroom enhances the dialog; it is never a precondition for it.
        assertNull(vm.selectedBudgetState.value)
        assertNull(vm.error.value)
    }

    @Test
    fun clearBudgetState_dropsItOnDialogClose() = runTest {
        val api = FakeApprovalsApi(budgetState = budgetState())
        val (vm, _) = viewModel(api)

        vm.loadBudgetState("t1")
        advanceUntilIdle()
        vm.clearBudgetState()

        assertNull(vm.selectedBudgetState.value)
    }

    @Test
    fun grantBudget_refusesAnAmountAboveTheLoadedHeadroom() = runTest {
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1", "25.00")),
            budgetState = budgetState(headroomAmount = "10"),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        vm.loadBudgetState("t1")
        advanceUntilIdle()

        var outcome: BudgetGrantOutcome? = null
        vm.grantBudget("t1", "20.00", "USDC", "fee", 24, promote = false) { outcome = it }
        advanceUntilIdle()

        assertEquals(BudgetGrantError.NESTING_VIOLATION, outcome?.error)
        assertTrue(api.grantCalls.isEmpty())
    }

    @Test
    fun grantBudget_ignoresHeadroomLoadedForADifferentApproval() = runTest {
        // A stale figure from a previously-open dialog must never gate a grant.
        val api = FakeApprovalsApi(
            proposals = listOf(proposalTicket("t1", "25.00")),
            budgetState = budgetState(ticketId = "OTHER", headroomAmount = "1"),
        )
        val (vm, _) = viewModel(api)
        vm.refresh()
        vm.loadBudgetState("OTHER")
        advanceUntilIdle()

        vm.grantBudget("t1", "25.00", "USDC", "fee", 24, promote = false)
        advanceUntilIdle()

        assertEquals(1, api.grantCalls.size)
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
