package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.ui.graphics.Color
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

    // Focus requester for the text input
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    // Note: CIRISApp wraps this screen in a Scaffold with TopAppBar,
    // so we don't need our own Scaffold here. Just use the column directly.
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFFAFAFA)) // Light gray background
            .imePadding() // Handle keyboard insets
    ) {
        // Status bar (from fragment_interact.xml:10-63)
        ConnectionStatusBar(
            isConnected = isConnected,
            status = agentStatus,
            onShutdown = { viewModel.shutdown(emergency = false) },
            onEmergencyStop = { viewModel.shutdown(emergency = true) }
        )

        // AI Warning banner (from fragment_interact.xml:65-76)
        AIWarningBanner()

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

        // Input bar (from fragment_interact.xml:243-291)
        ChatInputBar(
            text = inputText,
            onTextChange = { viewModel.onInputTextChanged(it) },
            onSend = { viewModel.sendMessage() },
            enabled = isConnected && !isSending,
            focusRequester = focusRequester,
            onFocused = { keyboardController?.show() },
            modifier = Modifier
                .fillMaxWidth()
                .windowInsetsPadding(WindowInsets.navigationBars)
        )
    }
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
        items(messages.reversed(), key = { it.id }) { message ->
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
    return String.format("%d:%02d %s", displayHours, minutes, amPm)
}
