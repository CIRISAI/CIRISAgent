package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.LocalCurrency
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.ActionDetails
import ai.ciris.mobile.shared.models.ActionType
import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.viewmodels.AgentProcessingState
import ai.ciris.mobile.shared.viewmodels.BubbleEmoji
import ai.ciris.mobile.shared.viewmodels.CreditStatus
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import ai.ciris.mobile.shared.viewmodels.LlmHealthStatus
import ai.ciris.mobile.shared.viewmodels.TimelineEvent
import ai.ciris.mobile.shared.viewmodels.TrustStatus
import ai.ciris.mobile.shared.viewmodels.WalletStatus
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.probeCellVizCapability
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.input.pointer.pointerInput
import kotlinx.coroutines.isActive
import kotlin.math.abs
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.testTag
import ai.ciris.mobile.shared.platform.FilePickerDialog
import ai.ciris.mobile.shared.platform.PickedFile
import ai.ciris.mobile.shared.platform.platformImePadding
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.zIndex
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.SystemWarning
import ai.ciris.mobile.shared.ui.screens.graph.CellVisualization
import ai.ciris.mobile.shared.ui.screens.graph.CellVizConfig
import ai.ciris.mobile.shared.ui.screens.graph.GraphColors
import ai.ciris.mobile.shared.ui.screens.graph.LiveGraphBackground
import ai.ciris.mobile.shared.ui.screens.graph.PipelineState
import ai.ciris.mobile.shared.ui.screens.graph.VisualizationMode
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.InteractTheme

