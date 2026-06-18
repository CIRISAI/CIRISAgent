package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.models.federation.SetupRootRequest
import ai.ciris.mobile.shared.platform.HardwareCredentialManager
import ai.ciris.mobile.shared.platform.HardwareCredentialUnavailable
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
        _bootstrap.value = NodeBootstrapState(inProgress = true, phase = BootstrapPhase.DECODING)
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
                _bootstrap.value = NodeBootstrapState(
                    decoded = decoded,
                    pinnedProfile = profile,
                    phase = BootstrapPhase.PINNED,
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
     * Claim admin (first-run ROOT) of a pinned node — the founder becomes
     * SYSTEM_ADMIN. Mints/uses the hardware-rooted federation identity (the same
     * one self-login uses) and POSTs `/v1/setup/root` with the node's NodeCode
     * pin in the body.
     *
     * The body must be `x-ciris-*` hybrid-signed by that identity. Per-request
     * signing is the known hardware blocker (CIRISAgent#887): when [hardware]
     * cannot produce request signatures the claim is attempted UNSIGNED and the
     * node's `401` is surfaced honestly rather than faked.
     */
    fun claimAdmin(
        profile: NodeProfile,
        hardware: HardwareCredentialManager,
        displayName: String,
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
        // CIRISServer v0.4.3 REQUIRES a valid cohort_scope (self|family|community);
        // a missing/invalid value → 400. Validate before signing so we never spend
        // a hardware signature on a body the node will reject.
        if (cohortScope !in COHORT_SCOPES) {
            _bootstrap.value = _bootstrap.value.copy(
                claimError = "Choose who this node belongs to (self, family, or community) before claiming it.",
            )
            return
        }
        _bootstrap.value = _bootstrap.value.copy(claimInProgress = true, claimError = null, claimedRole = null)
        viewModelScope.launch {
            try {
                // Mint (or reload) the founder's long-lived HYBRID federation
                // identity (Ed25519 + ML-DSA-65). This is the claim's signing
                // authority and is stable across launches (CIRISAgent#887).
                val founder = try {
                    hardware.createFederationIdentity(displayName = displayName, rpId = profile.baseUrl)
                    hardware.currentIdentity()
                } catch (e: HardwareCredentialUnavailable) {
                    PlatformLogger.w(TAG, "[claimAdmin] hybrid identity unavailable: ${e.message}")
                    null
                }

                // Build the claim body: the NodeCode identity-pin AND the founder's
                // hybrid pubkeys (self-attested hybrid proof-of-possession). The
                // node verifies the two x-ciris-signature-* headers against THESE
                // pubkeys over the exact body bytes (Strict: both required).
                val request = SetupRootRequest(
                    keyId = profile.pinnedKeyId,
                    pubkeyEd25519Base64 = profile.pinnedPubkeyBase64,
                    // One-time PIN the operator read off the node's console. It is
                    // a field of the body that claimRoot serializes ONCE and signs
                    // those exact bytes — so the PIN is signature-bound (signed ==
                    // sent). A wrong/expired PIN is rejected by the node below.
                    claimPin = claimPin.trim(),
                    // The cohort this node is being added to (self/family/community).
                    // A serialized body field, so it rides inside the signed bytes
                    // (signed == sent). Required by CIRISServer v0.4.3 or it 400s.
                    cohortScope = cohortScope,
                    founder = founder?.let {
                        ai.ciris.mobile.shared.models.federation.FounderIdentity(
                            keyId = it.keyId,
                            ed25519PubkeyB64 = it.ed25519PublicKeyB64,
                            mlDsa65PubkeyB64 = it.mlDsa65PublicKeyB64,
                        )
                    },
                )

                // The signer hashes/signs the EXACT serialized body bytes inside
                // claimRoot (serialize-once-sign-that-send-that). When the hybrid
                // identity is unavailable we pass no signer and the node's 401 is
                // surfaced honestly rather than faked.
                val signer: (suspend (ByteArray) -> ai.ciris.mobile.shared.platform.HybridSignature)? =
                    if (founder != null) { bytes -> hardware.sign(bytes) } else null
                val resp = apiClient.claimRoot(
                    request = request,
                    nodeUrl = profile.baseUrl,
                    signingKeyId = founder?.keyId,
                    signer = signer,
                )
                PlatformLogger.i(TAG, "[claimAdmin] claimed ROOT on ${profile.baseUrl} → role=${resp.role}")
                _bootstrap.value = _bootstrap.value.copy(
                    claimInProgress = false,
                    claimedRole = resp.role,
                    claimError = if (resp.role == null) resp.error else null,
                )
                // Refresh the profile list (claim may have minted a session later).
                _profiles.value = store.loadProfiles()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[claimAdmin] failed: ${e.message}", e)
                // Surface a clear PIN error when the node rejected the claim PIN.
                // The node returns 4xx with a body that mentions the pin (e.g.
                // "invalid_claim_pin" / "claim pin"); claimRoot re-throws it.
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
