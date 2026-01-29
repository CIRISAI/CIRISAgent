package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.viewmodels.AgentProcessingState
import ai.ciris.mobile.shared.viewmodels.BubbleEmoji
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import ai.ciris.mobile.shared.viewmodels.TimelineEvent
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.zIndex
import kotlinx.datetime.Instant

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
    val agentProcessingState by viewModel.agentProcessingState.collectAsState()
    val sseConnected by viewModel.sseConnected.collectAsState()
    val timelineEvents by viewModel.timelineEvents.collectAsState()
    val showTimeline by viewModel.showTimeline.collectAsState()
    val showLegend by viewModel.showLegend.collectAsState()

    // Focus requester for the text input
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    // Note: CIRISApp wraps this screen in a Scaffold with TopAppBar,
    // so we don't need our own Scaffold here. Use Box for bubble overlay.
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFFAFAFA))
            .windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars))
    ) {
        // Main content column
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            // Status bar (from fragment_interact.xml:10-63)
            ConnectionStatusBar(
            isConnected = isConnected,
            status = agentStatus,
            onShutdown = { viewModel.shutdown(emergency = false) },
            onEmergencyStop = { viewModel.shutdown(emergency = true) }
        )

        // Auth error banner - shown when session expires
        AnimatedVisibility(
            visible = authError != null,
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            AuthErrorBanner(
                message = authError ?: "",
                onDismiss = { viewModel.clearAuthError() }
            )
        }

        // AI Warning banner (from fragment_interact.xml:65-76)
        AIWarningBanner()

        // Bubble Net - timeline of events (expandable)
        BubbleNet(
            events = timelineEvents,
            isExpanded = showTimeline,
            onToggle = { viewModel.toggleTimeline() },
            onClear = { viewModel.clearTimeline() }
        )

        // Processing status (from fragment_interact.xml:78-117)
        AnimatedVisibility(
            visible = processingStatus.isNotEmpty(),
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            ProcessingStatusBar(status = processingStatus)
        }

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
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            if (messages.isEmpty() && !isLoading) {
                EmptyStateView()
            } else {
                ChatMessageList(messages = messages)
            }
        }

        // Message count indicator (from fragment_interact.xml:192-200)
        if (messages.isNotEmpty()) {
            Text(
                text = "Showing last ${messages.size} messages",
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color.White)
                    .padding(horizontal = 12.dp, vertical = 4.dp),
                fontSize = 11.sp,
                color = Color(0xFF9CA3AF),
                textAlign = TextAlign.Center
            )
        }

            // Input bar with agent state icon
            // Note: Don't use windowInsetsPadding(navigationBars) here as it conflicts
            // with imePadding() on parent, creating a gap when keyboard is open
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
                modifier = Modifier.fillMaxWidth()
            )
        } // End of Column

        // Emoji legend dialog
        if (showLegend) {
            EmojiLegendDialog(onDismiss = { viewModel.toggleLegend() })
        }

        // Bubble overlay - floats up from bottom-left over the entire screen
        BubbleOverlay(
            bubbles = bubbleEmojis,
            modifier = Modifier
                .fillMaxSize()
                .padding(start = 8.dp, bottom = 70.dp) // Align with agent icon position
        )
    } // End of Box
}

/**
 * Connection status bar with shutdown controls
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
                text = if (isConnected) "Connected" else "Disconnected",
                modifier = Modifier.weight(1f),
                fontSize = 14.sp,
                color = if (isConnected) Color(0xFF10B981) else Color(0xFFEF4444)
            )

            // Shutdown button (from fragment_interact.xml:37-48)
            OutlinedButton(
                onClick = onShutdown,
                modifier = Modifier.height(32.dp),
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
                modifier = Modifier.height(32.dp),
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
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Text(
                    text = "Dismiss",
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
private fun AIWarningBanner(modifier: Modifier = Modifier) {
    Text(
        text = "⚠️ AI HALLUCINATES - CHECK FACTS",
        modifier = modifier
            .fillMaxWidth()
            .background(Color(0xFFFEF3C7))
            .padding(horizontal = 12.dp, vertical = 4.dp),
        fontSize = 11.sp,
        color = Color(0xFFB45309),
        textAlign = TextAlign.Center
    )
}

/**
 * Processing status indicator
 * From fragment_interact.xml:78-117
 */
@Composable
private fun ProcessingStatusBar(
    status: String,
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color(0xFFF0F9FF),
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = getStatusEmoji(status),
                fontSize = 16.sp
            )
            Text(
                text = status,
                modifier = Modifier.weight(1f),
                fontSize = 12.sp,
                color = Color(0xFF0369A1),
                maxLines = 1
            )
        }
    }
}

/**
 * Get emoji for processing status
 * Based on InteractFragment.kt:525-562
 */
private fun getStatusEmoji(status: String): String {
    return when {
        status.contains("Thinking") -> "🤔"
        status.contains("context") -> "📋"
        status.contains("Evaluating") -> "⚖️"
        status.contains("Selecting action") -> "🎯"
        status.contains("ethics") -> "🧭"
        status.contains("Speaking") -> "💬"
        status.contains("Complete") -> "✅"
        status.contains("memory") -> "💾"
        status.contains("Recalling") -> "🔍"
        status.contains("tool") -> "🔧"
        status.contains("Pondering") -> "💭"
        status.contains("Deferred") -> "⏸️"
        else -> "⏳"
    }
}

