package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.safety.AgeAssurance
import ai.ciris.mobile.shared.models.safety.ExistenceVerdict
import ai.ciris.mobile.shared.models.safety.ModerationDuty
import ai.ciris.mobile.shared.models.safety.SafetyHonesty
import ai.ciris.mobile.shared.models.safety.WatchlistClass
import ai.ciris.mobile.shared.models.safety.WatchlistEnable
import ai.ciris.mobile.shared.models.safety.WatchlistHonesty
import ai.ciris.mobile.shared.models.safety.WatchlistMode
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private const val TAG = "SafetyViewModel"

/**
 * UI state for the holistic SAFETY surface (moderation + child-safety cards).
 *
 * The app holds NO keys and performs NO crypto: this VM only DRIVES the local
 * node's `/v1/safety/` endpoints and surfaces the results. The caller's
 * identity key_id is resolved by probing the local node's self-key-record (it
 * becomes both the `signer_key_id` for actions and the `key_id` for status).
 */
data class SafetyState(
    // ── Caller identity (probed from the local node) ──
    /** This device's federation key_id, or null until probed (no identity yet). */
    val selfKeyId: String? = null,
    val identityProbed: Boolean = false,

    // ── Protective posture (GET /v1/safety/status/{key_id}) ──
    val ageAssurance: AgeAssurance? = null,
    val statusHonesty: SafetyHonesty? = null,
    val statusLoading: Boolean = false,

    // ── Moderation card ──
    /** The community key_id the report / named-moderator lookup is scoped to. */
    val communityKeyId: String = "",
    val selectedDuty: ModerationDuty = ModerationDuty.MODERATE,
    /** The `moderation:{allegation_type}` token (free-vocab). */
    val allegationType: String = "",
    /** Comma-separated target key_ids the report names (optional). */
    val targetKeyIdsRaw: String = "",
    val reportNote: String = "",
    val filing: Boolean = false,
    /** Result of the last filing: the attestation id, or null. */
    val lastModerationAttestationId: String? = null,

    // ── Named-moderator existence invariant (GET /v1/safety/named-moderator) ──
    val namedModeratorLoading: Boolean = false,
    val namedModeratorVerdict: ExistenceVerdict? = null,
    /** Always true on the wire — surfaced verbatim (better no group than one
     *  with no moderator). */
    val namedModeratorFailsSecure: Boolean = true,

    // ── Child-safety / watchlist card ──
    /** The group key_id the watchlist applies to (you must hold `moderate`). */
    val watchlistGroupKeyId: String = "",
    val watchlistId: String = "",
    val watchlistClass: WatchlistClass = WatchlistClass.OTHER_CONTENT,
    val watchlistMode: WatchlistMode = WatchlistMode.ALERT_ONLY,
    val routeToModerator: String = "",
    val watchlistLoading: Boolean = false,
    val watchlistEnables: List<WatchlistEnable> = emptyList(),
    val watchlistHonesty: WatchlistHonesty? = null,
    val watchlistMutating: Boolean = false,

    // ── Shared ──
    val error: String? = null,
    val message: String? = null,
)

/**
 * Drives the **holistic SAFETY surface** — moderation + child-safety, built
 * AHEAD of content. Every action is a localhost call to THIS device's local node
 * (`http://127.0.0.1:8080`). The app does NO crypto; the node's substrate signs
 * + runs the admission gates (the §11.10 duty gate, the CC 4.5.4 existence
 * invariant). 403s from non-duty-holders are surfaced honestly.
 */
class SafetyViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(SafetyState())
    val state: StateFlow<SafetyState> = _state.asStateFlow()

    /**
     * Probe THIS device's local node for the caller's federation key_id, then
     * load the protective posture (age assurance) for it. The identity is the
     * `signer_key_id` for moderation/watchlist actions and the `key_id` for
     * status. If the node holds no identity yet, the cards surface that honestly.
     */
    fun probeIdentityAndStatus() {
        viewModelScope.launch {
            val keyId = try {
                apiClient.getSelfKeyRecord(CIRISApiClient.LOCAL_NODE_URL).keyId
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "probeIdentity: local node has no identity yet: ${e.message}")
                null
            }
            _state.value = _state.value.copy(selfKeyId = keyId, identityProbed = true)
            if (keyId != null) loadStatus(keyId)
        }
    }

    /** Load the aggregate protective posture (`GET /v1/safety/status/{key_id}`). */
    fun loadStatus(keyId: String) {
        _state.value = _state.value.copy(statusLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = apiClient.getSafetyStatus(keyId)
                _state.value = _state.value.copy(
                    statusLoading = false,
                    ageAssurance = resp.ageAssurance,
                    statusHonesty = resp.honesty,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    statusLoading = false,
                    error = "Couldn't load safety status: ${e.message}",
                )
            }
        }
    }

    // ── Moderation card setters ──
    fun setCommunityKeyId(v: String) { _state.value = _state.value.copy(communityKeyId = v) }
    fun setDuty(d: ModerationDuty) { _state.value = _state.value.copy(selectedDuty = d) }
    fun setAllegationType(v: String) { _state.value = _state.value.copy(allegationType = v) }
    fun setTargetKeyIdsRaw(v: String) { _state.value = _state.value.copy(targetKeyIdsRaw = v) }
    fun setReportNote(v: String) { _state.value = _state.value.copy(reportNote = v) }

    /**
     * **File a ModerationEvent** (`POST /v1/safety/moderation`). Admitted by the
     * node IFF the signer holds the duty or sits on a live delegated chain;
     * non-holders get a 403 surfaced here. The app does no crypto.
     */
    fun fileModeration() {
        val s = _state.value
        val signer = s.selfKeyId
        if (signer == null) {
            _state.value = s.copy(error = "No federation identity on this device yet.")
            return
        }
        if (s.communityKeyId.isBlank() || s.allegationType.isBlank()) {
            _state.value = s.copy(error = "Community and allegation type are required.")
            return
        }
        val targets = s.targetKeyIdsRaw.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        _state.value = s.copy(filing = true, error = null, message = null, lastModerationAttestationId = null)
        viewModelScope.launch {
            try {
                val resp = apiClient.fileModeration(
                    signerKeyId = signer,
                    communityKeyId = s.communityKeyId.trim(),
                    duty = s.selectedDuty,
                    allegationType = s.allegationType.trim(),
                    targetKeyIds = targets,
                    note = s.reportNote.trim().ifBlank { null },
                )
                _state.value = _state.value.copy(
                    filing = false,
                    lastModerationAttestationId = resp.attestationId,
                    message = "Report filed (${resp.duty}).",
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    filing = false,
                    error = "Couldn't file report: ${e.message}",
                )
            }
        }
    }

    /**
     * **Look up the named moderator** for the current community
     * (`GET /v1/safety/named-moderator/{community_key_id}`). Surfaces the CC
     * 4.5.4 existence verdict (operate / auto_promote / quiesce).
     */
    fun loadNamedModerator() {
        val community = _state.value.communityKeyId.trim()
        if (community.isBlank()) {
            _state.value = _state.value.copy(error = "Enter a community key_id first.")
            return
        }
        _state.value = _state.value.copy(namedModeratorLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = apiClient.getNamedModerator(community)
                _state.value = _state.value.copy(
                    namedModeratorLoading = false,
                    namedModeratorVerdict = resp.existence,
                    namedModeratorFailsSecure = resp.failsSecure,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    namedModeratorLoading = false,
                    error = "Couldn't load named moderator: ${e.message}",
                )
            }
        }
    }

    // ── Child-safety / watchlist setters ──
    fun setWatchlistGroupKeyId(v: String) { _state.value = _state.value.copy(watchlistGroupKeyId = v) }
    fun setWatchlistId(v: String) { _state.value = _state.value.copy(watchlistId = v) }
    fun setWatchlistClass(c: WatchlistClass) { _state.value = _state.value.copy(watchlistClass = c) }
    fun setWatchlistMode(m: WatchlistMode) { _state.value = _state.value.copy(watchlistMode = m) }
    fun setRouteToModerator(v: String) { _state.value = _state.value.copy(routeToModerator = v) }

    /** Load the current watchlist enables + honesty block for the group. */
    fun loadWatchlist() {
        val group = _state.value.watchlistGroupKeyId.trim()
        if (group.isBlank()) {
            _state.value = _state.value.copy(error = "Enter a group key_id first.")
            return
        }
        _state.value = _state.value.copy(watchlistLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = apiClient.getWatchlist(group)
                _state.value = _state.value.copy(
                    watchlistLoading = false,
                    watchlistEnables = resp.enables,
                    watchlistHonesty = resp.honesty,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    watchlistLoading = false,
                    error = "Couldn't load watchlist: ${e.message}",
                )
            }
        }
    }

    /**
     * **Enable or disable** a per-group watchlist (`POST /v1/safety/watchlist`).
     * Opt-in, default OFF, per-group, NEVER global. `moderate`-gated; CSAM also
     * `takedown`-gated. Disable is a POST with `enabled=false` (the node emits a
     * `withdraws`). Non-authorized signers get a 403 surfaced here.
     */
    fun setWatchlistEnabled(enabled: Boolean) {
        val s = _state.value
        val signer = s.selfKeyId
        if (signer == null) {
            _state.value = s.copy(error = "No federation identity on this device yet.")
            return
        }
        if (s.watchlistGroupKeyId.isBlank() || s.watchlistId.isBlank()) {
            _state.value = s.copy(error = "Group and watchlist id are required.")
            return
        }
        _state.value = s.copy(watchlistMutating = true, error = null, message = null)
        viewModelScope.launch {
            try {
                apiClient.setWatchlist(
                    signerKeyId = signer,
                    groupKeyId = s.watchlistGroupKeyId.trim(),
                    watchlistId = s.watchlistId.trim(),
                    watchlistClass = s.watchlistClass,
                    enabled = enabled,
                    mode = s.watchlistMode,
                    routeToModerator = s.routeToModerator.trim().ifBlank { null },
                )
                _state.value = _state.value.copy(
                    watchlistMutating = false,
                    message = if (enabled) "Watchlist enabled for this group." else "Watchlist disabled for this group.",
                )
                loadWatchlist()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    watchlistMutating = false,
                    error = "Couldn't update watchlist: ${e.message}",
                )
            }
        }
    }

    fun clearMessages() { _state.value = _state.value.copy(error = null, message = null) }
}
