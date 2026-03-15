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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

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
                title = { Text("Task Scheduler") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_scheduler_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
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
                            contentDescription = "Create Task"
                        )
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !state.isLoading,
                        modifier = Modifier.testableClickable("btn_scheduler_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh"
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
                    contentDescription = "Create Task"
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
                        text = "Scheduled Tasks",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${state.tasks.size} tasks",
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
                                text = "No Scheduled Tasks",
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = "Create a task to schedule automated actions",
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
    val (color, description) = when (state.uppercase()) {
        "WORK" -> Pair(Color(0xFF4CAF50), "Processing tasks normally")
        "PLAY" -> Pair(Color(0xFF9C27B0), "Creative/exploratory mode")
        "SOLITUDE" -> Pair(Color(0xFF607D8B), "Reflection mode")
        "DREAM" -> Pair(Color(0xFF3F51B5), "Deep introspection")
        "WAKEUP" -> Pair(Color(0xFFFFA000), "Starting up")
        "SHUTDOWN" -> Pair(Color(0xFFF44336), "Shutting down")
        else -> Pair(Color(0xFF9E9E9E), "Unknown state")
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
                    text = "Cognitive State",
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
                    text = description,
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
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        SchedulerStatCard(
            icon = Icons.Filled.DateRange,
            label = "Pending",
            value = overview.pendingCount.toString(),
            color = if (overview.pendingCount > 0) Color(0xFFFFA000) else Color(0xFF4CAF50),
            modifier = Modifier.weight(1f)
        )
        SchedulerStatCard(
            icon = Icons.Filled.Refresh,
            label = "Recurring",
            value = overview.recurringCount.toString(),
            color = Color(0xFF2196F3),
            modifier = Modifier.weight(1f)
        )
        SchedulerStatCard(
            icon = Icons.Filled.CheckCircle,
            label = "Completed",
            value = overview.completedTotal.toString(),
            color = Color(0xFF4CAF50),
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
    val statusColor = when (task.status.uppercase()) {
        "PENDING" -> Color(0xFFFFA000)
        "ACTIVE" -> Color(0xFF2196F3)
        "COMPLETE" -> Color(0xFF4CAF50)
        "FAILED" -> Color(0xFFF44336)
        "CANCELLED" -> Color(0xFF9E9E9E)
        else -> Color(0xFF9E9E9E)
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
                        contentDescription = if (task.isRecurring) "Recurring" else "One-time",
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
                        text = "Deferred ${task.deferralCount}x",
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
                        Text("Cancel")
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
        title = { Text("Create Scheduled Task") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Task name
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Task Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating
                )

                // Goal description
                OutlinedTextField(
                    value = goalDescription,
                    onValueChange = { goalDescription = it },
                    label = { Text("Goal Description") },
                    minLines = 2,
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating
                )

                // Trigger prompt
                OutlinedTextField(
                    value = triggerPrompt,
                    onValueChange = { triggerPrompt = it },
                    label = { Text("Trigger Prompt") },
                    minLines = 2,
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isCreating,
                    supportingText = { Text("What CIRIS should do when task triggers") }
                )

                // Schedule type toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Recurring task")
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
                        label = { Text("Cron Expression") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isCreating,
                        supportingText = { Text("e.g., '0 9 * * *' for daily at 9am") }
                    )

                    // Common cron presets
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        SuggestionChip(
                            onClick = { scheduleCron = "0 9 * * *" },
                            label = { Text("Daily 9am") },
                            enabled = !isCreating
                        )
                        SuggestionChip(
                            onClick = { scheduleCron = "0 9 * * 1" },
                            label = { Text("Weekly Mon") },
                            enabled = !isCreating
                        )
                        SuggestionChip(
                            onClick = { scheduleCron = "0 */2 * * *" },
                            label = { Text("Every 2h") },
                            enabled = !isCreating
                        )
                    }
                } else {
                    OutlinedTextField(
                        value = deferHours,
                        onValueChange = { deferHours = it.filter { c -> c.isDigit() } },
                        label = { Text("Defer Hours") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isCreating,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        supportingText = { Text("Hours from now to execute") }
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
                        val currentTimeMs = System.currentTimeMillis()
                        val futureTimeMs = currentTimeMs + (hours * 60 * 60 * 1000L)
                        // Simple ISO format
                        java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply {
                            timeZone = java.util.TimeZone.getTimeZone("UTC")
                        }.format(java.util.Date(futureTimeMs))
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
                    Text("Create")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isCreating
            ) {
                Text("Cancel")
            }
        }
    )
}
