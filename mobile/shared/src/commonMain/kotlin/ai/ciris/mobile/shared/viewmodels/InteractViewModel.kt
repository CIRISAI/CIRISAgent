package ai.ciris.mobile.shared.viewmodels

import ai.ciris.api.models.DocumentPayload
import ai.ciris.api.models.ImagePayload
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.SystemWarning
import ai.ciris.mobile.shared.api.ReasoningEvent
import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.localization.LocalizationManager
import ai.ciris.mobile.shared.api.ReasoningStreamClient
import ai.ciris.mobile.shared.ui.screens.graph.AdapterOrbit
import ai.ciris.mobile.shared.ui.screens.graph.PipelineState
import ai.ciris.mobile.shared.ui.screens.graph.orbitFor
import ai.ciris.mobile.shared.auth.TokenManager
import ai.ciris.mobile.shared.models.ActionDetails
import ai.ciris.mobile.shared.models.ActionType
import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.PickedFile
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.createEnvFileUpdater
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

/**
 * A bubble emoji that floats up from the agent icon
 */
data class BubbleEmoji(
    val id: Long,
    val emoji: String,
    // Short human-readable summary of the event that spawned this bubble.
    // Lives only as long as the bubble is in flight (or caught).
    val payload: String? = null,
    // Absolute millis when the bubble should pop. Used so a tap handler can
    // distinguish "in flight" (still interactive) from "already expired".
    val expiresAtMs: Long = 0L
)

/**
 * A timeline event - minimal storage (emoji + timestamp + event type)
 */
data class TimelineEvent(
    val emoji: String,
    val eventType: String, // action name for display
    val timestamp: Long // epoch millis
)

/**
 * Agent processing state for the icon
 */
enum class AgentProcessingState {
    IDLE,       // 💭 - not processing
    PROCESSING  // 🔄 - actively processing
}

/**
 * Shared ViewModel for chat interface
 * Ported from Android InteractFragment.kt
 *
 * Features:
 * - Message history polling
 * - Agent status monitoring
 * - Processing status tracking via SSE bubbles
 * - Message submission
 * - Shutdown controls
 */
/**
 * LLM health status for status bar display
 */
data class LlmHealthStatus(
    val provider: String = "unknown",
    val isHealthy: Boolean = false,
    val model: String = "unknown",
    val isCirisProxy: Boolean = false
)

/**
 * Credit status for status bar display
 */
data class CreditStatus(
    val hasCredit: Boolean = false,
    val creditsRemaining: Int = 0,
    val freeUsesRemaining: Int = 0,
    val dailyFreeUsesRemaining: Int = 0,
    val dailyFreeUsesLimit: Int = 2,
    val planName: String? = null,
    val isLoaded: Boolean = false
) {
    /**
     * Total available uses (paid + free + daily free)
     */
    val totalAvailable: Int get() = creditsRemaining + freeUsesRemaining + dailyFreeUsesRemaining

    /**
     * Whether user can send a message (has any credits/uses available)
     */
    val canSendMessage: Boolean get() = hasCredit || totalAvailable > 0

    /**
     * Calculate hours until next midnight UTC (when daily credits renew).
     * Returns a value between 0 and 24.
     */
    fun hoursUntilRenewal(): Int {
        val now = Clock.System.now()
        val currentHourUtc = (now.toEpochMilliseconds() / 3600000) % 24
        return (24 - currentHourUtc.toInt()) % 24
    }

    /**
     * Whether daily credits will renew (user has used some daily credits)
     */
    val willRenew: Boolean get() = dailyFreeUsesRemaining < dailyFreeUsesLimit
}

/**
 * Trust status for trust shield display
 */
data class TrustStatus(
    val maxLevel: Int = 0,
    val isLoaded: Boolean = false,
    val keyStatus: String = "none",
    val attestationStatus: String = "not_attempted",
    val levelPending: Boolean = false  // True when waiting for Play Integrity
)

/**
 * Wallet status for wallet badge display
 */
data class WalletStatus(
    val isLoaded: Boolean = false,
    val hasWallet: Boolean = false,
    val balance: String = "0.00",
    val currency: String = "USDC",
    val provider: String = "x402",
    val network: String = "base-sepolia",
    val address: String? = null,
    val isReceiveOnly: Boolean = false,  // True if hardware trust degraded
    val isInitializing: Boolean = false  // True while wallet provider is starting up
)

class InteractViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "InteractViewModel"
        private const val POLL_INTERVAL_MS = 3000L
        private const val STATUS_POLL_INTERVAL_MS = 5000L
        private const val HEALTH_POLL_INTERVAL_MS = 30000L  // Less frequent health checks
        private const val TRUST_PENDING_POLL_INTERVAL_MS = 5000L  // Fast polling when Play Integrity pending
        private const val MAX_BUBBLES = 8
        private const val BUBBLE_LIFETIME_MS = 2000L
        private const val MAX_TIMELINE_EVENTS = 100
        // Bounded to keep caught-bubble memory within the 32-bit ARM budget.
        // Worst case: MAX_CAUGHT_BUBBLES × ReasoningEvent.PAYLOAD_MAX_CHARS ≈ 3.8KB.
        private const val MAX_CAUGHT_BUBBLES = 12
        private const val SSE_RECONNECT_BASE_MS = 1000L
        private const val SSE_RECONNECT_MAX_MS = 30000L
        /** Max recent SSE events retained per pipeline stage (ring buffer). */
        private const val STAGE_EVENT_BUFFER = 5
        /** 1 Hz poll cadence for selected-element detail fetches. */
        // FG selection detail poll cadence. Slowed from 1s to 2s after
        // 429s from the agent backend — 0.5 Hz is still fast enough for
        // "live" feel on stage-event streams while halving request
        // pressure on endpoints that feed multiple selection kinds.
        private const val SELECTION_POLL_INTERVAL_MS = 2000L
    }

    // Device attestation callback for triggering Play Integrity at startup
    private var deviceAttestationCallback: ai.ciris.mobile.shared.DeviceAttestationCallback? = null
    private var deviceAttestationTriggered = false  // Track if we've already triggered it

    /**
     * Set the device attestation callback for Play Integrity.
     * Should be called after ViewModel creation from CIRISApp.
     */
    fun setDeviceAttestationCallback(callback: ai.ciris.mobile.shared.DeviceAttestationCallback?) {
        logInfo("setDeviceAttestationCallback", "Device attestation callback ${if (callback != null) "SET" else "CLEARED"}")
        deviceAttestationCallback = callback
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
            else -> PlatformLogger.i(TAG, fullMessage)
        }
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    /**
     * Clear all cached state. Called during factory reset / wipe
     * to prevent stale messages from appearing after restart.
     */
    fun resetState() {
        val method = "resetState"
        logInfo(method, "Clearing all ViewModel state for clean restart")
        _messages.value = emptyList()
        _inputText.value = ""
        _isConnected.value = false
        _agentStatus.value = "Initializing..."
        _isSending.value = false
        _isLoading.value = true
        _authError.value = null
        authErrorCount = 0
        pollingStarted = false
        isFirstLoad = true
        pollingJob?.cancel()
        pollingJob = null
        sseJob?.cancel()
        sseJob = null
        capacityRefreshJob?.cancel()
        capacityRefreshJob = null
    }

    private val _inputText = MutableStateFlow("")
    val inputText: StateFlow<String> = _inputText.asStateFlow()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _agentStatus = MutableStateFlow("Initializing...")
    val agentStatus: StateFlow<String> = _agentStatus.asStateFlow()

    private val _isSending = MutableStateFlow(false)
    val isSending: StateFlow<Boolean> = _isSending.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _processingStatus = MutableStateFlow("")
    val processingStatus: StateFlow<String> = _processingStatus.asStateFlow()

    private val _authError = MutableStateFlow<String?>(null)
    val authError: StateFlow<String?> = _authError.asStateFlow()

    // Bubble emoji state - emojis float up from agent icon
    private val _bubbleEmojis = MutableStateFlow<List<BubbleEmoji>>(emptyList())
    val bubbleEmojis: StateFlow<List<BubbleEmoji>> = _bubbleEmojis.asStateFlow()

    // Caught bubbles - user tapped a floating bubble to pin it.
    // Payload survives past the 2s float window because the user explicitly asked.
    // Capped at MAX_CAUGHT_BUBBLES to preserve the 32-bit ARM memory budget.
    private val _caughtBubbles = MutableStateFlow<List<BubbleEmoji>>(emptyList())
    val caughtBubbles: StateFlow<List<BubbleEmoji>> = _caughtBubbles.asStateFlow()

    // Adapter orbits - the agent's "body" rendered as satellites around the
    // memory/pipeline cylinder. Fetched once at screen mount; bounded by
    // the number of loaded adapters (< 20 in practice).
    private val _adapterOrbits = MutableStateFlow<List<AdapterOrbit>>(emptyList())
    val adapterOrbits: StateFlow<List<AdapterOrbit>> = _adapterOrbits.asStateFlow()

    // Agent processing state for icon
    private val _agentProcessingState = MutableStateFlow(AgentProcessingState.IDLE)
    val agentProcessingState: StateFlow<AgentProcessingState> = _agentProcessingState.asStateFlow()

    // SSE stream connected
    private val _sseConnected = MutableStateFlow(false)
    val sseConnected: StateFlow<Boolean> = _sseConnected.asStateFlow()

    // Timeline events - minimal storage for bubble net
    private val _timelineEvents = MutableStateFlow<List<TimelineEvent>>(emptyList())
    val timelineEvents: StateFlow<List<TimelineEvent>> = _timelineEvents.asStateFlow()

    // H3ERE pipeline scaffolding state - tracks which pipeline stages are active
    // Labels are localized via LocalizationHelper for multilingual support
    // Note: Initialize with default (English) labels - they will be updated when localization is ready
    private val _pipelineState = MutableStateFlow(PipelineState())
    val pipelineState: StateFlow<PipelineState> = _pipelineState.asStateFlow()

    // Track language observation job
    private var languageObserverJob: Job? = null

    // Show timeline popup
    private val _showTimeline = MutableStateFlow(false)
    val showTimeline: StateFlow<Boolean> = _showTimeline.asStateFlow()

    // Show emoji legend popup
    private val _showLegend = MutableStateFlow(false)
    val showLegend: StateFlow<Boolean> = _showLegend.asStateFlow()

    // LLM health status for status bar
    private val _llmHealth = MutableStateFlow(LlmHealthStatus())
    val llmHealth: StateFlow<LlmHealthStatus> = _llmHealth.asStateFlow()

    // Credit status for status bar (only shown when isCirisProxy)
    private val _creditStatus = MutableStateFlow(CreditStatus())
    val creditStatus: StateFlow<CreditStatus> = _creditStatus.asStateFlow()

    // Trust status for shield display
    private val _trustStatus = MutableStateFlow(TrustStatus())
    val trustStatus: StateFlow<TrustStatus> = _trustStatus.asStateFlow()

    // Wallet status for wallet badge display
    private val _walletStatus = MutableStateFlow(WalletStatus())
    val walletStatus: StateFlow<WalletStatus> = _walletStatus.asStateFlow()

    // Pending deferrals count for WA banner display
    private val _pendingDeferrals = MutableStateFlow(0)
    val pendingDeferrals: StateFlow<Int> = _pendingDeferrals.asStateFlow()

    // System warnings (e.g., no LLM provider configured)
    private val _systemWarnings = MutableStateFlow<List<SystemWarning>>(emptyList())
    val systemWarnings: StateFlow<List<SystemWarning>> = _systemWarnings.asStateFlow()

    // File attachments for current message
    private val _attachedFiles = MutableStateFlow<List<PickedFile>>(emptyList())
    val attachedFiles: StateFlow<List<PickedFile>> = _attachedFiles.asStateFlow()

    // CIRIS capacity (ratchet) — drives cell-viz ambient dials. Defaults to
    // CellVizState.DEFAULT so the cell renders as-designed until the first
    // fetch arrives. User-facing only; never piped into agent context.
    private val _cellVizState = MutableStateFlow(
        ai.ciris.mobile.shared.ui.screens.graph.CellVizState.DEFAULT
    )
    val cellVizState: StateFlow<ai.ciris.mobile.shared.ui.screens.graph.CellVizState> =
        _cellVizState.asStateFlow()

    // Tier-1 events — bus-arc shimmers on SSE activity. Bounded to a small
    // ring of recent pulses; each self-expires after BUS_PULSE_DURATION_MS
    // via the launched coroutine in [addBusPulse]. Passing the full list
    // to Compose lets multiple concurrent pulses coexist (memory + llm
    // firing on the same thought step is common).
    private val _busPulses = MutableStateFlow<List<ai.ciris.mobile.shared.ui.screens.graph.BusPulse>>(emptyList())
    val busPulses: StateFlow<List<ai.ciris.mobile.shared.ui.screens.graph.BusPulse>> =
        _busPulses.asStateFlow()

    // Tier-1 gratitude motes — warm ejections from the nucleus on
    // task_complete events. Gated by a 3 s cooldown (see canEmitGratitude)
    // so the signal stays meaningful; anything more frequent would blur
    // into ambient noise.
    private val _gratitudePulses =
        MutableStateFlow<List<ai.ciris.mobile.shared.ui.screens.graph.GratitudePulse>>(emptyList())
    val gratitudePulses: StateFlow<List<ai.ciris.mobile.shared.ui.screens.graph.GratitudePulse>> =
        _gratitudePulses.asStateFlow()

    private var lastGratitudeMs: Long = 0L

    // Tier-3 deferral ripple — single concentric wave from nucleus outward
    // on every DEFER action (routing to Wise Authority). Start-timestamp
    // null when idle; set to the event-time on DEFER, cleared ~2.5s later.
    // FSD §2.5.3 + §18 Step 9. The pre-ripple "pause" (rotation slowdown
    // 800ms) is a follow-up — it needs the external rotation driver to
    // read this state too, which this StateFlow makes possible.
    private val _deferralRippleStartMs = MutableStateFlow<Long?>(null)
    val deferralRippleStartMs: StateFlow<Long?> = _deferralRippleStartMs.asStateFlow()

    // Per-stage SSE ring buffer — the data source for the "tap a nucleus
    // shell and see the most recent rationales" demo scenario. Keyed by
    // SSE event_type, capped at STAGE_EVENT_BUFFER capacity per type so
    // memory stays bounded (<= 7 × 5 × ~200 chars ≈ 7 KB worst case).
    //
    // Updated on every ReasoningEvent.Emoji so the buffer always holds
    // the last K events for each stage, independent of FG/BG mode.
    private val _stageEvents = MutableStateFlow<Map<String, List<StageEvent>>>(emptyMap())
    val stageEvents: StateFlow<Map<String, List<StageEvent>>> = _stageEvents.asStateFlow()

    // Current FG selection. Null = nothing selected. Only settable from
    // CellVisualization's tap handler; cleared on every FG → BG
    // transition so re-entering FG starts fresh.
    private val _selectionKind =
        MutableStateFlow<ai.ciris.mobile.shared.ui.screens.graph.SelectionKind?>(null)
    val selectionKind: StateFlow<ai.ciris.mobile.shared.ui.screens.graph.SelectionKind?> =
        _selectionKind.asStateFlow()

    // Polled detail for whatever is currently selected. The poll job
    // swaps endpoints based on `_selectionKind` and writes the raw
    // JSON-parsed body here for the panel composable to render.
    private val _selectionDetail = MutableStateFlow<SelectionDetail?>(null)
    val selectionDetail: StateFlow<SelectionDetail?> = _selectionDetail.asStateFlow()

    /**
     * Horizontal position of the selected element as a 0..1 fraction of
     * the cell viz canvas width. The FG detail panel reads this to
     * anchor itself on the OPPOSITE side — tap on the right, panel
     * appears on the left (and vice-versa) so the user always sees what
     * they tapped.
     */
    private val _selectionAnchorX = MutableStateFlow(0.5f)
    val selectionAnchorX: StateFlow<Float> = _selectionAnchorX.asStateFlow()

    private var selectionPollJob: Job? = null

    private var capacityRefreshJob: Job? = null

    private var pollingJob: Job? = null
    private var statusJob: Job? = null
    private var healthJob: Job? = null
    private var trustPollJob: Job? = null  // Separate fast polling for trust when pending
    private var sseJob: Job? = null
    private var isFirstLoad = true
    private var authErrorCount = 0
    private var bubbleIdCounter = 0L
    private var sseReconnectDelay = SSE_RECONNECT_BASE_MS

    // SSE client for reasoning stream
    private val sseClient = ReasoningStreamClient(
        baseUrl = apiClient.baseUrl,
        getToken = { apiClient.getAccessToken() }
    )

    // Track if polling has been started (to avoid duplicate starts)
    private var pollingStarted = false

    init {
        logInfo("init", "InteractViewModel initialized (polling deferred until token available)")
        // NOTE: Don't auto-start polling here - wait for startPolling() to be called
        // after auth token is set. This avoids 401 errors during startup.
    }

    /**
     * Observe language changes from LocalizationManager and update pipeline labels.
     * Call this from CIRISApp after localization manager is initialized.
     *
     * This is necessary because the ViewModel is created during composition,
     * but LocalizationManager.initialize() runs in a LaunchedEffect AFTER composition.
     * So we need to update pipeline labels when:
     * 1. Localization finishes loading (strings become available)
     * 2. User changes language
     */
    fun observeLanguageChanges(localizationManager: LocalizationManager) {
        val method = "observeLanguageChanges"
        if (languageObserverJob != null) {
            logDebug(method, "Already observing language changes, skipping")
            return
        }
        logInfo(method, "Starting language observation for pipeline localization")

        languageObserverJob = viewModelScope.launch {
            // Combine isLoading, currentLanguage, and hasExplicitLanguageSelection
            // Only update on: initial load completing OR explicit user language change
            // Skip temporary rotation changes (login screen language cycling)
            kotlinx.coroutines.flow.combine(
                localizationManager.isLoading,
                localizationManager.currentLanguage,
                localizationManager.hasExplicitLanguageSelection
            ) { isLoading, language, isExplicit ->
                Triple(isLoading, language, isExplicit)
            }.collect { (isLoading, language, isExplicit) ->
                if (!isLoading && (isExplicit || language == "en")) {
                    // Update pipeline labels when: localization ready + (explicit selection OR English default)
                    logInfo(method, "Updating pipeline labels for language: $language (explicit=$isExplicit)")
                    _pipelineState.value = _pipelineState.value.withLocalizedLabels { key ->
                        LocalizationHelper.getString("mobile.$key")
                    }
                }
            }
        }
    }

    /**
     * Start all polling and SSE streams.
     * Call this after the auth token has been set on the API client.
     */
    fun startPolling() {
        if (pollingStarted) {
            logDebug("startPolling", "Polling already started, skipping")
            return
        }
        logInfo("startPolling", "Starting polling and SSE streams")
        pollingStarted = true
        startStatusPolling()
        startMessagePolling()
        startHealthPolling()
        startSseStream()
        startFileInjectionObserver()
        fetchWalletStatus()
        fetchAdapterOrbits()
        startCapacityRefresh()
    }

    /**
     * Periodic CIRIS capacity refresh. One immediate fetch then every 15 min
     * while the view is active. Backend caches against the enrichment cache
     * for the same TTL, so worst-case we hit lens once per 15-min window
     * per running occurrence. A failure is non-fatal — the cell viz falls
     * back to [CellVizState.DEFAULT] (neutral), never crashes.
     */
    private fun startCapacityRefresh() {
        if (capacityRefreshJob?.isActive == true) return
        capacityRefreshJob = viewModelScope.launch {
            while (isActive) {
                refreshCapacity()
                delay(15 * 60_000L)  // 15 min
            }
        }
    }

    /**
     * Compute and write a per-occurrence local capacity score into
     * [_cellVizState] using the health signals the client already polls.
     * Minimal, efficient, NOT a trust signal (trust = device attestation,
     * capacity = behavioural/coherence health). See §5a in
     * FSD/CELL_VIZ_REDESIGN.md and the Coherence Collapse Analysis paper.
     *
     * Called from:
     *  - status poll (services_online / services_total)
     *  - llmHealth update (provider healthy / not)
     *  - refreshCapacity (so fleet+local land together)
     *
     * No backend call. No new state fields beyond [CellVizState.localScore].
     */
    private fun recomputeLocalScore() {
        val lastStatus = _lastSystemStatus
        val serviceFrac = if (lastStatus != null && lastStatus.services_total > 0) {
            lastStatus.services_online.toFloat() / lastStatus.services_total.toFloat()
        } else null
        val llm = _llmHealth.value
        val llmFrac: Float? = when {
            llm.provider == "unknown" -> null
            llm.isHealthy -> 1f
            else -> 0f
        }
        val newLocal = ai.ciris.mobile.shared.ui.screens.graph
            .computeLocalScore(serviceFrac, llmFrac)
        val prev = _cellVizState.value
        if (prev.localScore != newLocal) {
            _cellVizState.value = prev.copy(localScore = newLocal).sanitized()
        }
    }

    // Most recent SystemStatus snapshot, kept as a field for the local-score
    // recomputation (the status poll otherwise consumes + discards it).
    // Stale reads across coroutines are benign: recomputeLocalScore is
    // called on every write to either input, so worst case we do one
    // extra recompute with the old value.
    private var _lastSystemStatus: ai.ciris.mobile.shared.models.SystemStatus? = null

    private suspend fun refreshCapacity() {
        val method = "refreshCapacity"
        try {
            val data = apiClient.getCapacity()
            // Prefer backend-authoritative local score when present (the
            // CCA proxy over runtime signals lives in my_data.py
            // _compute_local_capacity). Fall back to the client-side
            // computation (recomputeLocalScore) for backward compat
            // with older backends or pre-fetch state.
            val prevLocal = _cellVizState.value.localScore
            val local = data.localScore?.toFloat() ?: prevLocal
            _cellVizState.value = ai.ciris.mobile.shared.ui.screens.graph.CellVizState(
                c = data.c.toFloat(),
                iInt = data.iInt.toFloat(),
                r = data.r.toFloat(),
                iInc = data.iInc.toFloat(),
                s = data.s.toFloat(),
                compositeScore = data.compositeScore.toFloat(),
                fragilityIndex = data.fragilityIndex.toFloat(),
                category = data.category,
                isPreFetch = false,
                localScore = local,
            ).sanitized()
            logDebug(method, "Capacity: ${data.agentName} ${data.category} " +
                    "composite=${data.compositeScore} cached=${data.cached}")
        } catch (e: Exception) {
            // Expected in offline / dev / pre-auth states — don't spam WARN.
            logDebug(method, "Capacity fetch skipped: ${e.message}")
        }
    }

    /**
     * Fetch the current adapter list and project each into an [AdapterOrbit]
     * so the LiveGraphBackground can render them as satellites around the
     * cylinder. One-shot — adapters don't change often and the cost is one
     * API round-trip at screen mount.
     */
    private fun fetchAdapterOrbits() {
        val method = "fetchAdapterOrbits"
        viewModelScope.launch {
            try {
                val data = apiClient.listAdapters()
                _adapterOrbits.value = data.adapters.mapIndexed { index, a ->
                    orbitFor(
                        id = a.adapterId,
                        type = a.adapterType,
                        index = index,
                        isActive = a.isRunning
                    )
                }
                logInfo(method, "Loaded ${_adapterOrbits.value.size} adapter orbits")
            } catch (e: Exception) {
                logError(method, "Failed to fetch adapters for orbits: ${e.message}")
                // Leave list empty — LiveGraphBackground will just not draw satellites.
            }
        }
    }

    /**
     * Fetch wallet status from the wallet API endpoint.
     * Updates WalletStatus with balance, address, and initialization state.
     */
    private fun fetchWalletStatus() {
        val method = "fetchWalletStatus"
        viewModelScope.launch {
            try {
                logInfo(method, "Fetching wallet status from API")
                val walletResponse = apiClient.getWalletStatus()

                logInfo(method, "Wallet response: hasWallet=${walletResponse.hasWallet}, isInitializing=${walletResponse.isInitializing}, provider=${walletResponse.provider}")

                _walletStatus.value = WalletStatus(
                    isLoaded = true,
                    hasWallet = walletResponse.hasWallet,
                    balance = walletResponse.balance,
                    currency = walletResponse.currency,
                    provider = walletResponse.provider,
                    network = walletResponse.network,
                    address = walletResponse.address,
                    isReceiveOnly = walletResponse.isReceiveOnly,
                    isInitializing = walletResponse.isInitializing
                )
            } catch (e: Exception) {
                logWarn(method, "Failed to fetch wallet status: ${e.message}")
                _walletStatus.value = WalletStatus(isLoaded = true, hasWallet = false)
            }
        }
    }

    fun onInputTextChanged(text: String) {
        _inputText.value = text
    }

    /**
     * Add a file attachment to the current message.
     * Validates size and count limits before adding.
     */
    fun addAttachment(file: PickedFile) {
        val method = "addAttachment"
        val current = _attachedFiles.value
        if (current.size >= PickedFile.MAX_ATTACHMENTS) {
            logWarn(method, "Max attachments (${PickedFile.MAX_ATTACHMENTS}) reached, ignoring ${file.name}")
            return
        }
        if (file.sizeBytes > PickedFile.MAX_FILE_SIZE_BYTES) {
            logWarn(method, "File ${file.name} exceeds max size (${file.sizeBytes} > ${PickedFile.MAX_FILE_SIZE_BYTES})")
            return
        }
        logInfo(method, "Adding attachment: ${file.name} (${file.mediaType}, ${file.sizeBytes} bytes)")
        _attachedFiles.value = current + file
    }

    fun removeAttachment(index: Int) {
        val current = _attachedFiles.value
        if (index in current.indices) {
            logInfo("removeAttachment", "Removing attachment at index $index: ${current[index].name}")
            _attachedFiles.value = current.filterIndexed { i, _ -> i != index }
        }
    }

    fun clearAttachments() {
        _attachedFiles.value = emptyList()
    }

    /**
     * Observe test automation file injection requests.
     * When the test server injects a file, add it as an attachment.
     */
    private fun startFileInjectionObserver() {
        if (!TestAutomation.isEnabled()) return
        val method = "startFileInjectionObserver"
        logInfo(method, "Starting file injection observer for test automation")

        viewModelScope.launch {
            TestAutomation.fileInjectionRequests.collect { file ->
                if (file != null) {
                    logInfo(method, "Test automation injected file: ${file.name} (${file.mediaType})")
                    addAttachment(file)
                    TestAutomation.clearFileInjectionRequest()
                }
            }
        }
    }

    /**
     * Send message to agent
     */
    fun sendMessage() {
        val method = "sendMessage"
        val text = _inputText.value.trim()
        val files = _attachedFiles.value

        if (text.isEmpty() && files.isEmpty()) {
            logDebug(method, "Ignoring empty message with no attachments")
            return
        }
        if (_isSending.value) {
            logDebug(method, "Already sending, ignoring")
            return
        }

        // Pre-flight credit check - only when using CIRIS proxy
        val currentCredits = _creditStatus.value
        if (_llmHealth.value.isCirisProxy && currentCredits.isLoaded && !currentCredits.canSendMessage) {
            logWarn(method, "No credits available - blocking send")
            val errorMessage = ChatMessage(
                id = generateMessageId(),
                text = LocalizationHelper.getString("mobile.credits_no_credits"),
                type = MessageType.SYSTEM,
                timestamp = Clock.System.now()
            )
            _messages.value = (_messages.value + errorMessage).takeLast(50)
            return
        }

        logInfo(method, "Sending message: '${text.take(50)}...' with ${files.size} attachments")

        viewModelScope.launch {
            try {
                _isSending.value = true
                _processingStatus.value = LocalizationHelper.getString("mobile.processing_sending")
                _inputText.value = ""
                _attachedFiles.value = emptyList()

                // Build attachment payloads
                val imagePayloads = files.filter { it.isImage }.map { file ->
                    ImagePayload(
                        data = file.dataBase64,
                        mediaType = file.mediaType,
                        filename = file.name
                    )
                }.ifEmpty { null }

                val documentPayloads = files.filter { it.isDocument }.map { file ->
                    DocumentPayload(
                        data = file.dataBase64,
                        mediaType = file.mediaType,
                        filename = file.name
                    )
                }.ifEmpty { null }

                // Add user message to chat immediately
                val displayText = if (text.isNotEmpty()) text else "Sent ${files.size} file${if (files.size > 1) "s" else ""}"
                val userMessage = ChatMessage(
                    id = generateMessageId(),
                    text = displayText,
                    type = MessageType.USER,
                    timestamp = Clock.System.now(),
                    attachmentCount = files.size,
                    attachmentNames = files.map { it.name },
                    hasImageAttachments = files.any { it.isImage },
                    hasDocumentAttachments = files.any { it.isDocument }
                )
                _messages.value = (_messages.value + userMessage).takeLast(50)

                logDebug(method, "Calling apiClient.sendMessage with ${imagePayloads?.size ?: 0} images, ${documentPayloads?.size ?: 0} documents")
                val response = apiClient.sendMessage(
                    message = if (text.isNotEmpty()) text else "Please review the attached file(s).",
                    images = imagePayloads,
                    documents = documentPayloads
                )
                logInfo(method, "Message sent successfully: messageId=${response.message_id}")

                // Add agent response to chat
                val agentResponse = response.response
                if (!agentResponse.isNullOrBlank()) {
                    logInfo(method, "Agent response: '${agentResponse.take(100)}...'")
                    val agentMessage = ChatMessage(
                        id = response.message_id,
                        text = agentResponse,
                        type = MessageType.AGENT,
                        timestamp = Clock.System.now(),
                        reasoning = response.reasoning
                    )
                    _messages.value = (_messages.value + agentMessage).takeLast(50)
                    _processingStatus.value = ""
                } else {
                    logWarn(method, "Empty response from agent")
                    _processingStatus.value = LocalizationHelper.getString("mobile.processing_waiting_response")
                }

            } catch (e: Exception) {
                logError(method, "Failed to send message: ${e::class.simpleName}: ${e.message}")
                logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")

                // Check if this is a timeout error - suppress it since responses come via SSE
                val errorMsg = e.message ?: ""
                val isTimeoutError = errorMsg.contains("timeout", ignoreCase = true) ||
                                     errorMsg.contains("30000", ignoreCase = true) ||
                                     e::class.simpleName?.contains("Timeout", ignoreCase = true) == true

                if (isTimeoutError) {
                    // Timeout is expected for async processing - message will arrive via SSE
                    logInfo(method, "Timeout during send - response will arrive via SSE")
                    _processingStatus.value = LocalizationHelper.getString("mobile.processing_generic")
                } else {
                    // Determine user-friendly error message
                    val userFriendlyMessage = getUserFriendlyErrorMessage(errorMsg)
                    val errorMessage = ChatMessage(
                        id = generateMessageId(),
                        text = userFriendlyMessage,
                        type = MessageType.SYSTEM,
                        timestamp = Clock.System.now()
                    )
                    _messages.value = (_messages.value + errorMessage).takeLast(50)
                    _processingStatus.value = ""

                    // If it's a credit error, refresh credit status
                    if (errorMsg.contains("credit", ignoreCase = true) ||
                        errorMsg.contains("insufficient", ignoreCase = true) ||
                        errorMsg.contains("payment", ignoreCase = true)) {
                        viewModelScope.launch {
                            fetchHealthData()
                        }
                    }
                }
            } finally {
                _isSending.value = false
            }
        }
    }

    /**
     * Initiate shutdown
     */
    fun shutdown(emergency: Boolean = false) {
        val method = "shutdown"
        logInfo(method, "Initiating shutdown: emergency=$emergency")

        viewModelScope.launch {
            try {
                if (emergency) {
                    logWarn(method, "Emergency shutdown triggered")
                    apiClient.emergencyShutdown()
                } else {
                    logInfo(method, "Graceful shutdown triggered")
                    apiClient.initiateShutdown()
                }

                val statusMsg = if (emergency) "Emergency shutdown initiated" else "Shutdown initiated"
                logInfo(method, statusMsg)
                _processingStatus.value = statusMsg

                delay(3000)
                _processingStatus.value = ""

            } catch (e: Exception) {
                logError(method, "Shutdown failed: ${e::class.simpleName}: ${e.message}")
                _processingStatus.value = "Shutdown failed: ${e.message}"
                delay(3000)
                _processingStatus.value = ""
            }
        }
    }

    /**
     * Poll for agent status
     * Fast polls (200ms) until cognitive_state is available, then switches to normal interval
     */
    private fun startStatusPolling() {
        val method = "startStatusPolling"
        logInfo(method, "Starting status polling (fast until agent ready)")

        statusJob = viewModelScope.launch {
            var pollCount = 0
            var agentReady = false  // True once we get a real cognitive_state
            val FAST_POLL_MS = 200L

            while (isActive) {
                pollCount++
                try {
                    val status = apiClient.getSystemStatus()
                    _lastSystemStatus = status
                    recomputeLocalScore()
                    val wasConnected = _isConnected.value
                    _isConnected.value = status.status == "healthy"

                    // Check if we got a real cognitive state
                    val cognitiveState = status.cognitive_state
                    if (cognitiveState != null) {
                        _agentStatus.value = cognitiveState.uppercase()
                        if (!agentReady) {
                            agentReady = true
                            logInfo(method, "Agent ready with state: ${_agentStatus.value}")
                        }
                    } else {
                        _agentStatus.value = LocalizationHelper.getString("mobile.processing_starting")
                    }

                    if (_isConnected.value != wasConnected) {
                        logInfo(method, "Connection state changed: ${wasConnected} -> ${_isConnected.value}")
                    }
                    if (pollCount % 10 == 0) {
                        logDebug(method, "Status poll #$pollCount: connected=${_isConnected.value}, state=${_agentStatus.value}")
                    }
                } catch (e: Exception) {
                    if (_isConnected.value) {
                        logError(method, "Status poll failed: ${e::class.simpleName}: ${e.message}")
                    }
                    _isConnected.value = false
                    _agentStatus.value = "Disconnected"
                }

                // Fast poll until agent ready, then normal interval
                delay(if (agentReady) STATUS_POLL_INTERVAL_MS else FAST_POLL_MS)
            }
        }
    }

    /**
     * Poll for LLM health, credits, and trust status (less frequent)
     * Fast polls (2s) until LLM health is loaded, then switches to normal interval.
     * Note: Using 2s to avoid rate limiting (429) from the /setup/config endpoint.
     */
    private fun startHealthPolling() {
        val method = "startHealthPolling"
        logInfo(method, "Starting health polling (fast until LLM ready)")

        healthJob = viewModelScope.launch {
            var llmReady = false  // True once LLM health is loaded successfully
            val FAST_HEALTH_POLL_MS = 2000L  // 2 seconds - avoid rate limiting

            while (isActive) {
                fetchHealthData()

                // Check if LLM health was loaded (provider is not "unknown" anymore)
                if (!llmReady && _llmHealth.value.provider != "unknown") {
                    llmReady = true
                    logInfo(method, "LLM health ready: provider=${_llmHealth.value.provider}")
                }

                // Fast poll until LLM ready, then normal interval
                delay(if (llmReady) HEALTH_POLL_INTERVAL_MS else FAST_HEALTH_POLL_MS)
            }
        }

        // Start separate fast trust polling for when Play Integrity is pending
        startTrustPendingPolling()
    }

    /**
     * Fast polling for trust status when Play Integrity is pending.
     * Polls every 5 seconds until Play Integrity completes, then stops.
     * Also triggers Play Integrity automatically if levelPending=true.
     */
    private fun startTrustPendingPolling() {
        val method = "startTrustPendingPolling"
        logInfo(method, "Starting trust pending polling (interval=${TRUST_PENDING_POLL_INTERVAL_MS}ms)")

        trustPollJob = viewModelScope.launch {
            // Wait a bit for initial health fetch to complete
            delay(2000)

            while (isActive) {
                // Fetch fresh trust status
                fetchTrustStatus()
                val currentTrust = _trustStatus.value

                // If levelPending is true, trigger Play Integrity if not already triggered
                if (currentTrust.levelPending) {
                    if (!deviceAttestationTriggered && deviceAttestationCallback != null) {
                        logInfo(method, "Level pending=true, triggering device attestation automatically...")
                        deviceAttestationTriggered = true
                        deviceAttestationCallback?.onDeviceAttestationRequested { result ->
                            logInfo(method, "Device attestation completed: $result")
                            // After device attestation succeeds, refresh trust status
                            // so the backend's re-attestation (with device attestation included)
                            // is picked up by the UI
                            viewModelScope.launch {
                                delay(2000) // Give backend time to re-attest
                                fetchTrustStatus()
                                logInfo(method, "Trust status refreshed after device attestation")
                            }
                        }
                    }
                    logDebug(method, "Level pending=true (level=${currentTrust.maxLevel}), continuing fast poll...")
                    delay(TRUST_PENDING_POLL_INTERVAL_MS)
                } else {
                    // Play Integrity is complete, stop fast polling
                    logInfo(method, "Level pending=false (level=${currentTrust.maxLevel}/5), stopping fast poll")
                    break
                }
            }
        }
    }

    /**
     * Fetch just trust status (for fast polling when pending)
     */
    private suspend fun fetchTrustStatus() {
        val method = "fetchTrustStatus"
        try {
            val verifyStatus = apiClient.getVerifyStatus()
            val previousLevel = _trustStatus.value.maxLevel
            val previousPending = _trustStatus.value.levelPending
            _trustStatus.value = TrustStatus(
                maxLevel = verifyStatus.maxLevel,
                isLoaded = verifyStatus.loaded,
                keyStatus = verifyStatus.keyStatus,
                attestationStatus = verifyStatus.attestationStatus,
                levelPending = verifyStatus.levelPending
            )
            if (verifyStatus.maxLevel != previousLevel) {
                logInfo(method, "Trust level changed: $previousLevel -> ${verifyStatus.maxLevel}")
            }
            if (verifyStatus.levelPending != previousPending) {
                logInfo(method, "Level pending changed: $previousPending -> ${verifyStatus.levelPending}")
            }
        } catch (e: Exception) {
            logWarn(method, "Failed to fetch trust status: ${e.message}")
        }
    }

    /**
     * Fetch LLM health, credits, and trust status
     */
    private suspend fun fetchHealthData() {
        val method = "fetchHealthData"
        try {
            // Fetch LLM config for health status
            // First try API, fall back to local .env file if API fails (e.g., 401)
            var configLoaded = false
            try {
                val config = apiClient.getLlmConfig()
                _llmHealth.value = LlmHealthStatus(
                    provider = config.provider,
                    isHealthy = config.apiKeySet || config.isCirisProxy,
                    model = config.model,
                    isCirisProxy = config.isCirisProxy
                )
                recomputeLocalScore()
                logDebug(method, "LLM health from API: provider=${config.provider}, isCirisProxy=${config.isCirisProxy}")
                configLoaded = true

                // Only fetch credits if using CIRIS proxy
                if (config.isCirisProxy) {
                    try {
                        val credits = apiClient.getCredits()
                        _creditStatus.value = CreditStatus(
                            hasCredit = credits.hasCredit,
                            creditsRemaining = credits.creditsRemaining,
                            freeUsesRemaining = credits.freeUsesRemaining,
                            dailyFreeUsesRemaining = credits.dailyFreeUsesRemaining ?: 0,
                            planName = credits.planName,
                            isLoaded = true
                        )
                        logDebug(method, "Credits: paid=${credits.creditsRemaining}, free=${credits.freeUsesRemaining}, daily=${credits.dailyFreeUsesRemaining}")
                    } catch (e: Exception) {
                        logWarn(method, "Failed to fetch credits: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                logWarn(method, "Failed to fetch LLM config from API: ${e.message}")
            }

            // Fallback: Read from local .env file if API failed
            if (!configLoaded && _llmHealth.value.provider == "unknown") {
                try {
                    val envConfig = createEnvFileUpdater().readLlmConfig()
                    if (envConfig != null) {
                        _llmHealth.value = LlmHealthStatus(
                            provider = envConfig.provider,
                            isHealthy = envConfig.apiKeySet || envConfig.isCirisProxy,
                            model = envConfig.model ?: "unknown",
                            isCirisProxy = envConfig.isCirisProxy
                        )
                        logInfo(method, "LLM health from .env fallback: provider=${envConfig.provider}, isCirisProxy=${envConfig.isCirisProxy}")
                    }
                } catch (e: Exception) {
                    logWarn(method, "Failed to read LLM config from .env: ${e.message}")
                }
            }

            // Fetch trust status (uses cached attestation from auth service)
            try {
                val verifyStatus = apiClient.getVerifyStatus()
                _trustStatus.value = TrustStatus(
                    maxLevel = verifyStatus.maxLevel,  // Use backend's authoritative level
                    isLoaded = verifyStatus.loaded,
                    keyStatus = verifyStatus.keyStatus,
                    attestationStatus = verifyStatus.attestationStatus,
                    levelPending = verifyStatus.levelPending
                )
                logDebug(method, "Trust: level=${verifyStatus.maxLevel}/5, keyStatus=${verifyStatus.keyStatus}, pending=${verifyStatus.levelPending}")
            } catch (e: Exception) {
                logWarn(method, "Failed to fetch trust status: ${e.message}")
            }

            // Fetch pending deferrals count for WA banner
            try {
                val waStatus = apiClient.getWAStatus()
                val prevCount = _pendingDeferrals.value
                _pendingDeferrals.value = waStatus.pendingDeferrals
                if (waStatus.pendingDeferrals != prevCount && waStatus.pendingDeferrals > 0) {
                    logInfo(method, "Pending deferrals: ${waStatus.pendingDeferrals}")
                }
            } catch (e: Exception) {
                logDebug(method, "Failed to fetch WA status: ${e.message}")
            }

            // Fetch system warnings (e.g., no LLM provider)
            try {
                val systemHealth = apiClient.getSystemHealth()
                _systemWarnings.value = systemHealth.warnings
                if (systemHealth.warnings.isNotEmpty()) {
                    logInfo(method, "System warnings: ${systemHealth.warnings.map { it.code }}")
                }
            } catch (e: Exception) {
                logDebug(method, "Failed to fetch system health: ${e.message}")
            }
        } catch (e: Exception) {
            logWarn(method, "Health polling error: ${e.message}")
        }
    }

    /**
     * Refresh trust status (called when opening trust page)
     * Also restarts fast polling if Play Integrity is still pending.
     */
    fun refreshTrustStatus() {
        viewModelScope.launch {
            try {
                val verifyStatus = apiClient.getVerifyStatus()
                val previousLevel = _trustStatus.value.maxLevel
                _trustStatus.value = TrustStatus(
                    maxLevel = verifyStatus.maxLevel,  // Use backend's authoritative level
                    isLoaded = verifyStatus.loaded,
                    keyStatus = verifyStatus.keyStatus,
                    attestationStatus = verifyStatus.attestationStatus,
                    levelPending = verifyStatus.levelPending
                )

                // Log level change and refresh wallet status (badge color depends on trust level)
                if (verifyStatus.maxLevel != previousLevel) {
                    logInfo("refreshTrustStatus", "Trust level changed: $previousLevel -> ${verifyStatus.maxLevel}")
                    // Wallet spending authority changes with trust level - refresh to update badge color
                    fetchWalletStatus()
                }

                // Restart fast polling if still pending and job isn't active
                if (verifyStatus.levelPending) {
                    if (trustPollJob?.isActive != true) {
                        logInfo("refreshTrustStatus", "Restarting fast trust polling (levelPending=true)")
                        startTrustPendingPolling()
                    }
                }
            } catch (e: Exception) {
                logWarn("refreshTrustStatus", "Failed: ${e.message}")
            }
        }
    }

    /**
     * Poll for message history and audit actions
     */
    private fun startMessagePolling() {
        val method = "startMessagePolling"
        logInfo(method, "Starting message polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    fetchHistory()
                    // Also fetch audit actions to show in timeline
                    fetchAuditActions()
                } catch (e: Exception) {
                    logError(method, "Message polling failed: ${e::class.simpleName}: ${e.message}")
                } finally {
                    if (isFirstLoad) {
                        logInfo(method, "First load complete")
                        _isLoading.value = false
                        isFirstLoad = false
                    }
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Fetch message history from API
     */
    fun clearAuthError() {
        _authError.value = null
        authErrorCount = 0
    }

    private suspend fun fetchHistory() {
        val method = "fetchHistory"
        try {
            val messages = apiClient.getMessages(limit = 50)
            // Success - clear any auth error
            if (_authError.value != null) {
                logInfo(method, "Auth restored, clearing error")
                _authError.value = null
                authErrorCount = 0
            }
            if (messages.isNotEmpty()) {
                logDebug(method, "Fetched ${messages.size} messages from API")
                // Deduplicate by ID (API might return same message from multiple channels)
                val deduplicatedMessages = messages
                    .distinctBy { it.id }
                    .sortedBy { it.timestamp }
                    .takeLast(50)

                // Check if there are new messages
                val existingIds = _messages.value.map { it.id }.toSet()
                val newMessages = deduplicatedMessages.filter { it.id !in existingIds }
                if (newMessages.isNotEmpty()) {
                    // Merge with existing messages to preserve action entries
                    // Use content + timestamp window deduplication for USER messages
                    // (local ID vs server ID differ, but we don't want to collapse
                    // legitimately repeated messages like "ok" sent at different times)
                    val previousSize = _messages.value.size
                    val allMessages = (_messages.value + deduplicatedMessages)
                        .distinctBy { msg ->
                            when (msg.type) {
                                MessageType.USER -> {
                                    // Dedupe USER messages by content + timestamp window (30 sec)
                                    // Wide window because optimistic local add and server fetch
                                    // can have different timestamps
                                    val timestampWindow = msg.timestamp.toEpochMilliseconds() / 30000
                                    "USER:${msg.text}:$timestampWindow"
                                }
                                MessageType.AGENT -> {
                                    // Dedupe AGENT messages by content + timestamp window (30 sec)
                                    val timestampWindow = msg.timestamp.toEpochMilliseconds() / 30000
                                    "AGENT:${msg.text}:$timestampWindow"
                                }
                                else -> msg.id // ACTION messages use ID
                            }
                        }
                        .sortedBy { it.timestamp }
                        .takeLast(50)
                    if (allMessages.size > previousSize) {
                        logInfo(method, "Added ${allMessages.size - previousSize} new messages to chat")
                    }
                    _messages.value = allMessages
                }
            }
        } catch (e: Exception) {
            // Check for auth errors (401)
            val errorMessage = e.message ?: ""
            val isAuthError = errorMessage.contains("401") ||
                              errorMessage.contains("Unauthorized", ignoreCase = true) ||
                              errorMessage.contains("authentication", ignoreCase = true)

            if (isAuthError) {
                authErrorCount++
                logWarn(method, "Auth error #$authErrorCount: $errorMessage")
                // On first auth error, trigger automatic token refresh via TokenManager
                if (authErrorCount == 1) {
                    logInfo(method, "Triggering automatic token refresh via TokenManager")
                    TokenManager.shared?.on401Error()
                }
                // Only show error after 3 consecutive failures to avoid flashing during token refresh
                if (authErrorCount >= 3 && _authError.value == null) {
                    logError(method, "Persistent auth error (3+ failures) - showing UI notification")
                    _authError.value = "Session expired. Please sign in again."
                }
            } else {
                logWarn(method, "Non-auth error: ${e::class.simpleName}: $errorMessage")
            }

            // Log on first load
            if (isFirstLoad) {
                logWarn(method, "Failed to fetch history on first load: ${e.message}")
            }
        }
    }

    // Track action IDs we've already added to avoid duplicates
    private val addedActionIds = mutableSetOf<String>()

    /**
     * Fetch recent audit actions and add them to the chat timeline.
     * Called on load and during polling to keep timeline up to date.
     */
    private suspend fun fetchAuditActions() {
        val method = "fetchAuditActions"

        try {
            // Fetch recent audit entries (all types, we'll filter by action types)
            val entries = apiClient.getAuditEntries(
                limit = 50,
                offset = 0
            )

            if (entries.entries.isEmpty()) {
                return
            }

            val newActionMessages = mutableListOf<ChatMessage>()

            // Get current message IDs to check if actions need re-adding after history refresh
            val currentMessageIds = _messages.value.map { it.id }.toSet()

            logDebug(method, "Processing ${entries.entries.size} entries, currentMessageIds=${currentMessageIds.size}")
            for (entry in entries.entries) {
                val actionMessageId = "action_${entry.id}"

                // Skip if already in current messages (already displayed)
                if (actionMessageId in currentMessageIds) {
                    continue
                }

                // Check if this is one of the 10 action types
                val actionType = ActionType.fromAuditEventType(entry.action)
                if (actionType == null) {
                    continue
                }

                // Skip SPEAK and TASK_COMPLETE - not interesting for timeline display
                // SPEAK is already shown as a chat message, TASK_COMPLETE is just a marker
                if (actionType == ActionType.SPEAK || actionType == ActionType.TASK_COMPLETE) {
                    continue
                }

                logDebug(method, "ADD ${entry.id}: ${actionType.name} from '${entry.action}'")


                // Track that we've processed this entry (for SSE deduplication)
                addedActionIds.add(entry.id)

                // Extract details from metadata
                val metadata = entry.context?.metadata
                val outcome = entry.context?.outcome
                    ?: metadata?.get("outcome")?.jsonPrimitiveContent()
                    ?: "success"
                val description = entry.context?.description
                    ?: metadata?.get("description")?.jsonPrimitiveContent()

                // Build action-specific details
                val actionDetails = buildActionDetails(actionType, outcome, entry.id, description, metadata)

                // Parse timestamp
                val timestamp = try {
                    kotlinx.datetime.Instant.parse(entry.timestamp)
                } catch (e: Exception) {
                    Clock.System.now()
                }

                val actionMessage = ChatMessage(
                    id = "action_${entry.id}",
                    text = actionType.displayName,
                    type = MessageType.ACTION,
                    timestamp = timestamp,
                    actionDetails = actionDetails
                )

                newActionMessages.add(actionMessage)
            }

            if (newActionMessages.isNotEmpty()) {
                logInfo(method, "Adding ${newActionMessages.size} action entries to timeline")

                // Merge with existing messages, sort by timestamp, keep last 50
                val allMessages = (_messages.value + newActionMessages)
                    .distinctBy { it.id }
                    .sortedBy { it.timestamp }
                    .takeLast(50)

                _messages.value = allMessages
            }

        } catch (e: Exception) {
            // Don't log errors on every poll, only on first failure
            if (isFirstLoad) {
                logWarn(method, "Failed to fetch audit actions: ${e.message}")
            }
        }
    }

    /**
     * Build ActionDetails from audit entry metadata
     */
    private fun buildActionDetails(
        actionType: ActionType,
        outcome: String,
        auditEntryId: String,
        description: String?,
        metadata: kotlinx.serialization.json.JsonObject?
    ): ActionDetails {
        return when (actionType) {
            ActionType.TOOL -> {
                val toolName = metadata?.get("tool_name")?.jsonPrimitiveContent() ?: "Unknown Tool"
                val toolAdapter = metadata?.get("tool_adapter")?.jsonPrimitiveContent() ?: "unknown"
                val toolParameters = parseToolParameters(metadata?.get("tool_parameters"))
                val toolResult = metadata?.get("tool_result")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    toolName = toolName,
                    toolAdapter = toolAdapter,
                    toolParameters = toolParameters,
                    toolResult = toolResult
                )
            }
            ActionType.MEMORIZE, ActionType.RECALL, ActionType.FORGET -> {
                val memoryKey = metadata?.get("memory_key")?.jsonPrimitiveContent()
                    ?: metadata?.get("key")?.jsonPrimitiveContent()
                val memoryContent = metadata?.get("content")?.jsonPrimitiveContent()
                    ?: metadata?.get("value")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    memoryKey = memoryKey,
                    memoryContent = memoryContent
                )
            }
            ActionType.DEFER -> {
                val deferReason = metadata?.get("reason")?.jsonPrimitiveContent()
                    ?: metadata?.get("defer_reason")?.jsonPrimitiveContent()
                val deferTarget = metadata?.get("target")?.jsonPrimitiveContent()
                    ?: metadata?.get("wise_authority")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    deferReason = deferReason,
                    deferTarget = deferTarget
                )
            }
            ActionType.REJECT -> {
                val rejectReason = metadata?.get("reason")?.jsonPrimitiveContent()
                    ?: metadata?.get("reject_reason")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    rejectReason = rejectReason
                )
            }
            ActionType.PONDER -> {
                val ponderTopic = metadata?.get("topic")?.jsonPrimitiveContent()
                    ?: metadata?.get("ponder_topic")?.jsonPrimitiveContent()

                // Parse ponder_questions - check direct metadata first, then nested in parameters
                val ponderQuestions = parsePonderQuestionsDirect(metadata?.get("ponder_questions"))
                    .ifEmpty { parsePonderQuestions(metadata?.get("parameters")) }

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    ponderTopic = ponderTopic,
                    ponderQuestions = ponderQuestions
                )
            }
            else -> {
                // SPEAK, OBSERVE, TASK_COMPLETE - just basic details
                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description
                )
            }
        }
    }

    /**
     * Trigger an immediate refresh of audit actions when an SSE emoji event is received.
     * This provides live updates to the timeline when actions occur.
     */
    private fun fetchAndAddLatestAction(actionType: ActionType) {
        val method = "fetchAndAddLatestAction"
        logDebug(method, "SSE triggered refresh for ${actionType.name}")

        // Trigger immediate fetch of audit actions
        viewModelScope.launch {
            // Small delay to allow audit entry to be written
            delay(500)
            fetchAuditActions()
        }
    }

    /**
     * Helper to extract string content from JsonElement
     */
    private fun kotlinx.serialization.json.JsonElement?.jsonPrimitiveContent(): String? {
        return when (this) {
            is kotlinx.serialization.json.JsonPrimitive -> this.content
            else -> this?.toString()
        }
    }

    /**
     * Parse tool parameters from a JSON element (may be string or object)
     */
    private fun parseToolParameters(element: kotlinx.serialization.json.JsonElement?): Map<String, String> {
        if (element == null) return emptyMap()

        val parameters = mutableMapOf<String, String>()
        try {
            val paramsContent = when (element) {
                is kotlinx.serialization.json.JsonPrimitive -> element.content
                is kotlinx.serialization.json.JsonObject -> {
                    // Already an object, extract directly
                    element.forEach { (key, value) ->
                        parameters[key] = value.jsonPrimitiveContent() ?: value.toString()
                    }
                    return parameters
                }
                else -> element.toString()
            }

            // Parse JSON string - handle double-quoted strings like "{...}"
            var jsonToParse = paramsContent.trim()
            // Strip outer quotes if present (double-encoded JSON)
            if (jsonToParse.startsWith("\"") && jsonToParse.endsWith("\"")) {
                jsonToParse = jsonToParse.drop(1).dropLast(1)
            }
            // Unescape escaped quotes and backslashes
            jsonToParse = jsonToParse
                .replace("\\\"", "\"")
                .replace("\\\\", "\\")

            if (jsonToParse.startsWith("{")) {
                val parsed = kotlinx.serialization.json.Json.parseToJsonElement(jsonToParse)
                if (parsed is kotlinx.serialization.json.JsonObject) {
                    parsed.forEach { (key, value) ->
                        parameters[key] = when (value) {
                            is kotlinx.serialization.json.JsonPrimitive -> value.content
                            else -> value.toString()
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // Ignore parse errors - return empty parameters
        }
        return parameters
    }

    /**
     * Parse ponder questions directly from metadata (when merged from graph entries).
     * Can be a JSON array, a JSON-encoded string array, or a double-encoded string.
     */
    private fun parsePonderQuestionsDirect(questionsElement: kotlinx.serialization.json.JsonElement?): List<String> {
        if (questionsElement == null) return emptyList()

        try {
            // Case 1: Already a JSON array
            if (questionsElement is kotlinx.serialization.json.JsonArray) {
                return questionsElement.mapNotNull { element ->
                    when (element) {
                        is kotlinx.serialization.json.JsonPrimitive -> element.content
                        else -> null
                    }
                }
            }

            // Case 2: JSON-encoded string - may be single or double encoded
            var questionsStr = questionsElement.jsonPrimitiveContent() ?: return emptyList()

            // Handle double-encoding: if it's a JSON string containing a JSON array string
            // e.g., "\"[\\\"Q1\\\", \\\"Q2\\\"]\"" - parse first to get the inner string
            if (questionsStr.startsWith("\"") || questionsStr.startsWith("\\\"")) {
                try {
                    val unescaped = kotlinx.serialization.json.Json.parseToJsonElement(questionsStr)
                    if (unescaped is kotlinx.serialization.json.JsonPrimitive) {
                        questionsStr = unescaped.content
                    }
                } catch (_: Exception) {
                    // First unescape failed, continue with original string
                }
            }

            // Now parse the array
            val questionsJson = kotlinx.serialization.json.Json.parseToJsonElement(questionsStr)
            if (questionsJson is kotlinx.serialization.json.JsonArray) {
                return questionsJson.mapNotNull { element ->
                    when (element) {
                        is kotlinx.serialization.json.JsonPrimitive -> element.content
                        else -> null
                    }
                }
            }
        } catch (e: Exception) {
            logInfo("parsePonderQuestionsDirect", "Failed to parse: ${e.message}")
        }
        return emptyList()
    }

    /**
     * Parse ponder questions from double-encoded parameters JSON.
     * The parameters field contains a JSON string like:
     * "{\"ponder_questions\": \"[\\\"Question 1\\\", \\\"Question 2\\\"]\", ...}"
     */
    private fun parsePonderQuestions(parametersElement: kotlinx.serialization.json.JsonElement?): List<String> {
        if (parametersElement == null) return emptyList()

        try {
            // First, get the parameters string
            val parametersStr = parametersElement.jsonPrimitiveContent() ?: return emptyList()

            // Parse the outer JSON
            val paramsJson = kotlinx.serialization.json.Json.parseToJsonElement(parametersStr)
            if (paramsJson !is kotlinx.serialization.json.JsonObject) return emptyList()

            // Get the ponder_questions field (which is also a JSON-encoded string)
            val questionsElement = paramsJson["ponder_questions"] ?: return emptyList()
            val questionsStr = when (questionsElement) {
                is kotlinx.serialization.json.JsonPrimitive -> questionsElement.content
                else -> questionsElement.toString()
            }

            // Parse the questions array
            val questionsJson = kotlinx.serialization.json.Json.parseToJsonElement(questionsStr)
            if (questionsJson !is kotlinx.serialization.json.JsonArray) return emptyList()

            return questionsJson.mapNotNull { element ->
                when (element) {
                    is kotlinx.serialization.json.JsonPrimitive -> element.content
                    else -> null
                }
            }
        } catch (e: Exception) {
            logDebug("parsePonderQuestions", "Failed to parse: ${e.message}")
            return emptyList()
        }
    }

    /**
     * Update processing status
     */
    fun updateProcessingStatus(eventType: String, action: String? = null) {
        val method = "updateProcessingStatus"
        logDebug(method, "Event: $eventType, action: $action")

        val statusText = when (eventType) {
            "thought_start" -> LocalizationHelper.getString("mobile.processing_thinking")
            "snapshot_and_context" -> LocalizationHelper.getString("mobile.processing_context")
            "dma_results" -> LocalizationHelper.getString("mobile.processing_evaluating")
            "idma_result" -> LocalizationHelper.getString("mobile.processing_idma")
            "aspdma_result" -> LocalizationHelper.getString("mobile.processing_selecting", mapOf("action" to (action ?: "...")))
            "tsaspdma_result" -> LocalizationHelper.getString("mobile.processing_tsaspdma")
            "conscience_result" -> LocalizationHelper.getString("mobile.processing_ethics")
            "action_result" -> {
                when {
                    action?.contains("speak") == true -> LocalizationHelper.getString("mobile.processing_speaking")
                    action?.contains("task_complete") == true -> LocalizationHelper.getString("status.completed")
                    action?.contains("memorize") == true -> LocalizationHelper.getString("mobile.processing_memorizing")
                    action?.contains("recall") == true -> LocalizationHelper.getString("mobile.processing_recalling")
                    action?.contains("tool") == true -> LocalizationHelper.getString("mobile.processing_tool")
                    action?.contains("ponder") == true -> LocalizationHelper.getString("mobile.processing_pondering")
                    action?.contains("defer") == true -> LocalizationHelper.getString("mobile.interact_action_defer")
                    else -> "Executing: ${action ?: "action"}"
                }
            }
            "idle" -> LocalizationHelper.getString("mobile.interact_legend_idle")
            else -> eventType.replace("_", " ").replaceFirstChar { it.uppercase() }
        }

        _processingStatus.value = statusText

        if (eventType == "action_result" &&
            (action?.contains("task_complete") == true || action?.contains("task_reject") == true)) {
            viewModelScope.launch {
                delay(3000)
                if (_processingStatus.value == statusText) {
                    _processingStatus.value = ""
                }
            }
        }
    }

    private fun generateMessageId(): String {
        return "msg_${Clock.System.now().toEpochMilliseconds()}"
    }

    /**
     * Convert raw error message to user-friendly localized message.
     * Avoids showing raw JSON or technical details to users.
     */
    private fun getUserFriendlyErrorMessage(rawError: String): String {
        val method = "getUserFriendlyErrorMessage"
        val lowerError = rawError.lowercase()

        return when {
            // Credit/billing errors
            lowerError.contains("insufficient") && lowerError.contains("credit") -> {
                logDebug(method, "Detected credit insufficiency error")
                LocalizationHelper.getString("mobile.credits_no_credits")
            }
            lowerError.contains("no credit") || lowerError.contains("out of credit") -> {
                logDebug(method, "Detected no credits error")
                LocalizationHelper.getString("mobile.credits_no_credits")
            }
            lowerError.contains("payment") || lowerError.contains("billing") -> {
                logDebug(method, "Detected payment/billing error")
                LocalizationHelper.getString("mobile.credits_purchase_required")
            }

            // Network errors
            lowerError.contains("network") || lowerError.contains("unreachable") ||
            lowerError.contains("connection refused") || lowerError.contains("no route") -> {
                logDebug(method, "Detected network error")
                LocalizationHelper.getString("mobile.credits_error_network")
            }

            // Server errors
            lowerError.contains("500") || lowerError.contains("502") ||
            lowerError.contains("503") || lowerError.contains("504") ||
            lowerError.contains("internal server") || lowerError.contains("service unavailable") -> {
                logDebug(method, "Detected server error")
                LocalizationHelper.getString("mobile.credits_error_server")
            }

            // Auth errors - don't show raw 401
            lowerError.contains("401") || lowerError.contains("unauthorized") ||
            lowerError.contains("authentication") -> {
                logDebug(method, "Detected auth error")
                LocalizationHelper.getString("mobile.credits_error_generic")
            }

            // JSON parse errors - hide technical details
            lowerError.contains("json") || lowerError.contains("parse") ||
            lowerError.contains("deserialize") || lowerError.contains("serialization") -> {
                logDebug(method, "Detected parsing error")
                LocalizationHelper.getString("mobile.credits_error_server")
            }

            // Generic fallback - use localized message with truncated error
            else -> {
                // Only include error summary, not full JSON/stack traces
                val cleanError = rawError
                    .substringBefore("{")  // Remove JSON
                    .substringBefore("\n") // Take first line only
                    .trim()
                    .take(100)  // Limit length

                if (cleanError.isNotEmpty() && !cleanError.contains("Exception")) {
                    LocalizationHelper.getString("mobile.processing_failed", mapOf("error" to cleanError))
                } else {
                    LocalizationHelper.getString("mobile.credits_error_generic")
                }
            }
        }
    }

    /**
     * Toggle timeline visibility
     */
    fun toggleTimeline() {
        _showTimeline.value = !_showTimeline.value
    }

    /**
     * Toggle emoji legend visibility
     */
    fun toggleLegend() {
        _showLegend.value = !_showLegend.value
    }

    /**
     * Start SSE stream for live reasoning events with robust reconnection
     */
    private fun startSseStream() {
        val method = "startSseStream"
        logInfo(method, "Starting SSE reasoning stream")

        sseJob = viewModelScope.launch {
            while (isActive) {
                try {
                    sseClient.connect().collect { event ->
                        when (event) {
                            is ReasoningEvent.Connected -> {
                                logInfo(method, "SSE connected")
                                _sseConnected.value = true
                                sseReconnectDelay = SSE_RECONNECT_BASE_MS // Reset on success
                            }
                            is ReasoningEvent.Disconnected -> {
                                logInfo(method, "SSE disconnected")
                                _sseConnected.value = false
                                _agentProcessingState.value = AgentProcessingState.IDLE
                            }
                            is ReasoningEvent.PipelineStep -> {
                                // Update pipeline scaffolding visualization
                                val now = Clock.System.now().toEpochMilliseconds()
                                if (event.isNewThought) {
                                    // New thought round - reset then activate
                                    _pipelineState.value = _pipelineState.value
                                        .reset()
                                        .activate(event.eventType, now)
                                } else if (event.eventType == "tsaspdma_result") {
                                    // TSASPDMA re-lights ASPDMA ring with extra brightness
                                    // (Tool-Specific ASPDMA refines the tool selection)
                                    _pipelineState.value = _pipelineState.value
                                        .activateWithTsaspdmaBoost(now)
                                } else {
                                    _pipelineState.value = _pipelineState.value
                                        .activate(event.eventType, now)
                                }
                                // Tier-1 event: route non-action pipeline steps
                                // to their owning bus so the matching arc shimmers.
                                val pulseBus = ai.ciris.mobile.shared.ui.screens.graph
                                    .busFromEventType(event.eventType, action = null)
                                if (pulseBus != null) {
                                    addBusPulse(pulseBus)
                                }
                            }
                            is ReasoningEvent.Emoji -> {
                                // Add bubble emoji (floats up and disappears).
                                // Pass the payload so the bubble becomes a tappable
                                // carrier for the event's semantic summary.
                                addBubbleEmoji(event.emoji, event.payload)

                                // Record into the per-stage ring buffer so the
                                // nucleus-shell selection panel can show recent
                                // rationales / conscience values without a poll.
                                recordStageEvent(event)

                                // Add to timeline (persists for bubble net)
                                addTimelineEvent(event.emoji, event.eventType)

                                // Check if this is one of the 10 CIRIS action emojis
                                val actionType = ActionType.fromEmoji(event.emoji)
                                if (actionType != null) {
                                    fetchAndAddLatestAction(actionType)
                                    // Tier-1 event: route the action to its bus.
                                    // task_complete returns null here — it fires a
                                    // gratitude mote instead.
                                    val actionBus = ai.ciris.mobile.shared.ui.screens.graph
                                        .busFromEventType(
                                            eventType = "action_result",
                                            action = actionType.name,
                                        )
                                    if (actionBus != null) {
                                        addBusPulse(actionBus)
                                    } else if (actionType.name.contains("task_complete", ignoreCase = true)) {
                                        // Signal-not-anthropomorphize: the mote says
                                        // "the system closed a loop cleanly", not
                                        // "the agent is happy".
                                        addGratitudePulse()
                                    }
                                    // Tier-3: DEFER → visible routing to wise
                                    // authority. Fire the nucleus ripple in
                                    // addition to the bus pulse; the ripple is
                                    // what distinguishes "consulting authority"
                                    // from "routine bus traffic".
                                    if (actionType == ActionType.DEFER) {
                                        triggerDeferralRipple()
                                    }
                                }

                                // Update processing state and status text
                                if (event.isComplete) {
                                    _agentProcessingState.value = AgentProcessingState.IDLE
                                    // Clear processing status text when task completes
                                    _processingStatus.value = ""
                                } else {
                                    _agentProcessingState.value = AgentProcessingState.PROCESSING
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    logError(method, "SSE error: ${e.message}")
                    _sseConnected.value = false
                }

                // Exponential backoff reconnection
                logInfo(method, "Reconnecting in ${sseReconnectDelay}ms...")
                delay(sseReconnectDelay)
                sseReconnectDelay = (sseReconnectDelay * 2).coerceAtMost(SSE_RECONNECT_MAX_MS)
            }
        }
    }

    /**
     * Add a bubble emoji that floats up, optionally carrying a short payload.
     *
     * Payload is the event's semantic summary (e.g. "Speak · Hello!" or
     * "→ tool:weather:current"). It lives only for the bubble's flight time,
     * so memory use stays bounded at MAX_BUBBLES × PAYLOAD_MAX_CHARS.
     * Users can "catch" a bubble mid-flight to promote its payload into the
     * caughtBubbles list for longer inspection.
     */
    /**
     * Spawn a bus-arc shimmer pulse. Auto-expires after the pulse
     * duration so the list never grows unbounded. Up to ~8 concurrent
     * pulses feels crowded; beyond that we drop the oldest.
     */
    private fun addBusPulse(bus: ai.ciris.mobile.shared.ui.screens.graph.CellBus) {
        val now = Clock.System.now().toEpochMilliseconds()
        val pulse = ai.ciris.mobile.shared.ui.screens.graph.BusPulse(bus, now)
        _busPulses.value = (_busPulses.value + pulse).takeLast(8)
        viewModelScope.launch {
            delay(ai.ciris.mobile.shared.ui.screens.graph.BUS_PULSE_DURATION_MS)
            _busPulses.value = _busPulses.value.filter { it.startMs != now || it.bus != bus }
        }
    }

    /**
     * Emit a gratitude mote from the nucleus, if the cooldown allows.
     * Fired on `task_complete` — never on every SPEAK/TOOL action, so
     * the signal reads as "task landed" rather than ambient motion.
     *
     * The mote's angle is randomised so consecutive emissions don't
     * stack along the same ray. Self-expires after
     * [GRATITUDE_MOTE_DURATION_MS].
     */
    private fun addGratitudePulse() {
        val now = Clock.System.now().toEpochMilliseconds()
        if (!ai.ciris.mobile.shared.ui.screens.graph.canEmitGratitude(lastGratitudeMs, now)) {
            return
        }
        lastGratitudeMs = now
        val angle = kotlin.random.Random.Default.nextFloat() * 360f
        val pulse = ai.ciris.mobile.shared.ui.screens.graph.GratitudePulse(
            startMs = now,
            angleDeg = angle,
        )
        _gratitudePulses.value = (_gratitudePulses.value + pulse).takeLast(4)
        viewModelScope.launch {
            delay(pulse.durationMs)
            _gratitudePulses.value = _gratitudePulses.value.filter { it.startMs != now }
        }
    }

    /**
     * Tier-3 deferral ripple — fires on DEFER actions. The nucleus emits
     * a single concentric wave outward (renderer owns the expand + ease-
     * out). We only need to stamp a start timestamp; the renderer reads
     * it every frame and stops drawing when the 1.5 s animation is done.
     * The state is cleared after 2.5 s (spec total) so follow-on DEFERs
     * restart cleanly instead of stacking.
     */
    private fun triggerDeferralRipple() {
        val now = Clock.System.now().toEpochMilliseconds()
        _deferralRippleStartMs.value = now
        viewModelScope.launch {
            delay(2500)
            if (_deferralRippleStartMs.value == now) {
                _deferralRippleStartMs.value = null
            }
        }
    }

    private fun addBubbleEmoji(emoji: String, payload: String? = null) {
        val bubbleId = bubbleIdCounter++
        val expiresAt = Clock.System.now().toEpochMilliseconds() + BUBBLE_LIFETIME_MS
        val bubble = BubbleEmoji(id = bubbleId, emoji = emoji, payload = payload, expiresAtMs = expiresAt)

        // Add to list (keep max bubbles)
        _bubbleEmojis.value = (_bubbleEmojis.value + bubble).takeLast(MAX_BUBBLES)

        // Remove after animation completes
        viewModelScope.launch {
            delay(BUBBLE_LIFETIME_MS)
            _bubbleEmojis.value = _bubbleEmojis.value.filter { it.id != bubbleId }
        }
    }

    /**
     * Pin an in-flight bubble so its payload survives past the 2s float window.
     *
     * No-op if the bubble already expired, is unknown, or has no payload —
     * catching an empty bubble would just create visual clutter.
     */
    fun catchBubble(id: Long) {
        val b = _bubbleEmojis.value.firstOrNull { it.id == id } ?: return
        if (b.payload.isNullOrBlank()) return
        // Remove from in-flight and promote to caught
        _bubbleEmojis.value = _bubbleEmojis.value.filter { it.id != id }
        _caughtBubbles.value = (_caughtBubbles.value + b).takeLast(MAX_CAUGHT_BUBBLES)
    }

    /**
     * Dismiss a previously-caught bubble.
     */
    fun dismissCaughtBubble(id: Long) {
        _caughtBubbles.value = _caughtBubbles.value.filter { it.id != id }
    }

    /**
     * Clear all caught bubbles.
     */
    fun clearCaughtBubbles() {
        _caughtBubbles.value = emptyList()
    }

    /**
     * Add event to timeline (minimal storage for bubble net)
     */
    private fun addTimelineEvent(emoji: String, eventType: String) {
        val event = TimelineEvent(
            emoji = emoji,
            eventType = formatEventTypeName(eventType),
            timestamp = Clock.System.now().toEpochMilliseconds()
        )
        _timelineEvents.value = (_timelineEvents.value + event).takeLast(MAX_TIMELINE_EVENTS)
    }

    /**
     * Format event type for display (e.g., "action_result" -> "Action Result")
     */
    private fun formatEventTypeName(eventType: String): String {
        return eventType
            .replace("_", " ")
            .split(" ")
            .joinToString(" ") { word ->
                word.replaceFirstChar { it.uppercase() }
            }
    }

    /**
     * Clear timeline events
     */
    fun clearTimeline() {
        _timelineEvents.value = emptyList()
    }

    // =========================================================================
    // FG selection + per-stage ring buffer + 1 Hz poll
    //
    // See FSD §12 — the detail panel in FG reads live agent data for the
    // element the user tapped. Nucleus shells use a client-side SSE
    // ring buffer (no poll), everything else polls @ 1 Hz while selected.
    // =========================================================================

    /** One entry in the per-stage SSE ring buffer. */
    data class StageEvent(
        val eventType: String,
        val emoji: String,
        val timestampMs: Long,
        /** Truncated semantic summary (<= 160 chars per ReasoningEvent). */
        val payload: String?,
    )

    /**
     * Parsed live data for whatever is currently selected in FG.
     * Kind-tagged so the panel composable can render the right shape.
     */
    sealed interface SelectionDetail {
        /** One-line status line common to every variant. */
        val summaryLine: String

        data class AdapterPort(
            override val summaryLine: String,
            val adapterId: String,
            val adapterType: String,
            val isRunning: Boolean,
            val messagesProcessed: Int,
            val errorsCount: Int,
            val lastError: String?,
            val lastActivity: String?,
            /** Queue depth if available (null = not yet surfaced). */
            val queueSize: Int?,
        ) : SelectionDetail

        data class BusArc(
            override val summaryLine: String,
            val bus: ai.ciris.mobile.shared.ui.screens.graph.CellBus,
            val messagesSent: Long,
            val averageLatencyMs: Double,
            val errorsLastHour: Int,
            val queueDepth: Int,
            /** LLM bus only: per-provider detail. Empty for other buses. */
            val llmProviders: List<LLMProviderRow> = emptyList(),
        ) : SelectionDetail

        data class LLMProviderRow(
            val name: String,
            val healthy: Boolean,
            val priority: String,
            val circuitBreakerState: String,  // "closed" / "open" / "half_open"
            val failureCount: Int,
            val rateLimited: Boolean,
        )

        data class NucleusShell(
            override val summaryLine: String,
            val stageIndex: Int,
            val stageLabel: String,
            val eventType: String,
            val recentEvents: List<StageEvent>,
        ) : SelectionDetail

        data class NucleusCore(
            override val summaryLine: String,
            val cognitiveState: String,
            val systemStatus: String,
            val servicesOnline: Int,
            val servicesTotal: Int,
        ) : SelectionDetail

        data class Mote(
            override val summaryLine: String,
            val nodeId: String,
            val scope: String,
            val nodeType: String?,
            val attributesJson: String?,
        ) : SelectionDetail

        data class Gratitude(
            override val summaryLine: String,
            val recentCompletions: List<String>,
        ) : SelectionDetail

        data class Loading(override val summaryLine: String = "Loading…") : SelectionDetail

        data class Error(override val summaryLine: String) : SelectionDetail
    }

    private fun recordStageEvent(event: ReasoningEvent.Emoji) {
        val entry = StageEvent(
            eventType = event.eventType,
            emoji = event.emoji,
            timestampMs = Clock.System.now().toEpochMilliseconds(),
            payload = event.payload,
        )
        _stageEvents.value = _stageEvents.value.toMutableMap().apply {
            val list = (get(event.eventType).orEmpty() + entry).takeLast(STAGE_EVENT_BUFFER)
            put(event.eventType, list)
        }
    }

    /**
     * Set the current FG selection. Starts / cancels / swaps the 1 Hz
     * poll job so we never poll endpoints for elements the user isn't
     * looking at.
     */
    fun setSelection(
        kind: ai.ciris.mobile.shared.ui.screens.graph.SelectionKind?,
        anchorXFraction: Float = 0.5f,
    ) {
        val prev = _selectionKind.value
        _selectionKind.value = kind
        _selectionAnchorX.value = anchorXFraction.coerceIn(0f, 1f)
        // No change → keep the existing poll running.
        if (prev == kind) return

        selectionPollJob?.cancel()
        selectionPollJob = null
        _selectionDetail.value = null
        if (kind == null) return

        _selectionDetail.value = SelectionDetail.Loading()
        selectionPollJob = viewModelScope.launch {
            while (isActive) {
                try {
                    val fresh = fetchSelectionDetail(kind)
                    // Cooperative cancel check: a rapid tap sequence can
                    // cancel this job while an HTTP call is in flight.
                    // Don't write the stale value after cancel — that's
                    // what used to wedge the UI on "Loading…" and
                    // occasionally trigger a fatal coroutine wrap.
                    if (!isActive) break
                    _selectionDetail.value = fresh
                } catch (e: kotlinx.coroutines.CancellationException) {
                    // Rethrow — coroutine hygiene rule: never swallow
                    // CancellationException, it must propagate so the
                    // coroutine unwinds cleanly.
                    throw e
                } catch (e: Exception) {
                    logDebug("fetchSelectionDetail", "poll error: ${e.message}")
                    if (!isActive) break
                    // Friendlier message for the common case — a node
                    // that was in the timeline at viz load but has
                    // since rotated out of the window returns 404 when
                    // the user taps. Don't scare the user with the
                    // raw HTTP code.
                    val msg = e.message ?: e::class.simpleName ?: "unknown error"
                    val friendly = when {
                        msg.contains("404") -> "This node is no longer available"
                        msg.contains("401") || msg.contains("403") ->
                            "Sign-in required to view this detail"
                        else -> "Couldn't fetch detail: $msg"
                    }
                    _selectionDetail.value = SelectionDetail.Error(summaryLine = friendly)
                }
                // Nucleus shells read the SSE ring buffer on every tick
                // too so newly-arrived events show up without a manual
                // refresh. For HTTP-backed kinds this is the rate cap.
                kotlinx.coroutines.delay(SELECTION_POLL_INTERVAL_MS)
            }
        }
    }

    private suspend fun fetchSelectionDetail(
        kind: ai.ciris.mobile.shared.ui.screens.graph.SelectionKind,
    ): SelectionDetail = when (kind) {
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.AdapterPort -> {
            val details = apiClient.getAdapterDetails(kind.adapterId)
            SelectionDetail.AdapterPort(
                summaryLine = "${kind.adapterType}:${kind.adapterId.take(12)} • " +
                    (if (details.isRunning) "running" else "stopped"),
                adapterId = kind.adapterId,
                adapterType = kind.adapterType,
                isRunning = details.isRunning,
                messagesProcessed = details.metrics?.messagesProcessed ?: 0,
                errorsCount = details.metrics?.errorsCount ?: 0,
                lastError = details.metrics?.lastError,
                lastActivity = details.lastActivity,
                // Adapter-level queue depth isn't surfaced yet.
                queueSize = null,
            )
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.BusArc -> {
            // LLM bus gets rich per-provider detail from the existing
            // /v1/system/llm/status + /v1/system/llm/providers endpoints.
            // Other buses fall back to the bus-name summary until a
            // per-bus telemetry endpoint is wired.
            if (kind.bus == ai.ciris.mobile.shared.ui.screens.graph.CellBus.LLM) {
                val status = try { apiClient.getLlmBusStatus() } catch (_: Exception) { null }
                val providers = try { apiClient.getLlmProviders() } catch (_: Exception) { emptyList() }
                val providerRows = providers.map { p ->
                    SelectionDetail.LLMProviderRow(
                        name = p.name,
                        healthy = p.healthy,
                        priority = p.priorityLabel,
                        circuitBreakerState = p.circuitBreaker.state.name.lowercase(),
                        failureCount = p.circuitBreaker.failureCount,
                        rateLimited = p.metrics.isRateLimited,
                    )
                }
                SelectionDetail.BusArc(
                    summaryLine = if (status != null) {
                        "LLM • ${status.providersAvailable}/${status.providersTotal} providers • " +
                            "${status.totalRequests} req • ${status.circuitBreakersSummary}"
                    } else "LLM bus",
                    bus = kind.bus,
                    messagesSent = status?.totalRequests?.toLong() ?: 0L,
                    averageLatencyMs = status?.averageLatencyMs?.toDouble() ?: 0.0,
                    errorsLastHour = status?.failedRequests ?: 0,
                    queueDepth = status?.providersRateLimited ?: 0,
                    llmProviders = providerRows,
                )
            } else {
                // Non-LLM buses — pull per-bus operational telemetry from
                // /v1/telemetry/unified?category=buses. Keyed by backend
                // bus name (``memory_bus``, ``communication_bus``, ...).
                val telem = try { apiClient.getBusTelemetry() } catch (_: Exception) { emptyMap() }
                val key = when (kind.bus) {
                    ai.ciris.mobile.shared.ui.screens.graph.CellBus.COMM -> "communication_bus"
                    ai.ciris.mobile.shared.ui.screens.graph.CellBus.MEMORY -> "memory_bus"
                    ai.ciris.mobile.shared.ui.screens.graph.CellBus.TOOL -> "tool_bus"
                    ai.ciris.mobile.shared.ui.screens.graph.CellBus.WISE -> "wise_bus"
                    ai.ciris.mobile.shared.ui.screens.graph.CellBus.RUNTIME -> "runtime_control_bus"
                    else -> ""
                }
                val t = telem[key]
                SelectionDetail.BusArc(
                    summaryLine = if (t != null) {
                        val health = if (t.healthy) "healthy" else "degraded"
                        "${kind.bus.name} • $health • ${t.messagesSent} msg"
                    } else "${kind.bus.name} bus",
                    bus = kind.bus,
                    messagesSent = t?.messagesSent ?: 0L,
                    averageLatencyMs = t?.averageLatencyMs ?: 0.0,
                    errorsLastHour = t?.errorsLastHour ?: 0,
                    queueDepth = t?.queueDepth ?: 0,
                )
            }
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.NucleusShell -> {
            val recent = _stageEvents.value[kind.eventType].orEmpty()
            SelectionDetail.NucleusShell(
                summaryLine = kind.eventType.replace('_', ' ')
                    .replaceFirstChar { it.uppercase() } + " • ${recent.size} recent",
                stageIndex = kind.stageIndex,
                stageLabel = kind.eventType.replace('_', ' ').uppercase(),
                eventType = kind.eventType,
                recentEvents = recent,
            )
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.NucleusCore -> {
            val status = apiClient.getSystemStatus()
            val cog = status.cognitive_state ?: "unknown"
            SelectionDetail.NucleusCore(
                summaryLine = "$cog • ${status.services_online}/${status.services_total} services",
                cognitiveState = cog,
                systemStatus = status.status,
                servicesOnline = status.services_online,
                servicesTotal = status.services_total,
            )
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.CytoplasmMote -> {
            val node = apiClient.getMemoryNode(kind.nodeId)
            SelectionDetail.Mote(
                summaryLine = "${node.type} • ${node.scope}",
                nodeId = kind.nodeId,
                scope = kind.scope,
                nodeType = node.type,
                attributesJson = node.attributesJson,
            )
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.SignalChannel -> {
            // A channel is the correspondent-facing surface of a port —
            // same data source.
            fetchSelectionDetail(
                ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.AdapterPort(
                    adapterId = kind.adapterId,
                    adapterType = "",
                    bus = kind.bus,
                )
            )
        }
        is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.GratitudeMote -> {
            // Latest completed tasks from the audit trail. We filter by
            // event_type=handler_action_task_complete (see
            // HANDLER_ACTION_TASK_COMPLETE in audit/core.py) and pull
            // only the most recent 5 — this is the "signalled gratitude"
            // surface, not a full history view.
            val audits = try {
                apiClient.getAuditEntries(
                    eventType = "handler_action_task_complete",
                    limit = 5,
                )
            } catch (_: Exception) { null }
            val rows = audits?.entries.orEmpty().map { e ->
                val desc = e.context?.description ?: e.context?.entityId ?: e.id
                val ts = e.timestamp.take(19).replace('T', ' ')
                "$ts • $desc"
            }
            SelectionDetail.Gratitude(
                summaryLine = if (rows.isEmpty()) {
                    "No recent task completions"
                } else "${rows.size} recent task${if (rows.size == 1) "" else "s"} completed",
                recentCompletions = rows,
            )
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, cancelling jobs")
        super.onCleared()
        pollingJob?.cancel()
        statusJob?.cancel()
        healthJob?.cancel()
        trustPollJob?.cancel()
        sseJob?.cancel()
        languageObserverJob?.cancel()
        capacityRefreshJob?.cancel()
        selectionPollJob?.cancel()
    }
}
