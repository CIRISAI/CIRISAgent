package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Contacts / Identities** screen — a browsable list of known
 * federation identities (the local node's peer store) that the owner can
 * inspect and pick from when delegating to an existing fed-ID.
 *
 * Source: ``GET /v1/federation/peers`` → ``{peers, total}``.
 * The backend returns ALL peers (canonical + organic); display-time search
 * is applied locally so the full list is always cached after the first load.
 *
 * The ViewModel exposes [selectedPeer] so the Delegations screen (or any
 * other caller) can receive the user's pick via the companion lambda
 * [onPeerSelected]. Callers that don't need a picker can ignore it.
 */
class ContactsViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "ContactsVM"

    // ── Raw peer list (all, unsearched) ──────────────────────────────────────

    private val _allPeers = MutableStateFlow<List<LocalPeerState>>(emptyList())

    // ── Search query ──────────────────────────────────────────────────────────

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    // ── Filtered view (recomputed whenever _allPeers or _searchQuery changes) ─

    private val _peers = MutableStateFlow<List<LocalPeerState>>(emptyList())
    val peers: StateFlow<List<LocalPeerState>> = _peers.asStateFlow()

    // ── Selection (used in picker mode) ──────────────────────────────────────

    private val _selectedPeer = MutableStateFlow<LocalPeerState?>(null)
    val selectedPeer: StateFlow<LocalPeerState?> = _selectedPeer.asStateFlow()

    init {
        load()
    }

    /** Initial load — idempotent; safe to call from a LaunchedEffect. */
    fun load() {
        refresh()
    }

    /** Pull a fresh peer list from the node. */
    fun refresh() {
        viewModelScope.launch {
            runApi("listFederationPeers") {
                apiClient.listFederationPeers()
            }?.let { resp ->
                _allPeers.value = sortedPeers(resp.peers)
                applySearch()
            }
        }
    }

    /** Update the search query and refilter the list locally. */
    fun setSearchQuery(q: String) {
        _searchQuery.value = q
        applySearch()
    }

    /** Set (or clear) the picked identity. */
    fun selectPeer(peer: LocalPeerState?) {
        _selectedPeer.value = peer
    }

    // ─── Internals ────────────────────────────────────────────────────────────

    private fun applySearch() {
        val q = _searchQuery.value.trim().lowercase()
        _peers.value = if (q.isEmpty()) {
            _allPeers.value
        } else {
            _allPeers.value.filter { peer ->
                peer.keyId.lowercase().contains(q) ||
                    (peer.aliasOverride?.lowercase()?.contains(q) == true) ||
                    (peer.notes?.lowercase()?.contains(q) == true) ||
                    peer.trust.wire.contains(q) ||
                    peer.pubkeyEd25519Base64.lowercase().contains(q)
            }
        }
        PlatformLogger.d(tag, "applySearch q=${q.take(20)} → ${_peers.value.size}/${_allPeers.value.size} peers")
    }

    companion object {
        /**
         * Canonical peers first; within each group sort trusted > unknown >
         * untrusted > blocked, then most-recently-seen first.
         */
        private fun trustPriority(peer: LocalPeerState): Int = when (peer.trust) {
            ai.ciris.mobile.shared.models.federation.PeerTrustState.TRUSTED -> 0
            ai.ciris.mobile.shared.models.federation.PeerTrustState.UNKNOWN -> 1
            ai.ciris.mobile.shared.models.federation.PeerTrustState.UNTRUSTED -> 2
            ai.ciris.mobile.shared.models.federation.PeerTrustState.BLOCKED -> 3
        }

        fun sortedPeers(peers: List<LocalPeerState>): List<LocalPeerState> =
            peers.sortedWith(
                compareByDescending<LocalPeerState> { it.canonical }
                    .thenBy { trustPriority(it) }
                    .thenByDescending { it.lastSeen?.toEpochMilliseconds() ?: 0L },
            )
    }
}
