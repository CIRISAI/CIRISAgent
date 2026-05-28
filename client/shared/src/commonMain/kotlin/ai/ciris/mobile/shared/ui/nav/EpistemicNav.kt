package ai.ciris.mobile.shared.ui.nav

import androidx.compose.ui.graphics.vector.ImageVector
import ai.ciris.mobile.shared.ui.components.CIRISIcons

/**
 * Epistemic Commons Framework navigation — 2.9.4.
 *
 * Three-group collapsible sidebar (Agent / Manage / Federation) plus a Client
 * group. Each top-level surface may have nested sub-surfaces; sidebar shows
 * top-level on collapse, expands inline to show children.
 *
 * Source design: Figma Make `oC84aP8FdamRjISS5UPvz3` (issue #799).
 * Umbrella: CIRISAgent#800.
 *
 * **Iconography**: every surface uses a `CIRISIcons.*` entry (the CIRIS
 * brand icon set from `ui/components/CIRISIcons.kt`). No Material icons are
 * referenced here — the CIRIS palette is the brand surface and Material
 * icons would re-introduce the "looks like Google" aesthetic the bus palette
 * was specifically designed to avoid (see `CIRISColors` doc on
 * non-uniform hue distribution).
 *
 * Group/surface structure is stable across 2.9.4 → 2.9.X. As substrate APIs
 * land, individual leaves lift their gate and consume their new data source;
 * the surface itself does not move.
 */

/**
 * A single navigable surface in the nav. May have [children] — sub-surfaces
 * rendered indented under this one when the parent is expanded.
 *
 * Convention: a surface with children may itself be navigable (the parent
 * screen is a useful overview), or may be purely a header (in which case
 * navigating to it routes to its first child).
 */
