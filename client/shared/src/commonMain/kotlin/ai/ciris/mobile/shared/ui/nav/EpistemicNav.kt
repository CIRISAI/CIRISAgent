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
    /**
     * English fallback label. Used as the sidebar display when [labelKey] is
     * null OR the localizer has no entry for that key. Always provide a
     * sensible English string — the localizer is best-effort.
     */
    val label: String,
    val icon: ImageVector,
    /** Substrate issue blocking this surface, or null if it ships today. */
    val gate: SubstrateGate? = null,
    /** Nested sub-surfaces, in display order. Empty = leaf. */
    val children: List<NavSurface> = emptyList(),
    /**
     * Optional localization key for the sidebar / card title. When set the
     * sidebar resolves `localizedString(labelKey)` and falls back to [label]
     * if the locale lacks an entry. Per 2.9.4 release-prep: every NavSurface
     * that ships a Commons-group / Federation-group card carries a labelKey
     * so the 28-locale fanout lands cleanly. Other surfaces stay on raw
     * [label] until they're touched.
     */
    val labelKey: String? = null,
) {
    // ═══════════════════════════════════════════════════════════════════════════
    // Agent group — runtime interaction surfaces
    // ═══════════════════════════════════════════════════════════════════════════

    object Sessions : NavSurface("sessions", "Sessions", CIRISIcons.dateRange,
        labelKey = "nav.surface.sessions",)
    object Interact : NavSurface(
        id = "interact", label = "Interact", icon = CIRISIcons.thought,
        children = listOf(Sessions),
        labelKey = "nav.surface.interact",)

    object Scheduler : NavSurface("scheduler", "Scheduler", CIRISIcons.stage,
        labelKey = "nav.surface.scheduler",)
    object Tickets : NavSurface(
        id = "tickets", label = "Tickets", icon = CIRISIcons.task,
        children = listOf(Scheduler),
        labelKey = "nav.surface.tickets",)

    object Tools : NavSurface("tools", "Tools", CIRISIcons.tools,
        labelKey = "nav.surface.tools",)
    object Services : NavSurface(
        id = "services", label = "Services", icon = CIRISIcons.bus,
        children = listOf(Tools),
        labelKey = "nav.surface.services",)

    object Logs : NavSurface("logs", "Logs", CIRISIcons.log,
        labelKey = "nav.surface.logs",)
    object Telemetry : NavSurface(
        id = "telemetry", label = "Telemetry", icon = CIRISIcons.telemetry,
        children = listOf(Logs),
        labelKey = "nav.surface.telemetry",)

    object GraphMemory : NavSurface("graph-memory", "Graph", CIRISIcons.graph,
        labelKey = "nav.surface.graph_memory",)
    object Memory : NavSurface(
        id = "memory", label = "Memory", icon = CIRISIcons.memory,
        children = listOf(GraphMemory),
        labelKey = "nav.surface.memory",)

    object WiseAuthority : NavSurface("wise-authority", "Wise Authority", CIRISIcons.agent,
        labelKey = "nav.surface.wise_authority",)

    // Settings sub-tree — collects LLM / System / Runtime / Config / Skills
    object LLMSettings : NavSurface("llm-settings", "LLM", CIRISIcons.model,
        labelKey = "nav.surface.llm_settings",)
    object System : NavSurface("system", "System", CIRISIcons.requirements,
        labelKey = "nav.surface.system",)
    object Runtime : NavSurface("runtime", "Runtime", CIRISIcons.processing,
        labelKey = "nav.surface.runtime",)
    object Config : NavSurface("config", "Config", CIRISIcons.instructions,
        labelKey = "nav.surface.config",)
    object Skills : NavSurface("skills", "Skills", CIRISIcons.skill,
        labelKey = "nav.surface.skills",)
    object AgentSettings : NavSurface(
        id = "agent-settings", label = "Settings", icon = CIRISIcons.settings,
        children = listOf(LLMSettings, System, Runtime, Config, Skills),
        labelKey = "nav.surface.agent_settings",)

    // ═══════════════════════════════════════════════════════════════════════════
    // Manage group — operator surfaces
    // ═══════════════════════════════════════════════════════════════════════════

    // Health & Reputation ships in 2.9.4 with local + fleet capacity score
    // (data: InteractViewModel.cellVizState ← /v1/my-data/capacity).
    // The federation-attestations sub-section inside the card retains the
    // LENSCORE_CAPACITY gate; the surface itself is not gated.
    object HealthReputation : NavSurface(
        id = "health-reputation", label = "Health & Reputation", icon = CIRISIcons.identity,
        labelKey = "nav.surface.health_reputation",)
    object Users : NavSurface("users", "Users", CIRISIcons.person,
        labelKey = "nav.surface.users",)
    object Adapters : NavSurface("adapters", "Adapters", CIRISIcons.adapter,
        labelKey = "nav.surface.adapters",)
    /**
     * Federation transport substrate — Reticulum + HTTPS + cohabitation Local.
     * Edge data is source of truth; UI is display + content-type-aware CRUD.
     * Lands in lockstep with CIRISEdge 1.0 / 1.1 (CIRISEdge#23–29 + the
     * sibling ask threads referenced in NETWORK_FFI_GAPS).
     *
     * Phase B (2026-05-31): no longer in `MANAGE_GROUP` — folded into
     * [LayerGlobalCommons] in `COMMONS_GROUP`. Surface object retained
     * because `surfaceToScreen` / `screenToSurface` keep a forwarding
     * mapping for backward compat, but the sidebar entry is gone.
     */
    object Network : NavSurface("network", "Network", CIRISIcons.globe,
        labelKey = "nav.surface.network",)

    object Audit : NavSurface("audit", "Audit", CIRISIcons.audit,
        labelKey = "nav.surface.audit",)
    object Consent : NavSurface("consent", "Consent", CIRISIcons.lock,
        labelKey = "nav.surface.consent",)
    object Data : NavSurface(
        id = "data", label = "Data", icon = CIRISIcons.pkg,
        children = listOf(Audit, Consent),
        labelKey = "nav.surface.data",)

    object Trust : NavSurface("trust", "Trust", CIRISIcons.shield,
        labelKey = "nav.surface.trust",)

    object Wallet : NavSurface("wallet", "Wallet", CIRISIcons.keySecure,
        labelKey = "nav.surface.wallet",)
    object Billing : NavSurface(
        id = "billing", label = "Billing", icon = CIRISIcons.wallet,
        children = listOf(Wallet),
        labelKey = "nav.surface.billing",)

    // ═══════════════════════════════════════════════════════════════════════════
    // Commons group — 5 UX-facing CEG 0.6 cohort scopes (per CEG §02 grammar:137).
    // The 7 → 5 fold: self / family / community / affiliations are 1:1; species +
    // planet + federation merge into Global Commons. See `CohortScope.kt` for the
    // mapping rationale. Phase A (2026-05-31): all 5 render LayerHubScreen with
    // section stubs (Identities · Trust · Policies) pinned to EDGE_PEERRESOLVER.
    // Phase B folds the existing Network federation hub into LayerGlobalCommons.
    // ═══════════════════════════════════════════════════════════════════════════

    /** Self — the agent itself. Implicit in the user's mental model. */
    object LayerAgent : NavSurface(
        id = "layer-agent", label = "Agent (Self)", icon = CIRISIcons.person,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        labelKey = "commons.layer.agent.title",
    )

    // ── Surfaces folded onto scale layers below (was the standalone Federation
    // group, deleted 2.9.6). Defined before the Layer* parents that nest them.

    object Participate : NavSurface(
        id = "participate", label = "Participate", icon = CIRISIcons.add,
        gate = SubstrateGate.NODECORE_NEEDS,
        labelKey = "commons.federation.participate.title",
    )
    object EnvironmentGraph : NavSurface(
        // Ungated 2.9.6 — routes to the live EnvironmentInfo screen
        // (/v1/memory?scope=environment). The cohort-overlay extension remains
        // future work; the base environment view ships now.
        id = "environment-graph", label = "Environment Graph", icon = CIRISIcons.snapshot,
        labelKey = "commons.federation.environment_graph.title",
    )
    object Delegation : NavSurface(
        id = "delegation", label = "Delegation", icon = CIRISIcons.send,
        gate = SubstrateGate.PERSIST_DELEGATES_TO,
        labelKey = "commons.federation.delegation.title",
    )
    object Constitutional : NavSurface(
        id = "constitutional", label = "Constitutional", icon = CIRISIcons.instructions,
        gate = SubstrateGate.REGISTRY_ACCORD_HOLDER,
        labelKey = "commons.federation.constitutional.title",
    )

    /** Other CIRIS occurrences sharing the operator's identity. */
    object LayerFamily : NavSurface(
        id = "layer-family", label = "Family", icon = CIRISIcons.home,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        children = listOf(Delegation),
        labelKey = "commons.layer.family.title",
    )

    /** One home channel / Discord guild / household — locally-trusted peers. */
    object LayerLocalCommunity : NavSurface(
        id = "layer-local-community", label = "Local Community", icon = CIRISIcons.location,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        labelKey = "commons.layer.local_community.title",
    )

    /** Cross-community affinity groups the agent has joined (CEG affiliations). */
    object LayerGlobalCommunities : NavSurface(
        id = "layer-global-communities", label = "Global Communities", icon = CIRISIcons.shield,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        children = listOf(Participate),
        labelKey = "commons.layer.global_communities.title",
    )

    /** The federation as the universal layer (folds species + planet + federation). */
    object LayerGlobalCommons : NavSurface(
        id = "layer-global-commons", label = "Global Commons", icon = CIRISIcons.globe,
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        children = listOf(EnvironmentGraph, Constitutional),
        labelKey = "commons.layer.global_commons.title",
    )

    // ═══════════════════════════════════════════════════════════════════════════
    // Client group — multi-agent + interface
    // ═══════════════════════════════════════════════════════════════════════════

    object AgentsList : NavSurface(
        id = "agents-list", label = "Agents", icon = CIRISIcons.identity,
        gate = SubstrateGate.POST_SUBSTRATE_SUBSTITUTION,
        labelKey = "nav.surface.agents_list",)
    object ClientInterface : NavSurface("client-interface", "Interface", CIRISIcons.home,
        labelKey = "nav.surface.client_interface",)
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
    /**
     * Optional localization key for the group's ALL-CAPS section header. When
     * set the sidebar resolves `localizedString(labelKey)` and falls back to
     * [label] if the locale has no entry. Per 2.9.4 release-prep: every group
     * carries one.
     */
    val labelKey: String? = null,
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
        labelKey = "nav.group.agent",)