/**
 * Chat interface screen
 * Ported from Android InteractFragment.kt and fragment_interact.xml
 *
 * Key Features:
 * - Message list with user/agent bubbles
 * - Different styling for user vs agent messages
 * - Timestamps and author names
 * - Processing status indicator
 * - Empty state for first launch
 * - Connection status bar
 * - Shutdown controls
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InteractScreen(
    viewModel: InteractViewModel,
    onNavigateBack: () -> Unit,
    onSessionExpired: () -> Unit = {},
    onOpenTrustPage: () -> Unit = {},
    onOpenWalletPage: () -> Unit = {},
    onOpenBilling: () -> Unit = {},
    onOpenSystem: () -> Unit = {},
    onOpenSettings: () -> Unit = {},
    onOpenLLMSettings: () -> Unit = {},  // Navigate to LLM Settings screen
    onOpenSessions: () -> Unit = {},  // Navigate to sessions screen
    onOpenWiseAuthority: () -> Unit = {},  // Navigate to WA/deferrals screen
    apiClient: CIRISApiClient? = null,  // For live background
    liveBackgroundEnabled: Boolean = false,  // From settings
    // User override: when true, force the legacy cylinder viz regardless of
    // device capability. Flipped via Settings → Use classic visualization.
    forceClassicViz: Boolean = false,
    colorTheme: ColorTheme = ColorTheme.DEFAULT,  // Color theme from settings
    isDarkMode: Boolean = true,  // From brightness preference
    // Cell-viz tuning config (FSD/CELL_VIZ_REDESIGN.md §2.8 + step 11).
    // Defaults to the built-in sanitized config; SettingsViewModel hydrates
    // the real value from secure storage and passes it through here so the
    // Visualization Settings sliders take effect live.
    cellVizConfig: CellVizConfig = CellVizConfig.DEFAULT,
    modifier: Modifier = Modifier
) {
    val messages by viewModel.messages.collectAsState()
    val inputText by viewModel.inputText.collectAsState()
    val isConnected by viewModel.isConnected.collectAsState()
    val agentStatus by viewModel.agentStatus.collectAsState()
    val isSending by viewModel.isSending.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val processingStatus by viewModel.processingStatus.collectAsState()
    val authError by viewModel.authError.collectAsState()
    val bubbleEmojis by viewModel.bubbleEmojis.collectAsState()
    val caughtBubbles by viewModel.caughtBubbles.collectAsState()
    val adapterOrbits by viewModel.adapterOrbits.collectAsState()
    val cellVizState by viewModel.cellVizState.collectAsState()
    val busPulses by viewModel.busPulses.collectAsState()
    val gratitudePulses by viewModel.gratitudePulses.collectAsState()
    val selectionKind by viewModel.selectionKind.collectAsState()
    val selectionDetail by viewModel.selectionDetail.collectAsState()

    // When auth error occurs, navigate to login silently
    LaunchedEffect(authError) {
        if (authError != null) {
            viewModel.clearAuthError()
            onSessionExpired()
        }
    }
    val agentProcessingState by viewModel.agentProcessingState.collectAsState()
    val sseConnected by viewModel.sseConnected.collectAsState()
    val timelineEvents by viewModel.timelineEvents.collectAsState()
    val showTimeline by viewModel.showTimeline.collectAsState()
    val showLegend by viewModel.showLegend.collectAsState()
    val llmHealth by viewModel.llmHealth.collectAsState()
    val creditStatus by viewModel.creditStatus.collectAsState()
    val trustStatus by viewModel.trustStatus.collectAsState()
    val walletStatus by viewModel.walletStatus.collectAsState()
    val attachedFiles by viewModel.attachedFiles.collectAsState()
    val pipelineState by viewModel.pipelineState.collectAsState()
    val pendingDeferrals by viewModel.pendingDeferrals.collectAsState()
    val systemWarnings by viewModel.systemWarnings.collectAsState()

    // Refresh trust status when screen becomes visible (handles app resume)
    LaunchedEffect(Unit) {
        viewModel.refreshTrustStatus()
    }

    // Observe text input requests for test automation
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            if (request.testTag == "input_message") {
                if (request.clearFirst) {
                    viewModel.onInputTextChanged(request.text)
                } else {
                    viewModel.onInputTextChanged(inputText + request.text)
                }
                TestAutomation.clearTextInputRequest()
            }
        }
    }

    // File picker state
    var showFilePicker by remember { mutableStateOf(false) }

    // Visualization legend state (separate from emoji legend)
    var showVizLegend by remember { mutableStateOf(false) }

    // Focus requester for the text input
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    // Visualization mode state - controls the live graph display
    var visualizationMode by remember {
        mutableStateOf(if (liveBackgroundEnabled) VisualizationMode.BACKGROUND else VisualizationMode.OFF)
    }

    // Sync visualization mode with liveBackgroundEnabled setting changes
    LaunchedEffect(liveBackgroundEnabled) {
        visualizationMode = if (liveBackgroundEnabled) {
            // When enabled, default to BACKGROUND (user can still toggle to FG/OFF)
            if (visualizationMode == VisualizationMode.OFF) VisualizationMode.BACKGROUND else visualizationMode
        } else {
            // When disabled, force OFF
            VisualizationMode.OFF
        }
    }

    // Leaving FG clears any live selection so re-entering is fresh.
    LaunchedEffect(visualizationMode) {
        if (visualizationMode != VisualizationMode.FOREGROUND) {
            viewModel.setSelection(null)
        }
    }

    // Effective live background: enabled when visualization mode is not OFF
    val effectiveLiveBackground = visualizationMode != VisualizationMode.OFF

    // Legacy alias kept for the cylinder-viz path (LiveGraphBackground's
    // isForegroundMode param). With cell viz, FG is "interactive inspect",
    // not a fidget — no Column alpha trick, no overlay drag-to-spin.
    val isFullscreenFidget = visualizationMode == VisualizationMode.FOREGROUND

    // Multi-axis rotation for fidget mode (vertical spin - full 360 rotation)
    var verticalRotation by remember { mutableStateOf(0f) }
    var verticalVelocity by remember { mutableStateOf(0f) }

    // Create theme based on live background state, color theme, and brightness preference
    // All colors defined in LiveBackgroundTheme.kt, accent colors from ColorTheme
    val theme = remember(effectiveLiveBackground, colorTheme, isDarkMode) {
        // Also update GraphColors to use the selected theme for graph node colors
        GraphColors.setTheme(colorTheme)
        InteractTheme.forLiveBackground(effectiveLiveBackground, colorTheme, isDarkMode)
    }

    // Cylinder rotation state for swipe-to-spin
    var cylinderRotation by remember { mutableStateOf(0f) }
    var rotationVelocity by remember { mutableStateOf(0f) }
    var isDraggingHorizontal by remember { mutableStateOf(false) }

    // Spin energy system - builds up over multiple fast flicks
    var spinEnergy by remember { mutableStateOf(0f) }
    val spinEnergyThreshold = 800f  // Need to build up this much energy to trigger spin apart (requires ~5-7 fast flicks)
    val energyDecayRate = 0.92f  // Energy decays faster when not spinning fast
    val energyGainMultiplier = 0.15f  // How much velocity contributes to energy (reduced for more flicks needed)

    // Momentum animation loop for cylinder spin and tilt. In FG mode
    // the whole loop short-circuits and velocity is zeroed — FG is
    // "pause and explore", so any residual spin from BG must stop
    // the moment the user flips modes. `rememberUpdatedState` keeps
    // the loop reading the CURRENT visualization mode rather than the
    // launch-time capture.
    val vizModeState = rememberUpdatedState(visualizationMode)
    LaunchedEffect(Unit) {
        while (isActive) {
            kotlinx.coroutines.delay(16)  // ~60 FPS

            if (vizModeState.value == VisualizationMode.FOREGROUND) {
                // Kill momentum instantly so re-entering BG later doesn't
                // resume with stale velocity. Don't advance rotation; a
                // dedicated FG rotate gesture (TODO: 2-finger rotate) is
                // the only way to spin the cell in this mode.
                rotationVelocity = 0f
                spinEnergy = 0f
                continue
            }

            // Horizontal spin momentum
            if (abs(rotationVelocity) > 0.1f) {
                cylinderRotation += rotationVelocity

                // Build up spin energy from fast spinning (only fast flicks count)
                if (abs(rotationVelocity) > 8f) {
                    spinEnergy += abs(rotationVelocity) * energyGainMultiplier
                } else {
                    // Decay energy when spinning slowly
                    spinEnergy *= energyDecayRate
                }

                // Only apply damping when not actively dragging
                if (!isDraggingHorizontal) {
                    rotationVelocity *= 0.97f  // Damping - slower decay for satisfying spin
                }

                // Normalize rotation
                while (cylinderRotation > 360f) cylinderRotation -= 360f
                while (cylinderRotation < -360f) cylinderRotation += 360f
            } else {
                // Faster energy decay when stopped
                spinEnergy *= 0.95f
            }

            // Vertical rotation momentum (fidget mode - full 360 spin over the top)
            if (abs(verticalVelocity) > 0.1f) {
                verticalRotation += verticalVelocity
                verticalVelocity *= 0.97f  // Same decay as horizontal for satisfying spin
                // Normalize rotation
                while (verticalRotation > 360f) verticalRotation -= 360f
                while (verticalRotation < -360f) verticalRotation += 360f
            }

            // Clamp energy
            if (spinEnergy < 0.1f) spinEnergy = 0f
        }
    }

    // Note: CIRISApp wraps this screen in a Scaffold with TopAppBar,
    // so we don't need our own Scaffold here. Use Box for bubble overlay.
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(theme.background)
    ) {
        // Live animated memory graph background (when enabled).
        //
        // Device gating: [probeCellVizCapability] decides whether this device
        // should render the new "cell" visualization (64-bit + ≥4 GB RAM) or
        // fall back to the legacy LiveGraphBackground (cylinder view). The
        // legacy path is frozen — no new features land there, it just keeps
        // CIRIS usable on constrained hardware.
        //
        // NOTE: both branches currently call the same composable. This is
        // scaffolding — the isCapable=true branch will be swapped for the
        // CellVisualization composable in a later commit once the cell
        // primitives are built. The gate goes in first so every subsequent
        // change can flip a single branch without touching Interact's layout.
        val cellVizCap = remember { probeCellVizCapability() }
        // Effective gate = capability AND user hasn't opted out.
        val useCellViz = cellVizCap.isCapable && !forceClassicViz
        LaunchedEffect(cellVizCap, forceClassicViz) {
            PlatformLogger.i(
                "InteractScreen",
                "cell-viz gate: useCellViz=$useCellViz (capable=${cellVizCap.isCapable}, " +
                    "forceClassic=$forceClassicViz, ram=${"%.1f".format(cellVizCap.totalRamGb)}GB, " +
                    "reason=${cellVizCap.reason})"
            )
        }
        // NOTE: CellVisualization / LiveGraphBackground are NOT rendered
        // here at the outer Box. They render INSIDE the chat-area Box
        // further down in the main Column — see the big Box with
        // Modifier.weight(1f). Rationale: Compose Desktop Canvas does not
        // respect zIndex against sibling Columns (the Canvas overdraws
        // chrome regardless of declared z). By making the viz a child of
        // the chat-area Box, normal Compose layout keeps the status bar,
        // FG detail panel, banners, and input bar above it by default —
        // no zIndex gymnastics, no painful layering bugs.

        // Main content column with platform-specific keyboard padding.
        // Structure (top → bottom):
        //   StatusBar | FgDetailPanel? | banners | BubbleNet | chat-area Box (cell viz + optional chat) | input
        // The cell viz lives INSIDE the chat-area Box so Compose's normal
        // layout keeps all chrome above it. No zIndex needed.
        Column(
            modifier = Modifier
                .fillMaxSize()
                .platformImePadding()
        ) {
            // Enhanced status bar with LLM health, credits, and trust shield
            EnhancedStatusBar(
                isConnected = isConnected,
                status = agentStatus,
                llmHealth = llmHealth,
                creditStatus = creditStatus,
                trustStatus = trustStatus,
                walletStatus = walletStatus,
                cellVizState = cellVizState,
                visualizationMode = visualizationMode,
                onVisualizationToggle = { visualizationMode = visualizationMode.next() },
                onShutdown = { viewModel.shutdown(emergency = false) },
                onEmergencyStop = { viewModel.shutdown(emergency = true) },
                onWalletClick = onOpenWalletPage,
                onTrustShieldClick = onOpenTrustPage,
                onCreditsClick = onOpenBilling,
                onLocalClick = onOpenSystem,
                onSettingsClick = onOpenSettings,
                onLLMSettingsClick = onOpenLLMSettings,
                onSessionsClick = onOpenSessions,
                theme = theme
            )

            // FG selection detail panel. Renders immediately below the
            // status bar when the user taps a selectable element on the
            // cell (only in FG — selection is cleared on BG entry).
            val sel = selectionKind
            if (visualizationMode == VisualizationMode.FOREGROUND && sel != null) {
                FgDetailPanel(
                    selection = sel,
                    detail = selectionDetail,
                    theme = theme,
                    onDismiss = { viewModel.setSelection(null) },
                    onOpenLLMSettings = onOpenLLMSettings,
                    onOpenWiseAuthority = onOpenWiseAuthority,
                    onOpenSystem = onOpenSystem,
                )
            }

        // Auth error is now handled by LaunchedEffect above - navigates to login silently

        // AI Warning banner (from fragment_interact.xml:65-76)
        AIWarningBanner(theme = theme)

        // Pending deferrals banner - shows when there are human review requests waiting
        if (pendingDeferrals > 0) {
            PendingDeferralsBanner(
                count = pendingDeferrals,
                onClick = onOpenWiseAuthority,
                theme = theme
            )
        }

        // System warnings banner - shows critical warnings like "no LLM provider"
        systemWarnings.forEach { warning ->
            SystemWarningBanner(
                warning = warning,
                onClick = {
                    // Navigate based on action_url
                    when (warning.actionUrl) {
                        "/settings/llm" -> onOpenLLMSettings()
                        else -> {} // Other action URLs can be added
                    }
                },
                theme = theme
            )
        }

        // Bubble Net - timeline of events (expandable)
        BubbleNet(
            events = timelineEvents,
            isExpanded = showTimeline,
            theme = theme,
            onToggle = { viewModel.toggleTimeline() },
            onClear = { viewModel.clearTimeline() }
        )

        // Loading indicator (from fragment_interact.xml:119-125)
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }

        // Chat messages container with empty state (from fragment_interact.xml:127-190)
        // Horizontal swipe rotates the background cylinder (fidget spin!)
        // — but ONLY in BG mode. FG is "pause and explore", so the parent
        // swipe-to-spin gesture must yield to the cell viz's own pan/zoom
        // gestures. Without this gate, detectHorizontalDragGestures on the
        // parent Box captures and `consume()`s pointer events before they
        // can reach the Canvas's detectTransformGestures / scroll handler.
        val swipeSpinActive = liveBackgroundEnabled &&
            visualizationMode != VisualizationMode.FOREGROUND
        // Only attach pointerInput when the gesture is actually active.
        // `Modifier.pointerInput { if (false) ... }` still registers a
        // pointer-event scope in the hit chain and appears to block
        // propagation to z-siblings below (cell viz Canvas). Using
        // `Modifier.then(...)` with a conditional Modifier means NO
        // pointerInput exists in FG — events pass cleanly through to
        // the Canvas underneath.
        val swipeSpinModifier = if (swipeSpinActive) {
            Modifier.pointerInput(Unit) {
                detectHorizontalDragGestures(
                    onDragStart = { isDraggingHorizontal = true },
                    onDragEnd = { isDraggingHorizontal = false },
                    onDragCancel = { isDraggingHorizontal = false },
                    onHorizontalDrag = { change, dragAmount ->
                        change.consume()
                        val rotationSensitivity = 0.5f
                        val deltaRotation = dragAmount * rotationSensitivity
                        cylinderRotation += deltaRotation
                        rotationVelocity = rotationVelocity * 0.3f + deltaRotation * 0.7f
                    }
                )
            }
        } else {
            Modifier
        }
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .then(swipeSpinModifier)
        ) {
            // Cell viz / legacy cylinder renders as the BACKGROUND of the
            // chat area. matchParentSize() fills this Box's bounds without
            // influencing its measurement — lets weight(1f) drive height.
            if (effectiveLiveBackground && apiClient != null) {
                if (useCellViz) {
                    CellVisualization(
                        modifier = Modifier.matchParentSize(),
                        isDarkMode = isDarkMode,
                        adapterOrbits = adapterOrbits,
                        externalRotation = cylinderRotation,
                        config = cellVizConfig.sanitized(),
                        apiClient = apiClient,
                        colorTheme = colorTheme,
                        eventTrigger = timelineEvents.size,
                        state = cellVizState,
                        busPulses = busPulses,
                        gratitudePulses = gratitudePulses,
                        pipelineState = pipelineState,
                        showSignalChannels = visualizationMode == VisualizationMode.FOREGROUND,
                        onSelection = { kind -> viewModel.setSelection(kind) },
                        selection = selectionKind,
                    )
                } else {
                    val graphOpacity = when (visualizationMode) {
                        VisualizationMode.FOREGROUND -> 1.0f
                        VisualizationMode.BACKGROUND -> 0.85f
                        VisualizationMode.OFF -> 0f
                    }
                    LiveGraphBackground(
                        apiClient = apiClient,
                        modifier = Modifier.matchParentSize(),
                        baseOpacity = graphOpacity,
                        eventTrigger = timelineEvents.size,
                        externalRotation = cylinderRotation,
                        externalTilt = verticalRotation,
                        spinEnergy = spinEnergy,
                        spinEnergyThreshold = spinEnergyThreshold,
                        onSpinApartTriggered = { spinEnergy = 0f },
                        pipelineState = pipelineState,
                        isForegroundMode = isFullscreenFidget,
                        ringColor = colorTheme.tertiary,
                        colorTheme = colorTheme,
                    )
                }
            }
            // In BG: chat/empty-state renders OVER the ambient viz.
            // In FG: chat is suppressed so the viz is the whole middle area.
            if (visualizationMode != VisualizationMode.FOREGROUND) {
                if (messages.isEmpty() && !isLoading) {
                    EmptyStateView(
                        transparentBackground = liveBackgroundEnabled,
                        isDarkMode = isDarkMode,
                    )
                } else {
                    ChatMessageList(messages = messages, transparentBackground = liveBackgroundEnabled)
                }
            }
        }

        // Message count indicator (from fragment_interact.xml:192-200)
        if (messages.isNotEmpty()) {
            Text(
                text = localizedString("mobile.interact_showing_messages", mapOf("count" to messages.size.toString())),
                modifier = Modifier
                    .fillMaxWidth()
                    .background(theme.messageCountBackground)
                    .padding(horizontal = 12.dp, vertical = 4.dp),
                fontSize = 11.sp,
                color = theme.messageCountText,
                textAlign = TextAlign.Center
            )
        }

            // Input bar with agent state icon
            // Input bar with agent state icon
            // navigationBarsPadding here so input sits above the system nav bar
            ChatInputBarWithBubbles(
                text = inputText,
                onTextChange = { viewModel.onInputTextChanged(it) },
                onSend = { viewModel.sendMessage() },
                enabled = isConnected && !isSending,
                focusRequester = focusRequester,
                onFocused = { keyboardController?.show() },
                agentState = agentProcessingState,
                bubbleEmojis = bubbleEmojis,
                sseConnected = sseConnected,
                onLegendToggle = { viewModel.toggleLegend() },
                attachedFiles = attachedFiles,
                onAttach = { showFilePicker = true },
                onRemoveAttachment = { viewModel.removeAttachment(it) },
                theme = theme,
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
            )

            // File picker dialog (platform-specific)
            FilePickerDialog(
                show = showFilePicker,
                onFilePicked = { file ->
                    viewModel.addAttachment(file)
                    showFilePicker = false
                },
                onDismiss = { showFilePicker = false }
            )
        } // End of Column

        // Emoji legend dialog
        if (showLegend) {
            EmojiLegendDialog(onDismiss = { viewModel.toggleLegend() })
        }

        // Bubble overlay - floats up from bottom-left over the entire screen.
        // Tapping a bubble with a payload "catches" it into the caughtBubbles list.
        BubbleOverlay(
            bubbles = bubbleEmojis,
            onCatch = { id -> viewModel.catchBubble(id) },
            modifier = Modifier
                .fillMaxSize()
                .padding(start = 8.dp, bottom = 70.dp) // Align with agent icon position
        )

        // Caught bubbles panel — pinned payloads from in-flight bubbles the
        // user tapped. Bounded (12 items × 160 chars) and dismissable.
        CaughtBubblesPanel(
            bubbles = caughtBubbles,
            theme = theme,
            onDismiss = { id -> viewModel.dismissCaughtBubble(id) },
            onClearAll = { viewModel.clearCaughtBubbles() },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(top = 230.dp, end = 8.dp)
                .widthIn(max = 280.dp)
                .zIndex(50f)
        )

        // Note: ErrorToast, DebugIndicator, and DebugConsole removed for production release

        // Legend button (BG + FG). Anchored to the outer Box's BottomEnd
        // so it sits above the cell viz and input bar in both modes.
        if (visualizationMode != VisualizationMode.OFF) {
            VisualizationLegendButton(
                isExpanded = showVizLegend,
                onToggle = { showVizLegend = !showVizLegend },
                theme = theme,
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(end = 16.dp, bottom = 140.dp)
            )
        }
    } // End of Box
}

/**
 * Enhanced status bar with:
 * - Connection status (local server)
 * - LLM provider health
 * - CIRIS credits (if CIRIS proxy)
 * - Wallet badge (balance display)
 * - Trust shield (X/5 level)
 * - Shutdown controls
 */
