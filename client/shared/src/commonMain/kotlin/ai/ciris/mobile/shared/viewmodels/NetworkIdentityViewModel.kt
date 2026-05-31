package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.models.federation.NodeCodeShareResponse
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the Network → Identity sub-screen.
 *
 * State:
 *  - [identity]: federation identity card (signer_key_id, crate, capabilities).
 *  - [nodeCode]: shareable NodeCode for inviting peers.
 *
 * Two round-trips per [load] / [refresh] — they run in parallel and either
 * one is allowed to fail independently (the other still renders).
 *
 * No write actions on this screen: identity is sourced from Edge, NodeCode
 * is a derived view of it; the only user actions are copy-to-clipboard
 * which the screen handles via [LocalClipboardManager] without touching
 * the ViewModel.
 */
class NetworkIdentityViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkIdentityVM"

    private val _identity = MutableStateFlow<FederationIdentity?>(null)
    val identity: StateFlow<FederationIdentity?> = _identity.asStateFlow()

    private val _nodeCode = MutableStateFlow<NodeCodeShareResponse?>(null)
    val nodeCode: StateFlow<NodeCodeShareResponse?> = _nodeCode.asStateFlow()

    /** Initial load — call from a LaunchedEffect on first composition. */
    fun load() {
        refresh()
    }

    /**
     * Refresh both round-trips. Failures land in [error] (the
     * BaseFederationViewModel surface) but identity vs nodeCode failures
     * are independent — we don't blank the visible card when only the
     * other endpoint flaked.
     */
    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            try {
                runCatching { apiClient.getFederationIdentity() }
                    .onSuccess { _identity.value = it }
                    .onFailure { e ->
                        PlatformLogger.e(tag, "getFederationIdentity failed: ${e.message}", e)
                        _error.value = e.message ?: "identity fetch failed"
                    }
                runCatching { apiClient.getMyNodeCode() }
                    .onSuccess { _nodeCode.value = it }
                    .onFailure { e ->
                        PlatformLogger.e(tag, "getMyNodeCode failed: ${e.message}", e)
                        // Only overwrite error if identity didn't already report one
                        if (_error.value == null) {
                            _error.value = e.message ?: "node code fetch failed"
                        }
                    }
            } finally {
                _loading.value = false
            }
        }
    }
}
