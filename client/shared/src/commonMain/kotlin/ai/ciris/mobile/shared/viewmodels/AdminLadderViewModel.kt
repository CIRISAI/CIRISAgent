package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.AdminLadderCommitRequest
import ai.ciris.mobile.shared.models.AdminLadderOp
import ai.ciris.mobile.shared.models.AdminOpOutcome
import ai.ciris.mobile.shared.models.AdminOpResponse
import ai.ciris.mobile.shared.models.AdminPreviewOutcome
import ai.ciris.mobile.shared.models.AdminPreviewResponse
import ai.ciris.mobile.shared.models.AdminRefusal
import ai.ciris.mobile.shared.models.AdminSelectionDto
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private const val TAG = "AdminLadderVM"

/**
 * UI state for the **graded enforcement ladder** (the `/v1/admin` routes).
 *
 * (Written without the glob: Kotlin block comments NEST, so a literal
 * `/v1/admin` followed by a star opens a comment inside this one and eats its
 * terminator. That cost one build.)
 *
 * The load-bearing invariant lives in this class and not in the screen:
 * [previewedSelection] and [preview] are captured TOGETHER by
 * [AdminLadderViewModel.runPreview], and a commit sends exactly that pair —
 * never the selection currently in the form. Every setter that touches a
 * hash-covered field drops both, so an edited selection cannot be signed under
 * a stale hash. If preview and commit could disagree, the pattern is defeated.
 */
data class AdminLadderState(
    // ── The selection (every field is covered by the selection hash) ──
    /** Rows authored BY this key — the key being judged, in almost every op. */
    val attestingKeyId: String = "",
    /**
     * **Many keys at once**, as pasted by the operator — newline / comma /
     * space separated, because a list arrives from wherever they keep it (an
     * incident ticket, a shell, a spreadsheet column) and reformatting it by
     * hand is exactly the tax this removes.
     *
     * Parsed by [parsedAttestingKeyIds]. Empty means the singular field alone
     * decides, so the ordinary one-subject act is unchanged.
     */
    val attestingKeyIdsRaw: String = "",
    /** `scores` / `delegates_to` / `withdraws` / … */
    val attestationType: String = "",
    /** One hierarchical dimension prefix. */
    val dimensionPrefix: String = "",
    /** RFC3339 lower bound on `asserted_at`. CHANGES THE SELECTION AND THE HASH. */
    val selectionAfter: String = "",

    // ── Attribution: MANDATORY, and not covered by the hash ──
    /** The `delegates_to` row the act is taken under. The node re-walks it. */
    val delegationId: String = "",
    /** WHY. Recorded in the tombstone, never interpreted. */
    val reason: String = "",

    // ── Per-op extras (none of them covered by the hash) ──
    /** Quarantine only: the community whose authority the marker is filed under. */
    val communityId: String = "",
    /** Descend only: the OTHER authorities' delegation ids, comma/newline separated. */
    val quorumDelegationIdsRaw: String = "",
    /**
     * De-admit only: the history bound on the revocation. Deliberately its own
     * field, NOT the selection's `after` — it bounds what is revoked without
     * re-scoping the preview, so it does not invalidate the hash.
     */
    val revokedAfter: String = "",

    val selectedOp: AdminLadderOp = AdminLadderOp.ANNOTATE,

    // ── Preview ──
    val previewing: Boolean = false,
    /** The preview that is currently ratifiable, or null. */
    val preview: AdminPreviewResponse? = null,
    /** The exact selection [preview]'s hash covers. Submitted verbatim. */
    val previewedSelection: AdminSelectionDto? = null,
    val previewRefusal: AdminRefusal? = null,
    /** Transport/parse fault while previewing — a third fact, not a refusal. */
    val previewError: String? = null,

    // ── Commit ──
    val confirmOpen: Boolean = false,
    /** Tier 3's typed acknowledgement. Compared against the localized ack word. */
    val descendAck: String = "",
    val committing: Boolean = false,
    val result: AdminOpResponse? = null,
    val commitRefusal: AdminRefusal? = null,
    val commitError: String? = null,
) {
    /** A hash may be presented only while a preview is held for THIS selection. */
    val canCommit: Boolean
        get() = preview != null &&
            previewedSelection != null &&
            delegationId.isNotBlank() &&
            reason.isNotBlank() &&
            (!selectedOp.requiresCommunityId || communityId.isNotBlank()) &&
            !committing

    /** Distinct quorum ids the operator has typed, in submission order. */
    val quorumDelegationIds: List<String>
        get() = quorumDelegationIdsRaw
            .split(',', '\n', ';')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
}

