package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * A saved fabric **node profile**.
 *
 * In the CIRIS fabric there is no "server" — every occurrence is a node, and
 * "connecting to a remote" simply means reaching another node and presenting
 * the identity/consent the owner's key roots. A [NodeProfile] is the
 * persisted handle the user holds to switch between the nodes they participate
 * in (node A, node B, …) without re-typing URLs or re-authenticating.
 *
 * Persisted (encrypted) via [ai.ciris.mobile.shared.services.NodeProfileStore].
 * The [sessionToken] is the bearer token already minted for this node; it is
 * sensitive and lives only in [ai.ciris.mobile.shared.platform.SecureStorage].
 */
@Serializable
data class NodeProfile(
    /** Stable id for this profile (derived from baseUrl at creation time). */
    val id: String,
    /** Human-friendly node name shown in the switcher (e.g. "Home", "Work"). */
    val name: String,
    /** Reachable base URL of the node, e.g. "http://192.168.1.20:8080". */
    val baseUrl: String,
    /** Bearer session token for this node, if the user has authenticated. */
    val sessionToken: String? = null,
    /** Epoch millis this profile was last switched-to; drives "most recent" ordering. */
    val lastUsedEpochMs: Long = 0L,
    /**
     * Pinned federation `key_id` of the node (CEG §0.10). Set when this profile
     * was added via a NodeCode and identity-pinned: the node served back a
     * NodeCode whose key_id matched the scanned code. Used to re-pin on
     * reconnect and to supply the NodeCode pin on a first-run ROOT claim.
     */
    val pinnedKeyId: String? = null,
    /** Pinned raw Ed25519 pubkey (base64) of the node — the other half of the pin. */
    val pinnedPubkeyBase64: String? = null,
) {
    /** True if this profile carries an identity pin (added + verified via NodeCode). */
    val isPinned: Boolean get() = !pinnedKeyId.isNullOrBlank() && !pinnedPubkeyBase64.isNullOrBlank()

    val isAuthenticated: Boolean get() = !sessionToken.isNullOrBlank()

    companion object {
        /**
         * Derive a stable id from a base URL. Normalises the same way
         * ServerConnectionViewModel does so the same node never produces two
         * profiles.
         */
        fun idFor(baseUrl: String): String =
            baseUrl.trim().trimEnd('/').lowercase()
    }
}
