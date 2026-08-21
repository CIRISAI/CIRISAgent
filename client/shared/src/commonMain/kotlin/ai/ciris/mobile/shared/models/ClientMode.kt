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
 * A brain that has not completed setup is NODE regardless of what it reports —
 * see [brainUnconfigured].
 *
 * @param cognitiveState the `cognitive_state` field (null when absent — the node case).
 * @param serviceCount the agent service count reported in the health envelope (0 on a node).
 * @param brainUnconfigured the brain says it still needs setup and holds no config,
 *   so its 10 first-run services are the wizard's, not an agent's. Only the brain
 *   knows this; the health envelope alone cannot distinguish it from a real agent.
 */
fun clientModeFrom(
    cognitiveState: String?,
    serviceCount: Int,
    brainUnconfigured: Boolean = false,
): ClientMode =
    when {
        // A HALF-STARTED BRAIN IS NOT AN AGENT (CIRISAgent#1075).
        //
        // A brain with no config starts 10 of its 22 services — enough to serve
        // the setup wizard, not enough to be an agent. It still reports a
        // `cognitive_state` of "SETUP", and that non-null value was taken as
        // proof of an agent, so the client ran the full AGENT UI against a
        // runtime missing telemetry, audit and the LLM bus. Every AGENT-only
        // poller then hammered services that do not exist:
        //
        //     listAdapters      503
        //     getAuditEntries   503   (every 3s, with a full stack trace each)
        //     getLlmBusStatus   503
        //     getLlmProviders   503
        //     addLlmProvider    503   <- so the user could not configure an escape
        //
        // This gate exists precisely to stop AGENT-only pollers firing at a
        // server that cannot answer them — its call site says so. It just had no
        // way to know that SETUP is not readiness.
        //
        // KEYED ON THE BRAIN'S OWN SETUP STATE, NOT ON SERVICE COUNT. The first
        // version of this check tested `serviceCount == 0`, which never fires:
        // the count is derived from the `services` map in /v1/system/health, and
        // during first-run that map holds the 10 that ARE running. Only the brain
        // can say whether it is configured, so the caller asks it and passes the
        // answer in.
        brainUnconfigured -> ClientMode.NODE
        cognitiveState != null || serviceCount > 0 -> ClientMode.AGENT
        else -> ClientMode.NODE
    }

/**
 * The client build version, used for the node-vs-client VERSION-MISMATCH banner.
 *
 * AUTHORITATIVE in committed source and kept in lockstep with the release
 * version (Cargo.toml `[package].version`) by `scripts/sync-client-version.sh`
 * — the pre-commit hook runs it on a version-bump commit, and CI runs it with
 * `--check` (build-wheels.yml) and FAILS on drift. CI never edits this at build
 * time: it is a `const val` in the foundational commonMain module, so mutating
 * it recompiled the whole Compose client and defeated the desktop-JAR gradle
 * cache every leg (CIRISServer#272). Do not hand-edit — run the script.
 *
 * IN THIS REPO there is no Cargo.toml and no sync script: CIRISAgent consumes
 * the substrate as a pinned wheel, so the value this must equal is the
 * `ciris-server==` pin in requirements.txt (and the matching Android gradle
 * pin). Nothing enforced that, and it drifted to 0.5.159 while the bundled node
 * moved to 0.5.163 — so the app showed every user a VERSION-MISMATCH banner
 * against the node it ships with. `tools/dev/check_version_alignment.py` now
 * asserts this equality, which is the enforcement the upstream comment assumes.
 */
const val CLIENT_VERSION = "0.5.184"

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