sealed class NavSurface(
    val id: String,
    val label: String,
    val icon: ImageVector,
    /** Substrate issue blocking this surface, or null if it ships today. */
    val gate: SubstrateGate? = null,
    /** Nested sub-surfaces, in display order. Empty = leaf. */
    val children: List<NavSurface> = emptyList(),
) {
    // ═══════════════════════════════════════════════════════════════════════════
    // Agent group — runtime interaction surfaces
    // ═══════════════════════════════════════════════════════════════════════════

    object Sessions : NavSurface("sessions", "Sessions", CIRISIcons.dateRange)
    object Interact : NavSurface(
        id = "interact", label = "Interact", icon = CIRISIcons.thought,
        children = listOf(Sessions),
    )

    object Scheduler : NavSurface("scheduler", "Scheduler", CIRISIcons.stage)
    object Tickets : NavSurface(
        id = "tickets", label = "Tickets", icon = CIRISIcons.task,
        children = listOf(Scheduler),
    )

    object Tools : NavSurface("tools", "Tools", CIRISIcons.tools)
    object Services : NavSurface(
        id = "services", label = "Services", icon = CIRISIcons.bus,
        children = listOf(Tools),
    )

    object Logs : NavSurface("logs", "Logs", CIRISIcons.log)
    object Telemetry : NavSurface(
        id = "telemetry", label = "Telemetry", icon = CIRISIcons.telemetry,
        children = listOf(Logs),
    )

    object GraphMemory : NavSurface("graph-memory", "Graph", CIRISIcons.graph)
    object Memory : NavSurface(
        id = "memory", label = "Memory", icon = CIRISIcons.memory,
        children = listOf(GraphMemory),
    )

    object WiseAuthority : NavSurface("wise-authority", "Wise Authority", CIRISIcons.agent)

    // Settings sub-tree — collects LLM / System / Runtime / Config / Skills
    object LLMSettings : NavSurface("llm-settings", "LLM", CIRISIcons.model)
    object System : NavSurface("system", "System", CIRISIcons.requirements)
    object Runtime : NavSurface("runtime", "Runtime", CIRISIcons.processing)
    object Config : NavSurface("config", "Config", CIRISIcons.instructions)
    object Skills : NavSurface("skills", "Skills", CIRISIcons.skill)
    object AgentSettings : NavSurface(
        id = "agent-settings", label = "Settings", icon = CIRISIcons.settings,
        children = listOf(LLMSettings, System, Runtime, Config, Skills),
    )

    // ═══════════════════════════════════════════════════════════════════════════
    // Manage group — operator surfaces
    // ═══════════════════════════════════════════════════════════════════════════

    // Health & Reputation ships in 2.9.4 with local + fleet capacity score
    // (data: InteractViewModel.cellVizState ← /v1/my-data/capacity).
    // The federation-attestations sub-section inside the card retains the
    // LENSCORE_CAPACITY gate; the surface itself is not gated.
    object HealthReputation : NavSurface(
        id = "health-reputation", label = "Health & Reputation", icon = CIRISIcons.identity,
    )
    object Users : NavSurface("users", "Users", CIRISIcons.person)
    object Adapters : NavSurface("adapters", "Adapters", CIRISIcons.adapter)
    /**
     * Federation transport substrate — Reticulum + HTTPS + cohabitation Local.
     * Edge data is source of truth; UI is display + content-type-aware CRUD.
     * Lands in lockstep with CIRISEdge 1.0 / 1.1 (CIRISEdge#23–29 + the
     * sibling ask threads referenced in NETWORK_FFI_GAPS).
     */
    object Network : NavSurface("network", "Network", CIRISIcons.globe)

    object Audit : NavSurface("audit", "Audit", CIRISIcons.audit)
    object Consent : NavSurface("consent", "Consent", CIRISIcons.lock)
    object Data : NavSurface(
        id = "data", label = "Data", icon = CIRISIcons.pkg,
        children = listOf(Audit, Consent),
    )

    object Trust : NavSurface("trust", "Trust", CIRISIcons.shield)

    object Wallet : NavSurface("wallet", "Wallet", CIRISIcons.keySecure)
    object Billing : NavSurface(
        id = "billing", label = "Billing", icon = CIRISIcons.wallet,
        children = listOf(Wallet),
    )

    // ═══════════════════════════════════════════════════════════════════════════
    // Federation group — 5 of 6 gated on substrate work
    // ═══════════════════════════════════════════════════════════════════════════

    object Commons : NavSurface(
        id = "commons", label = "The Commons", icon = CIRISIcons.globe,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
    )
    object Participate : NavSurface(
        id = "participate", label = "Participate", icon = CIRISIcons.add,
        gate = SubstrateGate.NODECORE_NEEDS,
    )
    object EnvironmentGraph : NavSurface(
        // EnvironmentInfoScreen partially covers; extension is gated.
        id = "environment-graph", label = "Environment Graph", icon = CIRISIcons.snapshot,
        gate = SubstrateGate.LENSCORE_COHORT,
    )
    object Delegation : NavSurface(
        id = "delegation", label = "Delegation", icon = CIRISIcons.send,
        gate = SubstrateGate.PERSIST_DELEGATES_TO,
    )
    object TrustTopology : NavSurface(
        id = "trust-topology", label = "Trust Topology", icon = CIRISIcons.welcome,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
    )
    object Constitutional : NavSurface(
        id = "constitutional", label = "Constitutional", icon = CIRISIcons.instructions,
        gate = SubstrateGate.REGISTRY_ACCORD_HOLDER,
    )

    // ═══════════════════════════════════════════════════════════════════════════
    // Client group — multi-agent + interface
    // ═══════════════════════════════════════════════════════════════════════════

    object AgentsList : NavSurface(
        id = "agents-list", label = "Agents", icon = CIRISIcons.identity,
        gate = SubstrateGate.POST_SUBSTRATE_SUBSTITUTION,
    )
    object ClientInterface : NavSurface("client-interface", "Interface", CIRISIcons.home)
}

/**
 * A blocking substrate issue + the FSD-002 prefix family the surface consumes.
 * Surfaces this metadata on the Coming Soon placeholder so users see *which*
 * upstream produces the data — "the wait itself teaches the architecture".
 */
