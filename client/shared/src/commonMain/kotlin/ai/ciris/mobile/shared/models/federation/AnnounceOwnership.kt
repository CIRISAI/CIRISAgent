package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire model for **opting IN to the federation** — `POST {localNodeUrl}/v1/federation/announce`.
 *
 * Ownership is SELF-SCOPED by default (private; full personal/self-family use; the
 * owner's nodes sync across their own devices but are invisible to the federation).
 * To participate in the community the owner OPTS IN: the local node promotes the
 * owner-binding self→FEDERATION and flips `net.announce_ownership=true` so the node
 * advertises its identity. Owner-gated (SYSTEM_ADMIN session) + loopback-only.
 *
 * The call is idempotent and takes effect on the node's NEXT boot.
 *
 * Node-side source of truth: the `/v1/federation/announce` handler in CIRISServer.
 */
@Serializable
data class AnnounceOwnershipResponse(
    /** The owner federation identity that was promoted (`key_id`). */
    val owner: String? = null,
    /** The cohort scope the ownership now advertises (e.g. `FEDERATION`). */
    @SerialName("cohort_scope")
    val cohortScope: String? = null,
    /** The attestation id of the promoted owner-binding, when one was written. */
    @SerialName("promoted_attestation_id")
    val promotedAttestationId: String? = null,
    /** Always true on success — the node's identity announce is now enabled. */
    @SerialName("announce_ownership")
    val announceOwnership: Boolean = false,
    /** When the change takes effect — `"next_boot"`. */
    @SerialName("announce_takes_effect")
    val announceTakesEffect: String? = null,
)
