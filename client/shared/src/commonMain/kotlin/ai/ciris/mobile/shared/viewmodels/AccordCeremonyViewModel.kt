package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.YubiKeyStatus
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

/**
 * Drives the **guided HUMANITY_ACCORD genesis ceremony** (CIRISServer #41, the
 * safe-mesh kill-switch floor). A foolproof multi-key flow so any founder trio
 * can stand up a NEW mesh's 2-of-3 human kill-switch without error.
 *
 * The ceremony mints **6 keys** — 3 humans, each a **primary** (becomes a family
 * SEAT) and a **cold spare** (registered but NOT seated) — in the fixed order
 * A1, A2, B1, B2, C1, C2. Per key the node provisions it from the holder's
 * re-inserted FIPS YubiKey + chosen ML-DSA USB path, then the owner registers it.
 * Genesis runs over the 3 PRIMARIES only: build the envelope → each primary
 * re-inserts + cosigns → assemble (needs ≥2 cosignatures). The assemble response's
 * `genesis` is the **bake artifact** the operator MUST save.
 *
 * No-crypto posture (mirrors [AccordViewModel] / [ProvisionAccordHolderViewModel]):
 * the app holds NO keys and does NO crypto — every signature comes from a
 * re-inserted YubiKey via the loopback endpoints; the node does everything.
 */
class AccordCeremonyViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "AccordCeremonyVM"

        /** The 6 keys, in the fixed JCS-significant ceremony order. */
        val KEY_SLOTS: List<KeySlot> = listOf(
            KeySlot("A", 1, primary = true),
            KeySlot("A", 2, primary = false),
            KeySlot("B", 1, primary = true),
            KeySlot("B", 2, primary = false),
            KeySlot("C", 1, primary = true),
            KeySlot("C", 2, primary = false),
        )
    }

    /** One of the 6 ceremony key slots: a person (A/B/C) + a tier (primary/spare). */
    data class KeySlot(
        val person: String,
        val index: Int,
        /** true = PRIMARY (a family SEAT); false = cold SPARE (vault, not seated). */
        val primary: Boolean,
    ) {
        /** The human-facing slot label, e.g. "A1". */
        val label: String get() = "$person$index"
    }

    /** A key that has been provisioned + registered during the ceremony. */
    data class ProvisionedKey(
        val slot: KeySlot,
        val holderName: String,
        val keyId: String,
        val usbPath: String,
    )

    /** A collected primary cosignature (verbatim relay objects for assemble). */
    data class CollectedCosign(
        val keyId: String,
        val signature: JsonElement,
        val member: JsonElement,
    )

    /** The high-level ceremony phase. */
    enum class Phase {
        /** The opening screen — requirements + what this creates. */
        INTRO,

        /** Provisioning + registering the 6 keys one at a time. */
        PROVISION,

        /** The 3 primaries re-insert + cosign the family envelope. */
        COSIGN,

        /** The assembled genesis (bake artifact) + the SAVE step. */
        DONE,
    }

    private val _phase = MutableStateFlow(Phase.INTRO)
    val phase: StateFlow<Phase> = _phase.asStateFlow()

    /** The index into [KEY_SLOTS] for the key currently being provisioned (0..5). */
    private val _currentSlotIndex = MutableStateFlow(0)
    val currentSlotIndex: StateFlow<Int> = _currentSlotIndex.asStateFlow()

    /** The keys provisioned + registered so far (grows to 6). */
    private val _provisioned = MutableStateFlow<List<ProvisionedKey>>(emptyList())
    val provisioned: StateFlow<List<ProvisionedKey>> = _provisioned.asStateFlow()

    // ── Per-key input (reset on each slot advance). ─────────────────────────────
    private val _holderName = MutableStateFlow("")
    val holderName: StateFlow<String> = _holderName.asStateFlow()

    private val _keyId = MutableStateFlow("")
    val keyId: StateFlow<String> = _keyId.asStateFlow()

    private val _usbPath = MutableStateFlow("")
    val usbPath: StateFlow<String> = _usbPath.asStateFlow()

    private val _userPin = MutableStateFlow("")
    val userPin: StateFlow<String> = _userPin.asStateFlow()

    // ── Genesis (cosign) state. ─────────────────────────────────────────────────
    /** The verbatim family envelope from `…/genesis/envelope` (never rebuilt). */
    private val _envelope = MutableStateFlow<JsonElement?>(null)
    val envelope: StateFlow<JsonElement?> = _envelope.asStateFlow()

    /** The index into the 3 PRIMARIES for the primary currently cosigning (0..2). */
    private val _currentCosignIndex = MutableStateFlow(0)
    val currentCosignIndex: StateFlow<Int> = _currentCosignIndex.asStateFlow()

    private val _cosigns = MutableStateFlow<List<CollectedCosign>>(emptyList())
    val cosigns: StateFlow<List<CollectedCosign>> = _cosigns.asStateFlow()

    private val _cosignUsbPath = MutableStateFlow("")
    val cosignUsbPath: StateFlow<String> = _cosignUsbPath.asStateFlow()

    private val _cosignUserPin = MutableStateFlow("")
    val cosignUserPin: StateFlow<String> = _cosignUserPin.asStateFlow()

    /** The assembled genesis (bake artifact). Non-null = ceremony complete. */
    private val _genesis = MutableStateFlow<JsonElement?>(null)
    val genesis: StateFlow<JsonElement?> = _genesis.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    /** The inserted YubiKey's readiness (detected / FIPS / 9C key+cert / PIN tries),
     *  driving the "YUBI DETECTED — FIPS COMPLIANT — 9C PROVISIONED — READY" banner. */
    private val _yubiKeyStatus = MutableStateFlow<YubiKeyStatus?>(null)
    val yubiKeyStatus: StateFlow<YubiKeyStatus?> = _yubiKeyStatus.asStateFlow()

    /** Re-probe the inserted YubiKey (called on entering PROVISION + on demand). */
    fun refreshYubiKeyStatus() {
        viewModelScope.launch {
            _yubiKeyStatus.value = apiClient.getYubiKeyStatus(CIRISApiClient.LOCAL_NODE_URL)
        }
    }

    /** The PRIMARY provisioned keys, in ceremony order (the genesis member set). */
    fun primaries(): List<ProvisionedKey> = _provisioned.value.filter { it.slot.primary }

    // ── Input setters. ──────────────────────────────────────────────────────────
    fun setHolderName(v: String) { _holderName.value = v }
    fun setKeyId(v: String) { _keyId.value = v }
    fun setUsbPath(v: String) { _usbPath.value = v }
    fun setUserPin(v: String) { _userPin.value = v }
    fun setCosignUsbPath(v: String) { _cosignUsbPath.value = v }
    fun setCosignUserPin(v: String) { _cosignUserPin.value = v }

    /** Begin the ceremony — move from the opening screen to the first key. */
    fun begin() {
        _phase.value = Phase.PROVISION
        _error.value = null
        _notice.value = null
    }

    /** True once the current slot's required inputs are set — gates Provision. */
    fun canProvisionCurrent(): Boolean =
        _holderName.value.isNotBlank() &&
            _keyId.value.isNotBlank() &&
            _usbPath.value.isNotBlank() &&
            !_busy.value

    /**
     * Provision + register the current key slot. POSTs to the loopback
     * `provision-holder`, then the owner-gated `holder` register. On success the
     * key is appended + the wizard advances to the next slot (or to cosign after
     * the 6th). The app does NO crypto; the node opens the YubiKey + signs.
     */
    fun provisionCurrent() {
        if (_busy.value) return
        val slot = KEY_SLOTS[_currentSlotIndex.value]
        val name = _holderName.value.trim()
        val keyId = _keyId.value.trim()
        val usb = _usbPath.value.trim()
        if (name.isBlank() || keyId.isBlank() || usb.isBlank()) {
            _error.value = "Enter the holder's name, a key ID, and the USB folder first."
            return
        }
        _busy.value = true
        _error.value = null
        // Progress feedback: slot 9c is touch-ALWAYS and provisioning does THREE
        // Ed25519 signs (USB ML-DSA wrap-challenge, holder record, custody
        // attestation), so the holder must touch the key for EACH blink. The call is
        // one blocking request (no per-touch granularity) — set expectations up front.
        _notice.value = "Provisioning ${slot.label}… TOUCH your YubiKey each time it " +
            "blinks (≈3 touches; up to ~3 min). Keep it inserted."
        PlatformLogger.i(TAG, "[provisionCurrent ${slot.label}] starting — expect ~3 YubiKey touches, key_id=$keyId")
        viewModelScope.launch {
            try {
                val res = apiClient.provisionAccordHolder(
                    keyId = keyId,
                    mldsaUsbPath = usb,
                    userPin = _userPin.value.takeIf { it.isNotBlank() },
                )
                val record = res.holderRecord
                    ?: throw RuntimeException("provision returned no holder_record")
                // Provision succeeded — the YubiKey signatures are done and the node
                // SAVED the artifacts to its USB outbox file (the touches are never
                // wasted). Registration's persist admission gate (a PlatformAttestation
                // attestation_evidence) isn't wired for YubiKey PIV custody yet — try
                // it, but DON'T block the ceremony: the outbox file is handed to verify
                // to wrap + register later. So advance regardless.
                val registered = try {
                    apiClient.registerAccordHolder(
                        holderRecord = record,
                        custodyAttestation = res.custodyAttestation,
                    )
                    true
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[provisionCurrent ${slot.label}] register deferred (saved to outbox): ${e.message}")
                    false
                }
                _provisioned.value = _provisioned.value + ProvisionedKey(slot, name, res.keyId, usb)
                _notice.value = if (registered) {
                    "${slot.label} (${if (slot.primary) "SEAT" else "VAULT"}) provisioned + registered."
                } else {
                    "${slot.label} provisioned — artifacts SAVED to the USB outbox " +
                        "(accord_holder_${res.keyId}.json); registration deferred to verify. Advancing."
                }
                advanceSlot()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[provisionCurrent ${slot.label}] ${e.message}")
                _error.value = plainLanguageError(e.message.orEmpty())
            } finally {
                _busy.value = false
            }
        }
    }

    /** Advance to the next key slot, or build the envelope after the 6th. */
    private fun advanceSlot() {
        clearPerKeyInput()
        val next = _currentSlotIndex.value + 1
        if (next < KEY_SLOTS.size) {
            _currentSlotIndex.value = next
        } else {
            buildEnvelope()
        }
    }

    private fun clearPerKeyInput() {
        _holderName.value = ""
        _keyId.value = ""
        _usbPath.value = ""
        _userPin.value = ""
    }

    /** Build the genesis envelope over the 3 PRIMARIES, then move to cosign. */
    private fun buildEnvelope() {
        _busy.value = true
        viewModelScope.launch {
            try {
                val members = primaries().map { it.keyId }
                val res = apiClient.genesisEnvelope(memberKeyIds = members)
                _envelope.value = res.envelope
                _phase.value = Phase.COSIGN
                _currentCosignIndex.value = 0
                _notice.value = "All 6 keys registered. Now each primary holder re-inserts to cosign."
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[buildEnvelope] ${e.message}")
                _error.value = "Couldn't build the genesis envelope: ${e.message}"
            } finally {
                _busy.value = false
            }
        }
    }

    /** True once the current primary's cosign USB folder is set — gates Cosign. */
    fun canCosignCurrent(): Boolean =
        _cosignUsbPath.value.isNotBlank() && _envelope.value != null && !_busy.value

    /**
     * The current primary re-inserts their YubiKey + cosigns the family envelope.
     * POSTs to the loopback `family/cosign`; the node re-opens the YubiKey + the
     * USB-wrapped ML-DSA half and cosigns. The physical touch IS consent. On
     * success the cosignature is collected + the wizard advances to the next
     * primary (or assembles once ≥2 cosignatures are in hand).
     */
    fun cosignCurrent() {
        if (_busy.value) return
        val envelope = _envelope.value ?: run {
            _error.value = "No envelope to cosign yet."
            return
        }
        val primaries = primaries()
        val idx = _currentCosignIndex.value
        if (idx >= primaries.size) return
        val primary = primaries[idx]
        val usb = _cosignUsbPath.value.trim()
        if (usb.isBlank()) {
            _error.value = "Choose ${primary.holderName}'s USB folder (the one provisioned for ${primary.slot.label})."
            return
        }
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.cosignAccordFamily(
                    keyId = primary.keyId,
                    mldsaUsbPath = usb,
                    envelope = envelope,
                    userPin = _cosignUserPin.value.takeIf { it.isNotBlank() },
                )
                _cosigns.value = _cosigns.value + CollectedCosign(res.keyId, res.signature, res.member)
                _notice.value = "${primary.slot.label} (${primary.holderName}) cosigned."
                advanceCosign()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[cosignCurrent ${primary.slot.label}] ${e.message}")
                _error.value = plainLanguageError(e.message.orEmpty())
            } finally {
                _busy.value = false
            }
        }
    }

    private fun advanceCosign() {
        _cosignUsbPath.value = ""
        _cosignUserPin.value = ""
        val next = _currentCosignIndex.value + 1
        if (next < primaries().size) {
            _currentCosignIndex.value = next
        }
        // The operator presses "Assemble" once ≥2 cosignatures are collected
        // (genesis is 2-of-3, not unanimous) — the third is optional but offered.
    }

    /** True once ≥2 primary cosignatures are collected — gates Assemble. */
    fun canAssemble(): Boolean = _cosigns.value.size >= 2 && _envelope.value != null && !_busy.value

    /**
     * Assemble the 2/3-founder-signed genesis. POSTs to the owner-gated
     * `genesis/assemble` with the verbatim envelope + the collected founders +
     * signatures. The response's `genesis` is the bake artifact (CIRISVerify#107)
     * the operator MUST save. On success the wizard moves to the DONE screen.
     */
    fun assemble() {
        if (_busy.value) return
        val envelope = _envelope.value ?: run {
            _error.value = "No envelope to assemble."
            return
        }
        if (_cosigns.value.size < 2) {
            _error.value = "Need at least 2 of 3 primary cosignatures to assemble genesis."
            return
        }
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.genesisAssemble(
                    envelope = envelope,
                    founders = _cosigns.value.map { it.member },
                    signatures = _cosigns.value.map { it.signature },
                )
                _genesis.value = res.genesis
                _phase.value = Phase.DONE
                _notice.value = res.message
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[assemble] ${e.message}")
                _error.value = plainLanguageError(e.message.orEmpty())
            } finally {
                _busy.value = false
            }
        }
    }

    /** The assembled genesis serialized as pretty JSON for the SAVE step. */
    fun genesisJson(): String = _genesis.value?.toString() ?: ""

    fun clearMessages() {
        _error.value = null
        _notice.value = null
    }

    /**
     * Map the raw server / transport error to plain language the operator can act
     * on — the common device / USB / PIN / touch / FIPS / feature / auth failures.
     */
    private fun plainLanguageError(msg: String): String = when {
        msg.contains("501") || msg.contains("NotImplemented", ignoreCase = true) ||
            msg.contains("without the `pkcs11`") ->
            "This node build can't reach a YubiKey (no pkcs11 support). Ask your operator to run a " +
                "ciris-server built with the pkcs11 feature on this host."
        msg.contains("different YubiKey", ignoreCase = true) || msg.contains("Ed25519 pubkey mismatch", ignoreCase = true) ->
            "That's not the same YubiKey + USB pair this key was provisioned with. Insert the matching pair."
        msg.contains("YubiKey", ignoreCase = true) || msg.contains("slot-", ignoreCase = true) ->
            "Couldn't use the YubiKey. Check it's inserted, FIPS-approved with a slot-9c key, and the PIN is correct."
        msg.contains("PIN", ignoreCase = true) ->
            "Wrong or missing PIN. Re-enter the YubiKey PIV PIN and try again."
        msg.contains("not writable", ignoreCase = true) || msg.contains("not a directory", ignoreCase = true) ->
            "That USB folder isn't usable. Insert the USB key, make sure it's mounted, and choose its folder."
        msg.contains("ykman", ignoreCase = true) ->
            "Couldn't read the YubiKey attestation (ykman not available). Ask your operator to install yubikey-manager."
        msg.contains("401") -> "Sign in as the owner on this node first, then continue the ceremony."
        msg.contains("403") -> "The ceremony must run on the node's own host (localhost only)."
        msg.contains("409") -> "The node rejected the quorum (short / duplicate / non-founder signatures)."
        else -> "Step failed: $msg"
    }
}
