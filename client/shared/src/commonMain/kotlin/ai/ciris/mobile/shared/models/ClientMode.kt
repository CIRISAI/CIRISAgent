package ai.ciris.mobile.shared.models

/**
 * The ONE node-vs-agent gate for the universal client.
 *
 * The same app runs against either:
 *   - a bare **ciris-server node** (no AI/brain)            → [NODE]
 *   - a full **CIRIS agent** (ciris-server + cognitive brain) → [AGENT]
 *
 * This is the single source of truth: it is derived ONCE from the server
 * capability probe (see [clientModeFrom]) after the server is reachable, held as
 * app/startup state in `CIRISApp`, and read everywhere that must branch on
 * node-vs-agent (the 22 cognitive service lights, "agent" wording in
 * login/status/startup, the WORK-state wait). Do NOT scatter ad-hoc probes —
 * everything keys off this gate.
 *
 * Canonical signal (see `src/health.rs` server-side): a bare node serves
 * `/v1/system/health` as `{"data":{"status":"ok","role":"fabric-node","services":{}}}`
 * with **no `cognitive_state`**; an agent INHERITS that endpoint and ENRICHES it
 * with `cognitive_state` plus its service map. So: AGENT iff the server reports a
 * `cognitive_state` (or a non-empty agent service map); otherwise NODE.
 */
enum class ClientMode {
    /** Bare ciris-server node — no cognitive brain, no 22-service map. */
    NODE,

    /** Full CIRIS agent — ciris-server + cognitive brain (reports cognitive_state). */
    AGENT;

    val isAgent: Boolean get() = this == AGENT
    val isNode: Boolean get() = this == NODE
}

/**
 * Derive the [ClientMode] from a probed `/v1/system/health` snapshot. AGENT iff
 * the server reports a `cognitive_state` (the agent enrichment) OR a non-empty
 * agent service map; otherwise a bare NODE.
 *
 * @param cognitiveState the `cognitive_state` field (null when absent — the node case).
 * @param serviceCount the agent service count reported in the health envelope (0 on a node).
 */
fun clientModeFrom(cognitiveState: String?, serviceCount: Int): ClientMode =
    if (cognitiveState != null || serviceCount > 0) ClientMode.AGENT else ClientMode.NODE

/**
 * The client build version, used for the node-vs-client VERSION-MISMATCH banner.
 *
 * NOTE: this is a hand-pinned constant; wire it to the real build version
 * (e.g. a generated `BuildKonfig`) when one is available. Kept in sync by hand
 * with the server release for now.
 */
const val CLIENT_VERSION = "0.5.46"

/**
 * Whether [nodeVersion] differs materially from [CLIENT_VERSION] — i.e. a
 * non-blocking "update recommended" banner should be shown. Compares the
 * leading `major.minor.patch` (ignoring any pre-release/build suffix) and only
 * flags an actual mismatch (never flags when the node version is unknown/blank).
 */
fun isVersionMismatch(nodeVersion: String?, clientVersion: String = CLIENT_VERSION): Boolean {
    val node = nodeVersion?.trim()?.removePrefix("v")?.takeWhile { it.isDigit() || it == '.' }
    if (node.isNullOrBlank()) return false
    val client = clientVersion.trim().removePrefix("v").takeWhile { it.isDigit() || it == '.' }
    return node != client
}