@Composable
private fun EnhancedStatusBar(
    isConnected: Boolean,
    status: String,
    llmHealth: LlmHealthStatus,
    creditStatus: CreditStatus,
    trustStatus: TrustStatus,
    walletStatus: WalletStatus,
    cellVizState: ai.ciris.mobile.shared.ui.screens.graph.CellVizState,
    visualizationMode: VisualizationMode,
    onVisualizationToggle: () -> Unit,
    onShutdown: () -> Unit,
    onEmergencyStop: () -> Unit,
    onWalletClick: () -> Unit,
    onTrustShieldClick: () -> Unit,
    onCreditsClick: () -> Unit,
    onLocalClick: () -> Unit,
    onSettingsClick: () -> Unit,
    onLLMSettingsClick: () -> Unit,
    onSessionsClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Surface(
        color = theme.surface,
        shadowElevation = if (theme.isDark) 0.dp else 2.dp,
        modifier = modifier.fillMaxWidth()
    ) {
        Column {
            // Main status row
            Row(
                modifier = Modifier
                    .padding(horizontal = 8.dp, vertical = 6.dp)
                    .fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // Connection status - tappable to Server Connection screen
                Row(
                    modifier = Modifier
                        .testableClickable("btn_connection_status") { onLocalClick() }
                        .padding(4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .background(
                                color = if (isConnected) theme.statusConnected else theme.statusDisconnected,
                                shape = CircleShape
                            )
                    )
                    Text(
                        text = if (isConnected) localizedString("mobile.interact_local") else localizedString("mobile.interact_offline"),
                        fontSize = 11.sp,
                        color = if (isConnected) theme.statusConnected else theme.statusDisconnected
                    )
                }

                // Divider
                Text(text = "•", fontSize = 10.sp, color = theme.textMuted)

                // LLM health indicator - tappable to LLM Settings
                LlmHealthIndicator(health = llmHealth, onClick = onLLMSettingsClick, theme = theme)

                // Credits indicator (only if CIRIS proxy) - clickable to billing
                if (llmHealth.isCirisProxy && creditStatus.isLoaded) {
                    Text(text = "•", fontSize = 10.sp, color = theme.textMuted)
                    CreditsIndicator(credits = creditStatus, onClick = onCreditsClick, theme = theme)
                }

                Spacer(modifier = Modifier.weight(1f))

                // Wallet badge (to the left of trust shield)
                WalletBadge(
                    walletStatus = walletStatus,
                    onClick = onWalletClick,
                    theme = theme
                )

                // CIRIS capacity (ratchet) badge — composite C/I_int/R/I_inc/S
                // score for this agent's template. Sits next to trust so the
                // two "at a glance" health signals (attestation + behavior)
                // live together.
                CapacityBadge(
                    state = cellVizState,
                    theme = theme
                )

                // Trust shield
                TrustShield(
                    trustStatus = trustStatus,
                    onClick = onTrustShieldClick,
                    theme = theme
                )
            }

            // Shutdown controls row (collapsed by default, could be expandable)
            Row(
                modifier = Modifier
                    .padding(horizontal = 8.dp)
                    .padding(bottom = 6.dp)
                    .fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // Cognitive state - clickable to go to Sessions
                Surface(
                    onClick = onSessionsClick,
                    shape = RoundedCornerShape(4.dp),
                    color = Color.Transparent
                ) {
                    Text(
                        text = localizedCognitiveState(status),
                        fontSize = 10.sp,
                        color = theme.textSecondary,
                        modifier = Modifier.padding(4.dp)
                    )
                }

                // Visualization mode toggle button
                Surface(
                    onClick = onVisualizationToggle,
                    shape = RoundedCornerShape(4.dp),
                    color = when (visualizationMode) {
                        VisualizationMode.FOREGROUND -> theme.statusConnected.copy(alpha = 0.2f)
                        VisualizationMode.BACKGROUND -> theme.textAccent.copy(alpha = 0.15f)
                        VisualizationMode.OFF -> Color.Transparent
                    },
                    modifier = Modifier.testableClickable("btn_viz_mode_toggle") {
                        onVisualizationToggle()
                    },
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(3.dp)
                    ) {
                        Text(
                            text = localizedString("mobile.interact_viz_label"),
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Medium,
                            color = when (visualizationMode) {
                                VisualizationMode.FOREGROUND -> theme.statusConnected
                                VisualizationMode.BACKGROUND -> theme.textAccent
                                VisualizationMode.OFF -> theme.textMuted
                            }
                        )
                        Text(
                            text = when (visualizationMode) {
                                VisualizationMode.OFF -> localizedString("mobile.interact_viz_mode_off")
                                VisualizationMode.BACKGROUND -> localizedString("mobile.interact_viz_mode_bg")
                                VisualizationMode.FOREGROUND -> localizedString("mobile.interact_viz_mode_fg")
                            },
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                            color = when (visualizationMode) {
                                VisualizationMode.FOREGROUND -> theme.statusConnected
                                VisualizationMode.BACKGROUND -> theme.textAccent
                                VisualizationMode.OFF -> theme.textMuted
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.weight(1f))

                // Shutdown button
                OutlinedButton(
                    onClick = onShutdown,
                    modifier = Modifier
                        .height(26.dp)
                        .testableClickable("btn_shutdown") { onShutdown() },
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = theme.shutdownOutline
                    ),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                ) {
                    Text(localizedString("mobile.interact_shutdown"), fontSize = 9.sp)
                }

                Spacer(modifier = Modifier.width(4.dp))

                // Emergency stop button
                Button(
                    onClick = onEmergencyStop,
                    modifier = Modifier
                        .height(26.dp)
                        .testableClickable("btn_emergency_stop") { onEmergencyStop() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFEF4444)
                    ),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                ) {
                    Text(localizedString("mobile.interact_stop"), fontSize = 9.sp, color = Color.White)
                }
            }
        }
    }
}

/**
 * LLM health indicator - shows provider and status
 */
@Composable
private fun LlmHealthIndicator(
    health: LlmHealthStatus,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .clickable(onClick = onClick)
            .padding(4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp)
    ) {
        val isMockLlm = health.provider == "mockllm" || health.provider == "mock"

        // Health dot - bright red for mock LLM
        Box(
            modifier = Modifier
                .size(6.dp)
                .background(
                    color = when {
                        isMockLlm -> theme.statusDisconnected
                        health.isHealthy -> theme.statusConnected
                        else -> theme.statusWarning
                    },
                    shape = CircleShape
                )
        )

        // Provider name - comprehensive provider display
        // Show "..." while loading (provider defaults to "unknown")
        val displayName = when {
            health.provider == "unknown" -> "..."  // Still loading
            isMockLlm -> "\u26A0\uFE0F MOCKLLM \u26A0\uFE0F"
            health.isCirisProxy -> "CIRIS"
            health.provider == "openai" -> "OpenAI"
            health.provider == "anthropic" -> "Anthropic"
            health.provider == "google" || health.provider == "google_ai" -> "Google AI"
            health.provider == "openrouter" -> "OpenRouter"
            health.provider == "groq" -> "Groq"
            health.provider == "together" || health.provider == "together_ai" -> "Together"
            health.provider == "local" || health.provider == "ollama" -> "Local"
            health.provider == "azure" || health.provider == "azure_openai" -> "Azure"
            health.provider == "mistral" -> "Mistral"
            health.provider == "cohere" -> "Cohere"
            health.provider == "deepseek" -> "DeepSeek"
            health.provider == "xai" || health.provider == "x_ai" -> "xAI"
            health.provider == "other" -> "Custom"
            else -> health.provider.replaceFirstChar { it.uppercase() }.take(10)
        }
        Text(
            text = displayName,
            fontSize = if (isMockLlm) 11.sp else 10.sp,
            fontWeight = if (isMockLlm) FontWeight.Bold else FontWeight.Normal,
            color = when {
                isMockLlm -> theme.statusDisconnected
                health.isHealthy -> theme.statusConnected
                else -> theme.statusWarning
            }
        )
    }
}

/**
 * Credits indicator - shows remaining credits (clickable to billing)
 */
@Composable
private fun CreditsIndicator(
    credits: CreditStatus,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Surface(
        onClick = onClick,
        color = Color.Transparent,
        modifier = modifier.testableClickable("btn_credits") { onClick() }
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(2.dp),
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
        ) {
            // Fire emoji for credits
            Text(text = "🔥", fontSize = 10.sp)

            // Credits count - prioritize showing what's available
            // Priority: paid credits > free uses > daily free uses > 0 with renewal time
            val creditsText = when {
                credits.creditsRemaining > 0 -> "${credits.creditsRemaining}"
                credits.freeUsesRemaining > 0 -> "Free: ${credits.freeUsesRemaining}"
                credits.dailyFreeUsesRemaining > 0 -> "Daily: ${credits.dailyFreeUsesRemaining}"
                else -> {
                    // Show renewal time when out of credits
                    val hoursUntil = credits.hoursUntilRenewal()
                    if (hoursUntil > 0) "⏰${hoursUntil}h" else "0"
                }
            }
            val creditsColor = when {
                credits.creditsRemaining > 10 -> theme.statusConnected
                credits.creditsRemaining > 0 -> theme.statusWarning
                credits.freeUsesRemaining > 0 -> theme.textAccent
                credits.dailyFreeUsesRemaining > 0 -> theme.textAccent
                else -> theme.statusDisconnected
            }
            Text(
                text = creditsText,
                fontSize = 10.sp,
                color = creditsColor,
                fontWeight = FontWeight.Medium
            )
        }
    }
}

/**
 * Wallet badge - shows wallet status and balance in user's selected currency
 * Colors: Green = funded, Amber = receive-only, Gray = not configured/empty
 * Balance is converted from USDC to selected display currency.
 */
@Composable
private fun WalletBadge(
    walletStatus: WalletStatus,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    // Get currency manager for conversion
    val currencyManager = LocalCurrency.current
    val currentCurrency by currencyManager?.currentCurrency?.collectAsState()
        ?: remember { mutableStateOf("USD") }

    // Log wallet status for debugging
    LaunchedEffect(walletStatus) {
        PlatformLogger.d("WalletBadge", "WalletStatus: isLoaded=${walletStatus.isLoaded}, hasWallet=${walletStatus.hasWallet}, balance=${walletStatus.balance}, provider=${walletStatus.provider}, isReceiveOnly=${walletStatus.isReceiveOnly}, isInitializing=${walletStatus.isInitializing}")
    }

    val isInitializing = walletStatus.isInitializing
    val hasBalance = walletStatus.balance != "0.00" && walletStatus.balance != "0"
    val badgeColor = when {
        isInitializing -> theme.trustLevel4               // Initializing - amber (waiting for CIRISVerify)
        walletStatus.isReceiveOnly -> theme.trustLevel4   // Receive-only (hardware degraded) - amber
        hasBalance -> theme.trustLevel5                   // Has funds - green
        walletStatus.hasWallet -> theme.trustDefault      // Empty wallet - gray
        else -> theme.trustDefault                        // Not configured - gray
    }

    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(4.dp),
        color = badgeColor.copy(alpha = 0.15f),
        modifier = modifier.testableClickable("btn_wallet_badge") { onClick() }
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(3.dp)
        ) {
            // Show spinner when initializing, otherwise wallet emoji
            if (isInitializing) {
                CircularProgressIndicator(
                    modifier = Modifier.size(12.dp),
                    strokeWidth = 1.5.dp,
                    color = badgeColor
                )
            } else {
                Text(text = "💰", fontSize = 12.sp)
            }

            // Balance or status text - convert to selected currency
            // Note: Receive-only status is shown via amber color, not text - always show balance
            val displayText = when {
                isInitializing -> localizedString("mobile.interact_wallet_loading")
                !walletStatus.hasWallet -> localizedString("mobile.interact_wallet_setup")
                hasBalance -> {
                    // Convert USDC balance to selected currency
                    val usdcAmount = walletStatus.balance.toDoubleOrNull() ?: 0.0
                    currencyManager?.convertFromUsdc(usdcAmount) ?: walletStatus.balance
                }
                else -> {
                    // Show "0" in selected currency format
                    currencyManager?.convertFromUsdc(0.0) ?: "0"
                }
            }
            Text(
                text = displayText,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = badgeColor
            )
        }
    }
}

