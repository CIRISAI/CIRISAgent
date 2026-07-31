package ai.ciris.mobile.shared.approvals

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The wire contract and the ≤-requested constraint.
 *
 * The constraint is the load-bearing rule of the whole budget-approval flow: a
 * human may approve at or below what the agent asked for, never above. It is
 * enforced server-side too, but a client that lets an operator type a larger
 * number and only learns better from a rejected round-trip has failed at the
 * point of decision.
 */
class BudgetApprovalSeamTest {

    private fun metadata(json: String): Map<String, JsonElement> =
        Json.parseToJsonElement(json) as JsonObject

    private val requested = RequestedBudget(
        requestedAmount = "25.00",
        requestedCurrency = "USDC",
        purpose = "Opt-out processing fee",
        justification = "The registry charges per request",
    )

    // ─── Amount parsing: money must never round-trip through a float ────────

    @Test
    fun parseAmount_handlesPlainDecimals() {
        assertEquals(BudgetApprovalSeam.parseAmount("1"), BudgetApprovalSeam.parseAmount("1.0"))
        assertEquals(BudgetApprovalSeam.parseAmount("1.00"), BudgetApprovalSeam.parseAmount("1.000000"))
        assertNotNull(BudgetApprovalSeam.parseAmount("0.000001"))
    }

    @Test
    fun parseAmount_rejectsAnythingThatIsNotAPlainDecimal() {
        assertNull(BudgetApprovalSeam.parseAmount(""))
        assertNull(BudgetApprovalSeam.parseAmount("abc"))
        assertNull(BudgetApprovalSeam.parseAmount("-5.00"))
        assertNull(BudgetApprovalSeam.parseAmount("1e3"))
        assertNull(BudgetApprovalSeam.parseAmount("1,000.00"))
        assertNull(BudgetApprovalSeam.parseAmount("$5"))
        assertNull(BudgetApprovalSeam.parseAmount("1.2.3"))
        // More precision than the fixed-point scale can hold is refused rather
        // than silently truncated.
        assertNull(BudgetApprovalSeam.parseAmount("1.123456789"))
    }

    @Test
    fun compareAmounts_ordersByValueNotByString() {
        // "9.00" > "10.00" lexically; the point of fixed-point is that it isn't here.
        assertTrue((BudgetApprovalSeam.compareAmounts("9.00", "10.00") ?: 0) < 0)
        assertEquals(0, BudgetApprovalSeam.compareAmounts("25", "25.000"))
        assertNull(BudgetApprovalSeam.compareAmounts("25", "twenty-five"))
    }

    @Test
    fun formatAmount_roundTrips() {
        val scaled = BudgetApprovalSeam.parseAmount("25.50")!!
        assertEquals("25.5", BudgetApprovalSeam.formatAmount(scaled))
        assertEquals("25", BudgetApprovalSeam.formatAmount(BudgetApprovalSeam.parseAmount("25.00")!!))
    }

    // ─── The ≤-requested constraint ────────────────────────────────────────

    @Test
    fun validateGrant_acceptsExactlyTheRequestedAmount() {
        val outcome = BudgetApprovalSeam.validateGrant(requested, "25.00", 24, "fee")
        assertTrue(outcome.ok, "approving exactly what was asked must be allowed")
    }

    @Test
    fun validateGrant_acceptsLessThanRequested() {
        val outcome = BudgetApprovalSeam.validateGrant(requested, "10.00", 24, "fee")
        assertTrue(outcome.ok)
    }

    @Test
    fun validateGrant_refusesMoreThanRequested() {
        val outcome = BudgetApprovalSeam.validateGrant(requested, "25.01", 24, "fee")
        assertFalse(outcome.ok)
        assertEquals(BudgetGrantError.EXCEEDS_REQUESTED, outcome.error)
    }

    @Test
    fun validateGrant_refusesMoreThanRequested_evenByTheSmallestUnit() {
        val outcome = BudgetApprovalSeam.validateGrant(requested, "25.00000001", 24, "fee")
        assertFalse(outcome.ok)
        assertEquals(BudgetGrantError.EXCEEDS_REQUESTED, outcome.error)
    }