enum class SubstrateGate(
    val repo: String,
    val issueNumber: Int,
    val prefixFamily: String,
    val fsdSection: String,
) {
    VERIFY_ATTESTATION_LADDER(
        repo = "CIRISVerify", issueNumber = 36,
        prefixFamily = "attestation:l1..l5 + provenance:* + hardware_custody:*",
        fsdSection = "FSD-002 §3.2",
    ),
    PERSIST_DELEGATES_TO(
        repo = "CIRISPersist", issueNumber = 104,
        prefixFamily = "federation_directory:* + delegates_to (structural)",
        fsdSection = "FSD-002 §3.3 + §2.2.1",
    ),
    EDGE_PEERRESOLVER(
        repo = "CIRISEdge", issueNumber = 22,
        prefixFamily = "peer_reachability:* + ContentFetch + VerifiedEnvelope feed",
        fsdSection = "FSD-002 §3.4 + §3.6.7",
    ),
    NODECORE_NEEDS(
        repo = "CIRISNodeCore", issueNumber = 12,
        prefixFamily = "need:{domain}:{kind} (new primitive, in flight)",
        fsdSection = "FSD-002 §3.6 (extension)",
    ),
    LENSCORE_CAPACITY(
        repo = "CIRISLensCore", issueNumber = 25,
        prefixFamily = "capacity:core_identity..sustained_coherence:composite",
        fsdSection = "FSD-002 §3.5.4",
    ),
    LENSCORE_COHORT(
        repo = "CIRISLensCore", issueNumber = 25,
        prefixFamily = "manifold_conformity:{cohort} + detection:correlated_action:{axis} + detection:distributive:access:*",
        fsdSection = "FSD-002 §3.5.2 + §3.5.3 + §3.5.5",
    ),
    REGISTRY_ACCORD_HOLDER(
        repo = "CIRISRegistry", issueNumber = 23,
        prefixFamily = "accord:* (reserved to identity_type=accord_holder)",
        fsdSection = "FSD-002 §3.9 + §4.1",
    ),
    POST_SUBSTRATE_SUBSTITUTION(
        repo = "CIRISAgent", issueNumber = 800,
        prefixFamily = "client / relay / node peer taxonomy (post Step-4)",
        fsdSection = "substrate-substitution trajectory",
    ),
    ;

    val url: String get() = "https://github.com/CIRISAI/$repo/issues/$issueNumber"
    val shortRef: String get() = "$repo#$issueNumber"
}

// ─── Group definitions ────────────────────────────────────────────────────────

/** A nav group — collapsible section in the sidebar. */
data class NavGroup(
    val id: String,
    val label: String,
    val icon: ImageVector,
    val surfaces: List<NavSurface>,
    /** Optional accent color hex; null = use default. */
    val accentHex: String? = null,
)

val AGENT_GROUP = NavGroup(
    id = "agent",
    label = "Agent",
    icon = CIRISIcons.identity,
    surfaces = listOf(
        NavSurface.Interact,        // + Sessions
        NavSurface.Tickets,         // + Scheduler
        NavSurface.Services,        // + Tools
        NavSurface.Telemetry,       // + Logs
        NavSurface.Memory,          // + Graph
        NavSurface.WiseAuthority,
        NavSurface.AgentSettings,   // + LLM, System, Runtime, Config, Skills
    ),
)

val MANAGE_GROUP = NavGroup(
    id = "manage",
    label = "Manage",
    icon = CIRISIcons.handler,
    surfaces = listOf(
        NavSurface.HealthReputation,
        NavSurface.Users,
        NavSurface.Adapters,
        NavSurface.Network,         // federation transport substrate (Edge 1.0/1.1)
        NavSurface.Data,            // + Audit, Consent
        NavSurface.Trust,
        NavSurface.Billing,         // + Wallet
    ),
)

val FEDERATION_GROUP = NavGroup(
    id = "federation",
    label = "Federation",
    icon = CIRISIcons.globe,
    accentHex = "#C96A38", // CIRISColors.BusTool — the federation group's identifying warm accent
    surfaces = listOf(
        NavSurface.Commons,
        NavSurface.Participate,
        NavSurface.EnvironmentGraph,
        NavSurface.Delegation,
        NavSurface.TrustTopology,
        NavSurface.Constitutional,
    ),
)

val CLIENT_GROUP = NavGroup(
    id = "client",
    label = "Client",
    icon = CIRISIcons.home,
    surfaces = listOf(
        NavSurface.AgentsList,
        NavSurface.ClientInterface,
    ),
)

/** All four groups in display order. */
val EPISTEMIC_NAV_GROUPS = listOf(AGENT_GROUP, MANAGE_GROUP, FEDERATION_GROUP, CLIENT_GROUP)

/**
 * Walk the entire surface tree (depth-first) — used by routers needing the
 * full leaf catalog without re-traversing the group structure each time.
 */
fun allSurfaces(): List<NavSurface> = EPISTEMIC_NAV_GROUPS.flatMap { group ->
    group.surfaces.flatMap { surface -> surface.descendantsAndSelf() }
}

/** This surface plus all transitive children (depth-first). */
fun NavSurface.descendantsAndSelf(): List<NavSurface> =
    listOf(this) + children.flatMap { it.descendantsAndSelf() }

/**
 * Surfaces NOT exposed via [EPISTEMIC_NAV_GROUPS] — flow-only screens reached
 * by direct app routing (pre-login flow, top-bar utilities). Listed here so the
 * nav module has a single authoritative inventory for testing the no-orphans
 * invariant.
 *
 * IDs only (no NavSurface instances) — these aren't sidebar-navigable.
 */
val FLOW_ONLY_SURFACES = listOf(
    "startup",
    "login",
    "setup",
    "server-connection",
    "help",
)
