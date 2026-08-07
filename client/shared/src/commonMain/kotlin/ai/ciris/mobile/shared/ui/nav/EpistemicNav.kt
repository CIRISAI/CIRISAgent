package ai.ciris.mobile.shared.ui.nav

import androidx.compose.ui.graphics.vector.ImageVector
import ai.ciris.mobile.shared.CIRISBuild
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
    // Node form: Services is a node-infra keeper; the agent-only Tools child is
    // dropped from the surfaced tree (the Tools object remains defined for
    // route compatibility).
    object Services : NavSurface(
        id = "services", label = "Services", icon = CIRISIcons.bus,
        labelKey = "nav.surface.services",)

    object Logs : NavSurface("logs", "Logs", CIRISIcons.log,
        labelKey = "nav.surface.logs",)

    /**
     * Transport — node transports + serial LoRa (RNode) radio configuration. A
     * node-infra surface: shows the node's current Reticulum transport/peers
     * (read-only) and an owner-gated radio config form persisting `net.radio.*`
     * config. Radio activation is desktop-only. Live (no gate).
     */
    object Transport : NavSurface("transport", "Transport", CIRISIcons.bus,
        labelKey = "nav.surface.transport",)
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
     * Network (CIRISEdge operator view) — THIS node's local edge facts:
     * federation signer_key_id, agent mode (client/proxy/server), disk budget,
     * data dir. Distinct from the Commons → Global Commons federation/peers
     * SOCIAL view; this is the operator-infra slice. Live (no gate).
     */
    object NetworkOps : NavSurface("network-ops", "Network", CIRISIcons.bus,
        labelKey = "nav.surface.network_ops",)

    /**
     * Storage (CIRISPersist operator view) — the graph store + on-disk facts:
     * total nodes, nodes by type/scope, recent activity, storage location.
     * Live (no gate).
     */
    object Storage : NavSurface("storage", "Storage", CIRISIcons.pkg,
        labelKey = "nav.surface.storage",)

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

    /**
     * Nodes — the first-class node-management surface (promoted from the
     * in-page node-switcher dropdown). Lists/adds/edits/removes the saved fabric
     * [ai.ciris.mobile.shared.models.NodeProfile]s and switches the active node.
     * Live (no gate) — it manages locally-held profiles.
     */
    object Nodes : NavSurface("nodes", "Nodes", CIRISIcons.bus,
        labelKey = "nav.surface.nodes",)

    /**
     * Manage Consent — view + manage the consent objects this device holds
     * (bilateral consent:replication peering today; user-data consent:state via
     * the existing Consent surface). Live (no gate).
     */
    object ManageConsent : NavSurface("manage-consent", "Manage Consent", CIRISIcons.lock,
        labelKey = "nav.surface.manage_consent",)

    /**
     * Contacts / Identities — browsable list of known federation identities
     * (the local node's peer store). Used both as a first-class explore surface
     * and as the picker when delegating to an existing fed-ID. Live (no gate).
     */
    object Contacts : NavSurface("contacts", "Contacts", CIRISIcons.person,
        labelKey = "nav.surface.contacts",)

    /**
     * Delegations — who the owner has authorized to act on their behalf (active
     * device-authorization grants), plus approve-a-new / revoke. The
     * human-consent gate for an agent acting on-behalf-of. Live (no gate).
     */
    object Delegations : NavSurface("delegations", "Delegations", CIRISIcons.keySecure,
        labelKey = "nav.surface.delegations",)

    /**
     * Identity Management — manage your self fed-ID + the roster of devices
     * (occurrences) bound to it, add a new device, revoke a lost / stolen one, or
     * "log in as yourself on another device". Laptop-loss resilience (§5.6.8.8 /
     * §11.7). The app holds no keys; the node signs. Live (no gate).
     */
    object IdentityManagement : NavSurface("identity-management", "My Identity", CIRISIcons.identity,
        labelKey = "nav.surface.identity_management",)

    /**
     * Accord — the HUMANITY_ACCORD constitutional surface (CIRISServer #41). The
     * entrenched accord family + its `quorum:2/3` kill-switch consensus protocol,
     * the FIPS / hardware-attested holder roster, and the pending invocations
     * (with the CC 4.2.1 per-kind visual treatment) the local holder may concur
     * on. Read view + owner-gated concur; the app holds no keys. Live (no gate).
     */
    object Accord : NavSurface("accord", "Trust Root", CIRISIcons.shield,
        labelKey = "nav.surface.accord",)

    /**
     * Provision Accord Holder — the foolproof guided flow (CIRISServer #41, the
     * safe-mesh custody floor). A would-be accord holder mints their portable-2FA
     * HUMANITY_ACCORD identity from an already-FIPS-approved FIPS YubiKey + a
     * chosen ML-DSA USB path, producing the holder record + custody attestation
     * the node owner then registers. Drives the loopback-only
     * `POST /v1/accord/provision-holder`; the app holds no keys (the node does the
     * crypto). Reachable from the Accord screen + the Manage group. Live (no gate).
     */
    object ProvisionAccordHolder : NavSurface(
        id = "provision-accord-holder", label = "Provision Holder", icon = CIRISIcons.keySecure,
        labelKey = "nav.surface.provision_accord_holder",
    )

    /**
     * Accord Genesis Ceremony — the foolproof guided wizard (CIRISServer #41) that
     * stands up a NEW mesh's 2-of-3 human kill-switch: 3 humans, each a primary
     * SEAT + a cold SPARE (6 keys). Provisions + registers each key, then the 3
     * primaries cosign the family envelope and the node assembles the genesis (the
     * cold-start bake artifact). Reachable from the Accord screen ONLY when no
     * accord family exists yet. Drives the loopback + owner-gated accord endpoints;
     * the app holds no keys (the re-inserted YubiKey signs). Live (no gate).
     */
    object AccordCeremony : NavSurface(
        id = "accord-ceremony", label = "Genesis Ceremony", icon = CIRISIcons.shield,
        labelKey = "nav.surface.accord_ceremony",
    )

    // ═══════════════════════════════════════════════════════════════════════════
    // Safety group — the holistic SAFETY surface (CIRISServer v0.4.6
    // /v1/safety/*). Safety is built in FIRST, ahead of content: a Discord /
    // Facebook / Wikipedia / YouTube superset where moderation + child-safety
    // are first-class fabric primitives, not bolt-ons. Live (no gate) — the
    // node ships the endpoints today; the app only drives the local node.
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Moderation — file a ModerationEvent (`POST /v1/safety/moderation`), see the
     * named-moderator existence status (`GET /v1/safety/named-moderator/{c}`),
     * and the delegable-duty concept. Moderation is a DUTY, not a role.
     */
    object Moderation : NavSurface("moderation", "Moderation", CIRISIcons.handler,
        labelKey = "nav.surface.moderation",)

    /**
     * Child Safety — per-group content watchlist (opt-in, default OFF, NEVER
     * global; `POST/GET /v1/safety/watchlist`) + the protective posture
     * (`GET /v1/safety/status`). Honest framing is load-bearing.
     */
    object ChildSafety : NavSurface("child-safety", "Child Safety", CIRISIcons.shield,
        labelKey = "nav.surface.child_safety",)

    /**
     * Safety (top-level surface) — the umbrella over Moderation + Child Safety.
     * Navigating to the parent routes to its first child (Moderation).
     */
    object Safety : NavSurface(
        id = "safety", label = "Safety", icon = CIRISIcons.shield,
        children = listOf(Moderation, ChildSafety),
        labelKey = "nav.surface.safety",)

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

    /**
     * **Commons** — the reverse-quorum plane a community polices itself with
     * (CIRISServer#367, `src/commons_surface.rs`): raise an objection, see the
     * fold's standing on one action, ballot on what the stewards left open, and
     * dismiss at the cohort's own m-of-n.
     *
     * It sits in the COMMONS group and NOT under Settings/Config, because that
     * is where its authority comes from. The `/v1/admin` routes and `/v1/mesh-config`
     * are authority acting ON a node; this is the commons acting on itself, and
     * one member is enough to raise a brake. The cohorts whose rosters supply
     * the quorum are the layers beside it. Live (no gate).
     */
    object Commons : NavSurface("commons", "Commons", CIRISIcons.handler,
        labelKey = "nav.surface.commons",)

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

