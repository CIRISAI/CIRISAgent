package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Response body for ``GET /v1/federation/peers``.
 *
 * Backend source of truth: ``FederationPeerListResponse`` in
 * ``ciris_engine/schemas/runtime/federation_api.py``.
 */
@Serializable
data class FederationPeerListResponse(
    val peers: List<LocalPeerState> = emptyList(),
    val total: Int = 0,
)

/**
 * Per-transport reachability snapshot for a single peer.
 *
 * Mirrors the Rust-side tuple ``(ratio, last_ok_ts)``:
 *  - [ratio]: rolling-window successes/attempts in ``[0.0, 1.0]``.
 *  - [lastOkTs]: wall-clock millisecond timestamp of the most recent
 *    successful attempt, ``0`` if none yet.
 *
 * Backend source of truth: ``EdgeReachabilityEntry``.
 */
@Serializable
data class EdgeReachabilityEntry(
    val ratio: Double,
    @SerialName("last_ok_ts")
    val lastOkTs: Long,
)

/**
 * Per-medium reachability map for a peer.
 *
 * An EMPTY [byMedium] map means "no measurement yet recorded" — UI
 * MUST render "unknown" rather than "0.0%". This is a load-bearing
 * distinction; do not collapse to a default 0.0 value.
 *
 * Mediums are open-ended strings (``reticulum-rs``, ``http``, future
 * transports), so the map type is `String -> EdgeReachabilityEntry`.
 *
 * Backend source of truth: ``EdgePeerReachability``.
 */
@Serializable
data class EdgePeerReachability(
    @SerialName("by_medium")
    val byMedium: Map<String, EdgeReachabilityEntry> = emptyMap(),
)

/**
 * Response body for ``GET /v1/federation/peers/{key_id}``.
 *
 * Backend source of truth: ``FederationPeerDetailResponse``.
 *
 * [reachability] is nullable because the backend reserves the option
 * of returning local state without Edge data; today the route returns
 * 503 instead, so when status==200 reachability is always populated.
 */
@Serializable
data class FederationPeerDetailResponse(
    val peer: LocalPeerState,
    val reachability: EdgePeerReachability? = null,
)

/**
 * Signal-style Short Authentication String for verifying a peer key.
 *
 * Both [words] and [digits] are derived deterministically by Edge from
 * the ``(local_pub, peer_pub, protocol-constant)`` tuple — sorted so
 * both sides of the call see the same value.
 *
 * Backend source of truth: ``FederationPeerSASResponse``.
 */
@Serializable
data class FederationPeerSASResponse(
    val words: List<String>,
    val digits: String,
    @SerialName("key_id")
    val keyId: String,
)

/**
 * Body for ``PUT /v1/federation/peers/{key_id}/trust``.
 */
@Serializable
data class FederationPeerTrustUpdateRequest(
    val trust: PeerTrustState,
)

/**
 * Body for ``PUT /v1/federation/peers/{key_id}/appearance``.
 */
@Serializable
data class FederationPeerAppearanceUpdateRequest(
    val appearance: PeerAppearance,
)
