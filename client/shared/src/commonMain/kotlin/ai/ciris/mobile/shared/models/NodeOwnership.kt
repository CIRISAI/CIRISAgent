package ai.ciris.mobile.shared.models

/**
 * The **three** ownership states of the local node (FSD FIRST_RUN_WIZARD_2.9.14 §5).
 *
 * The 2.9.13 first-run loop exists because the startup router knew only *fresh* vs
 * *claimed*. There is a third, named state — a node owned the LEGACY way (a ROOT
 * WaCert with a password/OAuth login but NO fed-ID `delegates_to` owner-binding).
 * A router that collapses it into *fresh* sends it to Setup, where `setup/root`
 * 409s, and the wizard loops.
 *
 * The two signals, and why each one:
 *
 * * **owner-binding** — `GET {node}/v1/setup/owned-nodes` (`owner`). Reads the CEG
 *   graph via `admission::owner_of` and is the SAME predicate `require_owner_bound`
 *   consults at every owner-gated operation (config writes, peering, commons, mesh
 *   config, peers). This is the only signal that GATES anything.
 * * **ROOT WaCert** — `GET {node}/v1/setup/status` (`setup_required`). The NODE's
 *   own first-run predicate: `false` ⇒ an active ROOT WA exists. Note this is the
 *   *node's* answer, not the brain's — the brain's `/v1/setup/status` asks whether
 *   `.env` exists and the two can legitimately disagree.
 *
 * `GET /v1/auth/owner-hint` is deliberately NOT used here. It reads the WaCert auth
 * store to render a GDPR-masked "welcome back" string on the login screen. It gates
 * nothing, and routing on it is what produced the loop.
 */
enum class NodeOwnership {
    /** No ROOT WaCert and no owner-binding — a genuinely fresh node. Route: Setup. */
    FRESH,

    /**
     * ROOT WaCert present, owner-binding ABSENT. The node is owned, just not rooted
     * on a fed-ID. Route: Login (the existing password/OAuth login still works),
     * then `POST /v1/self/upgrade-owner` — never Setup.
     */
    LEGACY_OWNED,

    /** Owner-binding present. Route: Login. */
    CLAIMED;

    /**
     * True when the node already has an owner in EITHER form, i.e. it is configured
     * and first-run must not be re-entered.
     */
    val isOwned: Boolean get() = this != FRESH

    /** True when the node needs `POST /v1/self/upgrade-owner` to be re-rooted on a fed-ID. */
    val needsOwnerUpgrade: Boolean get() = this == LEGACY_OWNED
}

/**
 * Derive the [NodeOwnership] state from the two node-side signals.
 *
 * @param ownerBinding the `owner` field of `GET /v1/setup/owned-nodes` — the bound
 *        owner's fed-ID key_id, or null/blank when the node carries no owner-binding.
 * @param nodeSetupRequired the `setup_required` field of the NODE's
 *        `GET /v1/setup/status` — false ⇒ an active ROOT WaCert exists. Pass null
 *        when the probe failed; an unknown WaCert state degrades to [FRESH] only
 *        when there is also no owner-binding, which is the pre-2.9.14 behaviour.
 */
fun nodeOwnershipFrom(ownerBinding: String?, nodeSetupRequired: Boolean?): NodeOwnership = when {
    !ownerBinding.isNullOrBlank() -> NodeOwnership.CLAIMED
    nodeSetupRequired == false -> NodeOwnership.LEGACY_OWNED
    else -> NodeOwnership.FRESH
}
