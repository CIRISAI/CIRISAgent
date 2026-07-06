package ai.ciris.mobile.shared

/**
 * Compile-time build flags for the CIRIS app.
 *
 * This module ships in two flavors from the SAME codebase:
 *  - **Node client (default):** the AI-free CIRIS app. Drives a local fabric node
 *    (ciris-server). No brain, no LLM/assistant configuration.
 *  - **Agent build:** CIRIS-Agent = fabric node + brain. The agent team adopts this
 *    client by swapping lens-core → ciris-server and flipping [HAS_AGENT] to true,
 *    which surfaces the AI/assistant (LLM provider, template) configuration that the
 *    node client deliberately hides.
 *
 * Keep agent-only surfaces gated on [HAS_AGENT] so the agent team's adoption is a
 * single flag flip rather than a re-merge.
 */
object CIRISBuild {
    /**
     * True only for the agent build (node + brain). When false (the node client),
     * AI/assistant configuration is hidden from setup and the rest of the UX.
     */
    const val HAS_AGENT: Boolean = false
}
