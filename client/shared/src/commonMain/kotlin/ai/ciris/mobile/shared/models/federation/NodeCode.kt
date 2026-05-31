package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Response body for ``GET /v1/system/peers/my-node-code``.
 *
 * Backend source of truth: ``NodeCodeShareResponse`` in
 * ``ciris_engine/schemas/runtime/node_code.py``.
 *
 *  - [code]: dashed display form (``CIRIS-V1-ABCD-...``) for users.
 *  - [qrPayload]: same content without dashes — for QR generators
 *    that prefer a continuous alphanumeric string.
 *  - [keyId]: local agent's federation ``signer_key_id``.
 *  - [aliasHint]: optional alias the local user supplied for
 *    themselves; round-tripped through the code so the receiver's UI
 *    can show a useful display name on first contact.
 */
@Serializable
data class NodeCodeShareResponse(
    val code: String,
    @SerialName("qr_payload")
    val qrPayload: String,
    @SerialName("key_id")
    val keyId: String,
    @SerialName("alias_hint")
    val aliasHint: String? = null,
)

/**
 * Request body for ``POST /v1/system/peers/add-from-code``.
 *
 * Whitespace and dashes are tolerated server-side — callers can pass
 * the dashed display form or the continuous QR payload.
 */
@Serializable
data class NodeCodeAddRequest(
    val code: String,
)

/**
 * Response body for ``POST /v1/system/peers/add-from-code``.
 *
 * Returns the resulting [LocalPeerState] (organic, ``trust=UNKNOWN``)
 * plus an idempotency signal: [wasAlreadyPresent] is true when the
 * peer was already in local state at call time. Either case is
 * success — the caller decides whether to surface "already added".
 */
@Serializable
data class NodeCodeAddResponse(
    val peer: LocalPeerState,
    @SerialName("was_already_present")
    val wasAlreadyPresent: Boolean,
)
