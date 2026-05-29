package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.AgentMode
import ai.ciris.mobile.shared.models.AgentModeChangeResult
import ai.ciris.mobile.shared.models.AgentModeStatus
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * NetworkViewModel — drives the Network hub screen + agent-mode selector.
 *
 * Owns the GET/PUT round-trip for `/v1/system/agent-mode` plus the
 * Edge-federation address surface. The hub's live-stats strip stays in
 * placeholder mode until Edge 1.0 exposes the corresponding FFI surface;
 * we model that as the absence of values rather than fake numbers.
 */
class NetworkViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "NetworkViewModel"
    }

    // ─── State ───────────────────────────────────────────────────────────────

    private val _status = MutableStateFlow<AgentModeStatus?>(null)
    val status: StateFlow<AgentModeStatus?> = _status.asStateFlow()

    private val _mode = MutableStateFlow(AgentMode.PROXY)
    val mode: StateFlow<AgentMode> = _mode.asStateFlow()

    /** Edge federation address (32-char hex). Sourced from the existing
     *  NetworkSnapshot mock until PyEdge FFI lands. */
    private val _federationAddress = MutableStateFlow<String?>(null)
    val federationAddress: StateFlow<String?> = _federationAddress.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Set when a mode-change requires a restart so the UI can warn. */
    private val _restartPending = MutableStateFlow(false)
    val restartPending: StateFlow<Boolean> = _restartPending.asStateFlow()

    /** Surface a typed insufficient-disk failure so the UI can render an
     *  actionable message inline with the SERVER button. */
    private val _insufficientDisk = MutableStateFlow<AgentModeChangeResult.InsufficientDisk?>(null)
    val insufficientDisk: StateFlow<AgentModeChangeResult.InsufficientDisk?> = _insufficientDisk.asStateFlow()

    // ─── Actions ─────────────────────────────────────────────────────────────

    /** Load the current agent-mode + disk facts. Idempotent + safe to retry. */
    fun loadAgentMode() {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            try {
                val s = apiClient.getAgentMode()
                _status.value = s
                _mode.value = s.mode
                PlatformLogger.i(TAG, "loaded agent-mode: ${s.mode.wire}, server_eligible=${s.serverEligible}")
            } catch (e: Exception) {
                _error.value = e.message ?: e::class.simpleName ?: "unknown error"
                PlatformLogger.e(TAG, "loadAgentMode failed: ${e.message}", e)
            } finally {
                _loading.value = false
            }
        }
    }

    /**
     * Switch the global [AgentMode]. Returns synchronously — callers should
     * observe [insufficientDisk], [restartPending], or [error] for the typed
     * outcome rather than awaiting a result.
     */
    fun setMode(target: AgentMode) {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            _insufficientDisk.value = null
            try {
                when (val result = apiClient.setAgentMode(target)) {
                    is AgentModeChangeResult.Success -> {
                        _status.value = result.status
                        _mode.value = result.status.mode
                        _restartPending.value = result.requiresRestart
                        PlatformLogger.i(TAG, "set mode → ${target.wire}, restart=${result.requiresRestart}")
                    }
                    is AgentModeChangeResult.InsufficientDisk -> {
                        _insufficientDisk.value = result
                        PlatformLogger.w(
                            TAG,
                            "insufficient disk for SERVER: available=${result.availableBytes}, required=${result.requiredBytes}",
                        )
                    }
                    is AgentModeChangeResult.Failure -> {
                        _error.value = result.message
                        PlatformLogger.e(TAG, "set mode failed: ${result.message}")
                    }
                }
            } finally {
                _loading.value = false
            }
        }
    }

    /** Acknowledge the restart-pending notice (dialog dismissed). */
    fun clearRestartPending() {
        _restartPending.value = false
    }

    /** Acknowledge an insufficient-disk error after the user sees it. */
    fun clearInsufficientDisk() {
        _insufficientDisk.value = null
    }

    /** Acknowledge a transient error after the user sees it. */
    fun clearError() {
        _error.value = null
    }

    /** Provisional setter for the local federation address — wired off the
     *  existing NetworkSnapshot mock so the identity card renders before
     *  Edge 1.0 exposes a real signer_key_id endpoint. */
    fun setFederationAddress(address: String?) {
        _federationAddress.value = address
    }
}