/**
 * The node-observation group (was "Agent"). This client is the standalone,
 * AI-free CIRIS node client (agent optional): the pure agent/brain cards
 * (Interact/Sessions, Tickets/Scheduler, Tools, Skills, LLM/Agent settings,
 * the agent task Memory card) are pruned from the nav. The keepers are the
 * generic node-observation + node-infra surfaces:
 *   - GraphMemory (the memory graph) and WiseAuthority (escalations/deferrals)
 *     moved here from the old Agent group.
 *   - Telemetry (+ Logs), Services, and System/Runtime/Config — node-infra,
 *     surfaced directly (previously buried under the agent Settings sub-tree).
 * The dropped NavSurface objects remain defined (route compatibility) but are
 * no longer surfaced in any group.
 */
/**
 * The AGENT group — the agent's own brain cards, re-applied on top of the
 * inherited server (node) nav shell ONLY on the agent build (gated in
 * [EPISTEMIC_NAV_GROUPS] on [CIRISBuild.HAS_AGENT]). This is the FULL agent
 * client = the node client + the agent's cards. The server prunes these pure
 * agent/brain surfaces for its standalone AI-free node build; on the agent build
 * they are surfaced again so the agent's Interact reasoning-stream chat, sessions,
 * tasks/scheduler, tools, task-memory and the agent Settings sub-tree (LLM /
 * System / Runtime / Config / Skills) are reachable. Node-observation infra
 * (GraphMemory, WiseAuthority, Telemetry+Logs, Services, System/Runtime/Config)
 * also lives in the [NODE_GROUP] below; a few surfaces intentionally appear in
 * both — the agent framing (a Settings sub-tree, a Memory→Graph card) alongside
 * the node-infra framing. Defined unconditionally (route/reference stability);
 * only surfaced when HAS_AGENT.
 */
