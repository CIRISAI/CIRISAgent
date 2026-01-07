package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
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
import androidx.compose.ui.unit.dp

/**
 * Chat interface screen
 * Based on InteractActivity.kt and activity_interact.xml
 * Replaces Android RecyclerView with Compose LazyColumn
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Chat with CIRIS") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = Color.White
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Status bar (replaces statusDot and statusText from InteractActivity.kt:54-55)
            AgentStatusBar(
                isConnected = isConnected,
                status = agentStatus
            )

            // Shutdown controls (from InteractActivity.kt:56-57)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = { viewModel.shutdown(emergency = false) },
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Graceful Shutdown")
                }

                Button(
                    onClick = { viewModel.shutdown(emergency = true) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Emergency Stop")
                }
            }

            // Chat messages (replaces RecyclerView from InteractActivity.kt:95)
            val listState = rememberLazyListState()

            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                reverseLayout = true, // Latest messages at bottom
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(messages.reversed(), key = { it.id }) { message ->
                    when (message.type) {
                        MessageType.USER -> UserChatBubble(message)
                        MessageType.AGENT -> AgentChatBubble(message)
                        MessageType.SYSTEM -> SystemMessage(message)
                    }
                }
            }

            // Input bar (replaces messageInput and sendButton from InteractActivity.kt:52-53)
            ChatInputBar(
                text = inputText,
                onTextChange = { viewModel.onInputTextChanged(it) },
                onSend = { viewModel.sendMessage() },
                enabled = isConnected && !isSending,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

@Composable
private fun AgentStatusBar(
    isConnected: Boolean,
    status: String,
    modifier: Modifier = Modifier
) {
    Surface(
        color = if (isConnected) Color(0xFF00d4ff) else Color(0xFF888888),
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Status dot (replaces statusDot View from InteractActivity.kt:54)
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .background(
                        color = if (isConnected) Color(0xFF00ff00) else Color.Gray,
                        shape = CircleShape
                    )
            )

            Text(
                text = if (isConnected) "Connected - $status" else "Disconnected",
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White,
                fontWeight = FontWeight.Medium
            )
        }
    }
}

@Composable
private fun UserChatBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.End
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp),
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Text(
                text = message.text,
                modifier = Modifier.padding(12.dp),
                color = Color.White,
                style = MaterialTheme.typography.bodyLarge
            )
        }
    }
}

@Composable
private fun AgentChatBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.Start
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = message.text,
                    style = MaterialTheme.typography.bodyLarge
                )

                // Show reasoning if available (from item_chat_agent.xml)
                message.reasoning?.let { reasoning ->
                    Text(
                        text = "Reasoning: $reasoning",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun SystemMessage(message: ChatMessage, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = MaterialTheme.colorScheme.secondaryContainer,
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Text(
                text = message.text,
                modifier = Modifier.padding(8.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSecondaryContainer
            )
        }
    }
}

@Composable
private fun ChatInputBar(
    text: String,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit,
    enabled: Boolean,
    modifier: Modifier = Modifier
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 3.dp,
        modifier = modifier
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedTextField(
                value = text,
                onValueChange = onTextChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Type a message...") },
                enabled = enabled,
                singleLine = false,
                maxLines = 4
            )

            IconButton(
                onClick = onSend,
                enabled = enabled && text.isNotBlank()
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send",
                    tint = if (enabled && text.isNotBlank()) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f)
                    }
                )
            }
        }
    }
}
