package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.FederationEventStream
import ai.ciris.mobile.shared.models.federation.FederationChannel
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * VM for ``NetworkDiagnosticsScreen`` — subscribes to
 * ``FederationChannel.ALL`` and exposes filter chips + free-text
 * search + an expand-on-tap raw-payload viewer.
 *
 * The filtered events derivation is intentionally kept as a pure
 * helper ([filterEvents]) so unit tests can drive it directly without
 * touching Compose state.
 */
class NetworkDiagnosticsViewModel(
    apiClient: CIRISApiClient,
    streamFactory: (CIRISApiClient) -> FederationEventStream = { FederationEventStream(it) },
) : FederationStreamViewModel(apiClient, streamFactory) {

    override val tag: String = "NetworkDiagnosticsViewModel"

    override fun channel(): FederationChannel = FederationChannel.ALL

    override fun bufferCapacity(): Int = 300

    private val _channelFilters = MutableStateFlow<Set<FederationChannel>>(
        // All Edge sub-channels enabled by default. Don't include ALL
        // because it's the meta-subscription, not a sub-channel any
        // envelope ever reports.
        setOf(
            FederationChannel.ANNOUNCES,
            FederationChannel.FEED,
            FederationChannel.INTERFACE_EVENTS,
            FederationChannel.LINK_EVENTS,
            FederationChannel.PATH_EVENTS,
            FederationChannel.RESOURCE_EVENTS,
        ),
    )
    val channelFilters: StateFlow<Set<FederationChannel>> = _channelFilters.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _expandedEventIds = MutableStateFlow<Set<String>>(emptySet())
    val expandedEventIds: StateFlow<Set<String>> = _expandedEventIds.asStateFlow()

    /** Per-channel counters for the top stats strip. */
    private val _channelCounters = MutableStateFlow<Map<FederationChannel, Int>>(emptyMap())
    val channelCounters: StateFlow<Map<FederationChannel, Int>> = _channelCounters.asStateFlow()

    fun toggleChannelFilter(channel: FederationChannel) {
        val current = _channelFilters.value
        _channelFilters.value = if (channel in current) current - channel else current + channel
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
    }

    fun toggleExpanded(eventId: String) {
        val current = _expandedEventIds.value
        _expandedEventIds.value = if (eventId in current) current - eventId else current + eventId
    }

    override fun onEnvelopeReceived(envelope: FederationEventEnvelope) {
        super.onEnvelopeReceived(envelope)
        FederationChannel.fromPathSegment(envelope.channel)?.let { ch ->
            val counts = _channelCounters.value.toMutableMap()
            counts[ch] = (counts[ch] ?: 0) + 1
            _channelCounters.value = counts
        }
    }

    /**
     * Apply the current channel/search filters to a snapshot of events.
     * Pure function — easy to unit-test without spinning up the VM.
     */
    fun filterEvents(
        all: List<FederationEventEnvelope>,
        filters: Set<FederationChannel>,
        query: String,
    ): List<FederationEventEnvelope> {
        val q = query.trim().lowercase()
        return all.filter { envelope ->
            val ch = FederationChannel.fromPathSegment(envelope.channel)
            val channelOk = ch == null || ch in filters
            val messageOk = if (q.isEmpty()) {
                true
            } else {
                val msg = envelope.payload["message"]?.jsonPrimitive?.contentOrNull?.lowercase()
                val eventType = envelope.eventType.lowercase()
                (msg?.contains(q) == true) || eventType.contains(q)
            }
            channelOk && messageOk
        }
    }
}
