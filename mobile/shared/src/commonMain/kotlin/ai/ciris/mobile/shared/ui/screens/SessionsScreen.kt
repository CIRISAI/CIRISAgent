package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Sessions screen for cognitive session management
 * Based on SessionsFragment.kt
 *
 * Features:
 * - Current cognitive state display
 * - Initiate DREAM, PLAY, SOLITUDE sessions
 * - Return to WORK state
 * - Real-time state monitoring
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionsScreen(
    currentState: String,
    isLoading: Boolean,
    onInitiateSession: (String) -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showConfirmDialog by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Cognitive Sessions") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    IconButton(onClick = onRefresh, enabled = !isLoading) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Current state banner
            CurrentStateBanner(currentState = currentState)

            // Session cards
            Text(
                text = "Available Sessions",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            SessionCard(
                title = "DREAM",
                description = "Deep introspection and memory consolidation",
                isActive = currentState == "DREAM",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "DREAM" }
            )

            SessionCard(
                title = "PLAY",
                description = "Creative exploration and experimentation",
                isActive = currentState == "PLAY",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "PLAY" }
            )

            SessionCard(
                title = "SOLITUDE",
                description = "Quiet reflection and planning",
                isActive = currentState == "SOLITUDE",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "SOLITUDE" }
            )

            // Return to work button
            if (currentState !in listOf("WORK", "WAKEUP", "SHUTDOWN")) {
                Button(
                    onClick = { showConfirmDialog = "WORK" },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.secondary
                    )
                ) {
                    Text("Return to Work")
                }
            }
        }
    }

    // Confirmation dialog
    showConfirmDialog?.let { targetState ->
        ConfirmSessionDialog(
            targetState = targetState,
            onConfirm = {
                onInitiateSession(targetState)
                showConfirmDialog = null
            },
            onDismiss = { showConfirmDialog = null }
        )
    }
}

@Composable
private fun CurrentStateBanner(
    currentState: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = getCurrentStateColor(currentState).copy(alpha = 0.2f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(16.dp)
                    .clip(CircleShape)
                    .background(getCurrentStateColor(currentState))
            )

            Spacer(modifier = Modifier.width(12.dp))

            Column(
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Current State",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                )
                Text(
                    text = currentState,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = getCurrentStateColor(currentState)
                )
            }
        }
    }
}

@Composable
private fun SessionCard(
    title: String,
    description: String,
    isActive: Boolean,
    isEnabled: Boolean,
    onInitiate: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = if (isActive) {
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer
            )
        } else {
            CardDefaults.cardColors()
        }
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f)
            ) {
                // Status dot
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .clip(CircleShape)
                        .background(
                            if (isActive) Color(0xFF10B981) else Color.LightGray
                        )
                )

                Column(
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        if (isActive) {
                            Surface(
                                color = Color(0xFF10B981),
                                shape = MaterialTheme.shapes.small
                            ) {
                                Text(
                                    text = "ACTIVE",
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White
                                )
                            }
                        }
                    }
                    Text(
                        text = description,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Button(
                onClick = onInitiate,
                enabled = isEnabled && !isActive
            ) {
                Text("Initiate")
            }
        }
    }
}

@Composable
private fun ConfirmSessionDialog(
    targetState: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    val (title, message) = when (targetState) {
        "DREAM" -> "Initiate DREAM Session" to "Initiate a DREAM session for deep introspection and memory consolidation?"
        "PLAY" -> "Initiate PLAY Session" to "Initiate a PLAY session for creative exploration and experimentation?"
        "SOLITUDE" -> "Initiate SOLITUDE Session" to "Initiate a SOLITUDE session for quiet reflection and planning?"
        "WORK" -> "Return to Work" to "Return to normal WORK state?"
        else -> "Change State" to "Change cognitive state to $targetState?"
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = {
            Button(onClick = onConfirm) {
                Text("Confirm")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

// Helper functions

private fun getCurrentStateColor(state: String): Color {
    return when (state.uppercase()) {
        "WORK" -> Color(0xFF3B82F6) // Blue
        "DREAM" -> Color(0xFF8B5CF6) // Purple
        "PLAY" -> Color(0xFFF59E0B) // Yellow
        "SOLITUDE" -> Color(0xFF06B6D4) // Cyan
        "WAKEUP" -> Color(0xFFF97316) // Orange
        "SHUTDOWN" -> Color(0xFFEF4444) // Red
        else -> Color.Gray
    }
}
