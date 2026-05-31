package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Filter chip selection for the Network → Peers list.
 *
 * - [ALL]: every peer (canonical + organic, every trust state).
 * - [CANONICAL]: only canonical peers (shipped with the agent).
 * - [TRUSTED] / [UNKNOWN] / [UNTRUSTED] / [BLOCKED]: filter by trust state.
 *
 * The "Show CIRIS infrastructure" toggle is independent from this filter:
 * it toggles whether canonical peers are included alongside organic peers
 * when the filter is not specifically [CANONICAL].
 */
enum class PeerTrustFilter {
    ALL,
    CANONICAL,
    TRUSTED,
    UNKNOWN,
    UNTRUSTED,
    BLOCKED,
    ;

    /** Map the filter to a [PeerTrustState] for the API, or null for ALL/CANONICAL. */
    fun toTrustState(): PeerTrustState? = when (this) {
        TRUSTED -> PeerTrustState.TRUSTED
        UNKNOWN -> PeerTrustState.UNKNOWN
        UNTRUSTED -> PeerTrustState.UNTRUSTED
        BLOCKED -> PeerTrustState.BLOCKED
        ALL, CANONICAL -> null
    }
}

/**
 * Drives the Network → Peers sub-screen.
 *
 * Owns the peer list + Add-Peer bottom sheet state. Peer rows are sorted
 * client-side: canonical first, then by trust priority
 * (TRUSTED > UNKNOWN > UNTRUSTED > BLOCKED), then by lastSeen desc.
 */
class NetworkPeersViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkPeersVM"

    // ─── Peer list ──────────────────────────────────────────────────────────

    private val _peers = MutableStateFlow<List<LocalPeerState>>(emptyList())
    val peers: StateFlow<List<LocalPeerState>> = _peers.asStateFlow()

    private val _filter = MutableStateFlow(PeerTrustFilter.ALL)
    val filter: StateFlow<PeerTrustFilter> = _filter.asStateFlow()

    /** When false, hide canonical (CIRIS-infrastructure) peers from the list. */
    private val _showCirisInfrastructure = MutableStateFlow(true)
    val showCirisInfrastructure: StateFlow<Boolean> = _showCirisInfrastructure.asStateFlow()

    // ─── Add-Peer sheet ─────────────────────────────────────────────────────

    private val _addPeerSheetOpen = MutableStateFlow(false)
    val addPeerSheetOpen: StateFlow<Boolean> = _addPeerSheetOpen.asStateFlow()

    private val _addPeerInput = MutableStateFlow("")
    val addPeerInput: StateFlow<String> = _addPeerInput.asStateFlow()

    private val _addPeerError = MutableStateFlow<String?>(null)
    val addPeerError: StateFlow<String?> = _addPeerError.asStateFlow()

    private val _addPeerInFlight = MutableStateFlow(false)
    val addPeerInFlight: StateFlow<Boolean> = _addPeerInFlight.asStateFlow()

    // ─── Load / filter actions ──────────────────────────────────────────────

    fun load() {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            runApi("listFederationPeers") {
                apiClient.listFederationPeers(
                    canonicalOnly = if (_filter.value == PeerTrustFilter.CANONICAL) true else null,
                    trust = _filter.value.toTrustState(),
                )
            }?.let { resp ->
                _peers.value = sortPeers(applyInfraToggle(resp.peers))
            }
        }
    }

    fun setFilter(f: PeerTrustFilter) {
        _filter.value = f
        refresh()
    }

    fun setShowCirisInfrastructure(show: Boolean) {
        _showCirisInfrastructure.value = show
        // Apply locally — no need to round-trip; the API doesn't know about
        // the "hide CIRIS infrastructure" UX toggle.
        _peers.value = sortPeers(applyInfraToggle(_peers.value))
        // But also refresh so we pull in any canonical peers the list missed.
        if (show) refresh()
    }

    private fun applyInfraToggle(peers: List<LocalPeerState>): List<LocalPeerState> =
        if (_showCirisInfrastructure.value) peers else peers.filterNot { it.canonical }

    // ─── Add-Peer sheet actions ─────────────────────────────────────────────

    fun openAddPeerSheet() {
        _addPeerSheetOpen.value = true
        _addPeerError.value = null
    }

    fun closeAddPeerSheet() {
        _addPeerSheetOpen.value = false
        _addPeerInput.value = ""
        _addPeerError.value = null
    }

    fun setAddPeerInput(input: String) {
        _addPeerInput.value = input
        if (_addPeerError.value != null) _addPeerError.value = null
    }

    fun submitAddPeer() {
        val code = _addPeerInput.value.trim()
        if (code.isEmpty()) {
            _addPeerError.value = "Empty code"
            return
        }
        viewModelScope.launch {
            _addPeerInFlight.value = true
            _addPeerError.value = null
            try {
                val response = apiClient.addPeerFromNodeCode(code)
                PlatformLogger.i(
                    tag,
                    "Add peer ok: keyId=${response.peer.keyId.take(12)}…, alreadyPresent=${response.wasAlreadyPresent}",
                )
                closeAddPeerSheet()
                refresh()
            } catch (e: Exception) {
                val msg = e.message ?: e::class.simpleName ?: "unknown error"
                PlatformLogger.e(tag, "addPeerFromNodeCode failed: $msg", e)
                _addPeerError.value = msg
            } finally {
                _addPeerInFlight.value = false
            }
        }
    }

    companion object {
        /** Trust-state sort priority — lower comes first. */
        private fun trustPriority(t: PeerTrustState): Int = when (t) {
            PeerTrustState.TRUSTED -> 0
            PeerTrustState.UNKNOWN -> 1
            PeerTrustState.UNTRUSTED -> 2
            PeerTrustState.BLOCKED -> 3
        }

        fun sortPeers(peers: List<LocalPeerState>): List<LocalPeerState> =
            peers.sortedWith(
                compareByDescending<LocalPeerState> { it.canonical }
                    .thenBy { trustPriority(it.trust) }
                    .thenByDescending { it.lastSeen?.toEpochMilliseconds() ?: 0L },
            )
    }
}
