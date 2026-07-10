package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.ModerationProposalResult
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The three proposable moderation actions of the CC 4.5.13 reverse-quorum
 * open-labeling path. ANYONE (any adult member) MAY propose any of these
 * against any piece of content — none of them is the authoritative
 * duty-holder action; each merely OPENS the 48-hour community window.
 *
 * [wire] is the token the server's report→`scores` Contribution carries
 * (see [CIRISApiClient.proposeModeration]).
 */
enum class ModerationAction(val wire: String) {
    /** Flag for attention — "something is off here." */
    REPORT("report"),

    /** Ask the community/moderator to remove the content. */
    TAKEDOWN("takedown"),

    /** Open a neutral keep-or-remove question for the window to decide. */
    QUESTION("question"),
}

/**
 * UI-facing state of a single moderation proposal submission.
 */
data class ModerationSubmitState(
    val isSubmitting: Boolean = false,
    /** Set once the proposal has been accepted (the window is open). */
    val result: ModerationProposalResult? = null,
    val error: String? = null,
) {
    val isDone: Boolean get() = result != null
}

/**
 * Drives the **reverse-quorum moderation PROPOSAL** flow (CC 4.5.13).
 *
 * This VM does not adjudicate anything — adjudication is server-side
 * governance (a present moderator/steward acts within 48h, else the live
 * community falls back). Its only job is to take the user's chosen
 * [ModerationAction] + optional reason for a given target content id and
 * POST the open-labeling report→`scores` Contribution via
 * [CIRISApiClient.proposeModeration], then surface the submit state.
 *
 * Adult-only gating + the minor-through-steward path are deliberately NOT
 * enforced here — they are being specced separately and are a follow-up.
 */
class ModerationViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "ModerationVM"

        /** The constitutional participation window — CC 4.5.13. */
        const val WINDOW_HOURS = 48
    }

    private val _state = MutableStateFlow(ModerationSubmitState())
    val state: StateFlow<ModerationSubmitState> = _state.asStateFlow()

    /** Reset before opening the sheet for a fresh target. */
    fun reset() {
        _state.value = ModerationSubmitState()
    }

    /**
     * Submit a moderation proposal against [targetId]. Opens the 48-hour
     * community window. [onComplete] fires (on success) so the caller can
     * dismiss the sheet.
     */
    fun submit(
        targetId: String,
        action: ModerationAction,
        reason: String?,
        onComplete: () -> Unit = {},
    ) {
        if (_state.value.isSubmitting) return
        _state.value = ModerationSubmitState(isSubmitting = true)
        viewModelScope.launch {
            try {
                PlatformLogger.i(
                    TAG,
                    "propose moderation target=$targetId action=${action.wire} hasReason=${!reason.isNullOrBlank()}",
                )
                val result = apiClient.proposeModeration(
                    targetId = targetId,
                    action = action.wire,
                    reason = reason?.trim()?.ifBlank { null },
                )
                _state.value = ModerationSubmitState(result = result)
                onComplete()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "moderation proposal failed: ${e.message}")
                _state.value = ModerationSubmitState(
                    error = e.message ?: "Could not submit. Please try again.",
                )
            }
        }
    }
}
