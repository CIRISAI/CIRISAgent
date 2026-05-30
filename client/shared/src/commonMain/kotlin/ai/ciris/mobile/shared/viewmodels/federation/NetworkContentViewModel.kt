package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationContentResponse
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.viewmodels.BaseFederationViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 2-step UX state for the content-fetch flow.
 *
 *  - [PICK_PEER]: list/search peers and pick one. The flat directory model
 *    (one peer at a time) maps to the backend requirement that
 *    ``peer_key_id`` is required on every fetch.
 *  - [FETCH]: enter content_id + timeout and POST. Stays in this step
 *    after a successful fetch so the result can be inspected.
 */
enum class ContentStep { PICK_PEER, FETCH }

/**
 * VM for the Network → Content sub-screen.
 *
 * Two-phase flow because Edge has no global content directory; the
 * caller must always pick a candidate holder before issuing the fetch.
 * [loadPeers] is idempotent and re-runnable from the picker; [selectPeer]
 * + [backToPicker] move between steps.
 *
 * Validation is client-side first ([validateContentId]) so the user gets
 * fast feedback on the SHA-256 hash form. The backend re-validates and
 * surfaces 4xx as exceptions; we surface those as [error] strings.
 */
class NetworkContentViewModel(
    apiClient: CIRISApiClient,
) : BaseFederationViewModel(apiClient) {

    override val tag: String = "NetworkContentVM"

    // ─── Step / peer state ───────────────────────────────────────────────────

    private val _step = MutableStateFlow(ContentStep.PICK_PEER)
    val step: StateFlow<ContentStep> = _step.asStateFlow()

    private val _peers = MutableStateFlow<List<LocalPeerState>>(emptyList())
    val peers: StateFlow<List<LocalPeerState>> = _peers.asStateFlow()

    private val _peerSearch = MutableStateFlow("")
    val peerSearch: StateFlow<String> = _peerSearch.asStateFlow()

    private val _selectedPeer = MutableStateFlow<LocalPeerState?>(null)
    val selectedPeer: StateFlow<LocalPeerState?> = _selectedPeer.asStateFlow()

    // ─── Step 2 fetch state ──────────────────────────────────────────────────

    private val _contentIdInput = MutableStateFlow("")
    val contentIdInput: StateFlow<String> = _contentIdInput.asStateFlow()

    private val _timeoutMs = MutableStateFlow(5_000)
    val timeoutMs: StateFlow<Int> = _timeoutMs.asStateFlow()

    private val _fetching = MutableStateFlow(false)
    val fetching: StateFlow<Boolean> = _fetching.asStateFlow()

    private val _result = MutableStateFlow<FederationContentResponse?>(null)
    val result: StateFlow<FederationContentResponse?> = _result.asStateFlow()

    private val _contentIdError = MutableStateFlow<String?>(null)
    val contentIdError: StateFlow<String?> = _contentIdError.asStateFlow()

    // ─── Public actions ──────────────────────────────────────────────────────

    fun loadPeers() {
        launchApi(
            operation = "listFederationPeers",
            block = { apiClient.listFederationPeers() },
            onSuccess = { _peers.value = it.peers },
        )
    }

    fun setPeerSearch(q: String) {
        _peerSearch.value = q
    }

    fun filteredPeers(): List<LocalPeerState> {
        val q = _peerSearch.value.trim().lowercase()
        val all = _peers.value
        if (q.isEmpty()) return all
        return all.filter { peer ->
            peer.keyId.lowercase().contains(q) ||
                (peer.aliasOverride?.lowercase()?.contains(q) == true)
        }
    }

    fun selectPeer(peer: LocalPeerState) {
        _selectedPeer.value = peer
        _step.value = ContentStep.FETCH
        // Reset fetch-side state when the peer changes so the previous
        // result doesn't ghost into the new selection.
        _result.value = null
        _contentIdError.value = null
    }

    fun backToPicker() {
        _step.value = ContentStep.PICK_PEER
    }

    fun setContentId(s: String) {
        _contentIdInput.value = s.trim()
        _contentIdError.value = if (_contentIdInput.value.isEmpty()) {
            null
        } else if (!validateContentId(_contentIdInput.value)) {
            "content.id.invalid"
        } else {
            null
        }
    }

    fun setTimeout(ms: Int) {
        // Clamp to the backend's accepted range [1, 300_000] — the slider
        // also clamps but we mirror server-side so direct callers don't
        // get a 422.
        _timeoutMs.value = ms.coerceIn(1_000, 30_000)
    }

    fun fetch() {
        val peer = _selectedPeer.value ?: return
        val cid = _contentIdInput.value.trim()
        if (!validateContentId(cid)) {
            _contentIdError.value = "content.id.invalid"
            return
        }
        _contentIdError.value = null
        _fetching.value = true
        launchApi(
            operation = "fetchFederationContent",
            block = {
                apiClient.fetchFederationContent(
                    contentId = cid,
                    peerKeyId = peer.keyId,
                    timeoutMs = _timeoutMs.value,
                )
            },
            onSuccess = { _result.value = it },
        )
        _fetching.value = false
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    companion object {
        private val HEX64_REGEX = Regex("^[0-9a-fA-F]{64}$")
    }

    /** Validate a SHA-256 content id (64-hex). */
    fun validateContentId(s: String): Boolean = HEX64_REGEX.matches(s)
}
