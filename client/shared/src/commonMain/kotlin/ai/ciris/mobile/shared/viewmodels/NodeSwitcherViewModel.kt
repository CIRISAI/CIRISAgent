package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.platform.util.DecodedNodeCode
import ai.ciris.mobile.shared.platform.util.NodeCodeCodec
import ai.ciris.mobile.shared.platform.util.NodeCodeException
import ai.ciris.mobile.shared.services.NodeProfileStore
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Drives the first-class **node switcher** surfaced in the main page top bar.
 *
 * In fabric terms: the user participates in several nodes (occurrences). This
 * VM holds the list of [NodeProfile]s, knows which one is active, and performs
 * the *switch* — repointing the shared [CIRISApiClient] at the chosen node's
 * base URL (via the existing [CIRISApiClient.updateBaseUrl]) and re-applying
 * that node's session token. Reloading of the per-node UI state is the
 * responsibility of the screens reacting to [activeProfile] changing, exactly
 * like the existing ServerConnection reconnect path.
 */
class NodeSwitcherViewModel(
    private val apiClient: CIRISApiClient,
    private val secureStorage: SecureStorage,
) : ViewModel() {

    companion object {
        private const val TAG = "NodeSwitcherVM"

        /**
         * The valid cohort scopes for a node-ownership claim (CIRISServer v0.4.3):
         * who the owner is adding the node to. CIRISServer validates the
         * `cohort_scope` body field against exactly these values (else `400`).
         */
        val COHORT_SCOPES = listOf("self", "family", "community")
    }

    private val store = NodeProfileStore(secureStorage)

    private val _profiles = MutableStateFlow<List<NodeProfile>>(emptyList())
    val profiles: StateFlow<List<NodeProfile>> = _profiles.asStateFlow()

    private val _activeProfileId = MutableStateFlow<String?>(null)
    val activeProfileId: StateFlow<String?> = _activeProfileId.asStateFlow()

    private val _isSwitching = MutableStateFlow(false)
    val isSwitching: StateFlow<Boolean> = _isSwitching.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    val activeProfile: NodeProfile?
        get() = _profiles.value.firstOrNull { it.id == _activeProfileId.value }

    init {
        viewModelScope.launch { reload() }
    }

    /** Reload profiles + active id from the store. */
    suspend fun reload() {
        _profiles.value = store.loadProfiles()
        _activeProfileId.value = store.getActiveProfileId()
        // If nothing is marked active yet, adopt the apiClient's current URL as
        // an implicit profile so the switcher always reflects reality.
        if (_activeProfileId.value == null) {
            val current = _profiles.value.firstOrNull { it.baseUrl == apiClient.baseUrl }
            _activeProfileId.value = current?.id
        }
    }

    /**
     * Add or update a node profile. Mirrors the add/edit path of
     * ServerConnectionScreen but persists a full [NodeProfile] rather than a
     * bare URL string.
     */
    fun saveProfile(name: String, baseUrl: String, sessionToken: String? = null) {
        viewModelScope.launch {
            val normalized = baseUrl.trim().trimEnd('/')
            val profile = NodeProfile(
                id = NodeProfile.idFor(normalized),
                name = name.ifBlank { normalized },
                baseUrl = normalized,
                sessionToken = sessionToken,
                lastUsedEpochMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds(),
            )
            _profiles.value = store.upsert(profile)
        }
    }

    fun removeProfile(id: String) {
        viewModelScope.launch { _profiles.value = store.remove(id) }
    }

    /**
     * Rename a saved node profile in place (keeps URL, token and any identity
     * pin — [NodeProfileStore.upsert] merges by id). Used by the Manage Nodes
     * CRUD surface. No-op for a blank name or an unknown id.
     */
    fun renameProfile(id: String, newName: String) {
        val name = newName.trim()
        if (name.isBlank()) return
        viewModelScope.launch {
            val existing = _profiles.value.firstOrNull { it.id == id } ?: return@launch
            _profiles.value = store.upsert(existing.copy(name = name))
        }
    }

    /**
     * Re-token a profile: replace the stored session token (or clear it when
     * [token] is blank). Manage Nodes "retoken" affordance. Note [NodeProfileStore.upsert]
     * preserves an existing token when the incoming one is null, so an explicit
     * clear writes the profile directly rather than via upsert.
     */
    fun retokenProfile(id: String, token: String?) {
        viewModelScope.launch {
            val existing = _profiles.value.firstOrNull { it.id == id } ?: return@launch
            val trimmed = token?.trim()?.takeIf { it.isNotBlank() }
            _profiles.value = if (trimmed == null) {
                // Explicit clear: upsert would preserve the old token, so go
                // through remove + re-add to drop it.
                store.remove(id)
                store.upsert(existing.copy(sessionToken = null))
            } else {
                store.upsert(existing.copy(sessionToken = trimmed))
            }
        }
    }

    /**
     * Switch the active node. Repoints the shared API client at the chosen
     * node and applies its token, then marks it active. Screens observing
     * [activeProfileId] should reload their data when it changes.
     */
    fun switchTo(profile: NodeProfile) {
        if (_isSwitching.value) return
        _isSwitching.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                PlatformLogger.i(TAG, "[switchTo] Switching to node '${profile.name}' @ ${profile.baseUrl}")
                apiClient.updateBaseUrl(profile.baseUrl)
                // Apply (or clear) the node's session token on the shared client.
                if (profile.isAuthenticated) {
                    apiClient.setAccessToken(profile.sessionToken!!)
                    // Keep the canonical access-token slot in sync so a cold
                    // start restores the same node's session.
                    secureStorage.saveAccessToken(profile.sessionToken)
                }
                val now = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                _profiles.value = store.markActive(profile.id, now)
                _activeProfileId.value = profile.id
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[switchTo] Failed: ${e.message}", e)
                _error.value = "Could not switch to ${profile.name}: ${e.message}"
            } finally {
                _isSwitching.value = false
            }
        }
    }

    fun clearError() { _error.value = null }

    // ─── Connect-by-NodeCode: decode → connect → identity-pin → claim ─────────
    //
    // The secure "become admin of a remote node" bootstrap (CEG §0.10). The
    // founder enters a node's CIRIS-V1- code (pasted or scanned). We decode it
    // LOCALLY (no server round-trip to learn what node it is), derive a base URL
    // from the transport hint, connect, then identity-pin: fetch the node's own
    // served NodeCode and refuse unless its key_id + pubkey match the decoded
    // code. Only a pinned node is saved as a profile.

    private val _bootstrap = MutableStateFlow(NodeBootstrapState())
    val bootstrap: StateFlow<NodeBootstrapState> = _bootstrap.asStateFlow()

    fun clearBootstrap() { _bootstrap.value = NodeBootstrapState() }

    /**
     * Derive a reachable base URL from a decoded code's [DecodedNodeCode.transportHint].
     * Accepts an explicit [overrideUrl] for when the hint is absent/unusable.
     * Normalises like [NodeProfile.idFor]. Returns null when nothing usable.
     */
    private fun baseUrlFor(decoded: DecodedNodeCode, overrideUrl: String?): String? {
        val raw = overrideUrl?.takeIf { it.isNotBlank() }
            ?: decoded.transportHint?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
        return raw?.trim()?.trimEnd('/')
    }

    /**
     * Connect to a node from a pasted/scanned NodeCode and identity-pin it.
     *
     * On success a verified [NodeProfile] (carrying the pinned key_id + pubkey)
     * is saved and the bootstrap state reports [NodeBootstrapState.pinnedProfile]
     * so the UI can offer "Claim admin" next. [overrideUrl] lets the user supply
     * the base URL when the code carries no usable transport hint.
     */
    fun connectByNodeCode(code: String, name: String? = null, overrideUrl: String? = null) {
        if (_bootstrap.value.inProgress) return
        // Capture the raw CIRIS-V1- code now: the claim step hands it verbatim to
        // the LOCAL node, which re-decodes + signs the owner-binding delegation.
        _bootstrap.value = NodeBootstrapState(inProgress = true, phase = BootstrapPhase.DECODING, nodeCode = code)
        viewModelScope.launch {
            val decoded = try {
                NodeCodeCodec.decode(code)
            } catch (e: NodeCodeException) {
                PlatformLogger.w(TAG, "[connectByNodeCode] decode failed: ${e.message}")
                _bootstrap.value = NodeBootstrapState(error = "That is not a valid node code: ${e.message}")
                return@launch
            }

            val baseUrl = baseUrlFor(decoded, overrideUrl)
            if (baseUrl == null) {
                _bootstrap.value = NodeBootstrapState(
                    decoded = decoded,
                    error = "This code carries no reachable address — enter the node's URL to continue.",
                    phase = BootstrapPhase.NEED_URL,
                )
                return@launch
            }

            _bootstrap.value = _bootstrap.value.copy(decoded = decoded, phase = BootstrapPhase.PINNING)
            try {
                // Identity-pin: the node must serve back a NodeCode matching the
                // one we decoded. Refuse on any mismatch (defeats a spoof node).
                val served = apiClient.getNodeCode(baseUrl)
                val servedDecoded = NodeCodeCodec.decode(served.code)
                if (servedDecoded.keyId != decoded.keyId ||
                    servedDecoded.pubkeyEd25519Base64 != decoded.pubkeyEd25519Base64
                ) {
                    PlatformLogger.e(
                        TAG,
                        "[connectByNodeCode] PIN MISMATCH: scanned key=${decoded.keyId} served=${servedDecoded.keyId}",
                    )
                    _bootstrap.value = NodeBootstrapState(
                        decoded = decoded,
                        error = "Identity mismatch — the node at $baseUrl is NOT the one this code is for. Refusing to connect.",
                    )
                    return@launch
                }

                val profile = NodeProfile(
                    id = NodeProfile.idFor(baseUrl),
                    name = (name ?: decoded.aliasHint ?: served.aliasHint).orEmpty().ifBlank { baseUrl },
                    baseUrl = baseUrl,
                    lastUsedEpochMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds(),
                    pinnedKeyId = decoded.keyId,
                    pinnedPubkeyBase64 = decoded.pubkeyEd25519Base64,
                )
                _profiles.value = store.upsert(profile)
                PlatformLogger.i(TAG, "[connectByNodeCode] pinned node '${profile.name}' @ $baseUrl key=${decoded.keyId}")
                _bootstrap.value = _bootstrap.value.copy(
                    decoded = decoded,
                    pinnedProfile = profile,
                    phase = BootstrapPhase.PINNED,
                    inProgress = false,
                    error = null,
                )
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[connectByNodeCode] connect/pin failed: ${e.message}", e)
                _bootstrap.value = NodeBootstrapState(
                    decoded = decoded,
                    error = "Could not reach or verify the node at $baseUrl: ${e.message}",
                )
            }
        }
    }

    /**
     * Claim ownership of a pinned target node — the owner becomes SYSTEM_ADMIN.
     *
     * ARCHITECTURE: the app is a NODE and does NO federation crypto. It DRIVES its
     * LOCAL node's `POST /v1/setup/claim-remote { node_code, claim_pin,
     * cohort_scope }`. The local node decodes the NodeCode, builds +
     * JCS-canonicalizes + HYBRID-SIGNS the owner-binding `delegates_to(user →
     * target, infra:*)` in its substrate with the owner's identity, and POSTs it
     * to the target node's `/v1/setup/root`. This call is a plain UNSIGNED
     * localhost POST; the local node authenticates the operator via the session.
     *
     * @param profile the identity-pinned target node (its decoded NodeCode is
     *        replayed as the `node_code` the local node claims).
     */
    fun claimAdmin(
        profile: NodeProfile,
        claimPin: String,
        cohortScope: String = "self",
    ) {
        if (_bootstrap.value.claimInProgress) return
        if (!profile.isPinned) {
            _bootstrap.value = _bootstrap.value.copy(claimError = "This node was not identity-pinned — cannot safely claim it.")
            return
        }
        if (claimPin.isBlank()) {
            _bootstrap.value = _bootstrap.value.copy(
                claimError = "Enter the one-time PIN shown on the node's console to claim it.",
            )
            return
        }
        // The cohort scope (self|family|community) is required by the local node;
        // a missing/invalid value → 400. Validate before the round-trip.
        if (cohortScope !in COHORT_SCOPES) {
            _bootstrap.value = _bootstrap.value.copy(
                claimError = "Choose who this node belongs to (self, family, or community) before claiming it.",
            )
            return
        }
        // The target node's full NodeCode (captured during connect). The local
        // node re-decodes it and signs the owner-binding delegation against it. We
        // need the original CIRIS-V1- string, not just the pinned halves.
        val targetNodeCode = _bootstrap.value.nodeCode
        if (targetNodeCode.isNullOrBlank()) {
            _bootstrap.value = _bootstrap.value.copy(
                claimError = "Missing the node's code — re-scan or paste the CIRIS-V1- code before claiming.",
            )
            return
        }
        _bootstrap.value = _bootstrap.value.copy(claimInProgress = true, claimError = null, claimedRole = null)
        viewModelScope.launch {
            try {
                // Drive the LOCAL node to claim the target. The local node does ALL
                // canonicalization + hybrid signing in its substrate; the app sends
                // only the NodeCode + PIN + cohort scope over plain localhost HTTP.
                val resp = apiClient.claimRemote(
                    nodeCode = targetNodeCode,
                    claimPin = claimPin.trim(),
                    cohortScope = cohortScope,
                )
                PlatformLogger.i(TAG, "[claimAdmin] local node claimed ${profile.baseUrl} → role=${resp.role}")
                _bootstrap.value = _bootstrap.value.copy(
                    claimInProgress = false,
                    claimedRole = resp.role,
                    claimError = if (resp.role == null) resp.error else null,
                )
                // Refresh the profile list (claim may have minted a session later).
                _profiles.value = store.loadProfiles()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[claimAdmin] failed: ${e.message}", e)
                // Surface a clear PIN error when the claim was rejected for the
                // PIN. The local node (or, via it, the target) returns 4xx with a
                // body that mentions the pin (e.g. "invalid_claim_pin" / "claim
                // pin"); claimRemote re-throws it.
                val msg = e.message.orEmpty()
                val isPinRejection = msg.contains("claim_pin", ignoreCase = true) ||
                    msg.contains("claim pin", ignoreCase = true) ||
                    msg.contains("invalid pin", ignoreCase = true)
                _bootstrap.value = _bootstrap.value.copy(
                    claimInProgress = false,
                    claimError = if (isPinRejection) {
                        "The node rejected the PIN — check the one-time PIN on the node's console and try again."
                    } else {
                        "Claim failed: ${e.message}"
                    },
                )
            }
        }
    }

}

/** Phase of the NodeCode bootstrap, for driving the connect/pin/claim UI. */
enum class BootstrapPhase { IDLE, DECODING, NEED_URL, PINNING, PINNED }

/**
 * UI state for the "add a node by NodeCode" bootstrap (connect → pin → claim).
 */
data class NodeBootstrapState(
    val inProgress: Boolean = false,
    val phase: BootstrapPhase = BootstrapPhase.IDLE,
    /** The raw CIRIS-V1- code as submitted; replayed verbatim to the local node. */
    val nodeCode: String? = null,
    /** The locally-decoded code, available as soon as decode succeeds. */
    val decoded: DecodedNodeCode? = null,
    /** Set once the node is reached AND identity-pinned; ready to claim/switch. */
    val pinnedProfile: NodeProfile? = null,
    val error: String? = null,
    val claimInProgress: Boolean = false,
    /** Non-null on a successful claim (e.g. "SYSTEM_ADMIN"). */
    val claimedRole: String? = null,
    val claimError: String? = null,
) {
    val isPinned: Boolean get() = pinnedProfile != null
    val isAdminClaimed: Boolean get() = claimedRole != null
}
