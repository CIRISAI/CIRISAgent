package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for **node-ownership claim, driven through the LOCAL node** —
 * `POST {localNodeUrl}/v1/setup/claim-remote`.
 *
 * ARCHITECTURE: the app is a NODE. It runs a local ciris-server with the full
 * substrate (JCS canonicalization + hybrid signing + the federation Engine). To
 * claim ownership of a remote/target node, the app does NOT build or sign
 * anything in Kotlin — it simply hands its LOCAL node the target's NodeCode + the
 * one-time claim PIN + the cohort scope. The local node then, IN ITS SUBSTRATE:
 *
 *  1. decodes the NodeCode,
 *  2. builds the owner-binding `delegates_to(user → target, infra:*)`,
 *  3. JCS-canonicalizes + HYBRID-SIGNS it with the owner's federation identity,
 *  4. POSTs the signed artifact to the target node's `/v1/setup/root`.
 *
 * The app therefore holds NO federation keys and performs NO federation crypto.
 * This is a plain UNSIGNED localhost call; the local node authenticates the
 * operator via the normal session.
 *
 * Node-side source of truth: `claim-remote` handler in CIRISServer.
 */
@Serializable
data class ClaimRemoteRequest(
    /**
     * The target node's full `CIRIS-V1-...` NodeCode string. The LOCAL node
     * decodes it to learn the target's identity + address, then builds and signs
     * the owner-binding delegation against it.
     */
    @SerialName("node_code")
    val nodeCode: String,
    /**
     * One-time **claim PIN** the operator reads off the TARGET node's console at
     * first-run. The local node forwards it inside the signed claim it POSTs to
     * the target's `/v1/setup/root`; the target rejects a wrong/expired PIN.
     */
    @SerialName("claim_pin")
    val claimPin: String,
    /**
     * The **cohort scope** the owner is adding the target node to — one of
     * `"self"` | `"family"` | `"community"`. Required; a missing/invalid value is
     * rejected by the local node (`400`).
     */
    @SerialName("cohort_scope")
    val cohortScope: String,
)

/**
 * Response of `POST {localNodeUrl}/v1/setup/claim-remote`.
 *
 * Surfaced verbatim by the claim UI. On success the local node has built, signed,
 * and delivered the owner-binding delegation to the target, which bound the owner
 * as ROOT and bridged the [role] (e.g. `SYSTEM_ADMIN`).
 */
@Serializable
data class ClaimRemoteResponse(
    /** The target node's `wa_id` that was claimed. */
    @SerialName("wa_id")
    val waId: String? = null,
    /** The owner federation identity that claimed it (`key_id`). */
    @SerialName("identity_key_id")
    val identityKeyId: String? = null,
    /** The bridged API role on the target — `SYSTEM_ADMIN` on success. */
    val role: String? = null,
    /** Error string when the claim was rejected (non-2xx bodies). */
    val error: String? = null,
)