/**
 * Trust shield - shows attestation level X/5
 * Colors match TrustPage: L5=green, L4=amber, L1-3=red (issues detected)
 */
@Composable
private fun TrustShield(
    trustStatus: TrustStatus,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    // TrustStatus.maxLevel now contains actual achieved level (calculated in ViewModel)
    val level = trustStatus.maxLevel
    val isLoaded = trustStatus.isLoaded
    val isPending = trustStatus.levelPending  // True when waiting for device attestation
    val isLoading = !isLoaded || isPending    // Show loading state until data is loaded

    // When pending/loading, use amber to indicate "in progress" state
    val shieldColor = when {
        !isLoaded -> theme.trustDefault        // Not loaded yet - gray with spinner
        isPending -> theme.trustLevel4         // Attestation in progress - amber (provisional)
        level >= 5 -> theme.trustLevel5        // Identity Validated - green
        level == 4 -> theme.trustLevel4        // Agent Validated - amber
        level >= 1 -> theme.trustLevelLow      // Issues Detected (L1-3) - red
        else -> theme.trustDefault             // Not started - gray
    }

    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(4.dp),
        color = shieldColor.copy(alpha = 0.15f),
        modifier = modifier.testableClickable("btn_trust_shield") { onClick() }
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(3.dp)
        ) {
            if (isLoading) {
                // Show spinner when loading or attestation is pending
                CircularProgressIndicator(
                    modifier = Modifier.size(12.dp),
                    strokeWidth = 1.5.dp,
                    color = shieldColor
                )
            } else {
                // Shield emoji when stable
                Text(text = "🛡", fontSize = 12.sp)
            }

            // Level text - show loading indicator when not loaded, provisional when pending
            Text(
                text = when {
                    !isLoaded -> "…"           // Loading
                    isPending -> "$level/5..."  // Attestation pending
                    else -> "$level/5"          // Stable
                },
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = shieldColor
            )
        }
    }
}

/**
 * CIRIS capacity (ratchet) badge — the clear, at-a-glance companion to
 * the ambient cell-viz dials. Sits immediately beside the Trust shield
 * so the two system-health signals (attestation + behaviour) are read
 * together.
 *
 * Colour scheme mirrors the Trust shield so "green / amber / red" means
 * the same thing in both:
 *   - high_capacity   → green  (L5-equivalent)
 *   - healthy         → green  (strong but with room)
 *   - moderate        → amber  (L4-equivalent)
 *   - high_fragility  → red    (low-L-equivalent)
 *   - pre-fetch       → gray   (no data yet — same treatment as trust)
 *
 * The per-factor detail lives in the cell viz itself (ambient dials +
 * multi-coloured nucleus shells). The badge is intentionally a single
 * status LED so the chrome row stays scannable.
 */
@Composable
private fun CapacityBadge(
    state: ai.ciris.mobile.shared.ui.screens.graph.CellVizState,
    theme: InteractTheme,
    modifier: Modifier = Modifier,
) {
    val isLoaded = !state.isPreFetch
    val badgeColor = when {
        !isLoaded -> theme.trustDefault
        state.category == "high_capacity" -> theme.trustLevel5
        state.category == "healthy" -> theme.trustLevel5
        state.category == "moderate" -> theme.trustLevel4
        state.category == "high_fragility" -> theme.trustLevelLow
        else -> theme.trustDefault
    }

    // Two-decimal fixed-width score. Avoid String.format (JVM-only in
    // commonMain); use integer math to produce "0.90", "1.00", "0.38".
    val scoreText = if (!isLoaded) {
        "…"
    } else {
        val hundredths = (state.compositeScore.coerceIn(0f, 1f) * 100f + 0.5f).toInt()
        val whole = hundredths / 100
        val frac = hundredths % 100
        val fracStr = if (frac < 10) "0$frac" else "$frac"
        "$whole.$fracStr"
    }

    Surface(
        shape = RoundedCornerShape(4.dp),
        color = badgeColor.copy(alpha = 0.15f),
        modifier = modifier.testable("capacity_badge"),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            if (!isLoaded) {
                CircularProgressIndicator(
                    modifier = Modifier.size(12.dp),
                    strokeWidth = 1.5.dp,
                    color = badgeColor,
                )
            } else {
                // Filled status dot — reads as a signal LED, not a heartbeat
                // or other anthropomorphic metaphor. Same shape as the
                // Connection-status dot earlier in the bar so the visual
                // language is consistent.
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .background(color = badgeColor, shape = CircleShape),
                )
            }

            Text(
                text = scoreText,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = badgeColor,
            )
        }
    }
}

/**
 * Legacy connection status bar with shutdown controls
 * From fragment_interact.xml:10-63
 */
@Composable
private fun ConnectionStatusBar(
    isConnected: Boolean,
    status: String,
    onShutdown: () -> Unit,
    onEmergencyStop: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color.White,
        shadowElevation = 2.dp,
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .padding(8.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Status dot (from fragment_interact.xml:21-25)
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .background(
                        color = if (isConnected) Color(0xFF10B981) else Color(0xFFEF4444),
                        shape = CircleShape
                    )
            )

            // Status text (from fragment_interact.xml:27-35)
            Text(
                text = if (isConnected) localizedString("mobile.interact_connected") else localizedString("mobile.interact_disconnected"),
                modifier = Modifier.weight(1f),
                fontSize = 14.sp,
                color = if (isConnected) Color(0xFF10B981) else Color(0xFFEF4444)
            )

            // Shutdown button (from fragment_interact.xml:37-48)
            OutlinedButton(
                onClick = onShutdown,
                modifier = Modifier
                    .height(32.dp)
                    .testableClickable("btn_shutdown_legacy") { onShutdown() },
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = Color(0xFFEF4444)
                ),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)
            ) {
                Text("Shutdown", fontSize = 11.sp)
            }

            // Emergency stop button (from fragment_interact.xml:50-61)
            Button(
                onClick = onEmergencyStop,
                modifier = Modifier
                    .height(32.dp)
                    .testableClickable("btn_emergency_stop_legacy") { onEmergencyStop() },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0xFFEF4444)
                ),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)
            ) {
                Text("STOP", fontSize = 11.sp, color = Color.White)
            }
        }
    }
}

/**
 * Auth error banner - shown when session expires
 * Provides option to dismiss or navigate to re-authenticate
 */
@Composable
private fun AuthErrorBanner(
    message: String,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color(0xFFFEE2E2), // Light red background
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = message,
                modifier = Modifier.weight(1f),
                fontSize = 12.sp,
                color = Color(0xFFDC2626) // Red text
            )
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_dismiss_auth_error") { onDismiss() },
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Text(
                    text = localizedString("mobile.interact_dismiss"),
                    fontSize = 11.sp,
                    color = Color(0xFFDC2626)
                )
            }
        }
    }
}

/**
 * AI warning banner
 * From fragment_interact.xml:65-76
 */
@Composable
private fun AIWarningBanner(
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Text(
        text = "⚠️ " + localizedString("mobile.interact_hallucination_warning"),
        modifier = modifier
            .fillMaxWidth()
            .background(theme.warningBackground)
            .padding(horizontal = 12.dp, vertical = 4.dp),
        fontSize = 11.sp,
        color = theme.warningText,
        textAlign = TextAlign.Center
    )
}

/**
 * Pending deferrals banner - shows when there are human review requests waiting
 * Tapping navigates to the Wise Authority screen to review and resolve deferrals
 */
@Composable
private fun PendingDeferralsBanner(
    count: Int,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(Color(0xFF2563EB).copy(alpha = 0.15f))  // Blue tint
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "📋",
            fontSize = 14.sp
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = localizedString(
                "mobile.interact_pending_deferrals",
                mapOf("count" to count.toString())
            ),
            fontSize = 12.sp,
            color = Color(0xFF2563EB),
            fontWeight = FontWeight.Medium
        )
        Spacer(modifier = Modifier.width(4.dp))
        Text(
            text = "→",
            fontSize = 14.sp,
            color = Color(0xFF2563EB)
        )
    }
}

/**
 * System warning banner - shows critical warnings like "no LLM provider configured"
 * Tapping navigates to the appropriate settings screen to resolve the warning
 */
@Composable
private fun SystemWarningBanner(
    warning: SystemWarning,
    onClick: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    val backgroundColor = when (warning.severity) {
        "error" -> Color(0xFFDC2626).copy(alpha = 0.15f)  // Red tint
        "warning" -> Color(0xFFF59E0B).copy(alpha = 0.15f)  // Amber tint
        else -> Color(0xFF2563EB).copy(alpha = 0.15f)  // Blue tint (info)
    }
    val textColor = when (warning.severity) {
        "error" -> Color(0xFFDC2626)
        "warning" -> Color(0xFFF59E0B)
        else -> Color(0xFF2563EB)
    }
    val icon = when (warning.severity) {
        "error" -> "⚠️"
        "warning" -> "⚡"
        else -> "ℹ️"
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(backgroundColor)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = icon,
            fontSize = 14.sp
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = warning.message,
            fontSize = 12.sp,
            color = textColor,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.weight(1f, fill = false)
        )
        if (warning.actionUrl != null) {
            Spacer(modifier = Modifier.width(4.dp))
            Text(
                text = "→",
                fontSize = 14.sp,
                color = textColor
            )
        }
    }
}

/**
 * Empty state view for first launch
 * From fragment_interact.xml:142-188
 */
@Composable
private fun EmptyStateView(
    modifier: Modifier = Modifier,
    transparentBackground: Boolean = false,
    isDarkMode: Boolean = false,
) {
    // When the background is transparent, text sits directly on top of the
    // cell viz. In dark mode that means dark-on-dark — so we flip the
    // title/subtitle to high-contrast light colours. The earlier hard-coded
    // gray values were chosen for light mode and became unreadable once
    // dark mode became the hero view (see FSD §2.6).
    val onTransparentDark = transparentBackground && isDarkMode
    val titleColor = if (onTransparentDark) Color(0xFFF5F5F7) else Color(0xFF1F2937)
    val subtitleColor = when {
        onTransparentDark -> Color(0xFFD1D5DB)              // light slate
        transparentBackground -> Color(0xFF4B5563)          // light mode on viz
        else -> Color(0xFF6B7280)                           // opaque card
    }
    val hintColor = when {
        onTransparentDark -> Color(0xFF5DD3D8)              // NavSignetLight — readable on dark
        transparentBackground -> Color(0xFF0E7490)          // darker cyan on light viz
        else -> Color(0xFF419CA0)                           // brand teal on opaque card
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .then(if (transparentBackground) Modifier else Modifier.background(Color(0xFFF3F4F6)))
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Icon placeholder (from fragment_interact.xml:153-158)
        Text(
            text = "🤖",
            fontSize = 64.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Welcome text (from fragment_interact.xml:160-167)
        Text(
            text = localizedString("mobile.interact_welcome_title"),
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = titleColor,
            modifier = Modifier.padding(bottom = 12.dp)
        )

        // Subtitle (from fragment_interact.xml:169-175)
        Text(
            text = localizedString("mobile.interact_welcome_subtitle"),
            fontSize = 14.sp,
            color = subtitleColor,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Hint text (from fragment_interact.xml:177-186)
        Text(
            text = localizedString("mobile.interact_welcome_hint"),
            fontSize = 14.sp,
            color = hintColor,
            textAlign = TextAlign.Center,
            lineHeight = 18.sp,
            modifier = Modifier.padding(horizontal = 16.dp)
        )
    }
}

/**
 * Chat message list
 * Replaces RecyclerView from fragment_interact.xml:133-140
 */
@Composable
private fun ChatMessageList(
    messages: List<ChatMessage>,
    modifier: Modifier = Modifier,
    transparentBackground: Boolean = false
) {
    val listState = rememberLazyListState()

    // Use BoxWithConstraints to calculate responsive bubble width
    // Phone (<600.dp): 85%, Tablet (600-900.dp): 70%, Desktop (>900.dp): 55%
    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .then(if (transparentBackground) Modifier else Modifier.background(Color(0xFFF3F4F6)))
    ) {
        val bubbleMaxWidth = when {
            maxWidth < 600.dp -> maxWidth * 0.85f
            maxWidth < 900.dp -> maxWidth * 0.70f
            else -> maxWidth * 0.55f
        }.coerceIn(200.dp, 600.dp)  // Min 200dp, max 600dp

        LazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxSize()
                .padding(8.dp),
            reverseLayout = true,
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            // Use distinctBy to prevent duplicate key crashes if same ID appears twice
            items(messages.reversed().distinctBy { it.id }, key = { it.id }) { message ->
                when (message.type) {
                    MessageType.USER -> UserChatBubble(message, bubbleMaxWidth = bubbleMaxWidth)
                    MessageType.AGENT -> AgentChatBubble(message, bubbleMaxWidth = bubbleMaxWidth)
                    MessageType.SYSTEM -> SystemMessage(message, bubbleMaxWidth = bubbleMaxWidth)
                    MessageType.ERROR -> ErrorMessage(message, bubbleMaxWidth = bubbleMaxWidth)
                    MessageType.ACTION -> ActionBubble(message, bubbleMaxWidth = bubbleMaxWidth)
                }
            }
        }
    }

    // Auto-scroll to latest message - trigger on size OR last message change
    val lastMessageKey = messages.lastOrNull()?.let { "${it.id}_${it.timestamp}" } ?: ""
    LaunchedEffect(messages.size, lastMessageKey) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(0)
        }
    }
}

