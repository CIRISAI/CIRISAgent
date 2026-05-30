package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationMetricsResponse
import ai.ciris.mobile.shared.viewmodels.BaseFederationViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * VM for the Network → Queue sub-screen.
 *
 * Polls ``GET /v1/federation/metrics`` every 5 s (faster than Interfaces
 * because durable queue depth can change between thoughts) and exposes
 * the aggregate counters the queue screen renders:
 *
 *  - [queueDepth] — sum across all queue kinds in
 *    ``durable_queue_depth``
 *  - [envelopesSent] / [envelopesReceived] — session totals across all
 *    envelope kinds
 *  - [sendFailures] / [verifyFailures] — total failure counters; non-zero
 *    is the UI's signal to flip the failure-section cards red
 *  - [bytesIn] / [bytesOut] — session throughput totals for the
 *    sparkline-ish summary at the bottom
 *
 * The polling interval is intentionally cheap-side rather than chatty;
 * the snapshot endpoint is O(1) on the backend so 5 s is a safe default.
 */
class NetworkQueueViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkQueueVM"

    private val _metrics = MutableStateFlow<FederationMetricsResponse?>(null)
    val metrics: StateFlow<FederationMetricsResponse?> = _metrics.asStateFlow()

    private var autoRefreshJob: Job? = null

    val queueDepth: Long get() = _metrics.value?.getQueueDepth() ?: 0L
    val envelopesSent: Long get() = _metrics.value?.getEnvelopesSent() ?: 0L
    val envelopesReceived: Long get() = _metrics.value?.getEnvelopesReceived() ?: 0L
    val sendFailures: Long get() = _metrics.value?.getSendFailures() ?: 0L
    val verifyFailures: Long get() = _metrics.value?.getVerifyFailures() ?: 0L
    val bytesIn: Long get() = _metrics.value?.getBytesIn() ?: 0L
    val bytesOut: Long get() = _metrics.value?.getBytesOut() ?: 0L

    fun refreshNow() {
        launchApi(
            operation = "getFederationMetrics",
            block = { apiClient.getFederationMetrics() },
            onSuccess = { _metrics.value = it },
        )
    }

    fun startAutoRefresh(intervalMs: Long = 5_000L) {
        autoRefreshJob?.cancel()
        autoRefreshJob = viewModelScope.launch {
            while (isActive) {
                runApi("getFederationMetrics:auto") {
                    apiClient.getFederationMetrics()
                }?.let { _metrics.value = it }
                delay(intervalMs)
            }
        }
    }

    fun stopAutoRefresh() {
        autoRefreshJob?.cancel()
        autoRefreshJob = null
    }

    override fun onCleared() {
        stopAutoRefresh()
        super.onCleared()
    }
}
