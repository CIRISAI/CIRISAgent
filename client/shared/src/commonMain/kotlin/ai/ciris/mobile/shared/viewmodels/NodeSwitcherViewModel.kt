package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.readTextFile
import ai.ciris.mobile.shared.platform.util.DecodedNodeCode
import ai.ciris.mobile.shared.platform.util.NodeCodeCodec
import ai.ciris.mobile.shared.platform.util.NodeCodeException
import ai.ciris.mobile.shared.platform.writeTextFile
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

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
 *
 * **CIRISServer#125 (live, stateless client).** The node list is read LIVE from
 * the local node's `GET /v1/setup/owned-nodes` projection (owner + the key_ids
 * the owner holds an owner-binding for), NOT from a client-side Java-prefs cache.
 * The old `NodeProfileStore` (a `~/.java/.userPrefs` side store OUTSIDE the ciris
 * folder) was the source of the #125 staleness bugs: a wipe left phantom nodes in
 * the switcher, the identity name was only correct after a restart, etc. There is
 * now NO cross-launch persistence of nodes here — the local node is the source of
 * truth, rebuilt on every [reload]. Nodes the user adds by URL / NodeCode within a
 * session ([saveProfile] / [connectByNodeCode]) live in memory only and are gone
 * on relaunch (re-add from the live node, mirroring the stateless posture).
 */
class NodeSwitcherViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "NodeSwitcherVM"

        /**
         * The valid cohort scopes for a node-ownership claim (CIRISServer v0.4.3):
         * who the owner is adding the node to. CIRISServer validates the
         * `cohort_scope` body field against exactly these values (else `400`).
         */
        val COHORT_SCOPES = listOf("self", "family", "community")

        /** Filename of the node list written to / read from a chosen USB folder. */
        const val NODE_LIST_FILENAME = "ciris-nodes.json"

        private val NODE_LIST_JSON = Json {
            prettyPrint = true
            ignoreUnknownKeys = true
            encodeDefaults = true
        }
    }

    private val _profiles = MutableStateFlow<List<NodeProfile>>(emptyList())
    val profiles: StateFlow<List<NodeProfile>> = _profiles.asStateFlow()

    private val _activeProfileId = MutableStateFlow<String?>(null)
    val activeProfileId: StateFlow<String?> = _activeProfileId.asStateFlow()

    private val _isSwitching = MutableStateFlow(false)
    val isSwitching: StateFlow<Boolean> = _isSwitching.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Transient success notice (e.g. "Saved 3 nodes to USB"); cleared by the UI. */
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    /**
     * Session-scoped, in-memory nodes the user added by URL or NodeCode this run
     * (NOT persisted — #125). Carried across [reload] so a live owned-nodes refresh
     * doesn't drop a node the user just typed in. Keyed/de-duped by [NodeProfile.id].
     */
    private val sessionProfiles = mutableListOf<NodeProfile>()

    val activeProfile: NodeProfile?
        get() = _profiles.value.firstOrNull { it.id == _activeProfileId.value }

    init {
        viewModelScope.launch { reload() }
    }

    /**
     * Reload the node list LIVE. **CEG-native, no client cache:** the list is the
     * set of nodes this fed ID owns — the local node's `delegates_to(user → node)`
     * owner-binding objects, read via `GET /v1/setup/owned-nodes` (now
     * self-replicated across the owner's devices). The local node (the one this app
     * launches + drives at [CIRISApiClient.LOCAL_NODE_URL]) is always listed once
     * self-claimed. Owned REMOTE nodes are listed by their `key_id` but carry no
     * reachable endpoint yet — mesh addressing by key_id is a separate transport
     * phase (see [switchTo]). Any node the user added this session ([saveProfile] /
     * [connectByNodeCode]) is appended (de-duped). If the local node can't be
     * reached, fall back to a bare local-node entry so the loopback stays usable.
     */
    suspend fun reload() {
        val owned = try {
            apiClient.getOwnedNodes()
        } catch (e: Exception) {
            PlatformLogger.w(TAG, "[reload] owned-nodes unavailable (${e.message}) — local node only")
            null
        }

        // Fed-ID presence for the logged-in owner: owner key_id present = has a
        // fed-ID; null/blank = legacy WA owner with no fed-ID (offer Add Fed ID);
        // owned==null = unknown (leave the entry hidden).
        _ownerHasFedId.value = owned?.let { !it.owner.isNullOrBlank() }

        val projected: List<NodeProfile> = if (owned != null) {
            PlatformLogger.i(
                TAG,
                "[reload] owned-nodes projection: owner=${owned.owner} nodes=${owned.nodes.size} — " +
                    owned.nodes.joinToString { "${it.keyId}(self=${it.isSelf})" },
            )
            // Ensure the local node is always present even if owned-nodes hasn't
            // listed a self entry yet (e.g. freshly booted, not yet self-claimed).
            val fromGraph = owned.nodes.map { on ->
                if (on.isSelf) {
                    localNodeProfile(on.keyId)
                } else {
                    // An owned REMOTE node — present per the graph but URL-less:
                    // reachable over the mesh by key_id, which is not wired yet.
                    NodeProfile(
                        id = on.keyId,
                        name = on.keyId,
                        baseUrl = "",
                        pinnedKeyId = on.keyId,
                        isOwned = true,
                    )
                }
            }
            if (fromGraph.any { it.isLocal }) fromGraph else listOf(localNodeProfile(null)) + fromGraph
        } else {
            // Local node unreachable for the projection — still list it so the
            // loopback node remains selectable/usable (the common, field-proven case).
            listOf(localNodeProfile(null))
        }

        // Append session-added nodes the projection didn't already represent
        // (de-dup by id, then by pinned key_id).
        val projectedIds = projected.map { it.id }.toSet()
        val projectedKeys = projected.mapNotNull { it.pinnedKeyId }.toSet()
        val extra = sessionProfiles.filter { sp ->
            sp.id !in projectedIds && (sp.pinnedKeyId == null || sp.pinnedKeyId !in projectedKeys)
        }
        _profiles.value = projected + extra
        PlatformLogger.i(
            TAG,
            "[reload] FINAL node list: ${_profiles.value.size} — " +
                _profiles.value.joinToString { "${it.name}(local=${it.isLocal}, owned=${it.isOwned})" },
        )

        // Keep the current selection if it's still present, else default to local.
        val current = _activeProfileId.value
        _activeProfileId.value = _profiles.value.firstOrNull { it.id == current }?.id
            ?: _profiles.value.firstOrNull { it.isLocal }?.id
            ?: _profiles.value.firstOrNull()?.id
    }

    /** The canonical local-node profile, optionally tagged with its CEG key_id. */
    private fun localNodeProfile(keyId: String?): NodeProfile = NodeProfile(
        id = NodeProfile.idFor(CIRISApiClient.LOCAL_NODE_URL),
        name = "This device",
        baseUrl = CIRISApiClient.LOCAL_NODE_URL,
        pinnedKeyId = keyId,
        isLocal = true,
        isOwned = true,
    )

    /** Insert or replace a session profile in both the in-memory list and the UI flow. */
    private fun upsertSessionProfile(profile: NodeProfile) {
        val idx = sessionProfiles.indexOfFirst { it.id == profile.id }
        if (idx >= 0) sessionProfiles[idx] = profile else sessionProfiles.add(profile)
        val cur = _profiles.value.toMutableList()
        val ci = cur.indexOfFirst { it.id == profile.id }
        if (ci >= 0) cur[ci] = profile else cur.add(profile)
        _profiles.value = cur
    }

    /**
     * Add or update a node profile (by URL) for THIS session only. Mirrors the
     * add/edit path of ServerConnectionScreen but holds a full [NodeProfile] in
     * memory rather than persisting it (#125 — no client cache).
     */
    fun saveProfile(name: String, baseUrl: String, sessionToken: String? = null) {
        val normalized = baseUrl.trim().trimEnd('/')
        upsertSessionProfile(
            NodeProfile(
                id = NodeProfile.idFor(normalized),
                name = name.ifBlank { normalized },
                baseUrl = normalized,
                sessionToken = sessionToken,
                lastUsedEpochMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds(),
            ),
        )
    }

    fun removeProfile(id: String) {
        sessionProfiles.removeAll { it.id == id }
        _profiles.value = _profiles.value.filterNot { it.id == id }
        // A live owned/local node reappears on the next reload — only session-added
        // nodes are truly removable. That is by design: the graph is the truth.
    }

    /**
     * Rename a node in place for this session (in-memory; reverts on the next live
     * [reload] for graph-derived nodes). Used by the Manage Nodes CRUD surface.
     */
    fun renameProfile(id: String, newName: String) {
        val name = newName.trim()
        if (name.isBlank()) return
        val existing = _profiles.value.firstOrNull { it.id == id } ?: return
        upsertSessionProfile(existing.copy(name = name))
    }

    /**
     * Re-token a session profile: replace (or clear when blank) the in-memory
     * session token. Manage Nodes "retoken" affordance.
     */
    fun retokenProfile(id: String, token: String?) {
        val existing = _profiles.value.firstOrNull { it.id == id } ?: return
        val trimmed = token?.trim()?.takeIf { it.isNotBlank() }
        upsertSessionProfile(existing.copy(sessionToken = trimmed))
    }

    /**
     * Switch the active node. Repoints the shared API client at the chosen node and
     * applies its token (in memory — the session token is NOT persisted, #125), then
     * marks it active. Screens observing [activeProfileId] should reload their data.
     *
     * REMOTE-by-key_id is OUT OF SCOPE: an owned remote node from the live
     * owned-nodes projection carries no reachable endpoint (`baseUrl == ""`).
     * Selecting one is refused with a clear "coming soon" message until mesh
     * addressing-by-key_id is wired.
     */
    fun switchTo(profile: NodeProfile) {
        if (_isSwitching.value) return
        // TODO(#125 mesh-addressing phase): reach an owned remote node by its
        // key_id over the mesh. Today owned-nodes returns only {key_id, is_self}
        // with no endpoint, so a URL-less node cannot be selected. Nodes added by
        // URL / NodeCode this session DO carry a baseUrl and remain switchable.
        if (profile.baseUrl.isBlank()) {
            _error.value = "${profile.name} is reachable over the mesh — switching to it is coming soon."
            return
        }
        _isSwitching.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                PlatformLogger.i(TAG, "[switchTo] Switching to node '${profile.name}' @ ${profile.baseUrl} (local=${profile.isLocal})")
                apiClient.updateBaseUrl(profile.baseUrl)
                // Apply (or skip) the node's session token on the shared client.
                // In-memory only — #125 drops cross-launch token persistence.
                if (profile.isAuthenticated) {
                    apiClient.setAccessToken(profile.sessionToken!!)
                }
                val now = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                _activeProfileId.value = profile.id
                _profiles.value = _profiles.value.map {
                    if (it.id == profile.id) it.copy(lastUsedEpochMs = now) else it
                }
                PlatformLogger.i(
                    TAG,
                    "[switchTo] active='${profile.id}' — node list (${_profiles.value.size}): " +
                        _profiles.value.joinToString { "${it.name}(local=${it.isLocal}, active=${it.id == profile.id})" },
                )
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[switchTo] Failed: ${e.message}", e)
                _error.value = "Could not switch to ${profile.name}: ${e.message}"
            } finally {
                _isSwitching.value = false
            }
        }
    }

    fun clearError() { _error.value = null }

    fun clearNotice() { _notice.value = null }

    // ─── Save / Restore node list to USB (private/offline sneakernet) ──────────
    //
    // After #125 the client is stateless: the switcher derives its list LIVE from
    // owned-nodes, and owned bindings self-replicate to the owner's devices ONLY
    // over their mesh (once announced/connected). An owner who stays PRIVATE — or
    // sets up a fresh/offline device — has no way to carry their known nodes
    // across devices. This is the USB sneakernet for the node list, mirroring the
    // fed-ID USB import UX. Restored nodes carry a baseUrl, so they land in the
    // session list AND become switchable — which also fills the interim
    // remote-reachability gap until mesh addressing-by-key_id is wired.

    /**
     * The nodes worth carrying to another device: everything EXCEPT this device's
     * pure local-loopback entry (its [CIRISApiClient.LOCAL_NODE_URL] is
     * device-specific, not portable). Owned remotes with an empty baseUrl are
     * included for completeness; the switchable value is the ones with a real
     * endpoint (session/URL/NodeCode-added).
     */
    private fun exportableNodes(): List<NodeProfile> =
        _profiles.value.filterNot { it.isLocal || it.baseUrl == CIRISApiClient.LOCAL_NODE_URL }

    /**
     * Serialize the user's known nodes to the portable node-list JSON. Pure +
     * testable — the file write is [saveNodeListToUsb]'s job.
     */
    fun exportNodeListJson(): String =
        NODE_LIST_JSON.encodeToString(
            ExportedNodeList(
                nodes = exportableNodes().map {
                    ExportedNode(keyId = it.pinnedKeyId.orEmpty(), name = it.name, baseUrl = it.baseUrl)
                },
            ),
        )

    /**
     * Parse a portable node-list JSON and ADD each switchable entry (non-empty
     * baseUrl) into the in-memory session list so it shows in the switcher and can
     * be switched to. De-dupes by [NodeProfile.idFor] (the normalised baseUrl), so
     * re-importing the same node just refreshes it. Returns the count added. Pure +
     * testable — the file read is [restoreNodeListFromUsb]'s job.
     */
    fun importNodeListJson(json: String): Int {
        val parsed = try {
            NODE_LIST_JSON.decodeFromString<ExportedNodeList>(json)
        } catch (e: Exception) {
            PlatformLogger.w(TAG, "[importNodeListJson] parse failed: ${e.message}")
            _error.value = "That file isn't a valid CIRIS node list: ${e.message}"
            return 0
        }
        var added = 0
        for (entry in parsed.nodes) {
            val url = entry.baseUrl.trim().trimEnd('/')
            // Owned remotes carry no endpoint yet (not switchable) and a foreign
            // device's loopback is meaningless here — skip both.
            if (url.isBlank() || url == CIRISApiClient.LOCAL_NODE_URL) continue
            upsertSessionProfile(
                NodeProfile(
                    id = NodeProfile.idFor(url),
                    name = entry.name.ifBlank { url },
                    baseUrl = url,
                    pinnedKeyId = entry.keyId.ifBlank { null },
                ),
            )
            added++
        }
        PlatformLogger.i(TAG, "[importNodeListJson] restored $added switchable node(s)")
        return added
    }

    /** Write the node list to [NODE_LIST_FILENAME] in the chosen USB [dir]. */
    fun saveNodeListToUsb(dir: String) {
        val target = dir.trim()
        if (target.isBlank()) return
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            val count = exportableNodes().size
            val ok = writeTextFile(target, NODE_LIST_FILENAME, exportNodeListJson())
            if (ok) {
                PlatformLogger.i(TAG, "[saveNodeListToUsb] wrote $count node(s) to $target/$NODE_LIST_FILENAME")
                _notice.value = "Saved $count node(s) to $NODE_LIST_FILENAME on the USB folder."
            } else {
                _error.value = "Couldn't write $NODE_LIST_FILENAME to that folder — saving to USB isn't available on this device yet."
            }
        }
    }

    /** Read [NODE_LIST_FILENAME] from the chosen USB [dir] and add its nodes. */
    fun restoreNodeListFromUsb(dir: String) {
        val target = dir.trim()
        if (target.isBlank()) return
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            val json = readTextFile(target, NODE_LIST_FILENAME)
            if (json == null) {
                _error.value = "No $NODE_LIST_FILENAME found in that folder — or restoring from USB isn't available on this device yet."
                return@launch
            }
            val count = importNodeListJson(json)
            if (count > 0) {
                _notice.value = "Restored $count node(s) from USB."
            } else if (_error.value == null) {
                _notice.value = "No switchable nodes found in $NODE_LIST_FILENAME."
            }
        }
    }

    private val _upgradeInProgress = MutableStateFlow(false)
    val upgradeInProgress: StateFlow<Boolean> = _upgradeInProgress.asStateFlow()

    /**
     * **Does the logged-in owner already have a federation ID?** — detected from the
     * local node's `GET /v1/setup/owned-nodes` projection: [OwnedNodesDto.owner] is
     * the bound owner's *fed-ID key_id*, and is null/blank when the node is owned the
     * legacy way (a password/OAuth ROOT WA with NO fed-ID). Within the management UI
     * the user is always the authenticated owner, so:
     *   - `false` = owner is bound but has NO fed-ID → offer "Add Federation ID".
     *   - `true`  = owner already has a fed-ID → hide the entry.
     *   - `null`  = unknown (owned-nodes not reachable) → hide the entry (fail-closed;
     *     don't offer an upgrade we can't reason about).
     * Refreshed on every [reload].
     */
    private val _ownerHasFedId = MutableStateFlow<Boolean?>(null)
    val ownerHasFedId: StateFlow<Boolean?> = _ownerHasFedId.asStateFlow()

    /**
     * **Upgrade THIS device's local node to a fed-ID owner-binding** — the
     * WAs-need-fed-IDs migration (the agent team's 2.9.7). For a node owned the
     * legacy way (a password/OAuth ROOT WA with NO fed-ID), this mints the owner's
     * hardware-rooted fed-ID (secure-only: YubiKey → TPM → software, the app does
     * NO crypto) and re-roots the node on it via `POST /v1/self/upgrade-owner` —
     * the existing login is PRESERVED (non-destructive owner-binding model).
     *
     * Requires the caller to be authenticated as the existing owner (the shared
     * client carries that session). [associateKeyId] is reserved for the
     * adopt-existing-fed-ID path (pkcs11/provision=false) — left for the YubiKey
     * reclaim case; null mints a fresh hardware-rooted fed-ID.
     */
    fun upgradeToFedId(
        label: String? = null,
        announce: Boolean = false,
        traceOptIn: Boolean = false,
    ) {
        if (_upgradeInProgress.value) return
        _upgradeInProgress.value = true
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                // 1) Mint the owner's fed-ID on the local node (owner-gated; uses the
                //    current owner session). Secure-only — substrate auto-picks custody.
                //    A validated, non-generic label is passed by the guided flow to
                //    avoid the ciris-client-user identity collision.
                apiClient.mintUserIdentity(
                    label = label?.trim()?.ifBlank { null },
                    backend = null,
                    localNodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                )
                // 2) Re-root the existing node on the just-minted fed-ID (login
                //    preserved — non-destructive owner-binding model).
                apiClient.upgradeOwnerToFedId(localNodeUrl = CIRISApiClient.LOCAL_NODE_URL)
                PlatformLogger.i(TAG, "[upgradeToFedId] node re-rooted on a fed-ID owner-binding")

                // 3) If the user chose to announce, promote the owner-binding
                //    self→FEDERATION + enable the identity announce. This is UPSTREAM
                //    of traces/community; takes effect next boot. Non-fatal — a failed
                //    announce must not undo the (successful) fed-ID upgrade, so surface
                //    a soft notice rather than an error (mirrors first-run handling).
                if (announce) {
                    try {
                        val ann = apiClient.announceOwnership(localNodeUrl = CIRISApiClient.LOCAL_NODE_URL)
                        PlatformLogger.i(
                            TAG,
                            "[upgradeToFedId] announced to federation owner=${ann.owner} " +
                                "scope=${ann.cohortScope} effect=${ann.announceTakesEffect}",
                        )
                    } catch (e: Exception) {
                        PlatformLogger.w(TAG, "[upgradeToFedId] federation announce failed (non-fatal): ${e.message}")
                        _notice.value = "Fed ID added, but announcing to the federation didn't go " +
                            "through — you can turn on announcing later. (${e.message})"
                    }
                }

                // 4) Trace opt-in (only meaningful once announced). Non-fatal.
                if (announce && traceOptIn) {
                    try {
                        apiClient.updateAccordSettings(consentGiven = true)
                        PlatformLogger.i(TAG, "[upgradeToFedId] accord metrics consent enabled")
                    } catch (e: Exception) {
                        PlatformLogger.w(TAG, "[upgradeToFedId] accord opt-in failed (non-fatal): ${e.message}")
                    }
                }

                if (_notice.value == null) {
                    _notice.value = if (announce) {
                        "Fed ID added and announced — federation visibility takes effect on next launch."
                    } else {
                        "Fed ID added. Your node stays private (self-scoped)."
                    }
                }
                reload()
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "[upgradeToFedId] failed: ${e.message}", e)
                _error.value = "Couldn't upgrade this account to a Fed ID: ${e.message}"
            } finally {
                _upgradeInProgress.value = false
            }
        }
    }

    // ─── Connect-by-NodeCode: decode → connect → identity-pin → claim ─────────
    //
    // The secure "become admin of a remote node" bootstrap (CEG §0.10). The
    // founder enters a node's CIRIS-V1- code (pasted or scanned). We decode it
    // LOCALLY (no server round-trip to learn what node it is), derive a base URL
    // from the transport hint, connect, then identity-pin: fetch the node's own
    // served NodeCode and refuse unless its key_id + pubkey match the decoded
    // code. Only a pinned node is added as a session profile.

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
     * is added (session-only) and the bootstrap state reports
     * [NodeBootstrapState.pinnedProfile] so the UI can offer "Claim admin" next.
     * [overrideUrl] lets the user supply the base URL when the code carries no
     * usable transport hint.
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
                upsertSessionProfile(profile)
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
                // Refresh the node list LIVE (the claim minted a new owner-binding).
                reload()
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

/** One node in the portable USB node-list file ([NodeSwitcherViewModel.NODE_LIST_FILENAME]). */
@Serializable
data class ExportedNode(
    val keyId: String = "",
    val name: String = "",
    val baseUrl: String = "",
)

/** The portable USB node-list file payload. */
@Serializable
data class ExportedNodeList(
    val version: Int = 1,
    val nodes: List<ExportedNode> = emptyList(),
)