/**
 * User message bubble
 * From item_chat_user.xml
 */
@Composable
private fun UserChatBubble(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 280.dp  // Default for backwards compat
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.End
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = bubbleMaxWidth)
                .background(
                    color = Color(0xFF2563EB), // Blue from chat_bubble_user.xml
                    shape = RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = 16.dp,
                        bottomEnd = 4.dp // Different corner radius
                    )
                )
                .padding(12.dp)
        ) {
            // Author (from item_chat_user.xml:17-23)
            Text(
                text = localizedString("mobile.interact_sender_you"),
                fontSize = 11.sp,
                color = Color(0xFFDBEAFE)
            )

            // Content (from item_chat_user.xml:25-32)
            SelectionContainer {
                Text(
                    text = message.text,
                    modifier = Modifier.padding(top = 2.dp),
                    fontSize = 14.sp,
                    color = Color.White
                )
            }

            // Attachment indicator
            if (message.attachmentCount > 0) {
                MessageAttachmentRow(
                    attachmentCount = message.attachmentCount,
                    hasImages = message.hasImageAttachments,
                    hasDocs = message.hasDocumentAttachments,
                    tintColor = Color(0xFFDBEAFE)
                )
            }

            // Timestamp (from item_chat_user.xml:34-42)
            Text(
                text = formatTimestamp(message.timestamp),
                modifier = Modifier
                    .align(Alignment.End)
                    .padding(top = 4.dp),
                fontSize = 10.sp,
                color = Color(0xFFBFDBFE)
            )
        }
    }
}

/**
 * Agent message bubble
 * From item_chat_agent.xml
 */
@Composable
private fun AgentChatBubble(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 280.dp  // Default for backwards compat
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Start
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = bubbleMaxWidth)
                .background(
                    color = Color.White,
                    shape = RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = 4.dp, // Different corner radius
                        bottomEnd = 16.dp
                    )
                )
                .padding(1.dp) // Border effect
                .background(
                    color = Color.White,
                    shape = RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = 4.dp,
                        bottomEnd = 16.dp
                    )
                )
                .padding(12.dp)
        ) {
            // Author (from item_chat_agent.xml:18-23)
            Text(
                text = localizedString("mobile.interact_sender_ciris"),
                fontSize = 11.sp,
                color = Color(0xFF6B7280)
            )

            // Content (from item_chat_agent.xml:25-32)
            SelectionContainer {
                Text(
                    text = message.text,
                    modifier = Modifier.padding(top = 2.dp),
                    fontSize = 14.sp,
                    color = Color(0xFF1F2937)
                )
            }

            // Timestamp (from item_chat_agent.xml:34-42)
            Text(
                text = formatTimestamp(message.timestamp),
                modifier = Modifier
                    .align(Alignment.End)
                    .padding(top = 4.dp),
                fontSize = 10.sp,
                color = Color(0xFF9CA3AF)
            )
        }
    }
}

/**
 * System message (informational notifications)
 * Styled with light blue/gray background and info styling
 */
@Composable
private fun SystemMessage(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 280.dp  // Default for backwards compat
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFFE0F2FE), // Light blue info background
            modifier = Modifier.widthIn(max = bubbleMaxWidth)
        ) {
            Row(
                modifier = Modifier.padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(
                    text = "\u2139\uFE0F", // ℹ️ info icon
                    fontSize = 14.sp
                )
                SelectionContainer {
                    Text(
                        text = message.text,
                        fontSize = 12.sp,
                        color = Color(0xFF0369A1) // Dark blue text
                    )
                }
            }
        }
    }
}

/**
 * Error message (error/warning notifications)
 * Styled with light red/orange background and warning styling
 */
@Composable
private fun ErrorMessage(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 280.dp  // Default for backwards compat
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFFFEE2E2), // Light red error background
            modifier = Modifier.widthIn(max = bubbleMaxWidth)
        ) {
            Row(
                modifier = Modifier.padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(
                    text = "\u26A0\uFE0F", // ⚠️ warning icon
                    fontSize = 14.sp
                )
                SelectionContainer {
                    Text(
                        text = message.text,
                        fontSize = 12.sp,
                        color = Color(0xFFDC2626) // Red text
                    )
                }
            }
        }
    }
}

/**
 * Action bubble - expandable card showing CIRIS action details
 * Supports all 10 action types: SPEAK, TOOL, OBSERVE, MEMORIZE, RECALL, FORGET, REJECT, PONDER, DEFER, TASK_COMPLETE
 */
