package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.AccordEventDto
import ai.ciris.mobile.shared.models.federation.AccordFamilyDto
import ai.ciris.mobile.shared.models.federation.AccordHolderDto
import ai.ciris.mobile.shared.models.federation.AccordHaltStatusResponse
import ai.ciris.mobile.shared.models.federation.AccordInvocationDto
import ai.ciris.mobile.shared.models.federation.PendingCoscrubDto
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/**
 * Drives the **Accord** screen — the HUMANITY_ACCORD constitutional surface
 * (CIRISServer #41). It surfaces the entrenched accord family + its
 * `quorum:2/3` consensus protocol, the hardware-attested holder roster, and the
 * pending invocations with quorum status. The owner may **concur** on a pending
 * invocation the local holder hasn't yet signed.
 *
 * No-crypto posture (mirrors Delegations): the app drives the LOCAL node only
 * with the owner session and holds NO keys. `concur` just POSTs — the node signs
 * with the resolved local holder signer.
 */
class AccordViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "AccordVM"
    }

    private val _family = MutableStateFlow<AccordFamilyDto?>(null)
    val family: StateFlow<AccordFamilyDto?> = _family.asStateFlow()

    private val _holders = MutableStateFlow<List<AccordHolderDto>>(emptyList())
    val holders: StateFlow<List<AccordHolderDto>> = _holders.asStateFlow()

    private val _holderThreshold = MutableStateFlow(2)
    val holderThreshold: StateFlow<Int> = _holderThreshold.asStateFlow()

    private val _invocations = MutableStateFlow<List<AccordInvocationDto>>(emptyList())
    val invocations: StateFlow<List<AccordInvocationDto>> = _invocations.asStateFlow()

    /** The enforceable kill-switch state (disk halt latch). Drives the unmissable
     *  ACTIVE-HALT banner — the most prominent thing on the card when halted. */
    private val _haltStatus = MutableStateFlow<AccordHaltStatusResponse?>(null)
    val haltStatus: StateFlow<AccordHaltStatusResponse?> = _haltStatus.asStateFlow()

    /** Surfaced NON-BINDING completed drills (most-recent-first). */
    private val _drills = MutableStateFlow<List<AccordEventDto>>(emptyList())
    val drills: StateFlow<List<AccordEventDto>> = _drills.asStateFlow()

    /** Surfaced single-holder announcements (most-recent-first). */
    private val _announcements = MutableStateFlow<List<AccordEventDto>>(emptyList())
    val announcements: StateFlow<List<AccordEventDto>> = _announcements.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    init {
        refresh()
    }

    /** Reload the accord family, holder roster, and pending invocations. */
    fun refresh() {
        _loading.value = true
        viewModelScope.launch {
            try {
                _family.value = apiClient.getAccordFamily()
                val holders = apiClient.getAccordHolders()
                _holders.value = holders.holders
                _holderThreshold.value = holders.threshold
                _invocations.value = apiClient.getAccordInvocations()
                // The enforceable kill-switch state + the surfaced non-binding events.
                _haltStatus.value = try {
                    apiClient.getAccordHaltStatus()
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] halt-status: ${e.message}")
                    _haltStatus.value
                }
                try {
                    val events = apiClient.listAccordEvents()
                    _drills.value = events.drills
                    _announcements.value = events.announcements
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] events: ${e.message}")
                }
                // The owner's nodes — the admit-node target picker selects from these.
                _ownedNodes.value = try {
                    apiClient.getOwnedNodes().nodes.map { it.keyId }.filter { it.isNotBlank() }
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] owned-nodes: ${e.message}")
                    emptyList()
                }
                _canonicalServers.value = try {
                    apiClient.listCanonicalServers().servers
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] canonical-servers: ${e.message}")
                    emptyList()
                }
                _canonicalWithdrawals.value = try {
                    apiClient.listCanonicalWithdrawals().withdrawals
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] canonical-withdrawals: ${e.message}")
                    emptyList()
                }
                _pendingCoscrubs.value = try {
                    apiClient.listPendingCoscrubs()
                } catch (e: Exception) {
                    PlatformLogger.w(TAG, "[refresh] pending-coscrubs: ${e.message}")
                    emptyList()
                }
                _error.value = null
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[refresh] ${e.message}")
                _error.value = "Couldn't load the accord: ${e.message}"
            } finally {
                _loading.value = false
            }
        }
    }

    /**
     * Concur on a pending invocation as an accord holder. Requires the owner session
     * (sign in first) AND the holder's hardware-scrub inputs ([holderKeyId] +
     * [mldsaUsbPath] + [userPin]) — the node RE-OPENS the holder's YubiKey +
     * USB-wrapped ML-DSA and produces the cosignature over the pending invocation's
     * bytes; the app holds no keys. Touch-gated (a YubiKey touch is consent).
     */
    fun concur(
        invocationKind: String,
        invocationId: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        if (!requireHolderInputs(holderKeyId, mldsaUsbPath, userPin)) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.concurInvocation(
                    invocationKind, invocationId, holderKeyId, mldsaUsbPath, userPin,
                    modulePath = modulePath,
                )
                _notice.value = if (res.quorumMet) {
                    "Concurred — quorum met (${res.validSigners.size} signers)."
                } else {
                    "Concurred — ${res.validSigners.size} signer(s) so far."
                }
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[concur] ${e.message}")
                _error.value = holderActionError(e, "concur")
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * The invocation write actions (concur / drill / announce) sign on the holder's
     * YubiKey via the node — every one needs the holder key + USB folder + PIN. Guard
     * up front with a clear message rather than letting the node 400/501.
     */
    private fun requireHolderInputs(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
    ): Boolean {
        if (holderKeyId.isBlank() || mldsaUsbPath.isBlank() || userPin.isNullOrBlank()) {
            _error.value =
                "Choose your accord holder key, USB folder, and PIN in “Sign as holder” first."
            return false
        }
        return true
    }

    /** Shared holder-action error mapping (owner-gate, missing pkcs11, YubiKey open). */
    private fun holderActionError(e: Exception, verb: String): String {
        val msg = e.message.orEmpty()
        return when {
            msg.contains("401") -> "Sign in as the owner first, then $verb."
            msg.contains("403") -> "This node isn't a current accord holder."
            msg.contains("501") || msg.contains("NotSupported", ignoreCase = true) ->
                "This build lacks pkcs11 — signing needs the YubiKey."
            else -> "Couldn't $verb: ${e.message}"
        }
    }

    /**
     * **Initiate a drill** — a NON-BINDING rehearsal of the 2-of-3 kill-switch
     * delivery path (holder action; requires the owner session). The node builds +
     * signs the drill with its resolved local holder signer (mirrors [concur]); the
     * app sends no crypto. On reaching quorum it surfaces in the drills list; it
     * NEVER halts. [invocationId] uniquely names this drill.
     */
    fun initiateDrill(
        invocationId: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        val id = invocationId.trim()
        if (id.isBlank()) {
            _error.value = "Enter a drill id first."
            return
        }
        if (!requireHolderInputs(holderKeyId, mldsaUsbPath, userPin)) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.initiateDrill(id, holderKeyId, mldsaUsbPath, userPin, modulePath = modulePath)
                _notice.value = if (res.quorumMet) {
                    "Drill $id complete — quorum met (${res.validSigners.size} signers)."
                } else {
                    "Drill $id opened — ${res.validSigners.size} signer(s) so far. Concur to reach quorum."
                }
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[initiateDrill] ${e.message}")
                _error.value = holderActionError(e, "run a drill")
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * **Raise a halt** — RAISE a 2-of-3 CONSTITUTIONAL kill-switch (holder action, owner
     * session). The node synthesizes the constitutional invocation and signs THIS holder's
     * initiating cosignature with the resolved local holder signer (mirrors [initiateDrill]);
     * the app sends no crypto. That single signature is **sub-quorum** — the halt does NOT
     * take effect until the other holders concur to 2-of-3. The binding twin of a drill.
     */
    fun initiateHalt(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
        modulePath: String? = null,
        invocationId: String = "",
    ) {
        if (_busy.value) return
        if (!requireHolderInputs(holderKeyId, mldsaUsbPath, userPin)) return
        val id = invocationId.trim().ifBlank { "halt-${kotlin.random.Random.nextInt(100000, 1000000)}" }
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.initiateHalt(id, holderKeyId, mldsaUsbPath, userPin, modulePath = modulePath)
                _notice.value = if (res.quorumMet) {
                    "HALT $id LATCHED — quorum met (${res.validSigners.size} signers). The mesh is halting."
                } else {
                    "Halt $id RAISED — ${res.validSigners.size} signer(s). It does NOT take effect until 2-of-3 holders concur."
                }
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[initiateHalt] ${e.message}")
                _error.value = holderActionError(e, "raise a halt")
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * **Post an announce** — a single-holder `notify` message (threshold 1; holder
     * action, owner session). The node signs the notify (binding [message] to the
     * payload hash) with its resolved local holder signer, gossips it, and surfaces
     * it in the announcements list. It NEVER halts.
     */
    fun initiateAnnounce(
        message: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        val text = message.trim()
        if (text.isBlank()) {
            _error.value = "Enter an announcement message first."
            return
        }
        if (!requireHolderInputs(holderKeyId, mldsaUsbPath, userPin)) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.initiateAnnounce(text, holderKeyId, mldsaUsbPath, userPin, modulePath = modulePath)
                _notice.value = if (res.posted) {
                    "Announcement posted to the mesh."
                } else {
                    "Announcement submitted."
                }
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[initiateAnnounce] ${e.message}")
                _error.value = holderActionError(e, "announce")
            } finally {
                _busy.value = false
            }
        }
    }

    private val _admitSavedTo = MutableStateFlow<String?>(null)
    val admitSavedTo: StateFlow<String?> = _admitSavedTo.asStateFlow()

    /** The owner's nodes (key_ids) — the admit-node target picker's options. */
    private val _ownedNodes = MutableStateFlow<List<String>>(emptyList())
    val ownedNodes: StateFlow<List<String>> = _ownedNodes.asStateFlow()

    /** The selected target node resolved to its hybrid pubkeys (from the local
     *  directory) — so the card auto-fills both pubkeys instead of a manual paste. */
    private val _resolvedTarget = MutableStateFlow<ResolvedTarget?>(null)
    val resolvedTarget: StateFlow<ResolvedTarget?> = _resolvedTarget.asStateFlow()

    data class ResolvedTarget(val keyId: String, val ed25519: String, val mldsa: String)

    /**
     * Resolve a selected owned node to its Ed25519 + ML-DSA-65 pubkeys via the LOCAL
     * directory (`GET /v1/federation/peers/{key_id}`) — no manual paste. A node
     * whose row is missing its ML-DSA half (a legacy bookmark) can't be admitted
     * until re-claimed (0.5.75 writes hybrid-complete rows).
     */
    fun resolveTargetNode(keyId: String) {
        _resolvedTarget.value = null
        if (keyId.isBlank()) return
        viewModelScope.launch {
            try {
                val peer = apiClient.getFederationPeer(keyId).peer
                val ml = peer.pubkeyMlDsa65Base64
                if (ml.isNullOrBlank()) {
                    _error.value =
                        "$keyId has no ML-DSA key in the directory yet — re-claim it first."
                } else {
                    _resolvedTarget.value = ResolvedTarget(keyId, peer.pubkeyEd25519Base64, ml)
                }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[resolveTargetNode] ${e.message}")
                _error.value = "Couldn't load $keyId's keys: ${e.message}"
            }
        }
    }

    /**
     * **Admit a node to the trust root** (CIRISServer#140 / CIRISVerify#162). The
     * local accord holder RE-OPENS their YubiKey + USB-wrapped ML-DSA and
     * scrub-signs the target node's registration (+ emits their own
     * `steward,accord_holder` anchor); the node writes the genesis **seed object**
     * to a predictable outbox path (surfaced as [admitSavedTo]) the operator hands
     * to CIRISPersist to bake. The app sends NO crypto — the YubiKey touch IS consent.
     */
    fun admitNode(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        userPin: String?,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        _admitSavedTo.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.admitNode(
                    holderKeyId = holderKeyId,
                    mldsaUsbPath = mldsaUsbPath,
                    targetKeyId = targetKeyId,
                    targetEd25519Base64 = targetEd25519Base64,
                    targetMlDsa65Base64 = targetMlDsa65Base64,
                    userPin = userPin,
                    modulePath = modulePath,
                )
                _admitSavedTo.value = res.savedTo
                _notice.value =
                    "Admitted $targetKeyId — seed saved to ${res.savedTo}. Hand it to persist to bake."
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[admitNode] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    msg.contains("501") || msg.contains("NotSupported", ignoreCase = true) ->
                        "This build lacks pkcs11 — admit-node needs the YubiKey signer."
                    else -> "Couldn't admit the node: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    // ── Canonical servers (CIRISServer#164) ─────────────────────────────────
    // A canonical server is a mesh-seed anchor: a node an accord holder scrub-signed
    // AND flagged `canonical`. Mirrors the admit-node section (same YubiKey + USB
    // scrub) plus an OPTIONAL bootstrap transport address.

    private val _canonicalServers =
        MutableStateFlow<List<ai.ciris.mobile.shared.models.federation.CanonicalServerDto>>(emptyList())
    val canonicalServers: StateFlow<List<ai.ciris.mobile.shared.models.federation.CanonicalServerDto>> =
        _canonicalServers.asStateFlow()

    private val _canonicalSavedTo = MutableStateFlow<String?>(null)
    val canonicalSavedTo: StateFlow<String?> = _canonicalSavedTo.asStateFlow()

    /**
     * The pretty-printed co-scrub JSON from the LAST propose (`partial`) or cosign
     * (`advanced`, when still short of quorum) — surfaced with Copy / Save-to-file so
     * the operator can hand the partial to the next holder without pulling it off disk.
     * Null when there's nothing to export (fresh screen, or a cosign that conferred).
     */
    private val _lastCoscrubJson = MutableStateFlow<String?>(null)
    val lastCoscrubJson: StateFlow<String?> = _lastCoscrubJson.asStateFlow()

    /** Dismiss the export affordance (Copy / Save) after the operator is done with it. */
    fun clearLastCoscrubJson() {
        _lastCoscrubJson.value = null
    }

    private val coscrubJson = Json { prettyPrint = true }

    /** Pretty-print a raw co-scrub payload for the clipboard / a saved file. */
    private fun prettyCoscrub(el: JsonElement?): String? =
        el?.let { runCatching { coscrubJson.encodeToString(JsonElement.serializer(), it) }.getOrNull() }

    /** Public pretty-printer for a pending co-scrub's `partial` (Copy op on the card). */
    fun exportPartial(el: JsonElement): String = prettyCoscrub(el) ?: el.toString()

    /**
     * The canonical co-scrubs (CIRISServer#174) this node holds that are still short
     * of the family m-of-n — arrived via accord gossip OR minted here by [proposeCanonical].
     * Each carries the full partial (`SignedKeyRecord` JSON) so [cosignCanonical] can
     * submit it verbatim. Refreshed on screen entry ([loadPendingCoscrubs]) + after ops.
     */
    private val _pendingCoscrubs = MutableStateFlow<List<PendingCoscrubDto>>(emptyList())
    val pendingCoscrubs: StateFlow<List<PendingCoscrubDto>> = _pendingCoscrubs.asStateFlow()

    /** The selected canonical target resolved to its hybrid pubkeys (mirrors
     *  [resolvedTarget]; separate so it doesn't collide with the admit-node picker). */
    private val _canonicalResolvedTarget = MutableStateFlow<ResolvedTarget?>(null)
    val canonicalResolvedTarget: StateFlow<ResolvedTarget?> = _canonicalResolvedTarget.asStateFlow()

    /** The withdrawn / superseded canonical servers audit log. */
    private val _canonicalWithdrawals =
        MutableStateFlow<List<ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalDto>>(emptyList())
    val canonicalWithdrawals:
        StateFlow<List<ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalDto>> =
        _canonicalWithdrawals.asStateFlow()

    /**
     * A canonical row the operator picked to **replace / update**: the form is
     * pre-filled with this record's key_id + both pubkeys + current IP so the
     * operator edits the IP and re-submits [addCanonicalServer] (a 1-of-N re-mint
     * that embeds the updated IP in a fresh scrubbed record). Consumed + cleared by
     * the screen (which seeds its local form state + scrolls to the add form).
     */
    data class CanonicalReplaceSeed(
        val keyId: String,
        val ed25519: String,
        val mldsa: String,
        val ip: String,
    )

    private val _canonicalReplaceTarget = MutableStateFlow<CanonicalReplaceSeed?>(null)
    val canonicalReplaceTarget: StateFlow<CanonicalReplaceSeed?> = _canonicalReplaceTarget.asStateFlow()

    /** Reload the canonical-servers roster (also refreshed on [refresh]). */
    fun loadCanonicalServers() {
        viewModelScope.launch {
            try {
                _canonicalServers.value = apiClient.listCanonicalServers().servers
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[loadCanonicalServers] ${e.message}")
            }
        }
    }

    /**
     * **Select an existing canonical server to replace / update.** Seeds the
     * add-canonical form with the row's key_id + both pubkeys (as the resolved
     * target — no owned-node re-pick needed) and its current IP, so the operator
     * only edits the IP and re-submits. A row missing its ML-DSA half can't be
     * replaced in-app (re-mint it from the owned-nodes picker instead).
     */
    fun selectCanonicalForReplace(
        server: ai.ciris.mobile.shared.models.federation.CanonicalServerDto,
    ) {
        val ml = server.pubkeyMlDsa65Base64
        if (ml.isNullOrBlank()) {
            _error.value =
                "${server.keyId} has no ML-DSA key in its record — re-mint it from the owned-nodes picker instead."
            return
        }
        val ip = server.transportHints?.firstOrNull { it.kind == "ip" }?.destination.orEmpty()
        _canonicalResolvedTarget.value = ResolvedTarget(server.keyId, server.pubkeyEd25519Base64, ml)
        _canonicalReplaceTarget.value = CanonicalReplaceSeed(server.keyId, server.pubkeyEd25519Base64, ml, ip)
    }

    /** Clear the replace seed once the screen has consumed it into its form. */
    fun clearCanonicalReplaceSeed() {
        _canonicalReplaceTarget.value = null
    }

    /**
     * **Withdraw a canonical server** (CIRISServer#164). DESTRUCTIVE — needs a
     * 2-of-3 accord proposal (a second/third holder must co-sign); a lone holder
     * cannot complete it. [proposalDigest] names the authorizing accord proposal.
     */
    fun withdrawCanonical(keyId: String, proposalDigest: String) {
        if (_busy.value) return
        if (proposalDigest.isBlank()) {
            _error.value = "Enter the 2-of-3 accord proposal digest first."
            return
        }
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.withdrawCanonical(keyId, proposalDigest)
                _notice.value = if (res.withdrawn) {
                    "Withdrew $keyId from the trust root."
                } else {
                    "Withdrawal recorded for $keyId — awaiting the 2-of-3 quorum."
                }
                refresh()
                loadCanonicalServers()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[withdrawCanonical] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    else -> "Couldn't withdraw the canonical server: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * Resolve a selected owned node to its Ed25519 + ML-DSA-65 pubkeys for the
     * canonical-add picker (mirrors [resolveTargetNode]). A node whose row is
     * missing its ML-DSA half can't be made canonical until re-claimed.
     */
    fun resolveCanonicalTarget(keyId: String) {
        _canonicalResolvedTarget.value = null
        if (keyId.isBlank()) return
        viewModelScope.launch {
            try {
                val peer = apiClient.getFederationPeer(keyId).peer
                val ml = peer.pubkeyMlDsa65Base64
                if (ml.isNullOrBlank()) {
                    _error.value =
                        "$keyId has no ML-DSA key in the directory yet — re-claim it first."
                } else {
                    _canonicalResolvedTarget.value = ResolvedTarget(keyId, peer.pubkeyEd25519Base64, ml)
                }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[resolveCanonicalTarget] ${e.message}")
                _error.value = "Couldn't load $keyId's keys: ${e.message}"
            }
        }
    }

    /**
     * **Add a canonical server** (CIRISServer#164). The local accord holder RE-OPENS
     * their YubiKey + USB-wrapped ML-DSA and scrub-signs the target node's
     * registration, ALSO flagging it `canonical` so it becomes a mesh-seed anchor;
     * the node writes the genesis **seed object** to a predictable outbox path
     * (surfaced as [canonicalSavedTo]) the operator hands to CIRISPersist to bake.
     * An OPTIONAL bootstrap transport ([transportKind] + [destination]) is recorded
     * as the canonical server's address. The app sends NO crypto — the touch IS consent.
     */
    fun addCanonicalServer(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        userPin: String?,
        transportKind: String? = null,
        destination: String? = null,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        _canonicalSavedTo.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.addCanonicalServer(
                    holderKeyId = holderKeyId,
                    mldsaUsbPath = mldsaUsbPath,
                    targetKeyId = targetKeyId,
                    targetEd25519Base64 = targetEd25519Base64,
                    targetMlDsa65Base64 = targetMlDsa65Base64,
                    userPin = userPin,
                    transportKind = transportKind?.takeIf { it.isNotBlank() },
                    destination = destination?.takeIf { it.isNotBlank() },
                    modulePath = modulePath,
                )
                _canonicalSavedTo.value = res.seedSavedTo
                _notice.value =
                    "Added canonical server ${res.canonicalKeyId}" +
                        (res.seedSavedTo?.let { " — seed saved to $it. Hand it to persist to bake." } ?: ".")
                refresh()
                loadCanonicalServers()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[addCanonicalServer] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    msg.contains("501") || msg.contains("NotSupported", ignoreCase = true) ->
                        "This build lacks pkcs11 — add-canonical needs the YubiKey signer."
                    else -> "Couldn't add the canonical server: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /** Reload the pending canonical co-scrubs (also refreshed on [refresh]). */
    fun loadPendingCoscrubs() {
        viewModelScope.launch {
            try {
                _pendingCoscrubs.value = apiClient.listPendingCoscrubs()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[loadPendingCoscrubs] ${e.message}")
            }
        }
    }

    /**
     * **Propose a canonical server (co-scrub scrub #1)** (CIRISServer#174). The local
     * accord holder RE-OPENS their YubiKey + USB-wrapped ML-DSA and scrub-signs the
     * target as `canonical`; the resulting 1-scrub partial does NOT yet confer canonical
     * (m-of-n). The node saves + gossips it to accord peers — hand / gossip it to the next
     * holder to [cosignCanonical]. Refreshes the canonical roster + pending list after.
     */
    fun proposeCanonical(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        userPin: String?,
        transportKind: String? = null,
        destination: String? = null,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        _canonicalSavedTo.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.proposeCanonicalServer(
                    holderKeyId = holderKeyId,
                    mldsaUsbPath = mldsaUsbPath,
                    targetKeyId = targetKeyId,
                    targetEd25519Base64 = targetEd25519Base64,
                    targetMlDsa65Base64 = targetMlDsa65Base64,
                    userPin = userPin,
                    transportKind = transportKind?.takeIf { it.isNotBlank() },
                    destination = destination?.takeIf { it.isNotBlank() },
                    modulePath = modulePath,
                )
                _canonicalSavedTo.value = res.savedTo
                _lastCoscrubJson.value = prettyCoscrub(res.partial)
                _notice.value =
                    "Proposed a co-scrub for ${res.targetKeyId} (${res.distinctScrubCount} scrub) — " +
                        "gossiped to ${res.gossipedTo} peer(s). Hand / gossip it to the next holder to cosign."
                loadCanonicalServers()
                loadPendingCoscrubs()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[proposeCanonical] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    msg.contains("501") || msg.contains("NotSupported", ignoreCase = true) ->
                        "This build lacks pkcs11 — propose needs the YubiKey signer."
                    else -> "Couldn't propose the canonical server: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * **Cosign a canonical co-scrub** (CIRISServer#174). THIS holder (e.g. B1) RE-OPENS
     * their YubiKey + USB ML-DSA and appends their scrub to [partial] over the
     * BYTE-IDENTICAL envelope. [partial] MUST be the verbatim `SignedKeyRecord` from a
     * pending entry OR a pasted partial — it is submitted UNCHANGED so the canonical
     * bytes match. At the family m-of-n the record is conferred; else it stays partial
     * (surfaced) for the next holder. Refreshes the canonical roster + pending list.
     */
    fun cosignCanonical(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String?,
        partial: kotlinx.serialization.json.JsonElement,
        modulePath: String? = null,
    ) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        _notice.value = null
        _canonicalSavedTo.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.cosignCanonicalServer(
                    holderKeyId = holderKeyId,
                    mldsaUsbPath = mldsaUsbPath,
                    partial = partial,
                    userPin = userPin,
                    modulePath = modulePath,
                )
                _canonicalSavedTo.value = res.savedTo
                // Conferred → nothing left to hand on; still short → export the advanced partial.
                _lastCoscrubJson.value = if (res.conferred) null else prettyCoscrub(res.advanced)
                _notice.value = if (res.conferred) {
                    "Cosigned — canonical CONFERRED for ${res.targetKeyId} at the family quorum (${res.distinctScrubCount} scrubs)."
                } else {
                    "Cosigned ${res.targetKeyId} (${res.distinctScrubCount} scrubs) — still short of the family quorum. " +
                        "Gossiped to ${res.gossipedTo} peer(s); hand / gossip it to the next holder."
                }
                loadCanonicalServers()
                loadPendingCoscrubs()
                refresh()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[cosignCanonical] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    msg.contains("501") || msg.contains("NotSupported", ignoreCase = true) ->
                        "This build lacks pkcs11 — cosign needs the YubiKey signer."
                    msg.contains("already signed", ignoreCase = true) ->
                        "This holder has already scrubbed this record — a distinct holder must cosign."
                    else -> "Couldn't cosign the co-scrub: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /**
     * **Supersede a canonical server** (CIRISServer#174). DESTRUCTIVE / 2-of-3: admits
     * the successor [newRecord] (a full A1-scrubbed `SignedKeyRecord`) BEFORE tombstoning
     * [oldKeyId], so the canonical set is never momentarily empty. [proposalDigest] names
     * the authorizing accord proposal (persist re-tallies it). [newRecord] rides verbatim.
     */
    fun supersedeCanonical(
        oldKeyId: String,
        newRecord: kotlinx.serialization.json.JsonElement,
        proposalDigest: String,
    ) {
        if (_busy.value) return
        if (proposalDigest.isBlank()) {
            _error.value = "Enter the 2-of-3 accord proposal digest first."
            return
        }
        _busy.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                val res = apiClient.supersedeCanonical(oldKeyId, newRecord, proposalDigest)
                _notice.value = if (res.superseded) {
                    "Superseded $oldKeyId${res.successor?.let { " → $it" } ?: ""}."
                } else {
                    "Supersede recorded for $oldKeyId — awaiting the 2-of-3 quorum."
                }
                refresh()
                loadCanonicalServers()
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "[supersedeCanonical] ${e.message}")
                val msg = e.message.orEmpty()
                _error.value = when {
                    msg.contains("401") || msg.contains("403") ->
                        "Sign in as the owner on this node first."
                    else -> "Couldn't supersede the canonical server: ${e.message}"
                }
            } finally {
                _busy.value = false
            }
        }
    }

    /** Surface a client-side error (e.g. a malformed pasted co-scrub partial). */
    fun showError(message: String) {
        _error.value = message
    }

    /** Surface a client-side notice / error from the UI (e.g. a copy / save result). */
    fun setExternalNotice(message: String, error: Boolean = false) {
        if (error) {
            _error.value = message
        } else {
            _notice.value = message
        }
    }

    fun clearMessages() {
        _error.value = null
        _notice.value = null
    }
}