    @Test
    fun validateGrant_refusesZeroAndNonNumericAmounts() {
        assertEquals(
            BudgetGrantError.INVALID_AMOUNT,
            BudgetApprovalSeam.validateGrant(requested, "0", 24, "fee").error,
        )
        assertEquals(
            BudgetGrantError.INVALID_AMOUNT,
            BudgetApprovalSeam.validateGrant(requested, "", 24, "fee").error,
        )
        assertEquals(
            BudgetGrantError.INVALID_AMOUNT,
            BudgetApprovalSeam.validateGrant(requested, "lots", 24, "fee").error,
        )
    }

    @Test
    fun validateGrant_enforcesExpiryBounds() {
        assertEquals(
            BudgetGrantError.INVALID_EXPIRY,
            BudgetApprovalSeam.validateGrant(requested, "10.00", 0, "fee").error,
        )
        assertEquals(
            BudgetGrantError.INVALID_EXPIRY,
            BudgetApprovalSeam.validateGrant(requested, "10.00", 8761, "fee").error,
        )
        assertTrue(BudgetApprovalSeam.validateGrant(requested, "10.00", 8760, "fee").ok)
    }

    @Test
    fun validateGrant_requiresAPurpose() {
        assertEquals(
            BudgetGrantError.MISSING_PURPOSE,
            BudgetApprovalSeam.validateGrant(requested, "10.00", 24, "   ").error,
        )
    }

    private fun headroom(amount: String, currency: String = "USDC") = TrustHeadroom(
        amount = amount,
        currency = currency,
        maxTransaction = "100",
        dailyRemaining = amount,
        source = "wallet",
    )

    @Test
    fun validateGrant_refusesGrantsWiderThanTheEnclosingEnvelope() {
        // A nested envelope may never be wider than the envelope it nests in,
        // even when it is within what the agent asked for.
        val outcome = BudgetApprovalSeam.validateGrant(requested, "20.00", 24, "fee", headroom = headroom("5.00"))
        assertFalse(outcome.ok)
        assertEquals(BudgetGrantError.NESTING_VIOLATION, outcome.error)
    }

    @Test
    fun validateGrant_allowsAGrantExactlyEqualToTheHeadroom() {
        // The gate allows a spend of exactly `amount`, so the UI must not be
        // stricter than the number it is showing the operator.
        assertTrue(BudgetApprovalSeam.validateGrant(requested, "5.00", 24, "fee", headroom = headroom("5.00")).ok)
    }

    @Test
    fun validateGrant_ignoresHeadroomWhenTheServerDoesNotReportIt() {
        // trust_headroom is null when no wallet adapter is loaded. That must be
        // normal, not a block.
        assertTrue(BudgetApprovalSeam.validateGrant(requested, "25.00", 24, "fee", headroom = null).ok)
    }

    @Test
    fun validateGrant_ignoresHeadroomDenominatedInADifferentCurrency() {
        // A USD ceiling says nothing about a USDC request; comparing them would
        // block a legitimate grant on a meaningless mismatch.
        val outcome = BudgetApprovalSeam.validateGrant(
            requested, "25.00", 24, "fee", headroom = headroom("5.00", currency = "USD"),
        )
        assertTrue(outcome.ok)
    }

    // ─── Proposal / budget metadata parsing ────────────────────────────────

    @Test
    fun isProposal_requiresBothBlockedStatusAndTheProposalKey() {
        val withProposal = metadata("""{"__proposal__": {"proposed_by": "agent"}}""")
        val without = metadata("""{"stages": {}}""")

        assertTrue(BudgetApprovalSeam.isProposal("blocked", withProposal))
        assertFalse(BudgetApprovalSeam.isProposal("pending", withProposal))
        assertFalse(BudgetApprovalSeam.isProposal("blocked", without))
    }

    @Test
    fun parseRequestedBudget_readsTheRequestedFields() {
        val meta = metadata(
            """
            {"__requested_budget__": {
               "requested_amount": "25.00",
               "requested_currency": "USDC",
               "purpose": "Opt-out fee",
               "justification": "registry charges per request"}}
            """.trimIndent()
        )
        val parsed = BudgetApprovalSeam.parseRequestedBudget(meta)
        assertNotNull(parsed)
        assertEquals("25.00", parsed.requestedAmount)
        assertEquals("USDC", parsed.requestedCurrency)
        assertEquals("Opt-out fee", parsed.purpose)
    }

