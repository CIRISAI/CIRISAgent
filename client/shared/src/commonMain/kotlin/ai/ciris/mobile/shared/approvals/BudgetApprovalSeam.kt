package ai.ciris.mobile.shared.approvals

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * THE SEAM.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Every piece of wire-format knowledge about the budget-envelope contract
 * (#938 / #939) lives in this object and nowhere else: the reserved metadata
 * key names, the grant endpoint path, the request body shape, the response
 * shape, and the HTTP status → error mapping. If the backend contract moves,
 * this is the one file that changes.
 *
 * ── Contract, as confirmed with the backend author (branch
 *    `feat/938-create-ticket`, `FSD/BUDGET_ENVELOPE.md`) ────────────────────
 *
 * **The approval object is a TICKET, not a deferral.** Nothing budget-related
 * rides `POST /v1/wa/deferrals/{id}/resolve` — that endpoint completes the
 * originating task and spawns a new one, so it cannot carry a grant that must
 * outlive a single task; and its `signature` field is a formatted string that
 * is never verified, which makes it unfit to carry money authorization.
 *
 * **Request.** The agent calls the `create_ticket` tool, producing a ticket
 * with `status == "blocked"` plus reserved metadata keys. The persist
 * ticket-status enum is closed (`pending|assigned|in_progress|blocked|
 * deferred|completed|cancelled|failed`) — there is no `proposed` variant, so
 * proposals ride `blocked`. A ticket is an unapproved proposal iff
 * `status == "blocked"` AND [KEY_PROPOSAL] is present. [KEY_REQUESTED_BUDGET]
 * is optional: a proposal may ask for no money at all.
 *
 * **Issuance.** `POST /v1/tickets/{ticket_id}/budget/grant`, requiring the
 * AUTHORITY role (level 3 — ADMIN at level 2 is NOT sufficient).
 *
 * **Promotion is a separate decision.** Granting a budget does not start the
 * work; the ticket stays `blocked` until a human also PATCHes it to `pending`.
 * The UI keeps those two actions visibly distinct because approving money and
 * starting work are genuinely different decisions.
 *
 * **The agent cannot approve its own proposal.** The agent-side `update_ticket`
 * tool refuses to move a ticket out of proposal state (except to `cancelled`,
 * i.e. withdrawing it) and refuses to write any of the four reserved metadata
 * keys. The human really is the only issuer.
 *
 * ── What is NOT available ───────────────────────────────────────────────────
 *
 * **Trust-envelope headroom is not exposed by any endpoint today.** Internally
 * it resolves as `min(spending_limits.max_transaction, daily_remaining)`. The
 * nearest existing surface, `GET /v1/wallet/status`, is x402-only and reports a
 * *different* number than the one the gate enforces. So [parseHeadroom] reads a
 * field that no server currently sends, and the UI renders the headroom row
 * only when it is non-null. Showing a number that disagrees with the gate would
 * be worse than showing nothing.
 */
object BudgetApprovalSeam {

    // ─── Reserved ticket-metadata keys (backend writes, agent may not) ──────

    /** Marks a ticket as an agent proposal awaiting a human. */
    const val KEY_PROPOSAL = "__proposal__"

    /** What the agent asked for. Disjoint from [KEY_GRANTED_BUDGET] by design. */
    const val KEY_REQUESTED_BUDGET = "__requested_budget__"

    /** What a human issued. Disjoint from [KEY_REQUESTED_BUDGET] by design. */
    const val KEY_GRANTED_BUDGET = "__granted_budget__"

    /** Burn-down against the grant. */
    const val KEY_BUDGET_SPENT = "__budget_spent__"

    /** The ticket status that carries an unapproved proposal. */
    const val PROPOSAL_STATUS = "blocked"

    /** The status a human PATCHes a ticket to in order to actually start the work. */
    const val PROMOTED_STATUS = "pending"

    /** The status a human PATCHes a ticket to in order to refuse it. */
    const val REJECTED_STATUS = "cancelled"

    // ─── Grant request/response field names ─────────────────────────────────

    private const val F_AMOUNT = "amount"
    private const val F_CURRENCY = "currency"
    private const val F_PURPOSE = "purpose"
    private const val F_EXPIRES_IN_HOURS = "expires_in_hours"
    private const val F_WA_ID = "wa_id"

    // ─── Bounds the server also enforces; duplicated here so the UI can
    //     refuse locally instead of round-tripping a guaranteed 422. ─────────

    const val MIN_EXPIRY_HOURS = 1
    const val MAX_EXPIRY_HOURS = 8760 // one year
    const val DEFAULT_EXPIRY_HOURS = 24

    /** Fixed-point scale used for all amount comparisons. USDC needs 6. */
    private const val AMOUNT_SCALE = 8
    private const val SCALE_FACTOR = 100_000_000L // 10^8

    /** Path of the issuance endpoint for [ticketId]. */
    fun grantPath(ticketId: String): String = "/v1/tickets/$ticketId/budget/grant"

    // ═══════════════════════════════════════════════════════════════════════
    // Parsing — ticket metadata → typed model
    // ═══════════════════════════════════════════════════════════════════════

    /** True iff this ticket is an agent proposal awaiting a human decision. */
    fun isProposal(status: String, metadata: Map<String, JsonElement>): Boolean =
        status.equals(PROPOSAL_STATUS, ignoreCase = true) && metadata.containsKey(KEY_PROPOSAL)

    fun parseProposal(metadata: Map<String, JsonElement>): TicketProposal? {
        val obj = metadata[KEY_PROPOSAL]?.asObjectOrNull() ?: return null
        return TicketProposal(
            originTaskId = obj.str("origin_task_id"),
            originThoughtId = obj.str("origin_thought_id"),
            proposedAt = obj.str("proposed_at"),
            proposedBy = obj.str("proposed_by"),
            goalDescription = obj.str("goal_description"),
        )
    }

    /**
     * Parse the agent's ask. Returns null when the proposal asks for no money —
     * which is a normal, common case, not an error.
     */
    fun parseRequestedBudget(metadata: Map<String, JsonElement>): RequestedBudget? {
        val obj = metadata[KEY_REQUESTED_BUDGET]?.asObjectOrNull() ?: return null
        val amount = obj.str("requested_amount") ?: return null
        val currency = obj.str("requested_currency") ?: return null
        return RequestedBudget(
            requestedAmount = amount,
            requestedCurrency = currency,
            purpose = obj.str("purpose").orEmpty(),
            justification = obj.str("justification"),
        )
    }

    /** Parse a grant already issued against this ticket. */
    fun parseGrantedBudget(metadata: Map<String, JsonElement>): GrantedBudget? {
        val obj = metadata[KEY_GRANTED_BUDGET]?.asObjectOrNull() ?: return null
        return parseGrantObject(obj)
    }

    /** Parse the burn-down ledger, when spend has occurred. */
    fun parseBudgetSpend(metadata: Map<String, JsonElement>): BudgetSpend? {
        val obj = metadata[KEY_BUDGET_SPENT]?.asObjectOrNull() ?: return null
        val total = obj.str("total_spent") ?: return null
        val records = runCatching { obj["records"]?.jsonArray?.size }.getOrNull() ?: 0
        return BudgetSpend(
            totalSpent = total,
            currency = obj.str("currency").orEmpty(),
            recordCount = records,
        )
    }

    /**
     * Remaining trust-envelope headroom, if the server ever reports it.
     *
     * No server sends this today (see the class doc). Kept as the single place
     * that would need to change when it lands, so the UI wiring is already
     * correct and simply renders nothing until then.
     */
    fun parseHeadroom(metadata: Map<String, JsonElement>): String? =
        metadata["__trust_envelope_remaining__"]?.asObjectOrNull()?.str("amount")

    // ═══════════════════════════════════════════════════════════════════════
    // Issuance — building the request, reading the response
    // ═══════════════════════════════════════════════════════════════════════

    /** Body for `POST /v1/tickets/{id}/budget/grant`. */
    fun buildGrantBody(
        amount: String,
        currency: String,
        purpose: String,
        expiresInHours: Int,
        waId: String? = null,
    ): JsonObject = buildJsonObject {
        put(F_AMOUNT, amount)
        put(F_CURRENCY, currency)
        put(F_PURPOSE, purpose)
        put(F_EXPIRES_IN_HOURS, expiresInHours)
        if (waId != null) put(F_WA_ID, waId)
    }

    /**
     * Read the `data` object of the standard response envelope into a
     * [GrantedBudget]. Returns null when the body is not the shape we expect —
     * callers treat that as [BudgetGrantError.UNKNOWN] rather than pretending a
     * grant succeeded.
     */
    fun parseGrantResponse(data: JsonObject?): GrantedBudget? {
        if (data == null) return null
        return parseGrantObject(data)
    }

    private fun parseGrantObject(obj: JsonObject): GrantedBudget? {
        val amount = obj.str("granted_amount") ?: return null
        return GrantedBudget(
            grantedAmount = amount,
            grantedCurrency = obj.str("granted_currency").orEmpty(),
            purpose = obj.str("purpose").orEmpty(),
            expiresAt = obj.str("expires_at"),
            grantedByWaId = obj.str("granted_by_wa_id"),
            grantedByUserId = obj.str("granted_by_user_id"),
            grantedAt = obj.str("granted_at"),
            signed = runCatching { obj["signed"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: false,
        )
    }

    /**
     * Map an HTTP status from the grant endpoint onto a typed error.
     *
     * 404 is genuinely ambiguous — it is either "no such ticket" or "no such
     * endpoint" — and the two need different UI. We disambiguate on the body:
     * a FastAPI route that exists answers 404 with a `detail` mentioning the
     * ticket; a route that does not exist answers with the bare
     * `{"detail":"Not Found"}`. Getting this wrong in the safe direction means
     * telling the operator the feature is unavailable when the ticket merely
     * vanished, which is recoverable; the reverse would leave them retrying a
     * button that can never work.
     */
    fun classifyHttpError(status: Int, body: String?): BudgetGrantError = when (status) {
        403 -> BudgetGrantError.FORBIDDEN_ROLE
        422 -> BudgetGrantError.NESTING_VIOLATION
        405 -> BudgetGrantError.ENDPOINT_UNAVAILABLE
        404 -> if (body != null && body.contains("ticket", ignoreCase = true)) {
            BudgetGrantError.TICKET_NOT_FOUND
        } else {
            BudgetGrantError.ENDPOINT_UNAVAILABLE
        }
        else -> BudgetGrantError.UNKNOWN
    }

    // ═══════════════════════════════════════════════════════════════════════
    // The ≤-requested constraint
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Validate a proposed grant against the agent's ask, **before** it leaves
     * the device.
     *
     * The load-bearing rule: a human may approve **at or below** the requested
     * amount, never above. The server enforces this too; the client enforces it
     * as well so the constraint is visible at the point of decision rather than
     * arriving as a rejected round-trip. Client-side enforcement is a usability
     * property, not a security one — the server remains the authority.
     *
     * @param headroom optional trust-envelope ceiling; when present, the grant
     *   must also fit inside it (a nested envelope may never be wider than the
     *   one it nests in).
     */
    fun validateGrant(
        requested: RequestedBudget,
        amount: String,
        expiresInHours: Int,
        purpose: String,
        headroom: String? = null,
    ): BudgetGrantOutcome {
        val requestedScaled = parseAmount(requested.requestedAmount)
            ?: return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Requested amount is not a valid number")
        val amountScaled = parseAmount(amount)
            ?: return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Enter an amount like 25.00")

        if (amountScaled <= 0L) {
            return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Amount must be greater than zero")
        }
        if (amountScaled > requestedScaled) {
            return BudgetGrantOutcome(
                false,
                BudgetGrantError.EXCEEDS_REQUESTED,
                "You can approve at most ${requested.requestedAmount} ${requested.requestedCurrency}",
            )
        }
        val headroomScaled = headroom?.let { parseAmount(it) }
        if (headroomScaled != null && amountScaled > headroomScaled) {
            return BudgetGrantOutcome(
                false,
                BudgetGrantError.NESTING_VIOLATION,
                "Only $headroom ${requested.requestedCurrency} remains in this deployment's envelope",
            )
        }
        if (expiresInHours < MIN_EXPIRY_HOURS || expiresInHours > MAX_EXPIRY_HOURS) {
            return BudgetGrantOutcome(
                false,
                BudgetGrantError.INVALID_EXPIRY,
                "Expiry must be between $MIN_EXPIRY_HOURS and $MAX_EXPIRY_HOURS hours",
            )
        }
        if (purpose.isBlank()) {
            return BudgetGrantOutcome(false, BudgetGrantError.MISSING_PURPOSE, "Say what the money is for")
        }
        return BudgetGrantOutcome(true)
    }

    /**
     * Compare two decimal-as-string amounts.
     * @return negative / zero / positive like [Comparable], or null when either
     *   side is unparseable (callers must not silently treat that as equal).
     */
    fun compareAmounts(a: String, b: String): Int? {
        val left = parseAmount(a) ?: return null
        val right = parseAmount(b) ?: return null
        return left.compareTo(right)
    }

    /**
     * Parse a decimal string to fixed-point at [AMOUNT_SCALE] digits.
     *
     * Deliberately NOT `toDouble()`: money in a binary float is how you approve
     * 25.000000000000004. Kotlin common has no BigDecimal, so this is exact
     * integer arithmetic over the scaled value.
     *
     * Returns null for anything that is not a plain non-negative decimal —
     * signs, exponents, thousands separators and currency symbols are all
     * rejected rather than coerced.
     */
    fun parseAmount(raw: String): Long? {
        val text = raw.trim()
        if (text.isEmpty()) return null
        if (!text.all { it.isDigit() || it == '.' }) return null
        if (text.count { it == '.' } > 1) return null

        val parts = text.split('.')
        val intPart = parts[0].ifEmpty { "0" }
        val fracPart = parts.getOrNull(1).orEmpty()
        if (fracPart.length > AMOUNT_SCALE) return null
        if (intPart.length > 12) return null // guards the Long multiply below

        val intValue = intPart.toLongOrNull() ?: return null
        val fracPadded = fracPart.padEnd(AMOUNT_SCALE, '0')
        val fracValue = if (fracPadded.isEmpty()) 0L else fracPadded.toLongOrNull() ?: return null
        return intValue * SCALE_FACTOR + fracValue
    }

    /** Render a fixed-point amount back to a trimmed decimal string. */
    fun formatAmount(scaled: Long): String {
        val whole = scaled / SCALE_FACTOR
        val frac = (scaled % SCALE_FACTOR).toString().padStart(AMOUNT_SCALE, '0').trimEnd('0')
        return if (frac.isEmpty()) whole.toString() else "$whole.$frac"
    }

    // ─── Small JSON helpers (kept private; nothing else should reach in) ─────

    private fun JsonElement.asObjectOrNull(): JsonObject? = runCatching { jsonObject }.getOrNull()

    private fun JsonObject.str(key: String): String? =
        runCatching { (this[key] as? JsonPrimitive)?.contentOrNull }.getOrNull()
}
