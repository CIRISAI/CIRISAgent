package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationPeerDetailResponse
import ai.ciris.mobile.shared.models.federation.FederationPeerSASResponse
import ai.ciris.mobile.shared.models.federation.PeerAppearance
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the Network → Peer Detail sub-screen.
 *
 * Lives as long as the screen does — recreated for each visited keyId.
 *
 * Owns the per-peer detail card, the SAS modal, and the local-only
 * appearance editor draft. Trust changes and appearance saves round-trip
 * through the API and reload the detail on success.
 */
class NetworkPeerDetailViewModel(
    apiClient: CIRISApiClient,
    val keyId: String,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkPeerDetailVM"

    // ─── Detail + SAS ───────────────────────────────────────────────────────

    private val _detail = MutableStateFlow<FederationPeerDetailResponse?>(null)
    val detail: StateFlow<FederationPeerDetailResponse?> = _detail.asStateFlow()

    private val _sas = MutableStateFlow<FederationPeerSASResponse?>(null)
    val sas: StateFlow<FederationPeerSASResponse?> = _sas.asStateFlow()

    private val _sasModalOpen = MutableStateFlow(false)
    val sasModalOpen: StateFlow<Boolean> = _sasModalOpen.asStateFlow()

    private val _sasLoading = MutableStateFlow(false)
    val sasLoading: StateFlow<Boolean> = _sasLoading.asStateFlow()

    // ─── Trust state ────────────────────────────────────────────────────────

    private val _trustChangeInFlight = MutableStateFlow(false)
    val trustChangeInFlight: StateFlow<Boolean> = _trustChangeInFlight.asStateFlow()

    private val _pendingTrust = MutableStateFlow<PeerTrustState?>(null)
    val pendingTrust: StateFlow<PeerTrustState?> = _pendingTrust.asStateFlow()

    // ─── Appearance editor ──────────────────────────────────────────────────

    private val _appearanceExpanded = MutableStateFlow(false)
    val appearanceExpanded: StateFlow<Boolean> = _appearanceExpanded.asStateFlow()

    private val _appearanceDraft = MutableStateFlow(PeerAppearance())
    val appearanceDraft: StateFlow<PeerAppearance> = _appearanceDraft.asStateFlow()

    private val _appearanceSaving = MutableStateFlow(false)
    val appearanceSaving: StateFlow<Boolean> = _appearanceSaving.asStateFlow()

    // ─── Actions ────────────────────────────────────────────────────────────

    fun load() {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            runApi("getFederationPeer") {
                apiClient.getFederationPeer(keyId)
            }?.let { resp ->
                _detail.value = resp
                _appearanceDraft.value = resp.peer.appearance ?: PeerAppearance()
            }
        }
    }

    /**
     * Apply a trust change. BLOCKED requires confirm-first: the screen
     * stages the change via [requestTrust] which routes through [pendingTrust]
     * for a confirmation dialog; non-BLOCKED states apply directly via
     * [setTrust].
     */
    fun requestTrust(target: PeerTrustState) {
        if (target == PeerTrustState.BLOCKED) {
            _pendingTrust.value = target
        } else {
            setTrust(target)
        }
    }

    fun confirmPendingTrust() {
        val target = _pendingTrust.value ?: return
        _pendingTrust.value = null
        setTrust(target)
    }

    fun cancelPendingTrust() {
        _pendingTrust.value = null
    }

    private fun setTrust(target: PeerTrustState) {
        viewModelScope.launch {
            _trustChangeInFlight.value = true
            _error.value = null
            try {
                val updated = apiClient.setFederationPeerTrust(keyId, target)
                PlatformLogger.i(tag, "trust set → ${target.wire} for $keyId")
                // Patch the local detail with the updated peer state.
                _detail.value = _detail.value?.copy(peer = updated)
            } catch (e: Exception) {
                val msg = e.message ?: e::class.simpleName ?: "unknown error"
                PlatformLogger.e(tag, "setFederationPeerTrust failed: $msg", e)
                _error.value = msg
            } finally {
                _trustChangeInFlight.value = false
            }
        }
    }

    fun showSAS() {
        _sasModalOpen.value = true
        if (_sas.value != null) return
        viewModelScope.launch {
            _sasLoading.value = true
            try {
                val resp = apiClient.getFederationPeerSAS(keyId)
                _sas.value = resp
            } catch (e: Exception) {
                val msg = e.message ?: e::class.simpleName ?: "unknown error"
                PlatformLogger.e(tag, "getFederationPeerSAS failed: $msg", e)
                _error.value = msg
            } finally {
                _sasLoading.value = false
            }
        }
    }

    fun hideSAS() {
        _sasModalOpen.value = false
    }

    fun toggleAppearanceExpanded() {
        _appearanceExpanded.value = !_appearanceExpanded.value
    }

    fun setAppearance(appearance: PeerAppearance) {
        _appearanceDraft.value = appearance
    }

    fun saveAppearance() {
        viewModelScope.launch {
            _appearanceSaving.value = true
            _error.value = null
            try {
                val updated = apiClient.setFederationPeerAppearance(keyId, _appearanceDraft.value)
                PlatformLogger.i(tag, "appearance saved for $keyId")
                _detail.value = _detail.value?.copy(peer = updated)
                _appearanceExpanded.value = false
            } catch (e: Exception) {
                val msg = e.message ?: e::class.simpleName ?: "unknown error"
                PlatformLogger.e(tag, "setFederationPeerAppearance failed: $msg", e)
                _error.value = msg
            } finally {
                _appearanceSaving.value = false
            }
        }
    }
}