/**
 * Drives the owner-gated **graded enforcement ladder** — tiers 0–4 of
 * `src/admin_ops.rs` (CIRISServer#346 / #361, plus #375's AV-77 write door).
 *
 * Two things this VM refuses to do, both on purpose:
 *
 *  - **It never re-derives a selection at commit time.** The commit body is
 *    built from [AdminLadderState.previewedSelection] + the hash that came back
 *    with it. The server would refuse a mismatch, but a client that could
 *    produce one at all has already shown the operator something other than
 *    what it signed.
 *  - **It never swallows a refusal.** Refusals carry the sentence describing
 *    what the op reaches and what it does not; they are surfaced as state, and
 *    only transport faults become [AdminLadderState.commitError].
 */
class AdminLadderViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(AdminLadderState())
    val state: StateFlow<AdminLadderState> = _state.asStateFlow()

    // ── Selection setters: each one INVALIDATES an outstanding preview ──

    fun setAttestingKeyId(value: String) = mutateSelection { it.copy(attestingKeyId = value) }

    /** The pasted key list. Changes the selection, therefore changes the hash. */
    fun setAttestingKeyIdsRaw(value: String) =
        mutateSelection { it.copy(attestingKeyIdsRaw = value) }

    fun setAttestationType(value: String) = mutateSelection { it.copy(attestationType = value) }

    fun setDimensionPrefix(value: String) = mutateSelection { it.copy(dimensionPrefix = value) }

    fun setSelectionAfter(value: String) = mutateSelection { it.copy(selectionAfter = value) }

    // ── Attribution + per-op setters: the hash does NOT cover these ──

    fun setDelegationId(value: String) {
        _state.value = _state.value.copy(delegationId = value)
    }

    fun setReason(value: String) {
        _state.value = _state.value.copy(reason = value)
    }

    fun setCommunityId(value: String) {
        _state.value = _state.value.copy(communityId = value)
    }

    fun setQuorumDelegationIds(value: String) {
        _state.value = _state.value.copy(quorumDelegationIdsRaw = value)
    }

    fun setRevokedAfter(value: String) {
        _state.value = _state.value.copy(revokedAfter = value)
    }

    fun setDescendAck(value: String) {
        _state.value = _state.value.copy(descendAck = value)
    }

    /**
     * Choose a rung. The preview SURVIVES: the selection hash is a function of
     * the selection alone, so the same ratified row set may be walked up or down
     * the ladder without re-previewing. The last op's result does not, because
     * "annotated 9 rows" must never sit under a heading that now says "descend".
     */
    fun selectOp(op: AdminLadderOp) {
        _state.value = _state.value.copy(
            selectedOp = op,
            result = null,
            commitRefusal = null,
            commitError = null,
            descendAck = "",
            confirmOpen = false,
        )
    }

    fun openConfirm() {
        if (_state.value.preview == null) return
        _state.value = _state.value.copy(
            confirmOpen = true,
            descendAck = "",
            result = null,
            commitRefusal = null,
            commitError = null,
        )
    }

    fun closeConfirm() {
        _state.value = _state.value.copy(confirmOpen = false, descendAck = "")
    }

    /** Clear the last committed result / refusal without touching the preview. */
    fun clearResult() {
        _state.value = _state.value.copy(
            result = null,
            commitRefusal = null,
            commitError = null,
        )
    }

    /**
     * Split a pasted key list on newlines, commas, semicolons or whitespace.
     *
     * Trims, drops blanks, de-duplicates while PRESERVING the order the
     * operator pasted — the preview they ratify should read in the order they
     * supplied, not sorted into something they have to re-check. A blank entry
     * would widen the predicate to a key that cannot exist, so it is dropped
     * rather than sent.
     */
    private fun parseKeyList(raw: String): List<String> =
        raw.split('\n', ',', ';', ' ', '\t')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()

    /** The selection as the wire sees it — the ONE place the form becomes a filter. */
    private fun AdminLadderState.toSelection(): AdminSelectionDto = AdminSelectionDto(
        attestingKeyId = attestingKeyId.trim().ifBlank { null },
        attestingKeyIds = parseKeyList(attestingKeyIdsRaw),
        attestationType = attestationType.trim().ifBlank { null },
        dimensionPrefixes = dimensionPrefix.trim().let { if (it.isEmpty()) emptyList() else listOf(it) },
        after = selectionAfter.trim().ifBlank { null },
    )

    /**
     * `POST /v1/admin/preview`. Captures the selection and its hash together;
     * everything downstream reads that captured pair.
     */
    fun runPreview() {
        val current = _state.value
        if (current.previewing) return
        val selection = current.toSelection()
        _state.value = current.copy(
            previewing = true,
            preview = null,
            previewedSelection = null,
            previewRefusal = null,
            previewError = null,
            result = null,
            commitRefusal = null,
            commitError = null,
        )
        viewModelScope.launch {
            try {
                when (val outcome = apiClient.adminPreview(selection)) {
                    is AdminPreviewOutcome.Ok -> {
                        PlatformLogger.i(
                            TAG,
                            "preview rows=${outcome.preview.counts.rows} " +
                                "targets=${outcome.preview.counts.targets} " +
                                "truncated=${outcome.preview.counts.truncated} " +
                                "window=${outcome.preview.windowEnforced}",
                        )
                        _state.value = _state.value.copy(
                            previewing = false,
                            preview = outcome.preview,
                            previewedSelection = selection,
                        )
                    }
                    is AdminPreviewOutcome.Refused -> {
                        PlatformLogger.w(
                            TAG,
                            "preview refused ${outcome.status}: ${outcome.refusal.refusal}",
                        )
                        _state.value = _state.value.copy(
                            previewing = false,
                            previewRefusal = outcome.refusal,
                        )
                    }
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "preview failed: ${e.message}")
                _state.value = _state.value.copy(
                    previewing = false,
                    previewError = e.message ?: e::class.simpleName ?: "unknown",
                )
            }
        }
    }

    /**
     * Commit the selected rung against the PREVIEWED selection.
     *
     * On a `preview_hash_mismatch` the server hands back the preview that IS
     * current; it is adopted here (together with the selection it was computed
     * for) so the operator re-reads the new blast radius before ratifying it —
     * never silently retried.
     */
    fun commit() {
        val current = _state.value
        val preview = current.preview ?: return
        val selection = current.previewedSelection ?: return
        if (current.committing) return
        if (current.delegationId.isBlank() || current.reason.isBlank()) return
        val op = current.selectedOp

        val request = AdminLadderCommitRequest(
            selection = selection,
            selectionHash = preview.selectionHash,
            delegationId = current.delegationId.trim(),
            reason = current.reason.trim(),
            communityId = if (op.requiresCommunityId) current.communityId.trim().ifBlank { null } else null,
            quorumDelegationIds = if (op.requiresQuorum) current.quorumDelegationIds else emptyList(),
            after = if (op.acceptsRevokedAfter) current.revokedAfter.trim().ifBlank { null } else null,
        )

        _state.value = current.copy(
            committing = true,
            result = null,
            commitRefusal = null,
            commitError = null,
        )
        viewModelScope.launch {
            try {
                when (val outcome = apiClient.adminLadderCommit(op, request)) {
                    is AdminOpOutcome.Ok -> {
                        PlatformLogger.w(
                            TAG,
                            "committed ${outcome.response.op} tier=${outcome.response.tier} " +
                                "hash=${preview.selectionHash.take(12)}",
                        )
                        _state.value = _state.value.copy(
                            committing = false,
                            confirmOpen = false,
                            descendAck = "",
                            result = outcome.response,
                        )
                    }
                    is AdminOpOutcome.Refused -> {
                        PlatformLogger.w(
                            TAG,
                            "commit refused ${outcome.status}: ${outcome.refusal.refusal}",
                        )
                        val fresh = outcome.refusal.current
                        _state.value = _state.value.copy(
                            committing = false,
                            descendAck = "",
                            commitRefusal = outcome.refusal,
                            // The selection did not change — only the rows under
                            // it did — so the fresh preview belongs to the same
                            // selection and is ratifiable once re-read.
                            preview = fresh ?: _state.value.preview,
                            previewedSelection = if (fresh != null) selection else _state.value.previewedSelection,
                        )
                    }
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "commit failed: ${e.message}")
                _state.value = _state.value.copy(
                    committing = false,
                    commitError = e.message ?: e::class.simpleName ?: "unknown",
                )
            }
        }
    }

    /**
     * Apply a selection edit and drop the outstanding preview with it. The two
     * happen in one write so no recomposition can observe a hash that no longer
     * describes the form beside it.
     */
    private inline fun mutateSelection(edit: (AdminLadderState) -> AdminLadderState) {
        _state.value = edit(_state.value).copy(
            preview = null,
            previewedSelection = null,
            previewRefusal = null,
            previewError = null,
            result = null,
            commitRefusal = null,
            commitError = null,
            confirmOpen = false,
        )
    }
}
