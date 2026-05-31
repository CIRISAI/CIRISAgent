package ai.ciris.mobile.shared.models.federation

import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Trust state of a federation peer — locked vocabulary mirroring the
 * Edge crate's ``EdgePeerTrust`` enum so the agent and Edge agree on
 * the wire. Wire format: lowercase strings.
 *
 * Backend source of truth: ``PeerTrustState`` in
 * ``ciris_engine/schemas/runtime/canonical_peer.py``.
 */
@Serializable
enum class PeerTrustState {
    @SerialName("trusted")
    TRUSTED,

    @SerialName("untrusted")
    UNTRUSTED,

    @SerialName("blocked")
    BLOCKED,

    @SerialName("unknown")
    UNKNOWN,
    ;

    /** Backend wire serialization (lowercase). */
    val wire: String get() = when (this) {
        TRUSTED -> "trusted"
        UNTRUSTED -> "untrusted"
        BLOCKED -> "blocked"
        UNKNOWN -> "unknown"
    }

    companion object {
        /** Parse a backend trust string, defaulting to [UNKNOWN] on miss. */
        fun fromWire(s: String?): PeerTrustState = when (s?.lowercase()) {
            "trusted" -> TRUSTED
            "untrusted" -> UNTRUSTED
            "blocked" -> BLOCKED
            else -> UNKNOWN
        }
    }
}

/**
 * Per-peer ``(icon, fg, bg)`` appearance tuple — owned by the local
 * user, never trusted from the wire. Sideband convention.
 *
 * All three fields are nullable: ``null`` means the UI uses defaults.
 *
 * Backend source of truth: ``PeerAppearance`` in
 * ``ciris_engine/schemas/runtime/canonical_peer.py``.
 */
@Serializable
data class PeerAppearance(
    val icon: String? = null,
    @SerialName("fg_color")
    val fgColor: String? = null,
    @SerialName("bg_color")
    val bgColor: String? = null,
)

/**
 * The persisted local state for a single federation peer (canonical or
 * organic). Mirrors backend ``LocalPeerState``.
 *
 * - ``canonical = true``: peer ships with the agent (constants or
 *   federation directory) and is reseeded on every boot. User-set
 *   fields ([trust], [appearance], [aliasOverride], [notes]) are
 *   preserved across reseed.
 * - ``canonical = false``: organic peer discovered via ANNOUNCE or
 *   added from a NodeCode. Defaults to [PeerTrustState.UNKNOWN].
 *
 * No online/offline flag is tracked — only [lastSeen]. Reticulum
 * convention: presence is a property of an attempted contact, not a
 * polled status. Render-time concern.
 *
 * ``keyId`` is the full 32-char hash form. Do not truncate at the
 * model layer.
 */
@Serializable
data class LocalPeerState(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    val canonical: Boolean,
    val trust: PeerTrustState,
    @SerialName("first_seen")
    val firstSeen: Instant,
    val appearance: PeerAppearance? = null,
    @SerialName("alias_override")
    val aliasOverride: String? = null,
    val notes: String? = null,
    @SerialName("last_seen")
    val lastSeen: Instant? = null,
)
