package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

/**
 * Drives the **Delegate moderation duty** card — conferring `slash` / `moderate` /
 * `review` on another self, with an explicit answer to "may they pass it on, and
 * how far?".
 *
 * Two loopback + owner-gated routes, the accord co-scrub shape:
 *  - [propose] mints the FIRST scrub. The returned `partial` does NOT yet confer
 *    the duty (it is 1 of `quorum_needed`).
 *  - [cosign] appends THIS holder's scrub to that partial. When
 *    [scrubCount] meets [quorumNeeded] the node flips [adopted] and the duty is
 *    conferred.
 *
 * The `partial` is OPAQUE: it is held as a raw [JsonElement] and handed back to
 * the node byte-for-byte, because the envelope's signature covers its exact
 * bytes. The app never re-encodes it and never reads its internals.
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. It supplies the
 * holder's key_id + ML-DSA USB path; the LOCAL node opens the hardware and signs
 * (the YubiKey touch is the consent).
 */
class DutyConferralViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "DutyConferralVM"

        /**
         * The duty verbs the node accepts — ALL FIVE the substrate defines.
         *
         * This list shipped with three. `takedown` and `consent_revocation` were
         * absent, so the card could not confer them and the menu looked complete.
         * The server holds the authoritative copy (imported from persist's own
         * consts and gated by `duty_scopes_match_the_substrate.rs`); these are the
         * display order, EMIT authorities first, then the one that takes away.
         */
        const val DUTY_CONSENT_REVOCATION = "consent_revocation"
        const val DUTY_MODERATE = "moderate"
        const val DUTY_TAKEDOWN = "takedown"
        const val DUTY_REVIEW = "review"
        const val DUTY_SLASH = "slash"

        val ALL_DUTIES = listOf(
            DUTY_CONSENT_REVOCATION, DUTY_MODERATE, DUTY_TAKEDOWN, DUTY_REVIEW, DUTY_SLASH,
        )

        /** The global sub-delegation rail — a null depth is bounded by THIS. */
        const val GLOBAL_DEPTH_RAIL = 5

        /** The node answered and there is no accord family — NOT a read failure. */
        const val NO_ACCORD_FAMILY =
            "this node knows no accord family yet, so there is no authority to confer from"
    }

    // ── The conferral being composed ─────────────────────────────────────────

    /** The self the duty is conferred ON. */
    private val _subjectKeyId = MutableStateFlow("")
    val subjectKeyId: StateFlow<String> = _subjectKeyId.asStateFlow()

    /**
     * The duties this grant carries — a SET, because persist admits `scope` as a
     * JSON array with set-containment. Conferring `moderate` AND `takedown`
     * together is one grant and one ceremony; forcing one duty per grant was a
     * narrowing this client invented, not a substrate limit.
     */
    private val _duties = MutableStateFlow(setOf(DUTY_MODERATE))
    val duties: StateFlow<Set<String>> = _duties.asStateFlow()

    /** May the subject pass the duty on at all? */
    private val _subDelegation = MutableStateFlow(false)
    val subDelegation: StateFlow<Boolean> = _subDelegation.asStateFlow()

    /** Further hops allowed; null = bounded only by [GLOBAL_DEPTH_RAIL]. */
    private val _subDelegationDepth = MutableStateFlow<Int?>(null)
    val subDelegationDepth: StateFlow<Int?> = _subDelegationDepth.asStateFlow()

    // ── The signing holder ───────────────────────────────────────────────────

    /** The accord holder's seal alias (its YubiKey + USB ML-DSA opens it). */
    private val _holderKeyId = MutableStateFlow("")
    val holderKeyId: StateFlow<String> = _holderKeyId.asStateFlow()

    /** The folder holding the USB-wrapped ML-DSA half. */
    private val _usbPath = MutableStateFlow("")
    val usbPath: StateFlow<String> = _usbPath.asStateFlow()

    /**
     * The PIV user PIN. Without it the node cannot open the holder's slot-9c key
     * and the ceremony fails at the token with
     * `accord.duty.holder_custody`. Every other holder-signing flow collects it;
     * this card omitted the field entirely, so the request always arrived with
     * `pkcs11: null` and could not have succeeded for anyone.
     */
    private val _userPin = MutableStateFlow("")
    val userPin: StateFlow<String> = _userPin.asStateFlow()

    /**
     * The BAKED accord holders, read from `GET /v1/accord-holders`.
     *
     * The holder was a free-text `key_id` box. Every other accord card offers the
     * registry as a dropdown ([`HolderSignInputs`]) — typing `A1` by hand is both
     * a typo waiting to happen and a worse answer than the node's own list, which
     * knows exactly which holders exist and is the same source the quorum is
     * counted from.
     */
    private val _holders = MutableStateFlow<List<ai.ciris.mobile.shared.models.federation.AccordHolderDto>>(emptyList())
    val holders: StateFlow<List<ai.ciris.mobile.shared.models.federation.AccordHolderDto>> =
        _holders.asStateFlow()

    // ── Co-scrub progress ────────────────────────────────────────────────────

    /** The opaque partial — round-tripped VERBATIM into the next [cosign]. */
    private val _partial = MutableStateFlow<JsonElement?>(null)
    val partial: StateFlow<JsonElement?> = _partial.asStateFlow()

    private val _scrubCount = MutableStateFlow(0)
    val scrubCount: StateFlow<Int> = _scrubCount.asStateFlow()

    private val _quorumNeeded = MutableStateFlow(0)
    val quorumNeeded: StateFlow<Int> = _quorumNeeded.asStateFlow()

    /** True once the conferral met quorum — the duty is conferred. */
    private val _adopted = MutableStateFlow(false)
    val adopted: StateFlow<Boolean> = _adopted.asStateFlow()

    /**
     * What the adopted grant says, in the node's own words ("moderate conferred on
     * X; sub-delegation: 2 hops"). Read-back beats inference: the operator sees the
     * sentence the node signed, not the one the form implied.
     */
    private val _conferred = MutableStateFlow<String?>(null)
    val conferred: StateFlow<String?> = _conferred.asStateFlow()

    private val _inProgress = MutableStateFlow(false)
    val inProgress: StateFlow<Boolean> = _inProgress.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // ── The SOURCE of the delegation, read live from the node ────────────────
    //
    // The conferring authority is the humanity accord — hardcoded server-side as
    // `HUMANITY_ACCORD_FAMILY_KEY_ID` and, before this, never stated anywhere the
    // operator could see it. The card showed a bare "have 1, need 2" with no
    // mention of WHOSE quorum, which is the wrong shape for a constitutional act:
    // you would be signing on behalf of an authority the card declined to name.
    //
    // Read from `GET /v1/accord/family` rather than written as a constant here. A
    // label the client hardcodes is a label that can disagree with the substrate;
    // this one cannot, because it IS the substrate's answer.

    /** The conferring family's `key_id` (`humanity-accord`), or null until loaded. */
    private val _sourceFamilyKeyId = MutableStateFlow<String?>(null)
    val sourceFamilyKeyId: StateFlow<String?> = _sourceFamilyKeyId.asStateFlow()

    /** Its display name (`HUMANITY_ACCORD`). */
    private val _sourceFamilyName = MutableStateFlow<String?>(null)
    val sourceFamilyName: StateFlow<String?> = _sourceFamilyName.asStateFlow()

    /** Its quorum policy verbatim (`quorum:2/3`) — the accord's own words. */
    private val _sourceConsensus = MutableStateFlow<String?>(null)
    val sourceConsensus: StateFlow<String?> = _sourceConsensus.asStateFlow()

    /** Whether that policy is entrenched (it cannot be lowered casually). */
    private val _sourceEntrenched = MutableStateFlow(false)
    val sourceEntrenched: StateFlow<Boolean> = _sourceEntrenched.asStateFlow()

    /** The LIVE seats (admitted minus revoked) — who may scrub this grant. */
    private val _sourceSeats = MutableStateFlow<List<String>>(emptyList())
    val sourceSeats: StateFlow<List<String>> = _sourceSeats.asStateFlow()

    /** Set when the source could not be read — the card must refuse, not guess. */
    private val _sourceError = MutableStateFlow<String?>(null)
    val sourceError: StateFlow<String?> = _sourceError.asStateFlow()

    /**
     * The inserted token's readiness (`GET /v1/accord/yubikey-status`). Shown as
     * the same banner the genesis ceremony uses, so an operator learns their
     * token is absent, not FIPS, or has an empty 9C slot BEFORE two people are in
     * the room rather than from a failed signature.
     */
    private val _yubiKeyStatus =
        MutableStateFlow<ai.ciris.mobile.shared.models.federation.YubiKeyStatus?>(null)
    val yubiKeyStatus: StateFlow<ai.ciris.mobile.shared.models.federation.YubiKeyStatus?> =
        _yubiKeyStatus.asStateFlow()

    fun refreshYubiKeyStatus() {
        viewModelScope.launch {
            runCatching { apiClient.getYubiKeyStatus() }
                .onSuccess { _yubiKeyStatus.value = it }
                .onFailure { PlatformLogger.w(TAG, "[yubikey] ${it.message}") }
        }
    }

    /**
     * **Load the source and prefill the subject.** Called when the card opens.
     *
     * The subject defaults to THIS node's bound owner (its fed-ID, from
     * `owned-nodes`) because conferring on yourself is the first thing anyone does
     * and retyping a 50-character key_id by hand is an invitation to confer a duty
     * on a typo. It stays editable — conferring on someone else is legitimate —
     * but the default is the identity the node already knows.
     */
    fun load() {
        viewModelScope.launch {
            runCatching { apiClient.getAccordFamily() }
                .onSuccess { fam ->
                    if (fam == null) {
                        // A 404 is a THIRD state, distinct from both success and
                        // failure: this node reached the substrate and it says
                        // there is no accord family yet. Nothing can be conferred,
                        // but nothing is broken either — and conflating it with a
                        // transport error would send the operator debugging a
                        // network that is working fine.
                        _sourceError.value = NO_ACCORD_FAMILY
                    } else {
                        _sourceFamilyKeyId.value = fam.familyKeyId
                        _sourceFamilyName.value = fam.familyName
                        _sourceConsensus.value = fam.consensusProtocol
                        _sourceEntrenched.value = fam.entrenched
                        _sourceSeats.value = fam.members.map { it.keyId }
                        _sourceError.value = null
                    }
                }
                .onFailure {
                    // Distinct from "no seats": we could not ASK. The card renders
                    // this instead of an empty roster, which would read as "the
                    // accord has no holders" — a very different and false claim.
                    _sourceError.value = it.message ?: "could not read the conferring authority"
                }
            refreshYubiKeyStatus()
            runCatching { apiClient.getAccordHolders() }
                .onSuccess { _holders.value = it.holders }
                .onFailure { PlatformLogger.w(TAG, "[load] holder registry unreadable: ${it.message}") }
            // Prefill only — never clobber something the operator already typed.
            if (_subjectKeyId.value.isBlank()) {
                runCatching { apiClient.getOwnedNodes() }
                    .onSuccess { owned -> owned.owner?.let { _subjectKeyId.value = it } }
            }
        }
    }

    // ── Field setters (the card is a form; the VM owns its state) ────────────

    fun setSubjectKeyId(value: String) {
        _subjectKeyId.value = value
    }

    /** Tick or untick one duty. */
    fun toggleDuty(value: String) {
        _duties.value = _duties.value.let { if (value in it) it - value else it + value }
    }

    fun setHolderKeyId(value: String) {
        _holderKeyId.value = value
    }

    fun setUserPin(value: String) {
        _userPin.value = value
    }

    fun setUsbPath(value: String) {
        _usbPath.value = value
    }

    /**
     * Set the delegation-depth choice. The two axes move TOGETHER — "leaf" is
     * (false, null); "N further hops" is (true, N); "unbounded" is (true, null),
     * i.e. bounded only by the global rail. Setting them independently is how a
     * client ends up asking for "no sub-delegation, depth 3".
     */
    fun setDelegationDepth(subDelegation: Boolean, depth: Int?) {
        _subDelegation.value = subDelegation
        _subDelegationDepth.value = if (subDelegation) depth else null
    }

    /**
     * Replace the partial (e.g. one pasted / handed over from the holder who
     * proposed it on another device), so THIS holder can [cosign] it.
     */
    fun setPartial(value: JsonElement?) {
        _partial.value = value
    }

    fun clearError() {
        _error.value = null
    }

    /** Drop the in-flight conferral and start a fresh one. */
    fun reset() {
        _partial.value = null
        _scrubCount.value = 0
        _quorumNeeded.value = 0
        _adopted.value = false
        _conferred.value = null
        _error.value = null
    }

    // ── The two round-trips ──────────────────────────────────────────────────

    /**
     * Scrub #1 — confer the duty. The result is a partial that still needs
     * [quorumNeeded] − 1 more holder scrubs before it takes effect.
     */
    fun propose() {
        val subject = _subjectKeyId.value.trim()
        val holder = _holderKeyId.value.trim()
        val usb = _usbPath.value.trim()
        if (subject.isEmpty()) {
            _error.value = "Enter the fed-ID (key_id) of the self you're conferring the duty on."
            return
        }
        if (holder.isEmpty() || usb.isEmpty()) {
            _error.value = "Enter the accord holder's key_id and the ML-DSA USB folder — the node signs with them."
            return
        }
        if (_inProgress.value) return
        _inProgress.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.proposeDutyConferral(
                    holderKeyId = holder,
                    mldsaUsbPath = usb,
                    subjectKeyId = subject,
                    duties = _duties.value.toList().sorted(),
                    userPin = _userPin.value.takeIf { it.isNotBlank() },
                    subDelegation = _subDelegation.value,
                    subDelegationDepth = _subDelegationDepth.value,
                )
                applyResult(result)
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[propose] ${e.message}")
                _error.value = friendly(e, "Couldn't propose the duty conferral")
            } finally {
                _inProgress.value = false
            }
        }
    }

    /**
     * Append THIS holder's scrub to the pending [partial]. The partial goes back
     * to the node UNCHANGED — the signature covers its exact bytes.
     */
    fun cosign() {
        val pending = _partial.value
        val holder = _holderKeyId.value.trim()
        val usb = _usbPath.value.trim()
        if (pending == null) {
            _error.value = "There's nothing to cosign yet — propose the conferral first (or paste a partial)."
            return
        }
        if (holder.isEmpty() || usb.isEmpty()) {
            _error.value = "Enter the accord holder's key_id and the ML-DSA USB folder — the node signs with them."
            return
        }
        if (_inProgress.value) return
        _inProgress.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.cosignDutyConferral(
                    holderKeyId = holder,
                    mldsaUsbPath = usb,
                    partial = pending,
                    userPin = _userPin.value.takeIf { it.isNotBlank() },
                )
                applyResult(result)
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[cosign] ${e.message}")
                _error.value = friendly(e, "Couldn't cosign the duty conferral")
            } finally {
                _inProgress.value = false
            }
        }
    }

    /** Both routes answer the same body — one place absorbs it. */
    /**
     * Clear the PIN after a successful scrub. The next signature is a DIFFERENT
     * human with a different token; leaving holder A's PIN in the box invites
     * holder B to press submit without noticing whose credential is in it.
     */
    private fun clearPinBetweenHolders() {
        _userPin.value = ""
    }

    private fun applyResult(result: ai.ciris.mobile.shared.models.federation.DutyConferralResponse) {
        // Keep the last good partial when a response omits it (adopted records
        // have nothing left to hand on).
        result.partial?.let { _partial.value = it }
        _scrubCount.value = result.scrubCount
        _quorumNeeded.value = result.quorumNeeded
        _adopted.value = result.adopted
        _conferred.value = result.conferred
    }

    /** Map the transport failure onto something the operator can act on. */
    private fun friendly(e: Exception, prefix: String): String {
        val msg = e.message.orEmpty()
        return when {
            msg.contains("401") || msg.contains("403") ->
                "Sign in as the owner on this node first — conferring a duty is owner-gated."
            msg.contains("404") ->
                "This node doesn't serve the duty routes yet — update the node."
            msg.contains("timed out", ignoreCase = true) || msg.contains("Timeout", ignoreCase = true) ->
                "Timed out waiting for the holder's key — touch it when it blinks and retry."
            else -> "$prefix: ${e.message}"
        }
    }
}