@Composable
private fun ActionBubble(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 320.dp  // Default for backwards compat (slightly wider for structured content)
) {
    var isExpanded by remember { mutableStateOf(false) }
    val actionDetails = message.actionDetails
    val actionType = actionDetails?.actionType

    // Color scheme based on action type
    val (bgColor, textColor, dividerColor) = when (actionType) {
        ActionType.SPEAK -> Triple(Color(0xFFEFF6FF), Color(0xFF1E40AF), Color(0xFFBFDBFE))  // Blue
        ActionType.TOOL -> Triple(Color(0xFFF0FDF4), Color(0xFF065F46), Color(0xFFD1FAE5))  // Green
        ActionType.OBSERVE -> Triple(Color(0xFFFEF3C7), Color(0xFF92400E), Color(0xFFFDE68A))  // Amber
        ActionType.MEMORIZE -> Triple(Color(0xFFF3E8FF), Color(0xFF6B21A8), Color(0xFFE9D5FF))  // Purple
        ActionType.RECALL -> Triple(Color(0xFFEDE9FE), Color(0xFF5B21B6), Color(0xFFDDD6FE))  // Violet
        ActionType.FORGET -> Triple(Color(0xFFFFF7ED), Color(0xFFC2410C), Color(0xFFFED7AA))  // Orange
        ActionType.REJECT -> Triple(Color(0xFFFEF2F2), Color(0xFFDC2626), Color(0xFFFECACA))  // Red
        ActionType.PONDER -> Triple(Color(0xFFF0F9FF), Color(0xFF0369A1), Color(0xFFBAE6FD))  // Sky
        ActionType.DEFER -> Triple(Color(0xFFFDF4FF), Color(0xFFA21CAF), Color(0xFFF5D0FE))  // Fuchsia
        ActionType.TASK_COMPLETE -> Triple(Color(0xFFECFDF5), Color(0xFF047857), Color(0xFFA7F3D0))  // Emerald
        null -> Triple(Color(0xFFF5F5F5), Color(0xFF6B7280), Color(0xFFE5E5E5))  // Gray fallback
    }

    // Action bubbles get extra width for structured content
    val actionBubbleWidth = (bubbleMaxWidth + 40.dp).coerceAtMost(700.dp)

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            onClick = { isExpanded = !isExpanded },
            shape = RoundedCornerShape(8.dp),
            color = bgColor,
            modifier = Modifier.widthIn(max = actionBubbleWidth)
        ) {
            Column(
                modifier = Modifier.padding(10.dp)
            ) {
                // Header row with emoji and action name
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Action emoji
                    Text(text = actionType?.emoji ?: "❓", fontSize = 16.sp)

                    // Action name and subtitle
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = getActionTitle(actionDetails),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            color = textColor
                        )
                        getActionSubtitle(actionDetails)?.let { subtitle ->
                            Text(
                                text = subtitle,
                                fontSize = 10.sp,
                                color = Color(0xFF6B7280)
                            )
                        }
                    }

                    // Outcome badge
                    val outcomeText = when (actionDetails?.outcome?.lowercase()) {
                        "success" -> localizedString("mobile.interact_outcome_success")
                        "failure", "failed" -> localizedString("mobile.interact_outcome_failure")
                        "error" -> localizedString("mobile.interact_outcome_error")
                        "pending" -> localizedString("mobile.interact_outcome_pending")
                        else -> actionDetails?.outcome ?: localizedString("mobile.interact_outcome_success")
                    }
                    val outcomeColor = when (actionDetails?.outcome?.lowercase()) {
                        "success" -> Color(0xFF10B981)
                        "failure", "error", "failed" -> Color(0xFFEF4444)
                        "pending" -> Color(0xFFD97706)
                        else -> Color(0xFF6B7280)
                    }
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = outcomeColor.copy(alpha = 0.15f)
                    ) {
                        Text(
                            text = outcomeText,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            fontSize = 10.sp,
                            color = outcomeColor,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    // Expand indicator
                    Text(
                        text = if (isExpanded) "▲" else "▼",
                        fontSize = 10.sp,
                        color = Color(0xFF9CA3AF)
                    )
                }

                // Expanded details
                AnimatedVisibility(
                    visible = isExpanded,
                    enter = expandVertically() + fadeIn(),
                    exit = shrinkVertically() + fadeOut()
                ) {
                    Column(
                        modifier = Modifier.padding(top = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Divider(color = dividerColor)

                        // Action-specific details
                        ActionExpandedDetails(actionDetails = actionDetails)

                        // Timestamp
                        Text(
                            text = formatTimestamp(message.timestamp),
                            fontSize = 9.sp,
                            color = Color(0xFF9CA3AF),
                            modifier = Modifier.align(Alignment.End)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Get the main title for an action
 */
@Composable
private fun getActionTitle(details: ActionDetails?): String {
    return when (details?.actionType) {
        ActionType.SPEAK -> localizedString("mobile.interact_action_speak")
        ActionType.TOOL -> details.toolName ?: localizedString("mobile.interact_action_tool")
        ActionType.OBSERVE -> localizedString("mobile.interact_action_observe")
        ActionType.MEMORIZE -> localizedString("mobile.interact_action_memorize")
        ActionType.RECALL -> localizedString("mobile.interact_action_recall")
        ActionType.FORGET -> localizedString("mobile.interact_action_forget")
        ActionType.REJECT -> localizedString("mobile.interact_action_reject")
        ActionType.PONDER -> localizedString("mobile.interact_action_ponder")
        ActionType.DEFER -> localizedString("mobile.interact_action_defer")
        ActionType.TASK_COMPLETE -> localizedString("mobile.interact_action_task_complete")
        null -> localizedString("mobile.interact_action_generic")
    }
}

/**
 * Get the subtitle for an action (adapter, target, etc.)
 */
private fun getActionSubtitle(details: ActionDetails?): String? {
    return when (details?.actionType) {
        ActionType.TOOL -> details.toolAdapter
        ActionType.MEMORIZE, ActionType.RECALL, ActionType.FORGET -> details.memoryKey
        ActionType.DEFER -> details.deferTarget
        ActionType.PONDER -> details.ponderTopic
        else -> null
    }
}

/**
 * Expanded details for each action type
 */
@Composable
private fun ActionExpandedDetails(
    actionDetails: ActionDetails?,
    modifier: Modifier = Modifier
) {
    if (actionDetails == null) return

    Column(
        modifier = modifier.padding(top = 4.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // Description (if present)
        actionDetails.description?.let { desc ->
            if (desc.isNotBlank()) {
                SelectionContainer {
                    Text(
                        text = desc,
                        fontSize = 11.sp,
                        color = Color(0xFF374151)
                    )
                }
            }
        }

        when (actionDetails.actionType) {
            ActionType.TOOL -> {
                // Tool parameters
                if (actionDetails.toolParameters.isNotEmpty()) {
                    Text(
                        text = localizedString("mobile.interact_field_parameters"),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF374151)
                    )
                    actionDetails.toolParameters.forEach { (key, value) ->
                        Row(
                            modifier = Modifier.padding(start = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            Text(
                                text = "$key:",
                                fontSize = 10.sp,
                                color = Color(0xFF6B7280)
                            )
                            SelectionContainer {
                                Text(
                                    text = value,
                                    fontSize = 10.sp,
                                    color = Color(0xFF1F2937)
                                )
                            }
                        }
                    }
                }
                // Tool result
                actionDetails.toolResult?.let { result ->
                    Text(
                        text = localizedString("mobile.interact_field_result"),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF374151)
                    )
                    SelectionContainer {
                        Text(
                            text = result.take(300) + if (result.length > 300) "..." else "",
                            fontSize = 10.sp,
                            color = Color(0xFF1F2937),
                            modifier = Modifier.padding(start = 8.dp)
                        )
                    }
                }
            }
            ActionType.MEMORIZE, ActionType.RECALL -> {
                actionDetails.memoryContent?.let { content ->
                    Text(
                        text = localizedString("mobile.interact_field_content"),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF374151)
                    )
                    SelectionContainer {
                        Text(
                            text = content.take(200) + if (content.length > 200) "..." else "",
                            fontSize = 10.sp,
                            color = Color(0xFF1F2937),
                            modifier = Modifier.padding(start = 8.dp)
                        )
                    }
                }
            }
            ActionType.DEFER -> {
                actionDetails.deferReason?.let { reason ->
                    Text(
                        text = localizedString("mobile.interact_field_reason", mapOf("reason" to reason)),
                        fontSize = 10.sp,
                        color = Color(0xFF6B7280)
                    )
                }
            }
            ActionType.REJECT -> {
                actionDetails.rejectReason?.let { reason ->
                    Text(
                        text = localizedString("mobile.interact_field_reason", mapOf("reason" to reason)),
                        fontSize = 10.sp,
                        color = Color(0xFF6B7280)
                    )
                }
            }
            ActionType.PONDER -> {
                // Show ponder questions if available
                val questions = actionDetails.ponderQuestions
                if (questions.isNotEmpty()) {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            text = localizedString("mobile.interact_field_questions"),
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Medium,
                            color = Color(0xFF0369A1)
                        )
                        questions.forEach { question ->
                            Text(
                                text = "• $question",
                                fontSize = 10.sp,
                                color = Color(0xFF6B7280),
                                lineHeight = 14.sp
                            )
                        }
                    }
                }
            }
            else -> {
                // No additional details for SPEAK, OBSERVE, FORGET, TASK_COMPLETE
            }
        }
    }
}

/**
 * Chat input bar with send button
 * From fragment_interact.xml:243-291
 */
/**
 * Format timestamp to "h:mm a" format in local timezone
 */
private fun formatTimestamp(timestamp: Instant): String {
    val localDateTime = timestamp.toLocalDateTime(TimeZone.currentSystemDefault())
    val hours = localDateTime.hour
    val minutes = localDateTime.minute
    val amPm = if (hours < 12) "AM" else "PM"
    val displayHours = if (hours == 0) 12 else if (hours > 12) hours - 12 else hours
    return "$displayHours:${minutes.toString().padStart(2, '0')} $amPm"
}

/**
 * Chat input bar with agent state icon, attachment button, and file preview strip
 */
@Composable
@Suppress("UNUSED_PARAMETER") // bubbleEmojis handled by BubbleOverlay
private fun ChatInputBarWithBubbles(
    text: String,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit,
    enabled: Boolean,
    focusRequester: FocusRequester? = null,
    onFocused: () -> Unit = {},
    agentState: AgentProcessingState,
    bubbleEmojis: List<BubbleEmoji>, // Kept for API compatibility, bubbles rendered in overlay
    sseConnected: Boolean,
    onLegendToggle: () -> Unit = {},
    attachedFiles: List<PickedFile> = emptyList(),
    onAttach: () -> Unit = {},
    onRemoveAttachment: (Int) -> Unit = {},
    theme: InteractTheme = InteractTheme.forLiveBackground(false),
    modifier: Modifier = Modifier
) {
    val hasContent = text.isNotBlank() || attachedFiles.isNotEmpty()

    Surface(
        color = theme.inputBackground,
        shadowElevation = 4.dp,
        modifier = modifier
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            // Attachment preview strip (shown when files are attached)
            if (attachedFiles.isNotEmpty()) {
                AttachmentPreviewStrip(
                    files = attachedFiles,
                    onRemove = onRemoveAttachment,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Agent state icon (compact, no extra height) - clickable for legend
                AgentStateIcon(
                    state = agentState,
                    sseConnected = sseConnected,
                    onClick = onLegendToggle
                )

                // Attach file button
                IconButton(
                    onClick = onAttach,
                    enabled = enabled && attachedFiles.size < PickedFile.MAX_ATTACHMENTS,
                    modifier = Modifier
                        .size(36.dp)
                        .testableClickable("btn_attach") { onAttach() }
                ) {
                    Icon(
                        imageVector = Icons.Default.Add,
                        contentDescription = localizedString("mobile.interact_attach_file"),
                        tint = if (enabled) theme.textSecondary else theme.inputButtonDisabled,
                        modifier = Modifier.size(20.dp)
                    )
                }

                // Message input
                OutlinedTextField(
                    value = text,
                    onValueChange = onTextChange,
                    modifier = Modifier
                        .weight(1f)
                        .testable("input_message")
                        .let { mod ->
                            if (focusRequester != null) {
                                mod.focusRequester(focusRequester)
                            } else {
                                mod
                            }
                        }
                        .onFocusChanged { focusState ->
                            if (focusState.isFocused) {
                                onFocused()
                            }
                        },
                    placeholder = { Text(localizedString("mobile.interact_input_placeholder"), color = theme.inputPlaceholder) },
                    enabled = enabled,
                    singleLine = true,  // Single line so Enter sends
                    maxLines = 1,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(
                        onSend = { if (enabled && hasContent) onSend() }
                    ),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = theme.inputText,
                        unfocusedTextColor = theme.inputText,
                        focusedBorderColor = theme.inputButtonEnabled,
                        unfocusedBorderColor = theme.inputBorder,
                        cursorColor = theme.inputButtonEnabled
                    )
                )

                // Send button
                IconButton(
                    onClick = onSend,
                    enabled = enabled && hasContent,
                    modifier = Modifier
                        .size(48.dp)
                        .background(
                            color = if (enabled && hasContent) {
                                theme.inputButtonEnabled
                            } else {
                                theme.inputButtonDisabled
                            },
                            shape = CircleShape
                        )
                        .testableClickable("btn_send") { onSend() }
                ) {
                    Icon(
                        imageVector = Icons.Default.Send,
                        contentDescription = localizedString("mobile.interact_send"),
                        tint = Color.White
                    )
                }
            }
        }
    }
}

/**
 * Horizontal strip showing attached file previews with remove buttons
 */
@Composable
private fun AttachmentPreviewStrip(
    files: List<PickedFile>,
    onRemove: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .horizontalScroll(rememberScrollState())
            .testable("attachment_strip"),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        files.forEachIndexed { index, file ->
            AttachmentChip(
                file = file,
                onRemove = { onRemove(index) },
                modifier = Modifier.testable("attachment_chip_$index")
            )
        }
    }
}

/**
 * Individual attachment chip showing file icon, name, and remove button
 */
@Composable
private fun AttachmentChip(
    file: PickedFile,
    onRemove: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = Color(0xFFF3F4F6),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            // File type indicator
            FileTypeIcon(file = file)

            Column {
                Text(
                    text = file.name.take(20) + if (file.name.length > 20) "..." else "",
                    fontSize = 12.sp,
                    color = Color(0xFF374151),
                    maxLines = 1
                )
                Text(
                    text = formatFileSize(file.sizeBytes),
                    fontSize = 10.sp,
                    color = Color(0xFF9CA3AF)
                )
            }
            IconButton(
                onClick = onRemove,
                modifier = Modifier.size(20.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = localizedString("mobile.interact_remove"),
                    tint = Color(0xFF9CA3AF),
                    modifier = Modifier.size(14.dp)
                )
            }
        }
    }
}

/**
 * File type visual indicator - colored badge with type label
 */
@Composable
private fun FileTypeIcon(file: PickedFile, modifier: Modifier = Modifier) {
    val bgColor = if (file.isImage) Color(0xFF419CA0) else Color(0xFFEF4444)
    val label = when {
        file.mediaType.contains("jpeg") || file.mediaType.contains("jpg") -> "JPG"
        file.mediaType.contains("png") -> "PNG"
        file.mediaType.contains("gif") -> "GIF"
        file.mediaType.contains("webp") -> "WEBP"
        file.mediaType.contains("pdf") -> "PDF"
        file.mediaType.contains("wordprocessingml") || file.mediaType.contains("docx") -> "DOC"
        else -> "FILE"
    }
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = bgColor,
        modifier = modifier.size(32.dp)
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = label,
                fontSize = 8.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )
        }
    }
}

/**
 * Attachment indicator shown inside message bubbles for sent messages with files
 */
@Composable
private fun MessageAttachmentRow(
    attachmentCount: Int,
    hasImages: Boolean,
    hasDocs: Boolean,
    tintColor: Color,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // Attachment icon
        Icon(
            imageVector = Icons.Default.Add,
            contentDescription = localizedString("mobile.interact_attachments"),
            tint = tintColor,
            modifier = Modifier.size(12.dp)
        )
        val typeLabel = when {
            hasImages && hasDocs -> "$attachmentCount file${if (attachmentCount > 1) "s" else ""}"
            hasImages -> "$attachmentCount image${if (attachmentCount > 1) "s" else ""}"
            hasDocs -> "$attachmentCount document${if (attachmentCount > 1) "s" else ""}"
            else -> "$attachmentCount file${if (attachmentCount > 1) "s" else ""}"
        }
        Text(
            text = typeLabel,
            fontSize = 10.sp,
            color = tintColor,
            fontWeight = FontWeight.Medium
        )
    }
}

private fun formatFileSize(bytes: Long): String {
    return when {
        bytes < 1024 -> "${bytes}B"
        bytes < 1024 * 1024 -> "${bytes / 1024}KB"
        else -> {
            val mb = bytes / (1024.0 * 1024.0)
            val rounded = (mb * 10).toLong() / 10.0
            "${rounded}MB"
        }
    }
}

/**
 * Localize cognitive state names (WORK, PLAY, SOLITUDE, etc.)
 */
@Composable
private fun localizedCognitiveState(state: String): String {
    return when (state.uppercase()) {
        "WORK" -> localizedString("mobile.interact_state_work")
        "PLAY" -> localizedString("mobile.interact_state_play")
        "SOLITUDE" -> localizedString("mobile.interact_state_solitude")
        "DREAM" -> localizedString("mobile.interact_state_dream")
        "WAKEUP" -> localizedString("mobile.interact_state_wakeup")
        "SHUTDOWN" -> localizedString("mobile.interact_state_shutdown")
        else -> state  // Fallback to original if unknown
    }
}

