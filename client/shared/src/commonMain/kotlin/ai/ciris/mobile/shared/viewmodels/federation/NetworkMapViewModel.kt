package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.viewmodels.BaseFederationViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * VM for the Network → Map sub-screen.
 *
 * The honest truth (per the Reticulum cribsheet): no app in the
 * Reticulum ecosystem renders geographic topology because no transport
 * surfaces geo telemetry. CIRIS doesn't ship a geo pipeline yet either,
 * so we deliberately do NOT fabricate locations.
 *
 * Instead we project the peer list into three concentric tiers:
 *  - inner  : canonical peers (`canonical == true`)
 *  - middle : trusted, non-canonical peers
 *  - outer  : all other peers (unknown / untrusted / blocked)
 *
 * The screen renders those counts as nested rings, with a "coming
 * later" panel explaining what a real map would show. When the geo
 * telemetry pipeline lands we replace this VM in place.
 */
class NetworkMapViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkMapVM"

    private val _canonicalCount = MutableStateFlow(0)
    val canonicalCount: StateFlow<Int> = _canonicalCount.asStateFlow()

    private val _trustedCount = MutableStateFlow(0)
    val trustedCount: StateFlow<Int> = _trustedCount.asStateFlow()

    private val _otherCount = MutableStateFlow(0)
    val otherCount: StateFlow<Int> = _otherCount.asStateFlow()

    fun load() {
        viewModelScope.launch {
            runApi("loadNetworkMap") {
                val peers = apiClient.listFederationPeers().peers
                _canonicalCount.value = peers.count { it.canonical }
                _trustedCount.value = peers.count { !it.canonical && it.trust == PeerTrustState.TRUSTED }
                _otherCount.value = peers.count {
                    !it.canonical && it.trust != PeerTrustState.TRUSTED
                }
            }
        }
    }

    fun refresh() = load()
}
