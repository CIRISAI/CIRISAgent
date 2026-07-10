package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One LIVE delegation the owner has granted — an active device-authorization
 * grant (`dgrant:`). The owner authorized a client (agent) to act on their behalf
 * with attribution. Source: ``GET /v1/auth/device/grants`` on the local node.
 */
@Serializable
data class DelegationDto(
    /** The actor the delegation is attributed to (e.g. ``claude-agent``). */
    @SerialName("client_id")
    val clientId: String,
    /** The granted scope (e.g. ``owner:act-on-behalf``). */
    val scope: String,
    /**
     * Unix-epoch seconds the delegated token expires. **Nullable** — the node
     * omits this for a non-expiring (durable) grant, so a required field broke
     * `listDelegations` deserialization (`MissingFieldException`). `null` = no expiry.
     */
    @SerialName("expires_at")
    val expiresAt: Long? = null,
)

@Serializable
data class DelegationsResponse(
    val grants: List<DelegationDto> = emptyList(),
)

/**
 * The result of creating a delegation the owner hands to an agent — the response
 * of ``POST /v1/auth/device/delegate``. The owner gives the agent the
 * [claimUrl] + [pin]; the agent claims it (``POST /v1/auth/device/claim``) to
 * receive its delegated token. The PIN expires after [expiresIn] seconds.
 */
@Serializable
data class CreateDelegationResponse(
    /** The relative claim endpoint the agent posts the PIN to. */
    @SerialName("claim_url")
    val claimUrl: String,
    /** The short human-handover secret (e.g. ``ABCD-1234``). */
    val pin: String,
    /** The client/actor id the delegation is attributed to (e.g. ``ciris-...``). */
    @SerialName("client_id")
    val clientId: String,
    /** The granted scope (e.g. ``["owner:act-on-behalf"]``). */
    val scope: List<String> = emptyList(),
    /** Seconds until the PIN expires. */
    @SerialName("expires_in")
    val expiresIn: Long = 0,
    /**
     * The grant's full characteristics, when the node echoes them. The
     * ``/delegate`` offer body itself is unchanged, but the node MAY carry a
     * ``delegation`` object (and an ``x-ciris-delegation`` response header) — the
     * SAME shape the agent later reads back off ``/claim`` and ``/token``. Populated
     * best-effort by the API client so the owner can review what they just granted.
     */
    val delegation: GrantCharacteristics? = null,
)

/**
 * The constraints an owner attaches to a delegation grant to NARROW what the
 * delegate may do. Sent on ``POST /v1/auth/device/delegate`` (issue) and
 * ``POST /v1/auth/device/approve`` (approve — tighten-only, never widen).
 *
 * Tri-state [actionsAllow]:
 *  - ``null`` (absent) — every owner verb is permitted (unconstrained).
 *  - ``[]`` (empty) — read-only: NO verbs permitted.
 *  - non-empty — only the listed verbs are permitted.
 *
 * [actionsDeny] ALWAYS overrides [actionsAllow]. [goal] is free-text intent.
 */
@Serializable
data class DelegationConstraints(
    @SerialName("actions_allow")
    val actionsAllow: List<String>? = null,
    @SerialName("actions_deny")
    val actionsDeny: List<String> = emptyList(),
    val goal: String? = null,
) {
    /** True when nothing is set — i.e. an unconstrained (full-authority) grant. */
    fun isUnconstrained(): Boolean =
        actionsAllow == null && actionsDeny.isEmpty() && goal.isNullOrBlank()
}

/**
 * The full characteristics of a delegation grant, surfaced on every use — the
 * ``delegation`` object embedded in ``/v1/auth/device/{claim,token}`` bodies and
 * the compact ``x-ciris-delegation`` response header. Read-only transparency for
 * the consumer: who acts, for whom, with what authority, and under what limits.
 */
@Serializable
data class GrantCharacteristics(
    /** The agent key_id the grant is attributed to. */
    val actor: String? = null,
    /** The owner wa_id the delegate acts on behalf of. */
    @SerialName("on_behalf_of")
    val onBehalfOf: String? = null,
    /** The owner's federation key_id. */
    @SerialName("owner_key_id")
    val ownerKeyId: String? = null,
    /** The role the delegate assumes (e.g. ``SYSTEM_ADMIN``). */
    val role: String? = null,
    /** The granted scope (e.g. ``["owner:act-on-behalf"]``). */
    val scope: List<String> = emptyList(),
    /** The owner's free-text goal for the grant, if any. */
    val purpose: String? = null,
    /** Whether the delegate may itself sub-delegate (always ``false`` today). */
    @SerialName("sub_delegation")
    val subDelegation: Boolean = false,
    /** Unix-epoch seconds the grant was issued. */
    @SerialName("issued_at")
    val issuedAt: Long? = null,
    /** Unix-epoch seconds the grant expires. */
    @SerialName("expires_at")
    val expiresAt: Long? = null,
    /** Seconds until the grant expires (relative). */
    @SerialName("expires_in")
    val expiresIn: Long? = null,
    /** The attestation id backing the grant, if any. */
    @SerialName("attestation_id")
    val attestationId: String? = null,
    /** Allowed verbs — ``null`` = all, ``[]`` = read-only, else the subset. */
    @SerialName("actions_allow")
    val actionsAllow: List<String>? = null,
    /** Denied verbs — always override [actionsAllow]. */
    @SerialName("actions_deny")
    val actionsDeny: List<String> = emptyList(),
)

/**
 * One owner-gated capability verb a delegate can be granted (or denied).
 * [verb] is the wire token; [label] is the human-readable name.
 */
data class CapabilityVerb(val verb: String, val label: String)

/**
 * The capability-verb catalog. [selectable] are the owner-gated ops a delegate
 * CAN be granted — the multi-select universe for allow / deny lists.
 * [neverDelegatable] are refused for any delegate by the server unconditionally;
 * they are shown only as an informational note, never as selectable chips.
 */
object CapabilityCatalog {
    val selectable: List<CapabilityVerb> = listOf(
        CapabilityVerb("claim_remote", "Claim remote nodes"),
        CapabilityVerb("announce", "Announce to federation"),
        CapabilityVerb("peer", "Set up peering"),
        CapabilityVerb("config_write", "Change configuration"),
        CapabilityVerb("set_age", "Set age"),
        CapabilityVerb("mesh_relay", "Relay to owned nodes"),
    )

    /** Verbs the server always refuses for a delegate (delegate / wipe / accord halt). */
    val neverDelegatable: List<String> = listOf("delegate", "wipe", "accord_halt")

    /** Human label for a verb, falling back to the raw token for unknown verbs. */
    fun labelFor(verb: String): String =
        selectable.firstOrNull { it.verb == verb }?.label ?: verb
}