val AGENT_GROUP = NavGroup(
    id = "agent",
    label = "Agent",
    icon = CIRISIcons.thought,
    surfaces = listOf(
        NavSurface.Interact,        // + Sessions (agent chat / reasoning stream)
        NavSurface.Tickets,         // + Scheduler (agent tasks)
        NavSurface.Tools,           // agent tools
        NavSurface.Memory,          // + Graph (agent task memory)
        NavSurface.AgentSettings,   // + LLM, System, Runtime, Config, Skills
    ),
        labelKey = "nav.group.agent",)

val NODE_GROUP = NavGroup(
    id = "node",
    label = "Node",
    icon = CIRISIcons.identity,
    surfaces = listOf(
        NavSurface.GraphMemory,     // memory graph (moved from Agent)
        NavSurface.WiseAuthority,   // escalations / deferrals (moved from Agent)
        NavSurface.Telemetry,       // + Logs (node-infra)
        NavSurface.Transport,       // node transports + LoRa/RNode radio config
        NavSurface.Services,        // node-infra (Tools child dropped)
        NavSurface.System,          // node-infra (lifted out of agent Settings)
        NavSurface.Runtime,         // node-infra (lifted out of agent Settings)
        NavSurface.Config,          // node-infra (lifted out of agent Settings)
    ),
        labelKey = "nav.group.node",)

/**
 * The holistic SAFETY group — safety built in FIRST, ahead of content
 * (CIRISServer v0.4.6, the `/v1/safety/` routes). Placed high in the nav (right after
 * Agent) to reflect that the superset's safety layer is foundational, not a
 * bolt-on. Both leaves ship live (the node has the endpoints; the app drives
 * the local node, no crypto in the app).
 */