/**
 * Empty state view for first launch
 * From fragment_interact.xml:142-188
 */
@Composable
private fun EmptyStateView(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF3F4F6))
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
            text = "Welcome to Ally",
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF1F2937),
            modifier = Modifier.padding(bottom = 12.dp)
        )

        // Subtitle (from fragment_interact.xml:169-175)
        Text(
            text = "Your personal thriving assistant",
            fontSize = 14.sp,
            color = Color(0xFF6B7280),
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Hint text (from fragment_interact.xml:177-186)
        Text(
            text = "Ask Ally how it can help with tasks, scheduling, decisions, or wellbeing — or ask how CIRIS works!",
            fontSize = 14.sp,
            color = Color(0xFF419CA0),
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
    modifier: Modifier = Modifier
) {
    val listState = rememberLazyListState()

    LazyColumn(
        state = listState,
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF3F4F6))
            .padding(8.dp),
        reverseLayout = true,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // Use distinctBy to prevent duplicate key crashes if same ID appears twice
        items(messages.reversed().distinctBy { it.id }, key = { it.id }) { message ->
            when (message.type) {
                MessageType.USER -> UserChatBubble(message)
                MessageType.AGENT -> AgentChatBubble(message)
                MessageType.SYSTEM -> SystemMessage(message)
                MessageType.ERROR -> ErrorMessage(message)
            }
        }
    }

    // Auto-scroll to latest message
    LaunchedEffect(messages.size) {
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
private fun UserChatBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.End
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 280.dp)
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
                text = "You",
                fontSize = 11.sp,
                color = Color(0xFFDBEAFE)
            )

            // Content (from item_chat_user.xml:25-32)
            Text(
                text = message.text,
                modifier = Modifier.padding(top = 2.dp),
                fontSize = 14.sp,
                color = Color.White
            )

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
private fun AgentChatBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Start
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 280.dp)
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
                text = "CIRIS",
                fontSize = 11.sp,
                color = Color(0xFF6B7280)
            )

            // Content (from item_chat_agent.xml:25-32)
            Text(
                text = message.text,
                modifier = Modifier.padding(top = 2.dp),
                fontSize = 14.sp,
                color = Color(0xFF1F2937)
            )

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
private fun SystemMessage(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFFE0F2FE), // Light blue info background
            modifier = Modifier.widthIn(max = 280.dp)
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
                Text(
                    text = message.text,
                    fontSize = 12.sp,
                    color = Color(0xFF0369A1) // Dark blue text
                )
            }
        }
    }
}

/**
 * Error message (error/warning notifications)
 * Styled with light red/orange background and warning styling
 */
@Composable
private fun ErrorMessage(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFFFEE2E2), // Light red error background
            modifier = Modifier.widthIn(max = 280.dp)
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
                Text(
                    text = message.text,
                    fontSize = 12.sp,
                    color = Color(0xFFDC2626) // Red text
                )
            }
        }
    }
}

/**
 * Chat input bar with send button
 * From fragment_interact.xml:243-291
 */
@Composable
private fun ChatInputBar(
    text: String,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit,
    enabled: Boolean,
    focusRequester: FocusRequester? = null,
    onFocused: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color.White,
        shadowElevation = 4.dp,
        modifier = modifier
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Message input (from fragment_interact.xml:264-277)
            OutlinedTextField(
                value = text,
                onValueChange = onTextChange,
                modifier = Modifier
                    .weight(1f)
                    .testTag("input_message")
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
                placeholder = { Text("Type your message...") },
                enabled = enabled,
                singleLine = false,
                maxLines = 3,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF419CA0),
                    unfocusedBorderColor = Color(0xFFE5E7EB)
                )
            )

            // Send button (from fragment_interact.xml:279-289)
            IconButton(
                onClick = onSend,
                enabled = enabled && text.isNotBlank(),
                modifier = Modifier
                    .size(48.dp)
                    .background(
                        color = if (enabled && text.isNotBlank()) {
                            Color(0xFF419CA0)
                        } else {
                            Color(0xFFE5E7EB)
                        },
                        shape = CircleShape
                    )
                    .testTag("btn_send")
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send",
                    tint = Color.White
                )
            }
        }
    }
}

/**
 * Format timestamp to "h:mm a" format
 * From InteractFragment.kt:732-742
 */
private fun formatTimestamp(timestamp: Instant): String {
    // Simple format: hours:minutes
    val epochMillis = timestamp.toEpochMilliseconds()
    val hours = ((epochMillis / 3600000) % 24).toInt()
    val minutes = ((epochMillis / 60000) % 60).toInt()
    val amPm = if (hours < 12) "AM" else "PM"
    val displayHours = if (hours == 0) 12 else if (hours > 12) hours - 12 else hours
    return "$displayHours:${minutes.toString().padStart(2, '0')} $amPm"
}