    @Test
    fun parseRequestedBudget_returnsNullForAProposalThatAsksForNoMoney() {
        assertNull(BudgetApprovalSeam.parseRequestedBudget(metadata("""{"__proposal__": {}}""")))
    }

    @Test
    fun parseRequestedBudget_neverReadsAGrantAsARequest() {
        // The two objects have deliberately disjoint field names so a grant can
        // never be mistaken for a request or vice versa.
        val grantOnly = metadata(
            """{"__requested_budget__": {"granted_amount": "999.00", "granted_currency": "USD"}}"""
        )
        assertNull(BudgetApprovalSeam.parseRequestedBudget(grantOnly))
    }

    @Test
    fun parseGrantedBudget_readsTheGrantedFieldsIncludingSignedFlag() {
        val meta = metadata(
            """
            {"__granted_budget__": {
               "granted_amount": "20.00",
               "granted_currency": "USDC",
               "purpose": "Opt-out fee",
               "expires_at": "2026-08-01T00:00:00Z",
               "granted_by_wa_id": "wa-1",
               "granted_by_user_id": "u-1",
               "granted_at": "2026-07-31T00:00:00Z",
               "signed": false}}
            """.trimIndent()
        )
        val granted = BudgetApprovalSeam.parseGrantedBudget(meta)
        assertNotNull(granted)
        assertEquals("20.00", granted.grantedAmount)
        assertFalse(granted.signed, "an unsigned grant must not silently read as signed")
    }

    @Test
    fun parseBudgetSpend_countsRecords() {
        val meta = metadata(
            """{"__budget_spent__": {"total_spent": "5.00", "currency": "USDC", "records": [{},{}]}}"""
        )
        val spend = BudgetApprovalSeam.parseBudgetSpend(meta)
        assertNotNull(spend)
        assertEquals("5.00", spend.totalSpent)
        assertEquals(2, spend.recordCount)
    }

    @Test
    fun parsingIsTotal_malformedMetadataYieldsNullNotAnException() {
        assertNull(BudgetApprovalSeam.parseProposal(metadata("""{"__proposal__": "not-an-object"}""")))
        assertNull(BudgetApprovalSeam.parseRequestedBudget(metadata("""{"__requested_budget__": 7}""")))
        assertNull(BudgetApprovalSeam.parseGrantedBudget(metadata("""{"__granted_budget__": []}""")))
        assertNull(BudgetApprovalSeam.parseBudgetSpend(metadata("""{}""")))
    }

    // ─── HTTP status → typed error ─────────────────────────────────────────

    @Test
    fun classifyHttpError_mapsTheStatusesTheServerActuallyReturns() {
        assertEquals(BudgetGrantError.FORBIDDEN_ROLE, BudgetApprovalSeam.classifyHttpError(403, null))
        assertEquals(BudgetGrantError.NESTING_VIOLATION, BudgetApprovalSeam.classifyHttpError(422, null))
        assertEquals(BudgetGrantError.ENDPOINT_UNAVAILABLE, BudgetApprovalSeam.classifyHttpError(405, null))
        assertEquals(BudgetGrantError.UNKNOWN, BudgetApprovalSeam.classifyHttpError(500, null))
    }

    @Test
    fun classifyHttpError_pinsOn404ErrorCodeNotProse() {
        // The contract path: a structured detail carrying a machine-readable code.
        assertEquals(
            BudgetGrantError.TICKET_NOT_FOUND,
            BudgetApprovalSeam.classifyHttpError(
                404,
                """{"detail":{"error_code":"TICKET_NOT_FOUND","message":"PROP-1 is gone"}}""",
            ),
        )
    }

    @Test
    fun classifyHttpError_bareNotFoundMeansTheEndpointIsAbsent() {
        // A route that does not exist answers with the bare FastAPI 404 and no
        // error_code. This is what keeps the capability check working against
        // servers predating the budget feature.
        assertEquals(
            BudgetGrantError.ENDPOINT_UNAVAILABLE,
            BudgetApprovalSeam.classifyHttpError(404, """{"detail":"Not Found"}"""),
        )
        assertEquals(BudgetGrantError.ENDPOINT_UNAVAILABLE, BudgetApprovalSeam.classifyHttpError(404, null))
    }

