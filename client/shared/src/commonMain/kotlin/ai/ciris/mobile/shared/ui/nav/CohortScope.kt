package ai.ciris.mobile.shared.ui.nav

/**
 * The 5 UX-facing cohort scopes — operator-friendly mirror of the 7
 * underlying CEG 0.6 cohort_scope values (CEG §02 grammar:137,
 * `self / family / community / affiliations / species / planet / federation`).
 *
 * The 7 → 5 fold:
 * - `self` → [AGENT]
 * - `family` → [FAMILY]
 * - `community` → [LOCAL_COMMUNITY]
 * - `affiliations` → [GLOBAL_COMMUNITIES]
 * - `species` + `planet` + `federation` → [GLOBAL_COMMONS]
 *
 * Each layer surfaces three concerns in the UX: a list of *identities*
 * known at that scope (with friendly names where available), the *trust
 * state* with respect to each identity (trusted / not, and how —
 * trust policy vs. direct trust), and the *trust policies* that govern
 * automatic trust at that scope.
 *
 * The Recursive Golden Rule is fractal — the same shape (identities ·
 * trust · policies) repeats at every scale. The UX renders the same
 * three-section composable for all 5 scopes; only the data source
 * differs. See [[recursive-golden-rule]] memory.
 */
enum class CohortScope(
    val id: String,
    val cegScope: String,
) {
    /** The agent itself — implicit "self" in the user's mental model. */
    AGENT(id = "agent", cegScope = "self"),

    /** Other CIRIS occurrences sharing the same operator identity. */
    FAMILY(id = "family", cegScope = "family"),

    /** Locally-trusted peers — typically one home channel / Discord guild / household. */
    LOCAL_COMMUNITY(id = "local-community", cegScope = "community"),

    /** Cross-community affinity groups the agent has joined. */
    GLOBAL_COMMUNITIES(id = "global-communities", cegScope = "affiliations"),

    /**
     * The federation as the universal layer. Folds CEG `species`
     * (humans + AI as a kind), `planet` (ecological scope), and
     * `federation` (the wire-format substrate itself) into one
     * operator-facing surface.
     */
    GLOBAL_COMMONS(id = "global-commons", cegScope = "federation");

    companion object {
        fun fromId(id: String): CohortScope? = entries.firstOrNull { it.id == id }
    }
}