val SAFETY_GROUP = NavGroup(
    id = "safety",
    label = "Safety",
    icon = CIRISIcons.shield,
    surfaces = listOf(
        NavSurface.Moderation,
        NavSurface.ChildSafety,
    ),
        labelKey = "nav.group.safety",)

val MANAGE_GROUP = NavGroup(
    id = "manage",
    label = "Manage",
    icon = CIRISIcons.handler,
    surfaces = listOf(
        NavSurface.HealthReputation,
        NavSurface.Contacts,        // known federation identities (peer store browser)
        NavSurface.IdentityManagement, // my self fed-ID + device roster (occurrences)
        NavSurface.Nodes,           // first-class node management (CRUD + switch)
        NavSurface.ManageConsent,   // consent:replication + user-data consent
        NavSurface.Delegations,     // device-auth grants — authorize an agent on-behalf
        NavSurface.Accord,          // HUMANITY_ACCORD — constitutional 2/3 kill-switch
        NavSurface.ProvisionAccordHolder, // mint a portable-2FA accord-holder identity
        NavSurface.Users,
        NavSurface.Adapters,
        // The substrate operator-infra trio: Edge / Verify / Persist.
        NavSurface.NetworkOps,      // Edge — local federation/transport facts
        NavSurface.Trust,           // Verify — attestation ladder (Security)
        NavSurface.Storage,         // Persist — graph store + disk facts
        NavSurface.Data,            // + Audit, Consent
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
    surfaces = buildList {
        // LayerAgent (Agent/Self) — the agent's own self-scope layer hub. Surfaced
        // only on the agent build; dropped from the AI-free node client's nav (the
        // object remains defined for route compatibility).
        if (CIRISBuild.HAS_AGENT) add(NavSurface.LayerAgent)
        add(NavSurface.LayerFamily)
        add(NavSurface.LayerLocalCommunity)
        add(NavSurface.LayerGlobalCommunities)
        add(NavSurface.LayerGlobalCommons)
        // The reverse-quorum plane those rosters are the quorum OF.
        add(NavSurface.Commons)
    },
        labelKey = "nav.group.commons_layers",)

// FEDERATION_GROUP deleted 2.9.6 — it duplicated COMMONS_GROUP (same domain,
// same accent/icon, sliced by feature instead of by scale). Its surfaces folded
// onto the scale layers: Participate → Global Communities, Delegation → Family,
// EnvironmentGraph + Constitutional → Global Commons (as children). "The Commons"
// (redundant with LayerGlobalCommons) and "Trust Topology" (subsumed by the
// per-scope Trust sections + NetworkTrustGraph) were removed entirely.

// CLIENT_GROUP — surfaced only on the agent build (gated in [EPISTEMIC_NAV_GROUPS]
// on [CIRISBuild.HAS_AGENT]). Its surfaces (AgentsList, ClientInterface) are pure
// agent/client cards the server drops for its standalone AI-free node build; on
// the agent build they are surfaced again. Defined unconditionally for
// route/reference stability.
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
 *  used to be the separate Federation group (deleted 2.9.6). The former "Agent"
 *  group is now the node-observation "Node" group.
 *
 *  Agent-only groups (AGENT_GROUP, CLIENT_GROUP) are gated on
 *  [CIRISBuild.HAS_AGENT] — dormant/absent for the AI-free node client, so the
 *  agent's adoption is a single flag flip. Under HAS_AGENT the full agent client
 *  leads with AGENT_GROUP (agent brain cards), followed by the inherited
 *  node-observation NODE_GROUP + the shared Safety / Manage / Commons shells, with
 *  CLIENT_GROUP last. */
val EPISTEMIC_NAV_GROUPS: List<NavGroup> = buildList {
    if (CIRISBuild.HAS_AGENT) add(AGENT_GROUP)
    add(NODE_GROUP)
    add(SAFETY_GROUP)
    add(MANAGE_GROUP)
    add(COMMONS_GROUP)
    if (CIRISBuild.HAS_AGENT) add(CLIENT_GROUP)
}

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
