package ai.ciris.mobile.shared.models.federation

import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Stable mobile-facing wire shape for one Edge subscription event.
 *
 * Every SSE ``data:`` frame on ``GET /v1/federation/events/{channel}``
 * JSON-encodes one of these. The envelope's identity fields are
 * statically typed; the channel-specific projection lives in
 * [payload]. Mobile decodes [payload] per channel via its own
 * per-channel domain model — see ``FederationChannel`` for the
 * channel list.
 *
 * Backend source of truth: ``FederationEventEnvelope`` in
 * ``ciris_engine/schemas/runtime/federation_events.py``.
 *
 * Per-channel ``event_type`` taxonomy:
 *  - ``announces`` / ``link_events`` / ``interface_events`` /
 *    ``path_events`` / ``resource_events`` / ``all``: NetworkEvent
 *    kinds — ``announce_received``, ``announce_sent``,
 *    ``path_discovered``, ``path_lost``, ``link_established``,
 *    ``link_dropped``, ``transport_up``, ``transport_down``,
 *    ``key_rotated``, ``signature_failure``, ``policy_block``,
 *    ``lagged``.
 *  - ``feed``: VerifiedFeedSubscription ``message_type`` (e.g.
 *    ``InlineText``, ``DurableInlineText``).
 *
 * Special non-Edge envelopes the SSE bridge emits:
 *  - ``event_type="resume-notice"`` — payload describes that replay
 *    is not supported; client should resync via a non-streaming
 *    endpoint. Surfaced when ``Last-Event-ID`` was set on reconnect.
 *  - ``event_type="connected"`` — initial handshake frame.
 *  - ``event_type="error"`` / ``stream-closed`` — terminal frames;
 *    [FederationEventStream] surfaces these as Flow errors.
 */
@Serializable
data class FederationEventEnvelope(
    @SerialName("event_id")
    val eventId: String,
    val channel: String,
    val timestamp: Instant,
    @SerialName("event_type")
    val eventType: String,
    /**
     * Channel-specific projection. Kept as a generic [JsonObject] so
     * the envelope stays stable across Edge releases; each consumer
     * screen decodes the slice it cares about with its own per-channel
     * model.
     */
    val payload: JsonObject = JsonObject(emptyMap()),
)

/**
 * Federation event SSE channels exposed by ``GET /v1/federation/events/{channel}``.
 *
 * Backend source of truth: channel constants in
 * ``ciris_engine/schemas/runtime/federation_events.py``.
 */
enum class FederationChannel(val pathSegment: String) {
    ANNOUNCES("announces"),
    FEED("feed"),
    INTERFACE_EVENTS("interface_events"),
    LINK_EVENTS("link_events"),
    PATH_EVENTS("path_events"),
    RESOURCE_EVENTS("resource_events"),
    ALL("all"),
    ;

    companion object {
        /** Lookup by wire path segment; returns ``null`` on miss. */
        fun fromPathSegment(s: String?): FederationChannel? =
            entries.firstOrNull { it.pathSegment == s }
    }
}
