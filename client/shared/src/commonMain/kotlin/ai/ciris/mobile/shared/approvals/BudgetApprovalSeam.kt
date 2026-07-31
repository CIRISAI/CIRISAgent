package ai.ciris.mobile.shared.approvals

import kotlinx.serialization.json.Json
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
import kotlin.math.roundToInt

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
 * **Budget state, in one read.** `GET /v1/tickets/{ticket_id}/budget` (OBSERVER)
 * returns request, grant, spend ledger and remaining trust headroom together.
 * The headroom is resolved through the wallet tool service's own
 * `_resolve_trust_envelope` — the same code path the spend gate runs — so the
 * number shown to an operator cannot drift from the number enforced when money
 * actually moves. It is null when no wallet adapter is loaded, and the UI then
 * renders nothing rather than inventing a figure.
 *
 * ── One asymmetry worth knowing ─────────────────────────────────────────────
 *
 * The server enforces `granted ≤ trust ceiling`. It does **not** enforce
 * `granted ≤ requested` — an AUTHORITY user is permitted to grant more than the
 * agent asked for, e.g. when the agent lowballed. [validateGrant] refuses that
 * anyway, which makes this client deliberately **stricter than the server**.
 * That is a product policy choice, not a security boundary; see the note on
 * [validateGrant].
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

    // ─── Audit marking of an over-grant — READ ONLY ─────────────────────────
    //
    // The client does NOT send these. The server derives both in `issue_grant`
    // by comparing the granted amount against the ticket's `__requested_budget__`
    // at issuance, and they sit inside the canonical signed payload so the
    // marking cannot be stripped or forged without invalidating the signature.
    //
    // That is strictly better than the client-asserted flag originally proposed
    // here, and for the same reason the over-grant ruling itself turned on: a
    // client-asserted audit flag is worthless precisely against the person it
    // needs to work against. An operator motivated to make an over-grant look
    // ordinary is the one calling the endpoint directly, and they would simply
    // omit the flag — it would be present exactly when it was not needed.
    //
    // Note `GrantBudgetRequest` now declares `extra="forbid"`: an unknown field
    // is a loud 422 rather than a silent default. [buildGrantBody] must send
    // only fields the server declares.

    /** True when the granted amount exceeded what the agent asked for. */
    private const val F_EXCEEDS_REQUEST = "exceeds_request"

    /**
     * The requested amount as it stood **at grant time** — the snapshot, so the
     * ratio stays reconstructable from the record alone even if the ticket's
     * requested budget later differs. Null when the ticket requested nothing at
     * all (a human-opened ticket, or a proposal asking for work but not money),
     * in which case there is no ratio to name and it is not an over-grant.
     */
    private const val F_REQUESTED_AT_GRANT = "requested_amount_at_grant"

    // ─── Bounds the server also enforces; duplicated here so the UI can
    //     refuse locally instead of round-tripping a guaranteed 422. ─────────

    const val MIN_EXPIRY_HOURS = 1
    const val MAX_EXPIRY_HOURS = 8760 // one year
    const val DEFAULT_EXPIRY_HOURS = 24

    /** Fixed-point scale used for all amount comparisons. USDC needs 6. */
    private const val AMOUNT_SCALE = 8
    private const val SCALE_FACTOR = 100_000_000L // 10^8

    /**
     * Machine-readable code the server returns when the *ticket* is missing, as
     * opposed to the *endpoint* being missing. Mirrors
     * `TICKET_NOT_FOUND_ERROR_CODE` in `routes/tickets.py`.
     */
    const val ERROR_CODE_TICKET_NOT_FOUND = "TICKET_NOT_FOUND"

    /** Path of the issuance endpoint for [ticketId]. */
    fun grantPath(ticketId: String): String = "/v1/tickets/$ticketId/budget/grant"

    /** Path of the read-only budget-state endpoint for [ticketId]. */
    fun budgetPath(ticketId: String): String = "/v1/tickets/$ticketId/budget"

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
    fun parseRequestedBudget(metadata: Map<String, JsonElement>): RequestedBudget? =
        metadata[KEY_REQUESTED_BUDGET]?.asObjectOrNull()?.let { parseRequestedObject(it) }

    private fun parseRequestedObject(obj: JsonObject): RequestedBudget? {
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
    fun parseBudgetSpend(metadata: Map<String, JsonElement>): BudgetSpend? =
        metadata[KEY_BUDGET_SPENT]?.asObjectOrNull()?.let { parseSpendObject(it) }

    private fun parseSpendObject(obj: JsonObject): BudgetSpend? {
        val total = obj.str("total_spent") ?: return null
        val records = runCatching { obj["records"]?.jsonArray?.size }.getOrNull() ?: 0
        return BudgetSpend(
            totalSpent = total,
            currency = obj.str("currency").orEmpty(),
            recordCount = records,
        )
    }

    /**
     * Parse the `data` object of `GET /v1/tickets/{id}/budget`.
     *
     * Returns null when the body is not the shape we expect — callers then fall
     * back to whatever the ticket metadata already gave them rather than
     * blanking a dialog the operator is reading.
     */
    fun parseTicketBudgetState(data: JsonObject?): TicketBudgetState? {
        if (data == null) return null
        val ticketId = data.str("ticket_id") ?: return null
        return TicketBudgetState(
            ticketId = ticketId,
            isProposal = runCatching { data["is_proposal"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: false,
            requested = data["requested_budget"]?.asObjectOrNull()?.let { parseRequestedObject(it) },
            granted = data["granted_budget"]?.asObjectOrNull()?.let { parseGrantObject(it) },
            spent = data["spent"]?.asObjectOrNull()?.let { parseSpendObject(it) },
            headroom = data["trust_headroom"]?.asObjectOrNull()?.let { parseHeadroomObject(it) },
        )
    }

    /**
     * Remaining trust-envelope headroom.
     *
     * `amount` is `min(max_transaction, daily_remaining)` and is **the number
     * the spend gate applies**, not a re-derivation — both bounds are carried so
     * the UI can explain which one is binding.
     */
    private fun parseHeadroomObject(obj: JsonObject): TrustHeadroom? {
        val amount = obj.str("amount") ?: return null
        return TrustHeadroom(
            amount = amount,
            currency = obj.str("currency").orEmpty(),
            maxTransaction = obj.str("max_transaction").orEmpty(),
            dailyRemaining = obj.str("daily_remaining").orEmpty(),
            source = obj.str("source").orEmpty(),
        )
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Issuance — building the request, reading the response
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Body for `POST /v1/tickets/{id}/budget/grant`.
     *
     * Sends **only** fields the server declares — `GrantBudgetRequest` uses
     * `extra="forbid"`, so an unknown field is a 422 rather than a silent
     * default. In particular the over-grant audit marking is *not* sent: the
     * server derives it (see [F_EXCEEDS_REQUEST]).
     */
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
            // Server-derived, inside the signed payload. Absent on servers
            // predating the marking, which reads as "not an over-grant" — the
            // same as an ordinary grant, which is the correct default.
            exceedsRequest = runCatching {
                obj[F_EXCEEDS_REQUEST]?.jsonPrimitive?.booleanOrNull
            }.getOrNull() ?: false,
            requestedAmountAtGrant = obj.str(F_REQUESTED_AT_GRANT),
        )
    }

    /**
     * Map an HTTP status from the budget endpoints onto a typed error.
     *
     * 404 is genuinely ambiguous — "no such ticket" and "no such endpoint" need
     * different UI, and only one of them means the feature is missing. The
     * server disambiguates for us with a structured detail:
     *
     * ```json
     * {"detail": {"error_code": "TICKET_NOT_FOUND", "message": "Ticket X not found — …"}}
     * ```
     *
     * We pin on [ERROR_CODE_TICKET_NOT_FOUND], never on prose. The substring
     * check is retained only as a fallback for a server that predates the
     * structured detail; a bare `{"detail": "Not Found"}` carries no
     * `error_code` and correctly reads as the endpoint being absent, which is
     * what keeps the capability check working against older servers.
     */
    fun classifyHttpError(status: Int, body: String?): BudgetGrantError = when (status) {
        403 -> BudgetGrantError.FORBIDDEN_ROLE
        422 -> BudgetGrantError.NESTING_VIOLATION
        405 -> BudgetGrantError.ENDPOINT_UNAVAILABLE
        404 -> classify404(body)
        else -> BudgetGrantError.UNKNOWN
    }

    private fun classify404(body: String?): BudgetGrantError {
        if (body.isNullOrBlank()) return BudgetGrantError.ENDPOINT_UNAVAILABLE
        val detail = runCatching {
            Json.parseToJsonElement(body).jsonObject["detail"]
        }.getOrNull()

        // Contract path: structured detail carrying a machine-readable code.
        detail?.asObjectOrNull()?.str("error_code")?.let { code ->
            return if (code == ERROR_CODE_TICKET_NOT_FOUND) {
                BudgetGrantError.TICKET_NOT_FOUND
            } else {
                BudgetGrantError.UNKNOWN
            }
        }

        // Fallback for servers predating the structured detail. Deliberately
        // last: prose is not a contract.
        return if (body.contains("ticket", ignoreCase = true)) {
            BudgetGrantError.TICKET_NOT_FOUND
        } else {
            BudgetGrantError.ENDPOINT_UNAVAILABLE
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // The ≤-requested constraint
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Validate a proposed grant **before** it leaves the device.
     *
     * Two rules are checked, and they have very different standing:
     *
     * **`granted ≤ trust ceiling` is the real bound, and the server owns it.**
     * Checked here only so the operator learns at the point of decision rather
     * than through a rejected round-trip. A modified client changes nothing: the
     * ceiling is enforced at issuance and again at every spend. **It is not
     * overridable by [overGrantConfirmed]** — confirming that you meant to
     * exceed the agent's request says nothing about the deployment's envelope,
     * and this check deliberately runs first so it wins.
     *
     * **`granted > requested` is permitted, with friction.** The agent's request
     * is *information for the human, not a constraint on them* — the agent may
     * simply have asked for too little, and an AUTHORITY user is the one with
     * standing to correct that. The server has always allowed it; a UI-only
     * refusal would just teach operators to reach for `curl`, moving the grant
     * outside every rendering and confirmation this dialog provides. So it is
     * allowed, but never *silently*: until [overGrantConfirmed] is true this
     * returns [BudgetGrantError.OVER_GRANT_UNCONFIRMED] with [BudgetGrantOutcome.overGrant]
     * populated so the caller can render the ratio. Fail-closed by construction —
     * a caller that never passes `overGrantConfirmed = true` cannot submit an
     * over-grant.
     *
     * @param headroom remaining trust envelope, when the server reports it.
     *   Ignored when its currency differs from the requested currency — a USD
     *   ceiling says nothing about a USDC request, and comparing them would
     *   block a legitimate grant on a meaningless mismatch.
     * @param overGrantConfirmed the human has explicitly acknowledged a grant
     *   above the request, having been shown by how much.
     */
    fun validateGrant(
        requested: RequestedBudget,
        amount: String,
        expiresInHours: Int,
        purpose: String,
        headroom: TrustHeadroom? = null,
        overGrantConfirmed: Boolean = false,
    ): BudgetGrantOutcome {
        val requestedScaled = parseAmount(requested.requestedAmount)
            ?: return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Requested amount is not a valid number")
        val amountScaled = parseAmount(amount)
            ?: return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Enter an amount like 25.00")

        if (amountScaled <= 0L) {
            return BudgetGrantOutcome(false, BudgetGrantError.INVALID_AMOUNT, "Amount must be greater than zero")
        }

        // The real bound, first, so no confirmation can talk past it.
        // Only compare against headroom denominated in the same currency.
        val comparableHeadroom = headroom?.takeIf {
            it.currency.isBlank() || it.currency.equals(requested.requestedCurrency, ignoreCase = true)
        }
        val headroomScaled = comparableHeadroom?.let { parseAmount(it.amount) }
        if (headroomScaled != null && amountScaled > headroomScaled) {
            return BudgetGrantOutcome(
                false,
                BudgetGrantError.NESTING_VIOLATION,
                "Only ${comparableHeadroom.amount} ${requested.requestedCurrency} remains in " +
                    "this deployment's envelope",
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

        // Permitted, but only deliberately.
        val overGrant = describeOverGrant(requested, amount, requestedScaled, amountScaled)
        if (overGrant != null && !overGrantConfirmed) {
            return BudgetGrantOutcome(
                ok = false,
                error = BudgetGrantError.OVER_GRANT_UNCONFIRMED,
                message = null, // the caller renders the ratio, not a generic string
                overGrant = overGrant,
            )
        }
        return BudgetGrantOutcome(ok = true, overGrant = overGrant)
    }

    /**
     * Describe by how much a grant exceeds the request, or null when it does
     * not exceed it.
     *
     * Banding rationale: the hazard is a **mis-typed extra zero**, which is
     * always ≥10× and therefore always lands in [OverGrantMagnitude.MULTIPLE].
     * Below 2× a multiple reads oddly ("1.2× the requested"), so a percentage is
     * clearer; at or under 5% no figure is shown at all, because dressing a
     * rounding-scale overage in alarm styling trains people to click past the
     * warning that matters.
     */
    fun describeOverGrant(requested: RequestedBudget, amount: String): OverGrant? {
        val requestedScaled = parseAmount(requested.requestedAmount) ?: return null
        val amountScaled = parseAmount(amount) ?: return null
        return describeOverGrant(requested, amount, requestedScaled, amountScaled)
    }

    private fun describeOverGrant(
        requested: RequestedBudget,
        amount: String,
        requestedScaled: Long,
        amountScaled: Long,
    ): OverGrant? {
        if (requestedScaled <= 0L || amountScaled <= requestedScaled) return null
        val multiple = amountScaled.toDouble() / requestedScaled.toDouble()
        val magnitude = when {
            multiple <= SLIGHT_OVER_GRANT_RATIO -> OverGrantMagnitude.SLIGHT
            multiple < MULTIPLE_OVER_GRANT_RATIO -> OverGrantMagnitude.PERCENT
            else -> OverGrantMagnitude.MULTIPLE
        }
        return OverGrant(
            requestedAmount = requested.requestedAmount,
            currency = requested.requestedCurrency,
            amount = amount,
            multiple = multiple,
            magnitude = magnitude,
            display = when (magnitude) {
                OverGrantMagnitude.SLIGHT -> ""
                OverGrantMagnitude.PERCENT -> "${((multiple - 1.0) * 100).roundToInt()}%"
                OverGrantMagnitude.MULTIPLE -> "${formatMultiple(multiple)}×"
            },
        )
    }

    /** At or below this ratio an over-grant is rendered without a figure. */
    private const val SLIGHT_OVER_GRANT_RATIO = 1.05

    /** At or above this ratio an over-grant is rendered as "N×" rather than a percentage. */
    private const val MULTIPLE_OVER_GRANT_RATIO = 2.0

    /** One decimal place, with a bare integer when the fraction is zero: 10, 2.5. */
    private fun formatMultiple(multiple: Double): String {
        val rounded = (multiple * 10).roundToInt()
        val whole = rounded / 10
        val frac = rounded % 10
        return if (frac == 0) whole.toString() else "$whole.$frac"
    }

    /**
     * Spend still available against an issued grant: `granted − spent`, clamped
     * at zero.
     *
     * **`granted_amount` alone overstates availability after any spend**, and
     * rendering it as though it were the remaining budget is simply wrong. A
     * second grant on a ticket raises the *ceiling*; it does not top the balance
     * up and it does not reset the ledger:
     *
     * ```
     * grant 25 → spend 25 → grant 40  ⇒  15 remaining   (not 40)
     * grant 50 → spend 40 → grant 10  ⇒   0 remaining   (clamped, never negative)
     * ```
     *
     * The second case is the de-facto revoke, since the API has no explicit
     * revoke verb.
     *
     * @return the remaining amount, or null when either side is unparseable —
     *   callers must render nothing rather than guess.
     */
    fun remainingAmount(grantedAmount: String, spentTotal: String?): String? {
        val granted = parseAmount(grantedAmount) ?: return null
        if (spentTotal.isNullOrBlank()) return formatAmount(granted)
        val spent = parseAmount(spentTotal) ?: return null
        val remaining = granted - spent
        return formatAmount(if (remaining < 0L) 0L else remaining)
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