/**
 * Agent state icon - shows idle or processing state
 * Clickable to show emoji legend
 */
@Composable
private fun AgentStateIcon(
    state: AgentProcessingState,
    sseConnected: Boolean,
    onClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val infiniteTransition = rememberInfiniteTransition(label = "agent_state")

    // Rotation animation for processing state
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(2000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rotation"
    )

    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = when {
            !sseConnected -> Color(0xFFE5E7EB)
            state == AgentProcessingState.PROCESSING -> Color(0xFFDBEAFE)
            else -> Color(0xFFD1FAE5)
        },
        modifier = modifier.size(40.dp).testableClickable("btn_agent_state") { onClick() }
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.fillMaxSize()
        ) {
            if (state == AgentProcessingState.PROCESSING && sseConnected) {
                Text(
                    text = "\u21BB", // ↻ clockwise circular arrow
                    fontSize = 22.sp,
                    color = Color(0xFF2563EB),
                    modifier = Modifier.graphicsLayer { rotationZ = rotation }
                )
            } else {
                Text(
                    text = if (!sseConnected) "\u26AA" else "\uD83D\uDCAD",
                    fontSize = 20.sp
                )
            }
        }
    }
}

/**
 * Full-screen bubble overlay - bubbles float up from bottom to top
 */
@Composable
private fun BubbleOverlay(
    bubbles: List<BubbleEmoji>,
    onCatch: (Long) -> Unit = {},
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier,
        contentAlignment = Alignment.BottomStart
    ) {
        bubbles.forEach { bubble ->
            FullScreenFloatingBubble(
                key = bubble.id,
                emoji = bubble.emoji,
                hasPayload = !bubble.payload.isNullOrBlank(),
                onTap = { onCatch(bubble.id) }
            )
        }
    }
}

/**
 * A floating bubble that travels the full screen height.
 *
 * If [hasPayload] is true, a subtle halo hints the bubble is tappable —
 * tapping it "catches" the bubble via [onTap] so the user can read its
 * semantic summary before it floats off screen.
 */
@Composable
private fun FullScreenFloatingBubble(
    key: Long,
    emoji: String,
    hasPayload: Boolean = false,
    onTap: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    // Animation state for this bubble
    var animationProgress by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(key) {
        // Animate from 0 to 1 over 2.5 seconds (slower for full screen travel)
        val startTime = withFrameNanos { it }
        while (true) {
            val currentTime = withFrameNanos { it }
            val elapsed = (currentTime - startTime) / 1_000_000f // Convert to ms
            animationProgress = (elapsed / 2500f).coerceIn(0f, 1f)
            if (animationProgress >= 1f) break
        }
    }

    // Eased progress for smoother motion
    val easedProgress = 1f - (1f - animationProgress) * (1f - animationProgress)

    // Float up - use a large value to travel most of the screen
    // Start from bottom, travel upward
    val offsetY = (-600).dp * easedProgress

    // Fade: full opacity at start, fade out in last 30%
    val alpha = when {
        animationProgress < 0.7f -> 1f
        else -> 1f - ((animationProgress - 0.7f) / 0.3f)
    }

    // Slight horizontal wobble for playfulness
    val wobble = kotlin.math.sin(animationProgress * 6f * 3.14159f).toFloat() * 8f

    // Tappable when carrying a payload. A faint halo hints at it so users
    // learn the affordance without any text.
    val tappableModifier = if (hasPayload) {
        Modifier
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onTap
            )
            .background(
                color = Color.White.copy(alpha = 0.15f),
                shape = CircleShape
            )
            .padding(4.dp)
    } else Modifier

    Text(
        text = emoji,
        fontSize = 28.sp,
        modifier = modifier
            .offset(x = wobble.dp, y = offsetY)
            .alpha(alpha)
            .zIndex(100f) // Ensure bubbles are on top
            .then(tappableModifier)
    )
}

/**
 * Panel showing bubbles the user has "caught" — clicking a floating bubble
 * pins its payload here so it survives past the 2s float window.
 *
 * This is the pattern that lets the client expose rich SSE semantics
 * without retaining unbounded event history: the UI only holds what the
 * user explicitly chose to keep.
 */
@Composable
private fun CaughtBubblesPanel(
    bubbles: List<BubbleEmoji>,
    theme: InteractTheme,
    onDismiss: (Long) -> Unit,
    onClearAll: () -> Unit,
    modifier: Modifier = Modifier
) {
    if (bubbles.isEmpty()) return
    Surface(
        color = theme.surface,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier.padding(horizontal = 8.dp)
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Caught (${bubbles.size})",
                    fontSize = 11.sp,
                    color = theme.textSecondary
                )
                TextButton(
                    onClick = onClearAll,
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                ) {
                    Text(text = "Clear", fontSize = 10.sp, color = theme.textMuted)
                }
            }
            bubbles.takeLast(6).reversed().forEach { b ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 2.dp)
                        .clickable { onDismiss(b.id) },
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(text = b.emoji, fontSize = 14.sp)
                    Text(
                        text = b.payload ?: "",
                        fontSize = 11.sp,
                        color = theme.textPrimary,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

/**
 * Bubble Net - shows timeline of events when tapped
 * Collapsed: just shows recent emojis in a row
 * Expanded: shows scrollable timeline with timestamps
 */
@Composable
private fun BubbleNet(
    events: List<TimelineEvent>,
    isExpanded: Boolean,
    theme: InteractTheme,
    onToggle: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier
) {
    if (events.isEmpty()) return

    Surface(
        onClick = onToggle,
        color = theme.timelineBackground,
        modifier = modifier.fillMaxWidth().testableClickable("btn_toggle_timeline") { onToggle() }
    ) {
        Column {
            // Collapsed view - horizontal row of recent emojis
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Recent emojis (last 15)
                Row(
                    horizontalArrangement = Arrangement.spacedBy(2.dp)
                ) {
                    events.takeLast(15).forEach { event ->
                        Text(
                            text = event.emoji,
                            fontSize = 14.sp
                        )
                    }
                }

                // Expand indicator and count
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "${events.size}",
                        fontSize = 11.sp,
                        color = theme.timelineText
                    )
                    Text(
                        text = if (isExpanded) "▲" else "▼",
                        fontSize = 10.sp,
                        color = theme.timelineText
                    )
                }
            }

            // Expanded view - scrollable timeline
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 200.dp)
                        .padding(horizontal = 12.dp, vertical = 8.dp)
                ) {
                    // Clear button
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(
                            onClick = onClear,
                            modifier = Modifier.testableClickable("btn_clear_timeline") { onClear() },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Text(
                                text = localizedString("mobile.interact_clear"),
                                fontSize = 11.sp,
                                color = Color(0xFF059669)
                            )
                        }
                    }

                    // Timeline rows
                    LazyColumn(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(2.dp)
                    ) {
                        items(events.reversed()) { event ->
                            TimelineRow(event = event, theme = theme)
                        }
                    }
                }
            }
        }
    }
}

/**
 * A single row in the timeline
 */
@Composable
private fun TimelineRow(
    event: TimelineEvent,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Timestamp - use theme color for readability
        Text(
            text = formatTimelineTimestamp(event.timestamp),
            fontSize = 10.sp,
            color = theme.timelineText,
            modifier = Modifier.width(60.dp)
        )

        // Emoji
        Text(
            text = event.emoji,
            fontSize = 16.sp
        )

        // Action name - use theme color for readability
        Text(
            text = event.eventType,
            fontSize = 11.sp,
            color = theme.timelineText
        )
    }
}

/**
 * Format timestamp for timeline (h:mm:ss)
 */
private fun formatTimelineTimestamp(epochMillis: Long): String {
    val instant = Instant.fromEpochMilliseconds(epochMillis)
    val localDateTime = instant.toLocalDateTime(TimeZone.currentSystemDefault())
    val hours = localDateTime.hour
    val minutes = localDateTime.minute
    val seconds = localDateTime.second
    val displayHours = if (hours == 0) 12 else if (hours > 12) hours - 12 else hours
    return "$displayHours:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}"
}

/**
 * Emoji legend dialog - shows all 10 CIRIS action emojis with descriptions
 */
