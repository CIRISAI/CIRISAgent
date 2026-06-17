package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for the **first-run ROOT claim** — `POST /v1/setup/root`.
 *
 * Node-side source of truth: `SetupRootRequest` / `SetupRootResponse` in
 * `CIRISServer/src/auth/bootstrap.rs`.
 *
 * The founder becomes `SYSTEM_ADMIN` on a FRESH node (no ROOT yet) by claiming
 * it. Three independent gates apply server-side:
 *
 *  1. **First-run only** — `409 Conflict` once a ROOT exists (no re-claim).
 *  2. **Signature** — the body is `x-ciris-*` hybrid-signed (the same verifier
 *     self-login uses); that federation identity is bound as ROOT. This is the
 *     CLAIM AUTHORITY and needs the hardware-rooted identity from the
 *     FEDERATION_IDENTITY_SETUP step.
 *  3. **NodeCode identity-pin (CEG §0.10)** — the claim MUST carry THIS node's
 *     own NodeCode (or its decoded `key_id` + `pubkey_ed25519_base64`); the node
 *     verifies the pin matches its real steward identity before admitting the
 *     claim, proving the founder reached the INTENDED node (not a spoof). The pin
 *     rides inside the signed body, so it is signature-bound.
 *
 * The client supplies the pin from the NodeCode it decoded + identity-pinned
 * during connect (change #2) — preferring the full [nodeCode] string.
 */
@Serializable
data class SetupRootRequest(
    /**
     * The node's full `CIRIS-V1-...` NodeCode string (dashes/whitespace/case
     * tolerated). When present the node decodes it and it takes precedence over
     * the [keyId] / [pubkeyEd25519Base64] pair.
     */
    @SerialName("node_code")
    val nodeCode: String? = null,
    /** The node's federation `key_id` — the decoded pin half (alternative to [nodeCode]). */
    @SerialName("key_id")
    val keyId: String? = null,
    /** The node's raw Ed25519 pubkey (base64) — the other decoded pin half. */
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String? = null,
)

/**
 * Response of `POST /v1/setup/root` (HTTP `201 Created` on success).
 *
 * On success the claiming federation identity is bound as ROOT and bridged to
 * the [role] `SYSTEM_ADMIN` — the founder can now run the consent-objects card.
 */
@Serializable
data class SetupRootResponse(
    /** The ROOT `wa_id` that was claimed. */
    @SerialName("wa_id")
    val waId: String? = null,
    /** The claiming federation identity (`key_id`). */
    @SerialName("identity_key_id")
    val identityKeyId: String? = null,
    /** The bridged API role — `SYSTEM_ADMIN` on success. */
    val role: String? = null,
    /** Error string when the node rejected the claim (non-2xx bodies). */
    val error: String? = null,
)
