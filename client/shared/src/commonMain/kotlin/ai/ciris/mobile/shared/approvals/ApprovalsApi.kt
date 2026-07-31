package ai.ciris.mobile.shared.approvals

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.ResolveDeferralData
import ai.ciris.mobile.shared.api.TicketData
import ai.ciris.mobile.shared.api.WAStatusData
import ai.ciris.mobile.shared.platform.PlatformLogger

/**
 * The narrow API surface the approval screen needs.
 *
 * Extracted as an interface for one reason: [ai.ciris.mobile.shared.viewmodels.WiseAuthorityViewModel]
 * previously took the concrete 12k-line [CIRISApiClient], which made its logic
 * — new-approval detection, the ≤-requested constraint, error and
 * permission-denied handling — untestable. A HITL gate whose behaviour cannot
 * be asserted is not a control.
 */
interface ApprovalsApi {

    /** WA service health + the pending-deferral count. */
    suspend fun fetchWAStatus(): WAStatusData

    /** Pending Wisdom-Based Deferrals. */
    suspend fun fetchDeferrals(): List<DeferralData>

    /**
     * Resolve a deferral.
     * @param resolution must be one of `approve` / `reject` / `modify` —
     *   the server validates against `^(approve|reject|modify)$`. Use
     *   [ApprovalDecision.wireResolution] rather than a literal.
     */
    suspend fun resolveDeferral(deferralId: String, resolution: String, guidance: String): ResolveDeferralData

    /**
     * Tickets the agent proposed and cannot itself start — `status=blocked`
     * carrying `metadata.__proposal__`. Implementations must return an empty
     * list (not throw) when the server has no tickets API, so a deployment
     * without it still shows deferrals.
     */
    suspend fun fetchProposals(): List<TicketData>

    /**
     * Full budget state for one ticket, including remaining trust headroom.
     * Returns null when the server does not expose it — headroom enhances the
     * approval dialog, it is never a precondition for showing it.
     */
    suspend fun fetchTicketBudget(ticketId: String): TicketBudgetState?

    /**
     * Issue a budget envelope against a proposal ticket.
     *
     * A grant above the agent's request is permitted but must have been
     * confirmed by a human first — see [BudgetApprovalSeam.validateGrant]. The
     * over-grant *marking* is not passed here: the server derives it and carries
     * it inside the signed payload, which is the only version of that fact worth
     * having.
     */
    suspend fun grantBudget(
        ticketId: String,
        amount: String,
        currency: String,
        purpose: String,
        expiresInHours: Int,
    ): BudgetGrantOutcome

    /**
     * Move a ticket to a new status. Promotion (`blocked` → `pending`) is what
     * actually starts the work; granting a budget does not.
     */
    suspend fun updateTicketStatus(ticketId: String, status: String, notes: String?): Boolean
}

/**
 * Production [ApprovalsApi] — a thin adapter over [CIRISApiClient].
 *
 * Deliberately contains no policy: every decision (what counts as a proposal,
 * what the ≤ constraint is, how errors map) lives in [BudgetApprovalSeam] or
 * the ViewModel, so this class stays a mechanical translation.
 */
class CIRISApprovalsApi(private val client: CIRISApiClient) : ApprovalsApi {

    private companion object {
        const val TAG = "CIRISApprovalsApi"
    }

    override suspend fun fetchWAStatus(): WAStatusData = client.getWAStatus()

    override suspend fun fetchDeferrals(): List<DeferralData> = client.getDeferrals()

    override suspend fun resolveDeferral(
        deferralId: String,
        resolution: String,
        guidance: String,
    ): ResolveDeferralData = client.resolveDeferral(deferralId, resolution, guidance)

    override suspend fun fetchProposals(): List<TicketData> = try {
        client.listTickets(statusFilter = BudgetApprovalSeam.PROPOSAL_STATUS, limit = 100)
            .filter { BudgetApprovalSeam.isProposal(it.status, it.metadata) }
    } catch (e: Exception) {
        // A deployment without the tickets API must still show deferrals.
        PlatformLogger.d(TAG, "[fetchProposals] tickets unavailable (${e.message}) — treating as none")
        emptyList()
    }

    override suspend fun fetchTicketBudget(ticketId: String): TicketBudgetState? =
        client.getTicketBudget(ticketId)

    override suspend fun grantBudget(
        ticketId: String,
        amount: String,
        currency: String,
        purpose: String,
        expiresInHours: Int,
    ): BudgetGrantOutcome =
        client.grantTicketBudget(ticketId, amount, currency, purpose, expiresInHours)

    override suspend fun updateTicketStatus(ticketId: String, status: String, notes: String?): Boolean =
        client.updateTicketStatus(ticketId, status, notes)
}

/**
 * Project a deferral onto the unified [PendingApproval].
 *
 * Deferrals never carry a budget: budget requests ride the ticket path (see
 * [BudgetApprovalSeam]). The `context` map is passed through for display only.
 */
fun DeferralData.toPendingApproval(): PendingApproval = PendingApproval(
    id = deferralId,
    kind = ApprovalKind.DEFERRAL,
    title = question ?: reason,
    detail = reason,
    createdAt = createdAt,
    priority = priority,
    requestedBy = deferredBy,
    status = status,
    context = context ?: emptyMap(),
)

/**
 * Project a proposal ticket onto the unified [PendingApproval].
 *
 * Returns null when the ticket is not an unapproved proposal, so callers can
 * `mapNotNull` a raw ticket list without re-implementing the predicate.
 */
fun TicketData.toPendingApprovalOrNull(): PendingApproval? {
    if (!BudgetApprovalSeam.isProposal(status, metadata)) return null
    val proposal = BudgetApprovalSeam.parseProposal(metadata)
    val requested = BudgetApprovalSeam.parseRequestedBudget(metadata)
    return PendingApproval(
        id = ticketId,
        kind = ApprovalKind.TICKET_PROPOSAL,
        title = proposal?.goalDescription?.takeIf { it.isNotBlank() }
            ?: notes?.takeIf { it.isNotBlank() }
            ?: "$displayType proposal",
        detail = notes.orEmpty(),
        createdAt = submittedAt,
        priority = when {
            priority >= 8 -> "high"
            priority >= 5 -> "medium"
            else -> "normal"
        },
        requestedBy = proposal?.proposedBy ?: "agent",
        status = status,
        requestedBudget = requested,
        grantedBudget = BudgetApprovalSeam.parseGrantedBudget(metadata),
        budgetSpend = BudgetApprovalSeam.parseBudgetSpend(metadata),
        proposal = proposal,
    )
}
