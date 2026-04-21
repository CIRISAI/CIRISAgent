package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.localization.localizedString

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
                title = { Text(localizedString("mobile.screen_cognitive_sessions")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_sessions_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.arrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onRefresh,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_sessions_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("mobile.common_refresh")
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

            // Experimental warning
            val semantic = SemanticColors.Default
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = semantic.surfaceWarning
                )
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Text(
                        text = "!",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = semantic.warning
                    )
                    Column {
                        Text(
                            text = localizedString("mobile.sessions_experimental"),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = semantic.onWarning
                        )
                        Text(
                            text = localizedString("mobile.sessions_warning"),
                            style = MaterialTheme.typography.bodySmall,
                            color = semantic.onWarning
                        )
                    }
                }
            }

            // Session cards
            Text(
                text = localizedString("mobile.sessions_available"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            SessionCard(
                title = localizedString("mobile.interact_state_dream"),
                description = localizedString("mobile.sessions_dream_desc"),
                isActive = currentState == "DREAM",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "DREAM" }
            )

            SessionCard(
                title = localizedString("mobile.interact_state_play"),
                description = localizedString("mobile.sessions_play_desc"),
                isActive = currentState == "PLAY",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "PLAY" }
            )

            SessionCard(
                title = localizedString("mobile.interact_state_solitude"),
                description = localizedString("mobile.sessions_solitude_desc"),
                isActive = currentState == "SOLITUDE",
                isEnabled = currentState == "WORK",
                onInitiate = { showConfirmDialog = "SOLITUDE" }
            )

            // Return to work button
            if (currentState !in listOf("WORK", "WAKEUP", "SHUTDOWN")) {
                Button(
                    onClick = { showConfirmDialog = "WORK" },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testableClickable("btn_return_to_work") { showConfirmDialog = "WORK" },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.secondary
                    )
                ) {
                    Text(localizedString("mobile.sessions_return_work"))
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
                    text = localizedString("mobile.sessions_current"),
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
    val semantic = SemanticColors.Default
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
                            if (isActive) semantic.online else semantic.inactive
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
                                color = semantic.success,
                                shape = MaterialTheme.shapes.small
                            ) {
                                Text(
                                    text = localizedString("mobile.sessions_active"),
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = semantic.onSuccess
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
                enabled = isEnabled && !isActive,
                modifier = Modifier.testableClickable("btn_initiate_${title.lowercase()}") { onInitiate() }
            ) {
                Text(localizedString("mobile.sessions_initiate"))
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
    val (titleKey, messageKey) = when (targetState) {
        "DREAM" -> "mobile.sessions_dialog_dream_title" to "mobile.sessions_dialog_dream_message"
        "PLAY" -> "mobile.sessions_dialog_play_title" to "mobile.sessions_dialog_play_message"
        "SOLITUDE" -> "mobile.sessions_dialog_solitude_title" to "mobile.sessions_dialog_solitude_message"
        "WORK" -> "mobile.sessions_dialog_work_title" to "mobile.sessions_dialog_work_message"
        else -> "mobile.sessions_dialog_change_title" to "mobile.sessions_dialog_change_message"
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString(titleKey)) },
        text = {
            Text(
                if (titleKey == "mobile.sessions_dialog_change_title") {
                    localizedString(messageKey, "state", targetState)
                } else {
                    localizedString(messageKey)
                }
            )
        },
        confirmButton = {
            Button(
                onClick = onConfirm,
                modifier = Modifier.testableClickable("btn_confirm_session") { onConfirm() }
            ) {
                Text(localizedString("mobile.common_confirm"))
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_cancel_session") { onDismiss() }
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        }
    )
}

// Helper functions

private fun getCurrentStateColor(state: String): Color {
    val semantic = SemanticColors.Default
    return when (state.uppercase()) {
        "WORK" -> semantic.info           // Blue (info)
        "DREAM" -> semantic.accentTertiary // Purple (theme tertiary)
        "PLAY" -> semantic.warning         // Amber/Yellow
        "SOLITUDE" -> semantic.accentSecondary // Cyan (theme secondary)
        "WAKEUP" -> semantic.pending       // Orange/Amber
        "SHUTDOWN" -> semantic.error       // Red
        else -> semantic.inactive
    }
}
