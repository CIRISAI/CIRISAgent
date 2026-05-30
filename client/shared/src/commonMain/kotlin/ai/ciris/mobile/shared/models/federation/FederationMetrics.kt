package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Edge metrics snapshot returned by ``GET /v1/federation/metrics``.
 *
 * Wraps the Rust-side ``Edge.metrics_snapshot()`` result. Each family
 * is a string-keyed map; the family keys themselves are stable across
 * Edge releases (typed below), but the sub-keys (envelope kinds,
 * transport mediums, failure reasons) are open-ended — new Edge
 * releases add new sub-keys without bumping the API contract.
 *
 * Backend source of truth: ``FederationMetricsResponse`` in
 * ``ciris_engine/schemas/runtime/federation_api.py``. The pydantic
 * model exposes one field per family (flat shape); we mirror that
 * flat shape exactly so kotlinx-serialization round-trips against the
 * backend's ``model_dump_json()`` output.
 *
 * For consumers that prefer a generic family-keyed view (e.g. a
 * "renderer that knows family names from config"), call [families].
 * Internal counters are typed as [Long] so 32-bit accumulators don't
 * truncate at the multi-day mark; the reachability ratio family uses
 * [Double].
 */
@Serializable
data class FederationMetricsResponse(
    @SerialName("envelopes_sent_total")
    val envelopesSentTotal: Map<String, Long> = emptyMap(),
    @SerialName("envelopes_received_total")
    val envelopesReceivedTotal: Map<String, Long> = emptyMap(),
    @SerialName("send_failures_total")
    val sendFailuresTotal: Map<String, Long> = emptyMap(),
    @SerialName("verify_failures_total")
    val verifyFailuresTotal: Map<String, Long> = emptyMap(),
    @SerialName("durable_queue_depth")
    val durableQueueDepth: Map<String, Long> = emptyMap(),
    @SerialName("transport_bytes_in_total")
    val transportBytesInTotal: Map<String, Long> = emptyMap(),
    @SerialName("transport_bytes_out_total")
    val transportBytesOutTotal: Map<String, Long> = emptyMap(),
    @SerialName("peer_reachability_ratio")
    val peerReachabilityRatio: Map<String, Double> = emptyMap(),
    @SerialName("inline_text_subscriber_count")
    val inlineTextSubscriberCount: Long = 0L,
) {

    /** Total envelopes sent across all envelope kinds. */
    fun getEnvelopesSent(): Long = envelopesSentTotal.values.sum()

    /** Total envelopes received across all envelope kinds. */
    fun getEnvelopesReceived(): Long = envelopesReceivedTotal.values.sum()

    /** Total send failures across all transport/reason combos. */
    fun getSendFailures(): Long = sendFailuresTotal.values.sum()

    /** Total verify failures across all reasons. */
    fun getVerifyFailures(): Long = verifyFailuresTotal.values.sum()

    /** Total queue depth across all queue kinds. */
    fun getQueueDepth(): Long = durableQueueDepth.values.sum()

    /** Total inbound transport bytes across all transports. */
    fun getBytesIn(): Long = transportBytesInTotal.values.sum()

    /** Total outbound transport bytes across all transports. */
    fun getBytesOut(): Long = transportBytesOutTotal.values.sum()

    /**
     * Mean reachability ratio across all observed (peer, medium) pairs
     * in ``[0.0, 1.0]``, or ``null`` when nothing has been measured
     * yet. Distinct from the empty-map "unknown" case which becomes
     * ``null`` here — same load-bearing distinction as
     * [EdgePeerReachability.byMedium].
     */
    fun meanReachabilityRatio(): Double? {
        if (peerReachabilityRatio.isEmpty()) return null
        return peerReachabilityRatio.values.average()
    }

    /**
     * Family-keyed view of the metrics for renderers that don't want
     * to switch on each typed field. Counter families are coerced to
     * Double so all families share a value type; consumers that need
     * integer accuracy should reach for the typed [Map] field
     * directly (the typed fields preserve [Long] precision).
     */
    fun families(): Map<String, Map<String, Double>> = mapOf(
        FAMILY_ENVELOPES_SENT to envelopesSentTotal.mapValues { it.value.toDouble() },
        FAMILY_ENVELOPES_RECEIVED to envelopesReceivedTotal.mapValues { it.value.toDouble() },
        FAMILY_SEND_FAILURES to sendFailuresTotal.mapValues { it.value.toDouble() },
        FAMILY_VERIFY_FAILURES to verifyFailuresTotal.mapValues { it.value.toDouble() },
        FAMILY_DURABLE_QUEUE_DEPTH to durableQueueDepth.mapValues { it.value.toDouble() },
        FAMILY_TRANSPORT_BYTES_IN to transportBytesInTotal.mapValues { it.value.toDouble() },
        FAMILY_TRANSPORT_BYTES_OUT to transportBytesOutTotal.mapValues { it.value.toDouble() },
        FAMILY_PEER_REACHABILITY_RATIO to peerReachabilityRatio,
    )

    companion object {
        const val FAMILY_ENVELOPES_SENT = "envelopes_sent_total"
        const val FAMILY_ENVELOPES_RECEIVED = "envelopes_received_total"
        const val FAMILY_SEND_FAILURES = "send_failures_total"
        const val FAMILY_VERIFY_FAILURES = "verify_failures_total"
        const val FAMILY_DURABLE_QUEUE_DEPTH = "durable_queue_depth"
        const val FAMILY_TRANSPORT_BYTES_IN = "transport_bytes_in_total"
        const val FAMILY_TRANSPORT_BYTES_OUT = "transport_bytes_out_total"
        const val FAMILY_PEER_REACHABILITY_RATIO = "peer_reachability_ratio"
    }
}