val MANAGE_GROUP = NavGroup(
    id = "manage",
    label = "Manage",
    icon = CIRISIcons.handler,
    surfaces = listOf(
        NavSurface.HealthReputation,
        NavSurface.Users,
        NavSurface.Adapters,
        // Phase B (2026-05-31): NavSurface.Network removed — federation
        // transport substrate now lives under COMMONS_GROUP as
        // NavSurface.LayerGlobalCommons.
        NavSurface.Data,            // + Audit, Consent
        NavSurface.Trust,
        NavSurface.Billing,         // + Wallet
    ),
        labelKey = "nav.group.manage",)

/**
 * The 5 CEG 0.6 cohort scopes (folded 7 → 5; see [CohortScope.kt]). Each surface
 * is a LayerHubScreen showing Identities · Trust · Policies at that scope. Phase A
 * lands the scaffolding; Phase B folds existing Network federation surface into
 * LayerGlobalCommons.
 */
val COMMONS_GROUP = NavGroup(
    id = "commons-layers",
    label = "Commons",
    icon = CIRISIcons.globe,
    accentHex = "#C96A38", // CIRISColors.BusTool — shares the federation accent
    surfaces = listOf(
        NavSurface.LayerAgent,
        NavSurface.LayerFamily,
        NavSurface.LayerLocalCommunity,
        NavSurface.LayerGlobalCommunities,
        NavSurface.LayerGlobalCommons,
    ),
        labelKey = "nav.group.commons_layers",)

// FEDERATION_GROUP deleted 2.9.6 — it duplicated COMMONS_GROUP (same domain,
// same accent/icon, sliced by feature instead of by scale). Its surfaces folded
// onto the scale layers: Participate → Global Communities, Delegation → Family,
// EnvironmentGraph + Constitutional → Global Commons (as children). "The Commons"
// (redundant with LayerGlobalCommons) and "Trust Topology" (subsumed by the
// per-scope Trust sections + NetworkTrustGraph) were removed entirely.

val CLIENT_GROUP = NavGroup(
    id = "client",
    label = "Client",
    icon = CIRISIcons.home,
    surfaces = listOf(
        NavSurface.AgentsList,
        NavSurface.ClientInterface,
    ),
        labelKey = "nav.group.client",)

/** All groups in display order. The scale-organized Commons group absorbs what
 *  used to be the separate Federation group (deleted 2.9.6). */
val EPISTEMIC_NAV_GROUPS = listOf(AGENT_GROUP, MANAGE_GROUP, COMMONS_GROUP, CLIENT_GROUP)

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
