package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Provision Accord Holder** guided flow (CIRISServer #41, the
 * safe-mesh custody floor). The would-be accord holder mints their portable-2FA
 * HUMANITY_ACCORD identity from an already-FIPS-approved FIPS YubiKey + a chosen
 * ML-DSA USB path.
 *
 * No-crypto posture (mirrors [AccordViewModel] / Delegations): the app holds NO
 * keys and does NO crypto. The single `provision` action POSTs to the loopback
 * `POST /v1/accord/provision-holder`; the node opens the YubiKey, AEAD-wraps the
 * ML-DSA seed to the USB, and mints the two artifacts. Touching the physical
 * YubiKey (PIN + touch) is the real authority.
 *
 * The flow is foolproof by construction: the YubiKey/FIPS acknowledgement (step
 * 1) and a non-empty ML-DSA USB path (step 2) gate the provision action (step 3),
 * and every device / USB / PIN / touch failure is mapped to plain language.
 */
class ProvisionAccordHolderViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "ProvisionHolderVM"
    }

    // ── Step 1: the YubiKey is inserted + already FIPS-approved (acknowledged). ──
    private val _fipsAcknowledged = MutableStateFlow(false)
    val fipsAcknowledged: StateFlow<Boolean> = _fipsAcknowledged.asStateFlow()

    // ── The holder's federation key_id (alias the artifacts are minted under). ──
    private val _keyId = MutableStateFlow("")
    val keyId: StateFlow<String> = _keyId.asStateFlow()

    // ── Step 2 (the centerpiece): the ML-DSA USB directory path. ────────────────
    private val _usbPath = MutableStateFlow("")
    val usbPath: StateFlow<String> = _usbPath.asStateFlow()

    // ── Optional PIV PIN (the token may prompt out of band when blank). ─────────
    private val _userPin = MutableStateFlow("")
    val userPin: StateFlow<String> = _userPin.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** The minted holder key_id, set once provisioning succeeds. Non-null = done. */
    private val _provisionedKeyId = MutableStateFlow<String?>(null)
    val provisionedKeyId: StateFlow<String?> = _provisionedKeyId.asStateFlow()

    fun setFipsAcknowledged(value: Boolean) {
        _fipsAcknowledged.value = value
    }

    fun setKeyId(value: String) {
        _keyId.value = value
    }

    fun setUsbPath(value: String) {
        _usbPath.value = value
    }

    fun setUserPin(value: String) {
        _userPin.value = value
    }

    /** True once steps 1 + 2 are satisfied — gates the Provision action (step 3). */
    fun canProvision(): Boolean =
        _fipsAcknowledged.value &&
            _keyId.value.isNotBlank() &&
            _usbPath.value.isNotBlank() &&
            !_busy.value

    /**
     * Step 3 — provision. POSTs to the loopback endpoint; the node does the
     * crypto. On success [provisionedKeyId] is set (the UI shows the success +
     * the "now ask the node owner to register you" next step). On failure the
     * plain-language reason is surfaced in [error].
     */
    fun provision() {
        if (_busy.value) return
        val keyId = _keyId.value.trim()
        val usb = _usbPath.value.trim()
        if (!_fipsAcknowledged.value) {
            _error.value = "Confirm your YubiKey is inserted and already FIPS-approved first."
            return
        }
        if (keyId.isBlank()) {
            _error.value = "Enter a key ID for this holder identity."
            return
        }
        if (usb.isBlank()) {
            _error.value = "Choose the USB folder for the ML-DSA key first."
            return
        }
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.provisionAccordHolder(
                    keyId = keyId,
                    mldsaUsbPath = usb,
                    userPin = _userPin.value.takeIf { it.isNotBlank() },
                )
                _provisionedKeyId.value = res.keyId
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[provision] ${e.message}")
                _error.value = plainLanguageError(e.message.orEmpty())
            } finally {
                _busy.value = false
            }
        }
    }

    /** Reset to provision another holder (or retry after a fix). */
    fun reset() {
        _provisionedKeyId.value = null
        _error.value = null
    }

    fun clearError() {
        _error.value = null
    }

    /**
     * Map the raw server / transport error to plain language a holder can act on.
     * The server already returns human-readable messages; this catches the common
     * device / USB / PIN / touch / FIPS / feature failures and the auth statuses.
     */
    private fun plainLanguageError(msg: String): String = when {
        msg.contains("501") || msg.contains("NotImplemented", ignoreCase = true) ||
            msg.contains("without the `pkcs11`") ->
            "This node build can't reach a YubiKey (no pkcs11 support). Ask your operator to run a " +
                "ciris-server built with the pkcs11 feature on this host."
        msg.contains("YubiKey", ignoreCase = true) || msg.contains("slot-", ignoreCase = true) ->
            "Couldn't use your YubiKey. Check it's inserted, already FIPS-approved with a slot-9c " +
                "key, and that your PIN is correct."
        msg.contains("PIN", ignoreCase = true) ->
            "Wrong or missing PIN. Re-enter your YubiKey PIV PIN and try again."
        msg.contains("not writable", ignoreCase = true) || msg.contains("not a directory", ignoreCase = true) ->
            "That USB folder isn't writable. Insert your USB key, make sure it's mounted, and choose " +
                "its folder."
        msg.contains("ykman", ignoreCase = true) ->
            "Couldn't read the YubiKey attestation (ykman not available). Ask your operator to install " +
                "yubikey-manager on this host."
        msg.contains("401") -> "Sign in as the owner on this node first, then provision."
        msg.contains("403") -> "Provisioning must run on the node's own host (localhost only)."
        else -> "Provisioning failed: $msg"
    }
}
