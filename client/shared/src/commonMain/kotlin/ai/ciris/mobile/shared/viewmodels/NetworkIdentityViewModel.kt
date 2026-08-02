package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.models.federation.FederationIdentityResponse
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
 *  - [federationId]: persist's full identity aggregate (Federation ID card).
 *
 * Three round-trips per [load] / [refresh] — each is allowed to fail
 * independently (the others still render).
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

    /**
     * Persist's full federation identity aggregate (Federation ID card).
     * Best-effort companion fetch: null while loading OR when the
     * backend reports 503 (persist identity still initializing) — the
     * card renders an "initializing" state for both, and failures here
     * never raise the screen-level error banner.
     */
    private val _federationId = MutableStateFlow<FederationIdentityResponse?>(null)
    val federationId: StateFlow<FederationIdentityResponse?> = _federationId.asStateFlow()

    /**
     * The bound OWNER's fed-ID key_id (the human's identity, e.g.
     * `eric-moore-v1-<fp>`) — projected from the local node's
     * `delegates_to(user → node)` owner-binding via `GET /v1/setup/owned-nodes`
     * (`owner` field). This is DISTINCT from [identity]'s `signer_key_id`, which
     * is the NODE's own federation signer key. The Identity header shows this as
     * the primary "your fed-ID" and falls back to the node key when null (the
     * node is still unclaimed / pre-claim).
     */
    private val _ownerKeyId = MutableStateFlow<String?>(null)
    val ownerKeyId: StateFlow<String?> = _ownerKeyId.asStateFlow()

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
                // Best-effort: returns null on 503 (persist identity
                // still initializing); other failures are logged but
                // never raise the error banner — the Federation ID card
                // simply stays in its "initializing" state.
                runCatching { apiClient.getFederationIdentityAggregate() }
                    .onSuccess { _federationId.value = it }
                    .onFailure { e ->
                        PlatformLogger.e(tag, "getFederationIdentityAggregate failed: ${e.message}", e)
                    }
                // Best-effort: the bound owner's fed-ID key_id (the human). Null
                // when the node is unclaimed; failures never raise the banner —
                // the header simply falls back to showing the node key.
                runCatching { apiClient.getOwnedNodes().owner }
                    .onSuccess { _ownerKeyId.value = it }
                    .onFailure { e ->
                        PlatformLogger.e(tag, "getOwnedNodes (owner) failed: ${e.message}", e)
                    }
            } finally {
                _loading.value = false
            }
        }
    }
}
