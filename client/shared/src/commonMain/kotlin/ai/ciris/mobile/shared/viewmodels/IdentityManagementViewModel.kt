package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.AddOccurrenceBody
import ai.ciris.mobile.shared.models.federation.AddOccurrenceRequest
import ai.ciris.mobile.shared.models.federation.MintedIdentity
import ai.ciris.mobile.shared.models.federation.SelfOccurrence
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Identity Management** screen — "manage my self + log in as myself
 * on another device" (CIRISServer#76, CEG §5.6.8.8 / §11.7). The client half of
 * the second-occurrence / laptop-loss-resilience feature.
 *
 * Two roles, one page:
 *  - On the PRIMARY device: shows the self fed-ID + device roster, lets the user
 *    ADD a new device (by its fedcode) and REVOKE a lost / stolen one.
 *  - On a NEW device: [enrollThisDevice] mints a local fed-ID and surfaces ITS
 *    fedcode for the primary to scan / paste.
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. The ADD / REVOKE are
 * federation-signed — the LOCAL node signs with the user's resolved fed-ID signer
 * (same posture as the consent / delegation cards). The app only DRIVES the node.
 */
class IdentityManagementViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "IdentityMgmtVM"
    }

    /** The self fed-ID `key_id` whose roster we list / mutate (the node's bound owner). */
    private val _identityKeyId = MutableStateFlow<String?>(null)
    val identityKeyId: StateFlow<String?> = _identityKeyId.asStateFlow()

    /** The shareable fedcode of THIS device's self fed-ID, when known. */
    private val _selfFedcode = MutableStateFlow<String?>(null)
    val selfFedcode: StateFlow<String?> = _selfFedcode.asStateFlow()

    /** The device roster — the ACTIVE occurrences of the self. */
    private val _occurrences = MutableStateFlow<List<SelfOccurrence>>(emptyList())
    val occurrences: StateFlow<List<SelfOccurrence>> = _occurrences.asStateFlow()

    /**
     * The fedcode this NEW device just minted (role 3) — render as text + QR for the
     * primary to enroll. Null until [enrollThisDevice] succeeds.
     */
    private val _enrolledIdentity = MutableStateFlow<MintedIdentity?>(null)
    val enrolledIdentity: StateFlow<MintedIdentity?> = _enrolledIdentity.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    init {
        load()
    }

    /**
     * Resolve THIS device's self fed-ID (from the node's self-key-record) and load
     * its device roster. The node's bound owner fed-ID IS its signer on a
     * self-claimed node, so the self-key-record key_id is the roster's
     * `identity_key_id`. Each round-trip fails independently.
     */
    fun load() {
        if (_loading.value) return
        _loading.value = true
        viewModelScope.launch {
            try {
                _error.value = null
                // Prefer the BOUND OWNER fed-ID (the human — e.g. eric-moore-v1).
                // getSelfKeyRecord() returns the NODE key (ciris-client), which is
                // the node's own signer, NOT the owner; on a self-claimed node the
                // roster we list/manage is the OWNER's occurrence roster, so the
                // owner fed-ID is the correct identity_key_id. Fall back to the node
                // self-key-record only when the node is still unclaimed (no owner).
                val keyId = _identityKeyId.value
                    ?: runCatching { apiClient.getOwnedNodes().owner }
                        .onFailure { PlatformLogger.w(TAG, "[load] owned-nodes owner: ${it.message}") }
                        .getOrNull()
                        ?.takeIf { it.isNotBlank() }
                    ?: runCatching { apiClient.getSelfKeyRecord() }
                        .onFailure { PlatformLogger.w(TAG, "[load] self-key-record: ${it.message}") }
                        .getOrNull()
                        ?.keyId
                if (keyId == null) {
                    _error.value = "Couldn't resolve this device's identity. Sign in / mint a fed-ID first."
                    _occurrences.value = emptyList()
                    return@launch
                }
                _identityKeyId.value = keyId
                refreshRoster(keyId)
            } finally {
                _loading.value = false
            }
        }
    }

    private suspend fun refreshRoster(keyId: String) {
        runCatching { apiClient.getSelfOccurrences(keyId) }
            .onSuccess { _occurrences.value = it.occurrences }
            .onFailure { e ->
                PlatformLogger.w(TAG, "[refreshRoster] ${e.message}")
                _error.value = "Couldn't load the device roster: ${e.message}"
            }
    }

    /** Reload the roster for the resolved self fed-ID. */
    fun refresh() {
        val keyId = _identityKeyId.value
        if (keyId == null) {
            load()
            return
        }
        _loading.value = true
        viewModelScope.launch {
            try {
                _error.value = null
                refreshRoster(keyId)
            } finally {
                _loading.value = false
            }
        }
    }

    /**
     * ADD a device (role 2, on the primary). [code] is the NEW device's fedcode (its
     * `occurrence_key_id` — the fedcode the new device showed via [enrollThisDevice]).
     * The node signs the enrollment with the user's fed-ID. [deviceClass] is one of
     * `phone | laptop | agent`.
     */
    fun addDevice(code: String, deviceClass: String = "laptop") {
        val occurrenceKeyId = code.trim()
        val keyId = _identityKeyId.value
        if (keyId == null) {
            _error.value = "This device's identity isn't resolved yet — try again."
            return
        }
        if (occurrenceKeyId.isEmpty()) {
            _error.value = "Paste or scan the new device's fed-ID (its key_id / fedcode)."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.addOccurrence(
                    AddOccurrenceRequest(
                        identityKeyId = keyId,
                        occurrence = AddOccurrenceBody(
                            occurrenceKeyId = occurrenceKeyId,
                            deviceClass = deviceClass,
                        ),
                    ),
                )
                _notice.value = if (result.keyFreshlyRegistered) {
                    "Device enrolled and its key admitted."
                } else {
                    "Device enrolled."
                }
                refreshRoster(keyId)
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[addDevice] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") -> "Sign in as yourself first, then add the device."
                    msg.contains("400") && msg.contains("occurrence_key_record") ->
                        "That fed-ID isn't known to this node yet — enroll it from the new device first (it must mint + publish its key)."
                    else -> "Couldn't add the device: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /** REVOKE a (lost / stolen) device. Sign with a SURVIVING key, never the lost one. */
    fun revoke(occurrenceKeyId: String, reason: String? = null) {
        val keyId = _identityKeyId.value
        if (keyId == null) {
            _error.value = "This device's identity isn't resolved yet — try again."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                apiClient.revokeOccurrence(keyId, occurrenceKeyId.trim(), reason)
                _notice.value = "Revoked ${occurrenceKeyId.take(16)}…"
                refreshRoster(keyId)
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[revoke] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") -> "Sign in with a surviving key first."
                    else -> "Couldn't revoke: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * "Log in as yourself on another device" (role 3, on the NEW device): mint a
     * local fed-ID. The node mints the hybrid keypair in its keyring/substrate and
     * returns the shareable fedcode; the screen renders it as text + a QR for the
     * primary to scan / paste into [addDevice].
     */
    fun enrollThisDevice() {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val minted = apiClient.mintUserIdentity()
                _enrolledIdentity.value = minted
                _notice.value = "Minted this device's fed-ID. Show its fedcode to your primary device to enroll it."
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[enrollThisDevice] ${e.message}")
                _error.value = "Couldn't mint this device's identity: ${e.message}"
            } finally {
                _busy.value = false
            }
        }
    }

    /** Dismiss the just-minted enroll card. */
    fun clearEnrolled() {
        _enrolledIdentity.value = null
    }

    /**
     * Create a **portable software identity occurrence** into [targetDir] (a USB
     * folder). The LOCAL node mints a fresh *software* hybrid keyset there and binds
     * it as a primary-authorized occurrence of the owner's self. The app passes only
     * the path; the node writes the seeds + does the crypto. A software keyset is
     * inherently insecure — the accepted bootstrap trade-off.
     */
    fun createPortableOccurrence(targetDir: String, label: String? = null) {
        val dir = targetDir.trim()
        if (dir.isEmpty()) {
            _error.value = "Choose the USB folder to write the portable keyset into."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.createPortableOccurrence(dir, label)
                _notice.value =
                    "Portable software identity occurrence created: ${result.keyId.take(20)}… — stored on $dir"
                _identityKeyId.value?.let { refreshRoster(it) }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[createPortableOccurrence] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner first, then create the portable occurrence."
                    msg.contains("no bound owner") || msg.contains("503") ->
                        "This node has no bound owner fed-ID yet — claim ownership first."
                    else -> "Couldn't create the portable occurrence: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * **Associate an existing fed-ID** as THIS device's active user identity. The
     * directory path installs a portable software keyset from [sourceDir]; the
     * YubiKey path ([yubikey] = true) is server-gated for now (501).
     */
    fun associateFedId(sourceDir: String? = null, yubikey: Boolean = false) {
        if (!yubikey && sourceDir.isNullOrBlank()) {
            _error.value = "Choose the folder holding the portable keyset to associate."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.associateFedId(sourceDir = sourceDir, yubikey = yubikey)
                _notice.value =
                    "Associated this device as ${result.associatedKeyId?.take(20) ?: result.alias}…"
                load()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[associateFedId] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("501") ->
                        "YubiKey association isn't available yet — use a directory for now."
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner first, then associate the fed-ID."
                    msg.contains("no portable keyset") ->
                        "No portable keyset found in that folder — pick the folder you wrote it to."
                    else -> "Couldn't associate the fed-ID: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    fun clearMessages() {
        _error.value = null
        _notice.value = null
    }
}
