package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.CreateDelegationResponse
import ai.ciris.mobile.shared.models.federation.DelegationConstraints
import ai.ciris.mobile.shared.models.federation.DelegationDto
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the **Delegations** card — the owner's view of who they've authorized to
 * act on their behalf (active device-authorization grants), plus the approve /
 * revoke controls.
 *
 * The flow: an agent generates a device code out-of-band (`POST
 * /v1/auth/device/code`) and shows the owner the short `user_code`. The owner
 * enters it here and approves — the human-consent gate. The local node mints a
 * delegated `dgrant:` token (the owner's authority, attributed to the agent). The
 * app drives the LOCAL node only with the owner session; it holds no crypto.
 */
class DelegationsViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "DelegationsVM"
    }

    private val _delegations = MutableStateFlow<List<DelegationDto>>(emptyList())
    val delegations: StateFlow<List<DelegationDto>> = _delegations.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    /** The most recently created delegation — the URL + PIN to hand to the agent. */
    private val _lastCreated = MutableStateFlow<CreateDelegationResponse?>(null)
    val lastCreated: StateFlow<CreateDelegationResponse?> = _lastCreated.asStateFlow()

    /**
     * The local node's base URL (``http://host:port``) — surfaced so the offer card
     * can show/copy the full ``host:port`` the agent dials (the claim URL is relative).
     */
    val nodeBaseUrl: String get() = apiClient.baseUrl

    // NOTE: do NOT refresh() in init — the VM is constructed at app startup, before the
    // owner has logged in, so an init fetch hits /v1/auth/device/grants with no bearer →
    // 401 "missing bearer session token", and that error sticks in the UI. The Delegations
    // screen calls refresh() on entry (LaunchedEffect), by which point the session token is
    // set. (CIRISServer node-client: deferred-until-auth. #117.)

    /** Reload the active delegations from the local node. */
    fun refresh() {
        _loading.value = true
        viewModelScope.launch {
            try {
                _delegations.value = apiClient.listDelegations()
                _error.value = null
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[refresh] ${e.message}")
                _error.value = "Couldn't load delegations: ${e.message}"
            } finally {
                _loading.value = false
            }
        }
    }

    /**
     * Create a delegation to hand to an agent. Requires the owner session (sign
     * in first). `mode` is `"create"` (mint a fresh agent fed-ID) or `"existing"`
     * (bind `existingKeyId`). On success [lastCreated] carries the claim URL +
     * PIN the owner hands over, and the active list refreshes.
     */
    fun createDelegation(
        label: String,
        mode: String,
        existingKeyId: String?,
        constraints: DelegationConstraints? = null,
    ) {
        val name = label.trim()
        if (name.isEmpty()) {
            _error.value = "Give the agent a label (e.g. my-laptop-agent)."
            return
        }
        if (mode == "existing" && existingKeyId?.trim().isNullOrEmpty()) {
            _error.value = "Enter the existing fed-ID key_id, or switch to creating a new one."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val result = apiClient.createDelegation(
                    label = name,
                    mode = mode,
                    existingKeyId = existingKeyId?.trim(),
                    constraints = constraints,
                )
                _lastCreated.value = result
                _notice.value = "Delegation created — hand the URL + PIN to the agent."
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[createDelegation] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") -> "Sign in as the owner first."
                    else -> "Couldn't create the delegation: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /** Dismiss the just-created delegation result card. */
    fun clearLastCreated() {
        _lastCreated.value = null
    }

    /**
     * Approve a pending device code the agent showed you. Requires the owner
     * session (sign in first). On success the agent receives its delegated token.
     */
    fun approve(userCode: String, constraints: DelegationConstraints? = null) {
        val code = userCode.trim()
        if (code.isEmpty()) {
            _error.value = "Enter the code the agent gave you (e.g. ABCD-1234)."
            return
        }
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                apiClient.approveDeviceCode(code, constraints = constraints)
                _notice.value = "Approved — the agent is now authorized to act on your behalf."
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[approve] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") -> "Sign in as the owner first, then approve."
                    msg.contains("404") || msg.contains("unknown user_code") ->
                        "That code wasn't recognized — check it with the agent (codes expire)."
                    else -> "Couldn't approve: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /** Revoke a delegation (withdraw the agent's authority). */
    fun revoke(clientId: String) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                apiClient.revokeDelegation(clientId)
                _notice.value = "Revoked $clientId."
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[revoke] ${e.message}")
                _error.value = "Couldn't revoke: ${e.message}"
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