    @Test
    fun classifyHttpError_fallsBackToProseForServersWithoutTheStructuredDetail() {
        assertEquals(
            BudgetGrantError.TICKET_NOT_FOUND,
            BudgetApprovalSeam.classifyHttpError(404, """{"detail":"Ticket abc not found"}"""),
        )
    }

    @Test
    fun classifyHttpError_doesNotGuessAtAnUnknownErrorCode() {
        // A structured detail we don't recognize is UNKNOWN, not silently
        // coerced into "the endpoint is missing" — that would flip the
        // capability check off on an unrelated error.
        assertEquals(
            BudgetGrantError.UNKNOWN,
            BudgetApprovalSeam.classifyHttpError(404, """{"detail":{"error_code":"SOMETHING_ELSE"}}"""),
        )
    }

    // ─── GET /v1/tickets/{id}/budget ───────────────────────────────────────

    @Test
    fun parseTicketBudgetState_readsTheWholeBudgetPictureInOneRead() {
        val data = Json.parseToJsonElement(
            """
            {"ticket_id": "PROP-1",
             "is_proposal": true,
             "requested_budget": {"requested_amount": "50.00", "requested_currency": "USDC",
                                  "purpose": "fee", "justification": "why"},
             "granted_budget": null,
             "spent": {"total_spent": "30", "currency": "USDC", "records": [{},{},{}]},
             "trust_headroom": {"amount": "40", "currency": "USDC", "max_transaction": "100",
                                "daily_remaining": "40", "source": "wallet"}}
            """.trimIndent()
        ) as JsonObject

        val state = BudgetApprovalSeam.parseTicketBudgetState(data)
        assertNotNull(state)
        assertEquals("PROP-1", state.ticketId)
        assertTrue(state.isProposal)
        assertEquals("50.00", state.requested?.requestedAmount)
        assertNull(state.granted)
        assertEquals(3, state.spent?.recordCount)
        assertEquals("40", state.headroom?.amount)
        // Both bounds are carried so the UI can say which one is binding.
        assertEquals("100", state.headroom?.maxTransaction)
        assertEquals("40", state.headroom?.dailyRemaining)
        assertEquals("wallet", state.headroom?.source)
    }

    @Test
    fun parseTicketBudgetState_toleratesAbsentHeadroom() {
        // trust_headroom is null when no wallet adapter is loaded — correct
        // behaviour, not a gap.
        val data = Json.parseToJsonElement(
            """{"ticket_id": "PROP-1", "is_proposal": true, "trust_headroom": null}"""
        ) as JsonObject
        val state = BudgetApprovalSeam.parseTicketBudgetState(data)
        assertNotNull(state)
        assertNull(state.headroom)
    }

    @Test
    fun parseTicketBudgetState_returnsNullOnAnUnrecognizedBody() {
        assertNull(BudgetApprovalSeam.parseTicketBudgetState(null))
        assertNull(
            BudgetApprovalSeam.parseTicketBudgetState(
                Json.parseToJsonElement("""{"unexpected": true}""") as JsonObject
            )
        )
    }

    @Test
    fun budgetPath_targetsTheReadOnlyStateEndpoint() {
        assertEquals("/v1/tickets/t-123/budget", BudgetApprovalSeam.budgetPath("t-123"))
    }

    @Test
    fun buildGrantBody_emitsTheFieldNamesTheServerExpects() {
        val body = BudgetApprovalSeam.buildGrantBody("25.00", "USDC", "fee", 24)
        assertEquals(setOf("amount", "currency", "purpose", "expires_in_hours"), body.keys)
        // wa_id is optional and omitted rather than sent as null.
        val withWa = BudgetApprovalSeam.buildGrantBody("25.00", "USDC", "fee", 24, waId = "wa-1")
        assertTrue("wa_id" in withWa.keys)
    }

    @Test
    fun grantPath_targetsTheDedicatedIssuanceEndpoint() {
        assertEquals("/v1/tickets/t-123/budget/grant", BudgetApprovalSeam.grantPath("t-123"))
    }
}
