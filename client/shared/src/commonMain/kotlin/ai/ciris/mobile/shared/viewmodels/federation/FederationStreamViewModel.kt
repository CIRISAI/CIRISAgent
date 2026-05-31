package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.FederationEventStream
import ai.ciris.mobile.shared.models.federation.FederationChannel
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.viewmodels.BaseFederationViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Federation-stream connection state surfaced to the UI as a single
 * traffic-light. Keeps the screen-level "should I show the green dot?"
 * decision out of compose code.
 */
enum class FederationStreamConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    PAUSED,
    ERROR,
}

/**
 * Shared scaffolding for the three SSE-stream federation sub-screens
 * (Announces, Paths, Diagnostics).
 *
 * Owns the subscribe/collect lifecycle, the bounded newest-first ring
 * buffer of envelopes, and the pause/resume/clear/reconnect control
 * surface. Subclasses only need to declare the [channel] they want and
 * (optionally) override [bufferCapacity].
 *
 * Lifecycle notes:
 *  - The collector job is cancelled on [pause], [stop], [reconnect],
 *    and [onCleared] so paused VMs don't keep an idle TCP socket open.
 *  - [resume] / [reconnect] re-launch with the last seen ``event_id``
 *    so the bridge can emit a ``resume-notice`` if it cares to.
 *  - On ``resume-notice`` we wipe the local buffer (replay is NOT
 *    supported on the Edge side) and surface a banner via
 *    [resumeNoticeShown].
 */
abstract class FederationStreamViewModel(
    apiClient: CIRISApiClient,
    private val streamFactory: (CIRISApiClient) -> FederationEventStream = { FederationEventStream(it) },
) : BaseFederationViewModel(apiClient) {

    private val stream: FederationEventStream by lazy { streamFactory(apiClient) }

    private val _events = MutableStateFlow<List<FederationEventEnvelope>>(emptyList())
    val events: StateFlow<List<FederationEventEnvelope>> = _events.asStateFlow()

    private val _paused = MutableStateFlow(false)
    val paused: StateFlow<Boolean> = _paused.asStateFlow()

    private val _connectionState = MutableStateFlow(FederationStreamConnectionState.DISCONNECTED)
    val connectionState: StateFlow<FederationStreamConnectionState> = _connectionState.asStateFlow()

    private val _resumeNoticeShown = MutableStateFlow(false)
    val resumeNoticeShown: StateFlow<Boolean> = _resumeNoticeShown.asStateFlow()

    private val _lastEventId = MutableStateFlow<String?>(null)
    val lastEventId: StateFlow<String?> = _lastEventId.asStateFlow()

    private var collectJob: Job? = null

    /** Sub-channel this VM subscribes to. Read once per [connect] call. */
    protected abstract fun channel(): FederationChannel

    /** Maximum events retained in the local newest-first ring buffer. */
    protected open fun bufferCapacity(): Int = 200

    /** Begin (or rebegin) the subscription. Idempotent. */
    fun connect() {
        if (collectJob?.isActive == true) {
            PlatformLogger.d(tag, "connect: already active")
            return
        }
        startSubscription(useLastEventId = false)
    }

    /** Pause the stream — cancels the collector and stops appending. */
    fun pause() {
        _paused.value = true
        collectJob?.cancel()
        collectJob = null
        _connectionState.value = FederationStreamConnectionState.PAUSED
        PlatformLogger.i(tag, "paused")
    }

    /** Resume from pause — re-subscribes with the last seen event id. */
    fun resume() {
        _paused.value = false
        startSubscription(useLastEventId = true)
    }

    /** Wipe local buffer. Does NOT change connection state. */
    fun clear() {
        _events.value = emptyList()
        _resumeNoticeShown.value = false
    }

    /** Re-subscribe after error or screen reuse, sending Last-Event-ID. */
    fun reconnect() {
        collectJob?.cancel()
        collectJob = null
        startSubscription(useLastEventId = true)
    }

    /** Acknowledge the resume-notice banner so the UI can hide it. */
    fun acknowledgeResumeNotice() {
        _resumeNoticeShown.value = false
    }

    /** Called from the screen's DisposableEffect when leaving the screen. */
    fun stop() {
        collectJob?.cancel()
        collectJob = null
        _connectionState.value = FederationStreamConnectionState.DISCONNECTED
    }

    /**
     * Append one envelope to the buffer. Open so subclasses (e.g. the
     * Diagnostics VM) can attach per-channel counters.
     */
    protected open fun onEnvelopeReceived(envelope: FederationEventEnvelope) {
        appendEvent(envelope)
    }

    private fun startSubscription(useLastEventId: Boolean) {
        val resumeId = _lastEventId.value.takeIf { useLastEventId }
        _connectionState.value = FederationStreamConnectionState.CONNECTING
        _error.value = null

        collectJob = viewModelScope.launch {
            try {
                stream.subscribe(channel(), resumeId)
                    .catch { e ->
                        PlatformLogger.w(tag, "stream error: ${e.message}")
                        _error.value = e.message ?: e::class.simpleName
                        _connectionState.value = FederationStreamConnectionState.ERROR
                    }
                    .onCompletion {
                        if (!isActive) {
                            // cancelled by pause/stop/reconnect — nothing to do.
                        } else if (_connectionState.value == FederationStreamConnectionState.CONNECTED) {
                            _connectionState.value = FederationStreamConnectionState.DISCONNECTED
                        }
                    }
                    .collect { envelope -> dispatch(envelope) }
            } catch (e: Exception) {
                PlatformLogger.w(tag, "subscribe failed: ${e.message}")
                _error.value = e.message ?: e::class.simpleName
                _connectionState.value = FederationStreamConnectionState.ERROR
            }
        }
    }

    private fun dispatch(envelope: FederationEventEnvelope) {
        _lastEventId.value = envelope.eventId

        when (envelope.eventType) {
            "connected" -> {
                _connectionState.value = FederationStreamConnectionState.CONNECTED
            }
            "resume-notice" -> {
                _resumeNoticeShown.value = true
                // Replay not supported — drop SSE-derived state and let the
                // UI re-fetch via REST if there's a snapshot endpoint.
                _events.value = emptyList()
            }
            else -> {
                if (_connectionState.value != FederationStreamConnectionState.CONNECTED) {
                    _connectionState.value = FederationStreamConnectionState.CONNECTED
                }
                onEnvelopeReceived(envelope)
            }
        }
    }

    protected fun appendEvent(envelope: FederationEventEnvelope) {
        val current = _events.value
        val next = (listOf(envelope) + current).take(bufferCapacity())
        _events.value = next
    }

    override fun onCleared() {
        collectJob?.cancel()
        super.onCleared()
    }
}
