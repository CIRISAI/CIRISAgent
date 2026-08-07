package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.surfaces.CommonsBallotRequest
import ai.ciris.mobile.shared.models.surfaces.CommonsDismissalRequest
import ai.ciris.mobile.shared.models.surfaces.CommonsObjectionRequest
import ai.ciris.mobile.shared.models.surfaces.CommonsScrubSig
import ai.ciris.mobile.shared.models.surfaces.CommonsStanding
import ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Commons** surface — persist's reverse-quorum plane
 * (CIRISServer#367, `src/commons_surface.rs`).
 *
 * # The asymmetry is structural here too
 *
 * [raiseObjection] is one call with one argument: grounds. There is nothing to
 * gather, nobody to wait for, and no threshold to reach — one member raises the
 * brake.
 *
 * [submitDismissal] cannot even be reached without [dismissDryRun] first,
 * because the co-signatures must be produced over the exact canonical bytes the
 * submission will carry and only the dry run knows them. That is not a UI
 * nicety layered on top of a symmetric API: the m-of-n is literally unreachable
 * without the round trip, so the state machine here has the same shape the
 * substrate rule does.
 *
 * # No arithmetic
 *
 * Not one threshold, count or window comparison happens in this class. Every
 * number rendered by the screen comes from [standing] or from a write's
 * `quorum`, both of which are persist's fold read verbatim. A second
 * implementation of a rule is a second answer that can disagree with the first.
 */
class CommonsViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "CommonsVM"

        /**
         * The rostered cohorts, as persist's own `Cohort::from_token` spells
         * them. `self` parses but is refused by the surface with its own token:
         * one identity's own devices are not a commons and have no roster to be
         * a quorum over.
         */
        val COHORTS = listOf("family", "community", "affiliations")
    }

    // ── What the operator is asking about ────────────────────────────────────

    private val _cohort = MutableStateFlow(COHORTS.first())
    val cohort: StateFlow<String> = _cohort.asStateFlow()

    private val _cohortKeyId = MutableStateFlow("")
    val cohortKeyId: StateFlow<String> = _cohortKeyId.asStateFlow()

    private val _actionId = MutableStateFlow("")
    val actionId: StateFlow<String> = _actionId.asStateFlow()

    fun setCohort(v: String) { _cohort.value = v }
    fun setCohortKeyId(v: String) { _cohortKeyId.value = v }
    fun setActionId(v: String) { _actionId.value = v }

    // ── What came back ───────────────────────────────────────────────────────

    /**
     * The fold's answer. `null` means **no question has been asked yet** — which
     * is a third thing, distinct from both "the plane was unreadable" and
     * "nobody objected".
     */
    private val _standing = MutableStateFlow<CommonsStanding?>(null)
    val standing: StateFlow<CommonsStanding?> = _standing.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    /** A TRANSPORT failure only. An unreadable plane is an ANSWER, not an error. */
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _writeResult = MutableStateFlow<CommonsWriteResult?>(null)
    val writeResult: StateFlow<CommonsWriteResult?> = _writeResult.asStateFlow()

    // ── The dismissal ceremony: dry run -> co-sign -> submit ─────────────────

    /**
     * The `payload_sha256` the last dry run produced — the exact bytes every
     * co-signer must sign. `null` keeps [submitDismissal] shut.
     */
    private val _dismissalPayloadSha256 = MutableStateFlow<String?>(null)
    val dismissalPayloadSha256: StateFlow<String?> = _dismissalPayloadSha256.asStateFlow()

    /** The objection the pending dry run was taken over. */
    private val _dismissalObjectionId = MutableStateFlow<String?>(null)
    val dismissalObjectionId: StateFlow<String?> = _dismissalObjectionId.asStateFlow()

    private val _cosigners = MutableStateFlow<List<CommonsScrubSig>>(emptyList())
    val cosigners: StateFlow<List<CommonsScrubSig>> = _cosigners.asStateFlow()

    fun addCosigner(keyId: String, classical: String, pqc: String?) {
        if (keyId.isBlank() || classical.isBlank()) return
        _cosigners.value = _cosigners.value + CommonsScrubSig(
            scrubKeyId = keyId.trim(),
            scrubSignatureClassical = classical.trim(),
            scrubSignaturePqc = pqc?.trim()?.takeIf { it.isNotBlank() },
        )
    }

    fun removeCosigner(index: Int) {
        _cosigners.value = _cosigners.value.filterIndexed { i, _ -> i != index }
    }

    /** Abandon the pending ceremony — the bytes and the signatures over them go together. */
    fun clearDismissalDraft() {
        _dismissalPayloadSha256.value = null
        _dismissalObjectionId.value = null
        _cosigners.value = emptyList()
    }

    fun clearWriteResult() {
        _writeResult.value = null
    }

    // ── Reads ────────────────────────────────────────────────────────────────

    /** Ask the fold about the named action. */
    fun readStanding() {
        val cohortKey = _cohortKeyId.value.trim()
        val action = _actionId.value.trim()
        if (cohortKey.isEmpty() || action.isEmpty()) return
        _loading.value = true
        viewModelScope.launch {
            try {
                _standing.value = apiClient.getCommonsStanding(
                    cohort = _cohort.value,
                    cohortKeyId = cohortKey,
                    actionId = action,
                )
                _error.value = null
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[readStanding] ${e.message}", e)
                _error.value = e.message ?: "commons standing read failed"
            } finally {
                _loading.value = false
            }
        }
    }

    // ── The one-signature door ───────────────────────────────────────────────

    /**
     * **Raise the brake.** One member is enough; nothing is gathered and nobody
     * is waited for. The objection is a MARKER, not a command — nothing is
     * changed by its arrival, and it replicates on the ordinary attestation
     * plane so a peer partitioned during the window still counts it later.
     */
    fun raiseObjection(grounds: String) {
        val cohortKey = _cohortKeyId.value.trim()
        val action = _actionId.value.trim()
        if (cohortKey.isEmpty() || action.isEmpty() || grounds.isBlank()) return
        _busy.value = true
        viewModelScope.launch {
            try {
                _writeResult.value = apiClient.postCommonsObjection(
                    CommonsObjectionRequest(
                        cohort = _cohort.value,
                        cohortKeyId = cohortKey,
                        actionId = action,
                        grounds = grounds.trim(),
                    ),
                )
                readStanding()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[raiseObjection] ${e.message}", e)
                _error.value = e.message ?: "objection failed"
            } finally {
                _busy.value = false
            }
        }
    }

    /** Answer a question the duty-holders left open. One signature, no force on its own. */
    fun castBallot(objectionId: String, upholds: Boolean, grounds: String) {
        val cohortKey = _cohortKeyId.value.trim()
        val action = _actionId.value.trim()
        if (cohortKey.isEmpty() || action.isEmpty() || objectionId.isBlank() || grounds.isBlank()) return
        _busy.value = true
        viewModelScope.launch {
            try {
                _writeResult.value = apiClient.postCommonsBallot(
                    CommonsBallotRequest(
                        cohort = _cohort.value,
                        cohortKeyId = cohortKey,
                        actionId = action,
                        grounds = grounds.trim(),
                        objectionId = objectionId.trim(),
                        upholds = upholds,
                    ),
                )
                readStanding()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[castBallot] ${e.message}", e)
                _error.value = e.message ?: "ballot failed"
            } finally {
                _busy.value = false
            }
        }
    }

    // ── The m-of-n door ──────────────────────────────────────────────────────

    /**
     * Step 1 of lifting a brake: ask for the canonical envelope and its
     * `payload_sha256` WITHOUT signing or submitting anything. The co-signers
     * sign these bytes and no others.
     */
    fun dismissDryRun(objectionId: String, grounds: String) {
        val cohortKey = _cohortKeyId.value.trim()
        val action = _actionId.value.trim()
        if (cohortKey.isEmpty() || action.isEmpty() || objectionId.isBlank() || grounds.isBlank()) return
        _busy.value = true
        viewModelScope.launch {
            try {
                val result = apiClient.postCommonsDismissal(
                    CommonsDismissalRequest(
                        cohort = _cohort.value,
                        cohortKeyId = cohortKey,
                        actionId = action,
                        grounds = grounds.trim(),
                        objectionId = objectionId.trim(),
                        dryRun = true,
                    ),
                )
                _writeResult.value = result
                _dismissalPayloadSha256.value = result.payloadSha256
                _dismissalObjectionId.value = objectionId.trim()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[dismissDryRun] ${e.message}", e)
                _error.value = e.message ?: "dismissal dry run failed"
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * Step 3: submit the dismissal with whatever co-signatures were gathered.
     * Refused unless a dry run has produced the bytes those signatures cover —
     * the substrate would refuse a scrub over anything else anyway, and this
     * keeps the client from pretending otherwise.
     *
     * What the co-signatures are WORTH is counted by the substrate; the returned
     * `quorum` names counted / required / roster_size on both arms.
     */
    fun submitDismissal(objectionId: String, grounds: String) {
        val cohortKey = _cohortKeyId.value.trim()
        val action = _actionId.value.trim()
        if (cohortKey.isEmpty() || action.isEmpty() || objectionId.isBlank() || grounds.isBlank()) return
        if (_dismissalPayloadSha256.value == null) return
        _busy.value = true
        viewModelScope.launch {
            try {
                _writeResult.value = apiClient.postCommonsDismissal(
                    CommonsDismissalRequest(
                        cohort = _cohort.value,
                        cohortKeyId = cohortKey,
                        actionId = action,
                        grounds = grounds.trim(),
                        objectionId = objectionId.trim(),
                        additionalScrubs = _cosigners.value,
                        dryRun = false,
                    ),
                )
                clearDismissalDraft()
                readStanding()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[submitDismissal] ${e.message}", e)
                _error.value = e.message ?: "dismissal failed"
            } finally {
                _busy.value = false
            }
        }
    }
}