@Composable
private fun EmojiLegendDialog(
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = modifier,
        title = {
            Text(
                text = localizedString("mobile.interact_legend_title"),
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Processing stages
                Text(
                    text = localizedString("mobile.interact_legend_processing"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("🤔", localizedString("mobile.interact_legend_thought_start"))
                LegendRow("📋", localizedString("mobile.interact_legend_snapshot"))
                LegendRow("⚖️", localizedString("mobile.interact_legend_dma"))
                LegendRow("〰️", localizedString("mobile.interact_legend_idma"))
                LegendRow("🎯", localizedString("mobile.interact_legend_action_selection"))
                LegendRow("🔧", localizedString("mobile.interact_legend_tsaspdma"))
                LegendRow("🧭", localizedString("mobile.interact_legend_conscience"))

                Spacer(modifier = Modifier.height(8.dp))

                // External actions
                Text(
                    text = localizedString("mobile.interact_legend_external"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("👀", localizedString("mobile.interact_legend_observe"))
                LegendRow("💬", localizedString("mobile.interact_legend_speak"))
                LegendRow("🔧", localizedString("mobile.interact_legend_tool"))

                Spacer(modifier = Modifier.height(8.dp))

                // Control actions
                Text(
                    text = localizedString("mobile.interact_legend_control"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("❌", localizedString("mobile.interact_legend_reject"))
                LegendRow("💭", localizedString("mobile.interact_legend_ponder"))
                LegendRow("⏸️", localizedString("mobile.interact_legend_defer"))

                Spacer(modifier = Modifier.height(8.dp))

                // Memory actions
                Text(
                    text = localizedString("mobile.interact_legend_memory"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("💾", localizedString("mobile.interact_legend_memorize"))
                LegendRow("🔍", localizedString("mobile.interact_legend_recall"))
                LegendRow("🗑️", localizedString("mobile.interact_legend_forget"))

                Spacer(modifier = Modifier.height(8.dp))

                // Terminal action
                Text(
                    text = localizedString("mobile.interact_legend_terminal"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("✅", localizedString("mobile.interact_legend_task_complete"))

                Spacer(modifier = Modifier.height(8.dp))

                // Agent state icons
                Text(
                    text = localizedString("mobile.interact_legend_agent_status"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("💭", localizedString("mobile.interact_legend_idle"))
                LegendRow("🔄", localizedString("mobile.interact_legend_processing_icon"))
                LegendRow("⚪", localizedString("mobile.interact_legend_disconnected"))

                Spacer(modifier = Modifier.height(8.dp))

                // Gestures — kept in the legend so the interact surface itself
                // stays clean of nagging hint overlays.
                Text(
                    text = "Gestures",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                LegendRow("↔️", "Swipe the background to spin the visualization")
                LegendRow("⚡", "Flick repeatedly — a bit of energy shatters it, then it reforms")
                LegendRow("🔍", "Tap the VIZ toggle to expand the scene to full screen")
            }
        },
        confirmButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_close_legend") { onDismiss() }
            ) {
                Text(localizedString("mobile.interact_close"))
            }
        }
    )
}

/**
 * A row in the emoji legend
 */
@Composable
private fun LegendRow(
    emoji: String,
    description: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = emoji,
            fontSize = 18.sp,
            modifier = Modifier.width(28.dp)
        )
        Text(
            text = description,
            fontSize = 14.sp,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * Visualization legend button - question mark that expands to show
 * H3ERE pipeline stages and graph node colors
 */
@Composable
private fun VisualizationLegendButton(
    isExpanded: Boolean,
    onToggle: () -> Unit,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.End
    ) {
        // Expandable legend panel
        AnimatedVisibility(
            visible = isExpanded,
            enter = expandVertically(expandFrom = Alignment.Bottom) + fadeIn(),
            exit = shrinkVertically(shrinkTowards = Alignment.Bottom) + fadeOut()
        ) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = theme.surface.copy(alpha = 0.9f),
                shadowElevation = 4.dp,
                modifier = Modifier
                    .widthIn(max = 200.dp)
                    .padding(bottom = 8.dp)
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Title
                    Text(
                        text = localizedString("mobile.interact_viz_title"),
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = theme.textPrimary
                    )

                    // Pipeline stages (bottom to top to match visualization)
                    VisualizationLegendItem("THINK", Color(0xFF60A5FA), localizedString("mobile.interact_viz_think"), theme)
                    VisualizationLegendItem("CONTEXT", Color(0xFF34D399), localizedString("mobile.interact_viz_context"), theme)
                    VisualizationLegendItem("DMA", Color(0xFFFBBF24), localizedString("mobile.interact_viz_dma"), theme)
                    VisualizationLegendItem("IDMA", Color(0xFFF97316), localizedString("mobile.interact_viz_idma"), theme)
                    VisualizationLegendItem("SELECT", Color(0xFFA78BFA), localizedString("mobile.interact_viz_select"), theme)
                    VisualizationLegendItem("ETHICS", Color(0xFF38BDF8), localizedString("mobile.interact_viz_ethics"), theme)
                    VisualizationLegendItem("ACT", Color(0xFF4ADE80), localizedString("mobile.interact_viz_act"), theme)

                    Divider(color = theme.textMuted.copy(alpha = 0.3f))

                    // Graph nodes
                    Text(
                        text = localizedString("mobile.interact_viz_memory"),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                        color = theme.textSecondary
                    )
                    VisualizationLegendItem("LOCAL", theme.textAccent, localizedString("mobile.interact_viz_local"), theme)
                    VisualizationLegendItem("IDENTITY", theme.textSecondary, localizedString("mobile.interact_viz_identity"), theme)
                    VisualizationLegendItem("ENVIRON", theme.statusConnected, localizedString("mobile.interact_viz_environ"), theme)
                }
            }
        }

        // Question mark button - larger and more visible
        Surface(
            onClick = onToggle,
            shape = CircleShape,
            color = theme.surface.copy(alpha = 0.95f),
            shadowElevation = 4.dp,
            modifier = Modifier.size(56.dp)
        ) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.fillMaxSize()
            ) {
                Text(
                    text = "?",
                    fontSize = 28.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = theme.textAccent
                )
            }
        }
    }
}

/**
 * Single item in the visualization legend
 */
@Composable
private fun VisualizationLegendItem(
    label: String,
    color: Color,
    description: String,
    theme: InteractTheme,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Color dot
        Box(
            modifier = Modifier
                .size(10.dp)
                .background(color, CircleShape)
        )
        // Label
        Text(
            text = label,
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = color,
            modifier = Modifier.width(60.dp)
        )
        // Description
        Text(
            text = description,
            fontSize = 9.sp,
            color = theme.textMuted
        )
    }
}

/**
 * FG detail panel — the transparency surface that opens when the user
 * taps a selectable element on the frozen cell diagram in Foreground
 * mode (FSD §12). Renders a compact summary of *this* element's live
 * state alongside a deeplink to the existing full-detail screen (e.g.
 * Adapters, Memory, System, LLM Settings) for drill-in.
 *
 * Framing discipline (per CIRIS accord):
 *   - Transparency by default — the element's live fields are visible,
 *     not hidden behind expert toggles.
 *   - Incompleteness is first-class — a NucleusShell with no recent
 *     events reads as "no recent activity" not as an error.
 *   - No anthropomorphizing. Panels narrate *what the system did by
 *     design*, never what the agent "feels" or "wants".
 *   - No surveillance framing — never "monitoring" / "tracking" /
 *     "profile" language for adapter channels.
 *
 * Hosts the kind-tagged content below the chat-bar area so it shares
 * vertical rhythm with the existing Interact chrome. A close button
 * dismisses back to the plain cell view.
 */
@Composable
private fun FgDetailPanel(
    selection: ai.ciris.mobile.shared.ui.screens.graph.SelectionKind,
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail?,
    theme: InteractTheme,
    onDismiss: () -> Unit,
    onOpenLLMSettings: () -> Unit,
    onOpenWiseAuthority: () -> Unit,
    onOpenSystem: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        shape = RoundedCornerShape(8.dp),
        color = theme.surface.copy(alpha = 0.96f),
        shadowElevation = if (theme.isDark) 0.dp else 4.dp,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Header row: kind label + dismiss button.
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = kindLabel(selection),
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = theme.textPrimary,
                )
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = Color.Transparent,
                    modifier = Modifier.testableClickable("btn_fg_detail_close") { onDismiss() },
                ) {
                    Text(
                        text = "✕",
                        fontSize = 14.sp,
                        color = theme.textMuted,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                    )
                }
            }

            // Body — kind-specific rendering against the live detail.
            when (val d = detail) {
                null, is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.Loading -> {
                    Text(
                        text = d?.summaryLine ?: "Loading…",
                        fontSize = 12.sp,
                        color = theme.textSecondary,
                    )
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.Error -> {
                    Text(
                        text = d.summaryLine,
                        fontSize = 12.sp,
                        color = theme.statusDisconnected,
                    )
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.AdapterPort -> {
                    AdapterPortBody(detail = d, theme = theme)
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.BusArc -> {
                    BusArcBody(
                        detail = d,
                        theme = theme,
                        onOpenLLMSettings = onOpenLLMSettings,
                        onOpenWiseAuthority = onOpenWiseAuthority,
                    )
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.NucleusShell -> {
                    NucleusShellBody(detail = d, theme = theme)
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.NucleusCore -> {
                    NucleusCoreBody(detail = d, theme = theme, onOpenSystem = onOpenSystem)
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.Mote -> {
                    MoteBody(detail = d, theme = theme)
                }
                is ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.Gratitude -> {
                    Text(
                        text = d.summaryLine,
                        fontSize = 12.sp,
                        color = theme.textSecondary,
                    )
                }
            }
        }
    }
}

private fun kindLabel(kind: ai.ciris.mobile.shared.ui.screens.graph.SelectionKind): String = when (kind) {
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.AdapterPort ->
        "Adapter · ${kind.adapterType}"
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.BusArc ->
        "${kind.bus.name} bus"
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.NucleusShell ->
        "Pipeline stage · ${kind.eventType.replace('_', ' ')}"
    ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.NucleusCore ->
        "Agent core"
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.CytoplasmMote ->
        "Memory node · ${kind.scope}"
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.SignalChannel ->
        "Signal channel · ${kind.bus.name}"
    is ai.ciris.mobile.shared.ui.screens.graph.SelectionKind.GratitudeMote ->
        "Signalled gratitude"
}

@Composable
private fun AdapterPortBody(
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.AdapterPort,
    theme: InteractTheme,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        DetailRow(label = "id", value = detail.adapterId, theme = theme)
        DetailRow(
            label = "status",
            value = if (detail.isRunning) "running" else "stopped",
            theme = theme,
        )
        DetailRow(label = "messages", value = "${detail.messagesProcessed}", theme = theme)
        if (detail.errorsCount > 0) {
            DetailRow(
                label = "errors",
                value = "${detail.errorsCount}",
                theme = theme,
                valueColor = theme.statusDisconnected,
            )
        }
        detail.lastError?.let {
            DetailRow(label = "last error", value = it.take(80), theme = theme,
                valueColor = theme.statusDisconnected)
        }
        detail.lastActivity?.let {
            DetailRow(label = "last activity", value = it, theme = theme)
        }
    }
}

@Composable
private fun BusArcBody(
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.BusArc,
    theme: InteractTheme,
    onOpenLLMSettings: () -> Unit,
    onOpenWiseAuthority: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (detail.llmProviders.isNotEmpty()) {
            Text(
                text = "${detail.llmProviders.size} provider(s)",
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
                color = theme.textPrimary,
            )
            detail.llmProviders.forEach { p ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .background(
                                color = if (p.healthy) theme.statusConnected
                                    else theme.statusDisconnected,
                                shape = CircleShape,
                            ),
                    )
                    Text(text = p.name, fontSize = 11.sp, color = theme.textPrimary)
                    Text(
                        text = "· cb=${p.circuitBreakerState}",
                        fontSize = 10.sp,
                        color = theme.textMuted,
                    )
                    if (p.rateLimited) {
                        Text(
                            text = "· rate-limited",
                            fontSize = 10.sp,
                            color = theme.trustLevel4,
                        )
                    }
                }
            }
        } else {
            DetailRow(label = "messages sent", value = "${detail.messagesSent}", theme = theme)
            DetailRow(
                label = "avg latency",
                value = "${detail.averageLatencyMs.toInt()} ms",
                theme = theme,
            )
            DetailRow(label = "queue", value = "${detail.queueDepth}", theme = theme)
            if (detail.errorsLastHour > 0) {
                DetailRow(
                    label = "errors/h",
                    value = "${detail.errorsLastHour}",
                    theme = theme,
                    valueColor = theme.statusDisconnected,
                )
            }
        }

        // Deeplink to the matching full screen.
        val (label, action) = when (detail.bus) {
            ai.ciris.mobile.shared.ui.screens.graph.CellBus.LLM ->
                "Open LLM settings" to onOpenLLMSettings
            ai.ciris.mobile.shared.ui.screens.graph.CellBus.WISE ->
                "Open Wise Authority" to onOpenWiseAuthority
            else -> null to null
        }
        if (label != null && action != null) {
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = theme.textAccent.copy(alpha = 0.15f),
                modifier = Modifier.testableClickable("btn_fg_detail_open") { action() },
            ) {
                Text(
                    text = label,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                    color = theme.textAccent,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun NucleusShellBody(
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.NucleusShell,
    theme: InteractTheme,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (detail.recentEvents.isEmpty()) {
            Text(
                text = "No recent activity on this stage.",
                fontSize = 12.sp,
                color = theme.textMuted,
            )
        } else {
            detail.recentEvents.asReversed().forEach { ev ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Text(text = ev.emoji, fontSize = 14.sp)
                    Text(
                        text = ev.payload ?: "(no payload)",
                        fontSize = 11.sp,
                        color = theme.textPrimary,
                        lineHeight = 14.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun NucleusCoreBody(
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.NucleusCore,
    theme: InteractTheme,
    onOpenSystem: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        DetailRow(label = "cognitive state", value = detail.cognitiveState, theme = theme)
        DetailRow(label = "system", value = detail.systemStatus, theme = theme)
        DetailRow(
            label = "services",
            value = "${detail.servicesOnline}/${detail.servicesTotal}",
            theme = theme,
        )
        Surface(
            shape = RoundedCornerShape(4.dp),
            color = theme.textAccent.copy(alpha = 0.15f),
            modifier = Modifier.testableClickable("btn_fg_detail_open_system") { onOpenSystem() },
        ) {
            Text(
                text = "Open system",
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                color = theme.textAccent,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            )
        }
    }
}

@Composable
private fun MoteBody(
    detail: ai.ciris.mobile.shared.viewmodels.InteractViewModel.SelectionDetail.Mote,
    theme: InteractTheme,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        DetailRow(label = "id", value = detail.nodeId.take(24), theme = theme)
        DetailRow(label = "type", value = detail.nodeType ?: "—", theme = theme)
        DetailRow(label = "scope", value = detail.scope, theme = theme)
        detail.attributesJson?.let {
            Text(
                text = it.take(300),
                fontSize = 10.sp,
                color = theme.textMuted,
                lineHeight = 13.sp,
            )
        }
    }
}

@Composable
private fun DetailRow(
    label: String,
    value: String,
    theme: InteractTheme,
    valueColor: Color? = null,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = label,
            fontSize = 11.sp,
            color = theme.textMuted,
            modifier = Modifier.width(100.dp),
        )
        Text(
            text = value,
            fontSize = 11.sp,
            color = valueColor ?: theme.textPrimary,
        )
    }
}
