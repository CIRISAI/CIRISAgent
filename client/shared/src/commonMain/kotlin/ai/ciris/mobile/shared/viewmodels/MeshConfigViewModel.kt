package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.surfaces.MeshConfigDurableRequest
import ai.ciris.mobile.shared.models.surfaces.MeshConfigHistory
import ai.ciris.mobile.shared.models.surfaces.MeshConfigRead
import ai.ciris.mobile.shared.models.surfaces.MeshConfigReliefRequest
import ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Mesh configuration** section of the Config surface
 * (CIRISServer#346 / #365, `src/mesh_config_surface.rs`).
 *
 * # It decides nothing
 *
 * No threshold, no durability rule, no TTL clamp and no consumption verdict is
 * computed here. Every one of those is the server's (and, under it, persist's),
 * re-read on each call and rendered verbatim — including the `consumption`
 * label, which is the whole point of #365 and the one field that makes
 * `effective: 10` a true statement instead of a confident lie.
 *
 * # A failed read is NOT an empty plane
 *
 * [read] going `null` and [read] carrying `standing = "unreadable"` with
 * `settings = null` are two different states, and neither is "nothing is set".
 * The surface answers 503 with a full body on the unreadable arm, so the normal
 * path is the second one; [error] only carries a transport failure.
 */
class MeshConfigViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "MeshConfigVM"
    }

    private val _read = MutableStateFlow<MeshConfigRead?>(null)
    val read: StateFlow<MeshConfigRead?> = _read.asStateFlow()

    private val _history = MutableStateFlow<MeshConfigHistory?>(null)
    val history: StateFlow<MeshConfigHistory?> = _history.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    /** A TRANSPORT failure only. A refused or unreadable plane is an ANSWER. */
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** The last write / dry-run answer, admitted or refused. */
    private val _writeResult = MutableStateFlow<MeshConfigWriteResult?>(null)
    val writeResult: StateFlow<MeshConfigWriteResult?> = _writeResult.asStateFlow()

    /** Read the effective values, the registry, the TTLs and the consumption labels. */
    fun refresh() {
        _loading.value = true
        viewModelScope.launch {
            try {
                _read.value = apiClient.getMeshConfig()
                _error.value = null
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[refresh] ${e.message}", e)
                _error.value = e.message ?: "mesh-config read failed"
            } finally {
                _loading.value = false
            }
        }
    }

    /** Load the row history — every mesh-config row this node holds, newest first. */
    fun loadHistory(limit: Int = 200) {
        viewModelScope.launch {
            try {
                _history.value = apiClient.getMeshConfigHistory(limit = limit)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[loadHistory] ${e.message}", e)
                _error.value = e.message ?: "mesh-config history read failed"
            }
        }
    }

    fun clearWriteResult() {
        _writeResult.value = null
    }

    /**
     * The durable path. [dryRun] signs and submits nothing and returns the
     * canonical bytes a co-signer must sign.
     */
    fun submitDurable(
        key: String,
        value: Long,
        rootRef: String,
        delegationId: String,
        grounds: String,
        ratifiesRowId: String? = null,
        dryRun: Boolean = false,
    ) {
        _busy.value = true
        viewModelScope.launch {
            try {
                _writeResult.value = apiClient.postMeshConfigDurable(
                    MeshConfigDurableRequest(
                        key = key,
                        value = value,
                        rootRef = rootRef,
                        delegationId = delegationId,
                        grounds = grounds,
                        ratifiesRowId = ratifiesRowId?.takeIf { it.isNotBlank() },
                        dryRun = dryRun,
                    ),
                )
                if (!dryRun) refresh()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[submitDurable] ${e.message}", e)
                _error.value = e.message ?: "durable submit failed"
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * The emergency relief path. [ttlHours] is mandatory — relief that does not
     * expire is not relief — and the admissible bound is the substrate's, which
     * refuses `ttl_too_long` at its own door. Nothing is clamped here.
     */
    fun submitRelief(
        key: String,
        value: Long,
        rootRef: String,
        delegationId: String,
        grounds: String,
        ttlHours: Long,
    ) {
        _busy.value = true
        viewModelScope.launch {
            try {
                _writeResult.value = apiClient.postMeshConfigRelief(
                    MeshConfigReliefRequest(
                        key = key,
                        value = value,
                        rootRef = rootRef,
                        delegationId = delegationId,
                        grounds = grounds,
                        ttlHours = ttlHours,
                    ),
                )
                refresh()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[submitRelief] ${e.message}", e)
                _error.value = e.message ?: "relief submit failed"
            } finally {
                _busy.value = false
            }
        }
    }
}
