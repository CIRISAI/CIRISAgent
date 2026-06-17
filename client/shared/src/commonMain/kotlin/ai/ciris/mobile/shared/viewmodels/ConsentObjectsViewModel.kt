package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.models.federation.PeeringRequest
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.services.NodeProfileStore
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Status of one direction of a bilateral consent:replication grant.
 */
enum class GrantDirectionState { IDLE, IN_PROGRESS, GRANTED, FAILED }

/**
 * UI state for the consent-objects card.
 *
 * The bilateral grant is **ratified iff both directions are [GrantDirectionState.GRANTED]**.
 */
data class ConsentObjectsState(
    val nodeA: NodeProfile? = null,
    val nodeB: NodeProfile? = null,
    /** Direction A→B: node A grants consent:replication to B (e.g. prefixes ["capacity:"]). */
    val aToB: GrantDirectionState = GrantDirectionState.IDLE,
    /** Direction B→A: node B grants consent:replication to A (e.g. prefixes ["health:"]). */
    val bToA: GrantDirectionState = GrantDirectionState.IDLE,
    val isRunning: Boolean = false,
    val error: String? = null,
    val message: String? = null,
) {
    val isRatified: Boolean
        get() = aToB == GrantDirectionState.GRANTED && bToA == GrantDirectionState.GRANTED
    val canRun: Boolean
        get() = nodeA != null && nodeB != null && !isRunning
}

/**
 * Drives the **consent-objects card** — the bilateral consent:replication setup
 * across the two connected fabric nodes.
 *
 * Flow (using the multi-node connections from the node switcher, change #1):
 *   1. GET A's self-key-record (from node A)
 *   2. GET B's self-key-record (from node B)
 *   3. POST /v1/federation/peering to A with peer=B, prefixes [aToBPrefixes]
 *   4. POST /v1/federation/peering to B with peer=A, prefixes [bToAPrefixes]
 *   5. report both directions; ratified iff both grants present.
 *
 * Each node is addressed by its own [NodeProfile.baseUrl] + session token via
 * the nodeUrl/token overloads on [CIRISApiClient].
 */
class ConsentObjectsViewModel(
    private val apiClient: CIRISApiClient,
    private val secureStorage: SecureStorage,
) : ViewModel() {

    companion object {
        private const val TAG = "ConsentObjectsVM"
        val DEFAULT_A_TO_B_PREFIXES = listOf("capacity:")
        val DEFAULT_B_TO_A_PREFIXES = listOf("health:")
    }

    private val store = NodeProfileStore(secureStorage)

    private val _state = MutableStateFlow(ConsentObjectsState())
    val state: StateFlow<ConsentObjectsState> = _state.asStateFlow()

    init {
        viewModelScope.launch { loadNodes() }
    }

    /**
     * Pick node A (active) and node B (most-recent other) from the saved
     * profiles. The card lets the user re-pick; this is just the default.
     */
    suspend fun loadNodes() {
        val profiles = store.loadProfiles()
        val activeId = store.getActiveProfileId()
        val a = profiles.firstOrNull { it.id == activeId } ?: profiles.firstOrNull()
        val b = profiles.firstOrNull { it.id != a?.id }
        _state.value = _state.value.copy(nodeA = a, nodeB = b)
    }

    fun setNodes(a: NodeProfile?, b: NodeProfile?) {
        _state.value = _state.value.copy(nodeA = a, nodeB = b, aToB = GrantDirectionState.IDLE, bToA = GrantDirectionState.IDLE)
    }

    fun clearMessages() {
        _state.value = _state.value.copy(error = null, message = null)
    }

    /**
     * Run the full bilateral peering. Each direction is reported independently
     * so a partial success (one grant emitted, the other failing) is visible.
     */
    fun runBilateralPeering(
        aToBPrefixes: List<String> = DEFAULT_A_TO_B_PREFIXES,
        bToAPrefixes: List<String> = DEFAULT_B_TO_A_PREFIXES,
    ) {
        val s = _state.value
        val nodeA = s.nodeA
        val nodeB = s.nodeB
        if (nodeA == null || nodeB == null || s.isRunning) {
            PlatformLogger.w(TAG, "[runBilateralPeering] need two nodes (a=$nodeA b=$nodeB) and not already running")
            return
        }

        _state.value = s.copy(
            isRunning = true,
            error = null,
            message = null,
            aToB = GrantDirectionState.IN_PROGRESS,
            bToA = GrantDirectionState.IN_PROGRESS,
        )

        viewModelScope.launch {
            try {
                // 1 + 2: fetch each node's self-key-record.
                PlatformLogger.i(TAG, "[runBilateralPeering] fetching self-key-records A=${nodeA.baseUrl} B=${nodeB.baseUrl}")
                val recordA = apiClient.getSelfKeyRecord(nodeA.baseUrl, nodeA.sessionToken)
                val recordB = apiClient.getSelfKeyRecord(nodeB.baseUrl, nodeB.sessionToken)

                // 3: POST peering to A with peer = B.
                val aGranted = try {
                    val resp = apiClient.postPeering(
                        request = PeeringRequest(
                            peerKeyId = recordB.keyId,
                            peerKeyRecord = recordB,
                            attestationPrefixes = aToBPrefixes,
                        ),
                        nodeUrl = nodeA.baseUrl,
                        token = nodeA.sessionToken,
                    )
                    resp.granted
                } catch (e: Exception) {
                    PlatformLogger.e(TAG, "[runBilateralPeering] A→B failed: ${e.message}", e)
                    false
                }
                _state.value = _state.value.copy(
                    aToB = if (aGranted) GrantDirectionState.GRANTED else GrantDirectionState.FAILED,
                )

                // 4: POST peering to B with peer = A.
                val bGranted = try {
                    val resp = apiClient.postPeering(
                        request = PeeringRequest(
                            peerKeyId = recordA.keyId,
                            peerKeyRecord = recordA,
                            attestationPrefixes = bToAPrefixes,
                        ),
                        nodeUrl = nodeB.baseUrl,
                        token = nodeB.sessionToken,
                    )
                    resp.granted
                } catch (e: Exception) {
                    PlatformLogger.e(TAG, "[runBilateralPeering] B→A failed: ${e.message}", e)
                    false
                }
                _state.value = _state.value.copy(
                    bToA = if (bGranted) GrantDirectionState.GRANTED else GrantDirectionState.FAILED,
                )

                val ratified = aGranted && bGranted
                _state.value = _state.value.copy(
                    isRunning = false,
                    message = if (ratified) "Bilateral consent:replication ratified"
                    else "Partial: A→B=${aGranted}, B→A=${bGranted}",
                )
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[runBilateralPeering] failed before grants: ${e.message}", e)
                _state.value = _state.value.copy(
                    isRunning = false,
                    aToB = GrantDirectionState.FAILED,
                    bToA = GrantDirectionState.FAILED,
                    error = "Peering failed: ${e.message}",
                )
            }
        }
    }
}
