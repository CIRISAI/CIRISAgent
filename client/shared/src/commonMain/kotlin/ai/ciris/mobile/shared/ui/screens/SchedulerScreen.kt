package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.ScheduledTaskData
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.SchedulerOverviewData
import ai.ciris.mobile.shared.viewmodels.SchedulerScreenState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.localization.localizedString

/**
 * Scheduler screen showing scheduled tasks and statistics.
 *
 * Features:
 * - Current cognitive state
 * - Task statistics (pending, recurring, completed, failed)
 * - Scheduled tasks list with status
 * - Create task dialog (one-time or recurring)
 * - Cancel task functionality
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SchedulerScreen(
    state: SchedulerScreenState,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    onShowCreateDialog: () -> Unit,
    onHideCreateDialog: () -> Unit,
    onCreateTask: (name: String, goalDescription: String, triggerPrompt: String, deferUntil: String?, scheduleCron: String?) -> Unit,
    onCancelTask: (taskId: String) -> Unit,
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_task_scheduler")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_scheduler_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onShowCreateDialog,
                        modifier = Modifier.testableClickable("btn_scheduler_create") { onShowCreateDialog() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Add,
                            contentDescription = localizedString("mobile.scheduler_create_title")
                        )
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !state.isLoading,
                        modifier = Modifier.testableClickable("btn_scheduler_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = localizedString("mobile.common_refresh")
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onShowCreateDialog,
                containerColor = MaterialTheme.colorScheme.primary
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = localizedString("mobile.scheduler_create_title")
                )
            }
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Loading state
            if (state.isLoading || state.isRefreshing) {
                item {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
            }

            // Error message
            state.error?.let { error ->
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = error,
                            modifier = Modifier.padding(16.dp),
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
            }

            // Cognitive State Card
            item {
                CognitiveStateCard(state = state.overview.cognitiveState)
            }

            // Stats cards
            item {
                SchedulerStatsRow(overview = state.overview)
            }

            // Tasks section header
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = localizedString("mobile.scheduler_tasks"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = localizedString("mobile.scheduler_task_count", "count", state.tasks.size.toString()),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Task list
            if (state.tasks.isEmpty() && !state.isLoading) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Filled.DateRange,
                                contentDescription = null,
                                modifier = Modifier.size(48.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = localizedString("mobile.scheduler_no_tasks"),
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = localizedString("mobile.scheduler_create_hint"),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            } else {
                items(state.tasks, key = { it.taskId }) { task ->
                    ScheduledTaskCard(
                        task = task,
                        onCancel = { onCancelTask(task.taskId) }
                    )
                }
            }
        }
    }

    // Create task dialog
    if (state.showCreateDialog) {
        CreateTaskDialog(
            isCreating = state.isCreatingTask,
            error = state.createTaskError,
            onDismiss = onHideCreateDialog,
            onCreate = onCreateTask
        )
    }
}

@Composable
private fun CognitiveStateCard(state: String) {
    val semantic = SemanticColors.Default
    val (color, descriptionKey) = when (state.uppercase()) {
        "WORK" -> Pair(semantic.success, "mobile.scheduler_state_work_desc")
        "PLAY" -> Pair(semantic.accentTertiary, "mobile.scheduler_state_play_desc")
        "SOLITUDE" -> Pair(semantic.inactive, "mobile.scheduler_state_solitude_desc")
        "DREAM" -> Pair(semantic.info, "mobile.scheduler_state_dream_desc")
        "WAKEUP" -> Pair(semantic.warning, "mobile.scheduler_state_wakeup_desc")
        "SHUTDOWN" -> Pair(semantic.error, "mobile.scheduler_state_shutdown_desc")
        else -> Pair(semantic.inactive, "mobile.scheduler_state_unknown_desc")
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = color.copy(alpha = 0.1f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = localizedString("mobile.scheduler_cognitive"),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = state,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = color
                )
                Text(
                    text = localizedString(descriptionKey),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Icon(
                imageVector = Icons.Filled.PlayArrow,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(48.dp)
            )
        }
    }
}

@Composable
private fun SchedulerStatsRow(overview: SchedulerOverviewData) {
    val semantic = SemanticColors.Default
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        SchedulerStatCard(
            icon = Icons.Filled.DateRange,
            label = localizedString("mobile.scheduler_stat_pending"),
            value = overview.pendingCount.toString(),
            color = if (overview.pendingCount > 0) semantic.warning else semantic.success,
            modifier = Modifier.weight(1f)
        )
        SchedulerStatCard(
            icon = Icons.Filled.Refresh,
            label = localizedString("mobile.scheduler_stat_recurring"),
            value = overview.recurringCount.toString(),
            color = semantic.info,
            modifier = Modifier.weight(1f)
        )
        SchedulerStatCard(
            icon = Icons.Filled.CheckCircle,
            label = localizedString("mobile.scheduler_stat_completed"),
            value = overview.completedTotal.toString(),
            color = semantic.success,
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun SchedulerStatCard(
    icon: ImageVector,
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = color.copy(alpha = 0.1f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(24.dp)
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = color
            )
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun ScheduledTaskCard(
    task: ScheduledTaskData,
    onCancel: () -> Unit
) {
    val semantic = SemanticColors.Default
    val statusColor = when (task.status.uppercase()) {
        "PENDING" -> semantic.warning
        "ACTIVE" -> semantic.info
        "COMPLETE" -> semantic.success
        "FAILED" -> semantic.error
        "CANCELLED" -> semantic.inactive
        else -> semantic.inactive
    }

    Card(
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = if (task.isRecurring) Icons.Filled.Refresh else Icons.Filled.DateRange,
                        contentDescription = if (task.isRecurring) {
                            localizedString("mobile.scheduler_stat_recurring")
                        } else {
                            localizedString("mobile.scheduler_onetime")
                        },
                        tint = statusColor,
                        modifier = Modifier.size(20.dp)
                    )
                    Text(
                        text = task.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Medium
                    )
                }
                AssistChip(
                    onClick = {},
                    label = { Text(task.statusDisplay) },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = statusColor.copy(alpha = 0.2f),
                        labelColor = statusColor
                    )
                )
            }

            // Description
            Text(
                text = task.goalDescription,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            // Schedule info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = task.scheduleDisplay,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )
                if (task.deferralCount > 0) {
                    Text(
                        text = localizedString("mobile.scheduler_deferred", "count", task.deferralCount.toString()),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Actions (only show cancel for pending/active tasks)
            if (task.status.uppercase() in listOf("PENDING", "ACTIVE")) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(
                        onClick = onCancel,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Close,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(localizedString("mobile.common_cancel"))
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateTaskDialog(
    isCreating: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onCreate: (name: String, goalDescription: String, triggerPrompt: String, deferUntil: String?, scheduleCron: String?) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var goalDescription by remember { mutableStateOf("") }
    var triggerPrompt by remember { mutableStateOf("") }
    var isRecurring by remember { mutableStateOf(false) }
    var scheduleCron by remember { mutableStateOf("") }
    var deferHours by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = { if (!isCreating) onDismiss() },
        title = { Text(localizedString("mobile.scheduler_create_title")) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Task name
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text(localizedString("mobile.scheduler_name")) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating
                )

                // Goal description
                OutlinedTextField(
                    value = goalDescription,
                    onValueChange = { goalDescription = it },
                    label = { Text(localizedString("mobile.scheduler_goal")) },
                    minLines = 2,
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating
                )

                // Trigger prompt
                OutlinedTextField(
                    value = triggerPrompt,
                    onValueChange = { triggerPrompt = it },
                    label = { Text(localizedString("mobile.scheduler_trigger")) },
                    minLines = 2,
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating,
                    supportingText = { Text(localizedString("mobile.scheduler_trigger_hint")) }
                )

                // Schedule type toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(localizedString("mobile.scheduler_recurring"))
                    Spacer(modifier = Modifier.weight(1f))
                    Switch(
                        checked = isRecurring,
                        onCheckedChange = { isRecurring = it },
                        enabled = !isCreating
                    )
                }

                // Schedule input based on type
                if (isRecurring) {
                    OutlinedTextField(
                        value = scheduleCron,
                        onValueChange = { scheduleCron = it },
                        label = { Text(localizedString("mobile.scheduler_cron")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isCreating,
                        supportingText = { Text(localizedString("mobile.scheduler_cron_hint")) }
                    )

                    // Common cron presets
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        SuggestionChip(
                            onClick = { scheduleCron = "0 9 * * *" },
                            label = { Text(localizedString("mobile.scheduler_daily_9am")) },
                            enabled = !isCreating
                        )
                        SuggestionChip(
                            onClick = { scheduleCron = "0 9 * * 1" },
                            label = { Text(localizedString("mobile.scheduler_weekly_mon")) },
                            enabled = !isCreating
                        )
                        SuggestionChip(
                            onClick = { scheduleCron = "0 */2 * * *" },
                            label = { Text(localizedString("mobile.scheduler_every_2h")) },
                            enabled = !isCreating
                        )
                    }
                } else {
                    OutlinedTextField(
                        value = deferHours,
                        onValueChange = { deferHours = it.filter { c -> c.isDigit() } },
                        label = { Text(localizedString("mobile.scheduler_defer_hours")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isCreating,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        supportingText = { Text(localizedString("mobile.scheduler_defer_hint")) }
                    )
                }

                // Error message
                error?.let {
                    Text(
                        text = it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val deferUntilValue = if (!isRecurring && deferHours.isNotEmpty()) {
                        // Calculate ISO timestamp for N hours from now
                        val hours = deferHours.toIntOrNull() ?: 1
                        val currentTimeMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                        val futureTimeMs = currentTimeMs + (hours * 60 * 60 * 1000L)
                        // Convert to ISO format via kotlinx.datetime.Instant
                        kotlinx.datetime.Instant.fromEpochMilliseconds(futureTimeMs).toString()
                    } else null

                    val cronValue = if (isRecurring && scheduleCron.isNotBlank()) scheduleCron else null

                    onCreate(name, goalDescription, triggerPrompt, deferUntilValue, cronValue)
                },
                enabled = !isCreating && name.isNotBlank() && goalDescription.isNotBlank() && triggerPrompt.isNotBlank() &&
                    (isRecurring && scheduleCron.isNotBlank() || !isRecurring && deferHours.isNotBlank())
            ) {
                if (isCreating) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text(localizedString("mobile.common_create"))
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isCreating
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        }
    )
}
