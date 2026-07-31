package ai.ciris.mobile.shared.models.federation

/**
 * THE definition of which attestation families this node consents to replicate.
 *
 * WHY THIS EXISTS
 * ---------------
 * Four call sites author `consent:replication:v1` — the setup wizard, the Data &
 * Privacy card, and both directions of the Manage Consent card — and they had
 * three different prefix lists between them. The A->B card declared
 * `["capacity:"]`, dropping `trace:`, which is not a cosmetic difference:
 *
 *   the promoter (`promote_consented_backlog`) only lifts a row from
 *   tier=local/cohort_scope=self to federation if its dimension is covered by a
 *   live grant's declared prefixes.
 *
 * A grant that omits `trace:` therefore leaves every sealed trace stranded at
 * (self, local) forever. The node still converges to its consent peer and still
 * reports healthy — it simply never offers the rows. Observed exactly that:
 * four `trace:complete:v1` rows at self/local, "converged to 1 consent peers",
 * `envelopes_sent_total` absent, and a canonical with zero trace_events.
 *
 * The failure is silent in both directions: nothing warns that a grant omits a
 * prefix, and nothing warns that a row is stranded. So the prefix list is a
 * correctness-critical value that must have exactly one definition.
 *
 * Adding a new replicated attestation family means adding its prefix HERE, and
 * nowhere else.
 */
object FederationConsentScopes {

    /**
     * What this node consents to SEND to a canonical server.
     *
     * `trace:` — sealed reasoning traces. Without this the canonical has no
     *            corpus, so it can never author a capacity score.
     * `capacity:` — the score the canonical authors back about this agent, which
     *            this node must also accept as a replicated row.
     */
    val TO_CANONICAL: List<String> = listOf("trace:", "capacity:")

    /**
     * What a peer is asked to send BACK on the reverse direction of a bilateral
     * pairing. Deliberately narrower than [TO_CANONICAL]: the reverse grant is a
     * health/liveness channel, not a trace channel.
     */
    val FROM_PEER: List<String> = listOf("health:")

    /** Render for logging. Log the ACTUAL value — never a hardcoded literal. */
    fun describe(prefixes: List<String>): String = prefixes.joinToString(",")
}