/**
 * Chat input bar with agent state icon (no gap - bubbles overlay separately)
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
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color.White,
        shadowElevation = 4.dp,
        modifier = modifier
    ) {
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

            // Message input
            OutlinedTextField(
                value = text,
                onValueChange = onTextChange,
                modifier = Modifier
                    .weight(1f)
                    .testTag("input_message")
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
                placeholder = { Text("Type your message...") },
                enabled = enabled,
                singleLine = false,
                maxLines = 3,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF419CA0),
                    unfocusedBorderColor = Color(0xFFE5E7EB)
                )
            )

            // Send button
            IconButton(
                onClick = onSend,
                enabled = enabled && text.isNotBlank(),
                modifier = Modifier
                    .size(48.dp)
                    .background(
                        color = if (enabled && text.isNotBlank()) {
                            Color(0xFF419CA0)
                        } else {
                            Color(0xFFE5E7EB)
                        },
                        shape = CircleShape
                    )
                    .testTag("btn_send")
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send",
                    tint = Color.White
                )
            }
        }
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
        modifier = modifier.size(40.dp)
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.fillMaxSize()
        ) {
            Text(
                text = when {
                    !sseConnected -> "⚪"
                    state == AgentProcessingState.PROCESSING -> "🔄"
                    else -> "💭"
                },
                fontSize = 20.sp,
                modifier = if (state == AgentProcessingState.PROCESSING && sseConnected) {
                    Modifier.graphicsLayer { rotationZ = rotation }
                } else {
                    Modifier
                }
            )
        }
    }
}

/**
 * Full-screen bubble overlay - bubbles float up from bottom to top
 */
@Composable
private fun BubbleOverlay(
    bubbles: List<BubbleEmoji>,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier,
        contentAlignment = Alignment.BottomStart
    ) {
        bubbles.forEach { bubble ->
            FullScreenFloatingBubble(
                key = bubble.id,
                emoji = bubble.emoji
            )
        }
    }
}

/**
 * A floating bubble that travels the full screen height
 */
@Composable
private fun FullScreenFloatingBubble(
    key: Long,
    emoji: String,
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

    Text(
        text = emoji,
        fontSize = 28.sp,
        modifier = modifier
            .offset(x = wobble.dp, y = offsetY)
            .alpha(alpha)
            .zIndex(100f) // Ensure bubbles are on top
    )
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
    onToggle: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier
) {
    if (events.isEmpty()) return

    Surface(
        onClick = onToggle,
        color = Color(0xFFF0FDF4), // Light green background
        modifier = modifier.fillMaxWidth()
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
                        color = Color(0xFF059669)
                    )
                    Text(
                        text = if (isExpanded) "▲" else "▼",
                        fontSize = 10.sp,
                        color = Color(0xFF059669)
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
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Text(
                                text = "Clear",
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
                            TimelineRow(event = event)
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
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Timestamp
        Text(
            text = formatTimelineTimestamp(event.timestamp),
            fontSize = 10.sp,
            color = Color(0xFF6B7280),
            modifier = Modifier.width(60.dp)
        )

        // Emoji
        Text(
            text = event.emoji,
            fontSize = 16.sp
        )

        // Action name
        Text(
            text = event.eventType,
            fontSize = 11.sp,
            color = Color(0xFF4B5563)
        )
    }
}

/**
 * Format timestamp for timeline (h:mm:ss)
 */
private fun formatTimelineTimestamp(epochMillis: Long): String {
    val hours = ((epochMillis / 3600000) % 24).toInt()
    val minutes = ((epochMillis / 60000) % 60).toInt()
    val seconds = ((epochMillis / 1000) % 60).toInt()
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
                text = "CIRIS Action Emojis",
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Processing stages
                Text(
                    text = "Processing Stages",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("🤔", "Thought Start")
                LegendRow("📋", "Snapshot & Context")
                LegendRow("⚖️", "DMA Results")
                LegendRow("🎯", "Action Selection")
                LegendRow("🧭", "Conscience Check")

                Spacer(modifier = Modifier.height(8.dp))

                // External actions
                Text(
                    text = "External Actions",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("👀", "Observe")
                LegendRow("💬", "Speak")
                LegendRow("🔧", "Tool")

                Spacer(modifier = Modifier.height(8.dp))

                // Control actions
                Text(
                    text = "Control Actions",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("❌", "Reject")
                LegendRow("💭", "Ponder")
                LegendRow("⏸️", "Defer")

                Spacer(modifier = Modifier.height(8.dp))

                // Memory actions
                Text(
                    text = "Memory Actions",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("💾", "Memorize")
                LegendRow("🔍", "Recall")
                LegendRow("🗑️", "Forget")

                Spacer(modifier = Modifier.height(8.dp))

                // Terminal action
                Text(
                    text = "Terminal",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("✅", "Task Complete")

                Spacer(modifier = Modifier.height(8.dp))

                // Agent state icons
                Text(
                    text = "Agent Status",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF6B7280)
                )
                LegendRow("💭", "Idle")
                LegendRow("🔄", "Processing")
                LegendRow("⚪", "Disconnected")
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Close")
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
            color = Color(0xFF1F2937)
        )
    }
}
