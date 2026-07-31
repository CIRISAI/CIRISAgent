package ai.ciris.mobile.shared.approvals

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * The human-in-the-loop (HITL) approval surface — client-side model.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * CIRIS is moving to a fail-closed authorization model (#938): consequential
 * actions — spend in particular (#939) — require an *explicit human approval*.
 * A fail-closed design whose approval path has no UI is not "secure by
 * default"; it is a silent denial-of-service on the agent, and the operator
 * never learns why the agent stopped. These types are the client's half of
 * that path.
 *
 * There are TWO independent sources of pending human approvals today, and the
 * UI folds them into one list so an operator has a single place to look:
 *
 *   [ApprovalKind.DEFERRAL] — Wisdom-Based Deferral. The agent asked a human a
 *      question mid-reasoning. Wire: `GET /v1/wa/deferrals`,
 *      `POST /v1/wa/deferrals/{id}/resolve`.
 *
 *   [ApprovalKind.TICKET_PROPOSAL] — a ticket the agent proposed but may not
 *      itself start. Wire: `GET /v1/tickets?status_filter=blocked`, filtered to
 *      those carrying `metadata.__proposal__`. Optionally carries a
 *      **requested budget** (`metadata.__requested_budget__`), which is the
 *      #938/#939 case: the human's approval is the *issuance event* that grants
 *      a budget envelope nested inside the deployment's trust envelope.
 *
 * All wire-format knowledge lives in [BudgetApprovalSeam] — nothing in this
 * file knows a JSON key name.
 */

/** Which pipeline produced this approval request. */
enum class ApprovalKind {
    /** Wisdom-Based Deferral — the agent asked a human a question. */
    DEFERRAL,

    /** A ticket the agent proposed and cannot itself start. */
    TICKET_PROPOSAL,
}

/**
 * A budget the agent has **asked for**. Never carries granted fields.
 *
 * The backend models request and grant as two Pydantic models with
 * `extra="forbid"` and deliberately **disjoint** field names, so a request can
 * never be misread as a grant. That disjointness is load-bearing and is
 * mirrored here as two distinct Kotlin types rather than one type with a
 * nullable "granted" flag — a nullable flag is exactly the shape that lets a
 * request be rendered as an authorization by a single missing null-check.
 */
data class RequestedBudget(
    /** Decimal-as-string, exactly as the agent asked. Never parsed to Double. */
    val requestedAmount: String,
    val requestedCurrency: String,
    /** What the money is for. */
    val purpose: String,
    /** Why the agent believes it is warranted. */
    val justification: String?,
)

/**
 * A budget a human has **issued**. Never carries requested fields.
 *
 * Present on a ticket once `POST /v1/tickets/{id}/budget/grant` has succeeded.
 * Its existence is the authorization; absence of a grant is a denial, not
 * "unbounded".
 */
data class GrantedBudget(
    val grantedAmount: String,
    val grantedCurrency: String,
    val purpose: String,
    /** ISO-8601 instant after which the envelope is void. */
    val expiresAt: String?,
    val grantedByWaId: String?,
    val grantedByUserId: String?,
    val grantedAt: String?,
    /**
     * Whether the grant carries a verifiable Ed25519 signature. False in
     * deployments with no WA signing key — surfaced to the operator rather
     * than hidden, because an unsigned grant is a weaker artifact and the
     * person issuing it should know that.
     */
    val signed: Boolean,
)

/** Burn-down against an issued grant. */
data class BudgetSpend(
    val totalSpent: String,
    val currency: String,
    val recordCount: Int,
)

/** Provenance of a ticket the agent proposed. */
data class TicketProposal(
    val originTaskId: String?,
    val originThoughtId: String?,
    val proposedAt: String?,
    val proposedBy: String?,
    val goalDescription: String?,
)

/**
 * One pending approval, normalized across both sources.
 *
 * @property id stable identity used as the notification dedupe key. Deferral
 *   id or ticket id; the [kind] prefix keeps the two id spaces from colliding.
 */
data class PendingApproval(
    val id: String,
    val kind: ApprovalKind,
    /** One-line "what is being asked". */
    val title: String,
    /** Longer "why" — the deferral reason or the proposal's goal description. */
    val detail: String,
    val createdAt: String,
    /** "low" | "normal" | "medium" | "high" | "critical" — free-form from the server. */
    val priority: String,
    /** Deferral: the agent that deferred. Proposal: the proposer. */
    val requestedBy: String,
    /** Raw status string from the server. */
    val status: String,
    /** Deferral context map, or a flattened view of ticket metadata. Display-only. */
    val context: Map<String, String> = emptyMap(),
    /** Present only when the agent asked for money. */
    val requestedBudget: RequestedBudget? = null,
    /** Present only once a human has issued a budget. */
    val grantedBudget: GrantedBudget? = null,
    /** Present only when spend has occurred against a grant. */
    val budgetSpend: BudgetSpend? = null,
    val proposal: TicketProposal? = null,
) {
    /** True when this approval is holding the agent up on a money decision. */
    val needsBudgetDecision: Boolean
        get() = requestedBudget != null && grantedBudget == null

    /** True when money is granted but the work has not been started by a human. */
    val needsPromotion: Boolean
        get() = kind == ApprovalKind.TICKET_PROPOSAL && grantedBudget != null

    val isHighPriority: Boolean
        get() = priority.lowercase() in setOf("high", "critical", "urgent")
}

/**
 * The decision a human renders on an approval.
 *
 * [wireResolution] is the value the **deferral** resolve endpoint accepts. That
 * endpoint validates `resolution` against `^(approve|reject|modify)$` server
 * side, so there is no `"defer"` wire value — a UI "Not now" maps to `modify`,
 * which returns the question to the agent with guidance instead of granting.
 * Sending the literal string "defer" would 422.
 */
enum class ApprovalDecision(val wireResolution: String) {
    APPROVE("approve"),
    REJECT("reject"),

    /** "Not now" — hand it back with guidance, grant nothing. */
    DEFER("modify"),
}

/**
 * Whether this deployment's server exposes budget *issuance*.
 *
 * There is no probe endpoint, so this is discovered lazily: it starts
 * [UNKNOWN], becomes [UNAVAILABLE] the first time the grant endpoint answers
 * 404/405 (an older server that has requests but not issuance), and [AVAILABLE]
 * on the first successful grant. The UI must degrade to a clear, non-blocking
 * explanation on [UNAVAILABLE] — never a silent failure, because a silent
 * failure here reads to the operator exactly like the agent being stuck.
 */
enum class BudgetCapability {
    UNKNOWN,
    AVAILABLE,
    UNAVAILABLE,
}

/** Why a budget grant was refused — before or after the request left the device. */
enum class BudgetGrantError {
    /** Amount is not a well-formed positive decimal. */
    INVALID_AMOUNT,

    /** Amount exceeds what the agent asked for. Enforced client-side AND server-side. */
    EXCEEDS_REQUESTED,

    /** Expiry outside 1..8760 hours. */
    INVALID_EXPIRY,

    /** Purpose was blank. */
    MISSING_PURPOSE,

    /** 403 — the signed-in user is not an AUTHORITY. */
    FORBIDDEN_ROLE,

    /** 404 on the ticket itself. */
    TICKET_NOT_FOUND,

    /**
     * 422 — the grant would exceed the deployment's trust-envelope ceiling.
     * The nested envelope may never be wider than the envelope it nests in.
     */
    NESTING_VIOLATION,

    /** 404/405 on the endpoint — this server does not expose budget issuance. */
    ENDPOINT_UNAVAILABLE,

    /** Anything else (network, 5xx, malformed body). */
    UNKNOWN,
}

/** Result of validating or submitting a grant. */
data class BudgetGrantOutcome(
    val ok: Boolean,
    val error: BudgetGrantError? = null,
    /** Server-supplied explanation, when there is one worth showing. */
    val message: String? = null,
    val granted: GrantedBudget? = null,
)
