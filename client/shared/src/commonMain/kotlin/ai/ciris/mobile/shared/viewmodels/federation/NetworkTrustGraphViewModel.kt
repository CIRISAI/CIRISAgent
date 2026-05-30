package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.EdgePeerReachability
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.viewmodels.BaseFederationViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

/**
 * Pairing of a peer with its (optional) per-medium reachability snapshot,
 * surfaced to the radial trust graph for edge-opacity rendering.
 *
 * [reachability] is nullable because the per-peer fetch can 404 / 503 in
 * isolation; the graph still renders the node, just without an averaged
 * edge weight. UI MUST not collapse `null` to 0.0 — render the edge with
 * a default mid-opacity instead.
 */
data class PeerWithReachability(
    val peer: LocalPeerState,
    val reachability: EdgePeerReachability? = null,
) {
    /** Averaged per-medium ratio in `[0.0, 1.0]`, or `null` if not measured. */
    val avgRatio: Double?
        get() {
            val r = reachability ?: return null
            if (r.byMedium.isEmpty()) return null
            return r.byMedium.values.map { it.ratio }.average()
        }
}

/**
 * VM for the Network → Trust Graph sub-screen.
 *
 * Builds a radial trust topology: canonical peers cluster at the center,
 * organic peers ring the outside sorted by trust state. Each peer's edge
 * to self is opacity-scaled by its averaged per-medium reachability.
 *
 * Fetches:
 *  1. ``GET /v1/federation/identity`` — local agent's signer key id.
 *  2. ``GET /v1/federation/peers`` — full peer list (canonical + organic).
 *  3. For each peer: ``GET /v1/federation/peers/{keyId}`` — per-peer
 *     reachability snapshot. This is N+1 by design; we cap concurrency
 *     at [FETCH_CONCURRENCY] (= 4) via a [Semaphore] to avoid hammering
 *     the agent on a large mesh. Per-peer failures are non-fatal — the
 *     peer renders with `null` reachability and a default-opacity edge.
 *
 * Selection state is local: tapping a node sets [selectedPeerId] for the
 * UI to highlight + drive `onPeerClick` navigation.
 */
class NetworkTrustGraphViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkTrustGraphVM"

    private val _identity = MutableStateFlow<FederationIdentity?>(null)
    val identity: StateFlow<FederationIdentity?> = _identity.asStateFlow()

    private val _peers = MutableStateFlow<List<PeerWithReachability>>(emptyList())
    val peers: StateFlow<List<PeerWithReachability>> = _peers.asStateFlow()

    private val _selectedPeerId = MutableStateFlow<String?>(null)
    val selectedPeerId: StateFlow<String?> = _selectedPeerId.asStateFlow()

    fun load() {
        viewModelScope.launch {
            runApi("loadTrustGraph") {
                val identityResp = apiClient.getFederationIdentity()
                val peerList = apiClient.listFederationPeers().peers
                val enriched = fetchReachabilityCapped(peerList)
                _identity.value = identityResp
                _peers.value = enriched
            }
        }
    }

    fun refresh() = load()

    fun selectPeer(id: String?) {
        _selectedPeerId.value = id
    }

    /**
     * Fan out N getFederationPeer calls with a concurrency cap. Failures
     * surface as `null` reachability — we never let one broken peer rip
     * the whole graph render.
     */
    private suspend fun fetchReachabilityCapped(
        peers: List<LocalPeerState>,
    ): List<PeerWithReachability> = coroutineScope {
        val semaphore = Semaphore(FETCH_CONCURRENCY)
        peers.map { peer ->
            async {
                semaphore.withPermit {
                    val reachability = try {
                        apiClient.getFederationPeer(peer.keyId).reachability
                    } catch (e: Exception) {
                        // Non-fatal: render node with default-opacity edge.
                        null
                    }
                    PeerWithReachability(peer = peer, reachability = reachability)
                }
            }
        }.awaitAll()
    }

    companion object {
        /** Max in-flight per-peer reachability fetches. */
        const val FETCH_CONCURRENCY: Int = 4
    }
}
