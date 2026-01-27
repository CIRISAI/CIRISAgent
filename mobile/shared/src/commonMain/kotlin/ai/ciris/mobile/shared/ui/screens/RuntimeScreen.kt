package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
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
 * Runtime control screen for step-by-step debugging and pipeline visualization
 * Based on ~/CIRISGUI-Standalone/apps/agui/app/runtime/page.tsx
 *
 * Features:
 * - Pause/Resume/Single-step runtime controls
 * - H3ERE Pipeline visualization (11 step points)
 * - Cognitive state display
 * - Queue depth monitoring
 * - Stream connection status
 * - Task/Thought tracking
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RuntimeScreen(
    runtimeData: RuntimeData,
    isLoading: Boolean,
    isAdmin: Boolean,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onSingleStep: () -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Runtime Control") },
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
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Pipeline Control Card
            item {
                PipelineControlCard(
                    processorState = runtimeData.processorState,
                    isAdmin = isAdmin,
                    isLoading = isLoading,
                    onPause = onPause,
                    onResume = onResume,
                    onSingleStep = onSingleStep
                )
            }

            // Pipeline Status Info
            item {
                PipelineStatusCard(
                    cognitiveState = runtimeData.cognitiveState,
                    queueDepth = runtimeData.queueDepth,
                    currentStepPoint = runtimeData.currentStepPoint,
                    lastStepTime = runtimeData.lastStepTimeMs,
                    tokensUsed = runtimeData.tokensUsed
                )
            }

            // Stream Connection Status
            item {
                StreamStatusCard(
                    isConnected = runtimeData.streamConnected,
                    updatesReceived = runtimeData.updatesReceived
                )
            }

            // H3ERE Pipeline Visualization
            item {
                H3EREPipelineCard(
                    currentStep = runtimeData.currentStepPoint,
                    completedSteps = runtimeData.completedSteps
                )
            }

            // Admin warning if not admin
            if (!isAdmin) {
                item {
                    AdminWarningCard()
                }
            }

            // Active Tasks Section
            if (runtimeData.activeTasks.isNotEmpty()) {
                item {
                    Text(
                        text = "Active Tasks",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(runtimeData.activeTasks) { task ->
                    TaskCard(task = task)
                }
            }

            // Step Details (if available)
            if (runtimeData.lastStepResult != null) {
                item {
                    StepDetailsCard(
                        stepResult = runtimeData.lastStepResult,
                        currentStep = runtimeData.currentStepPoint
                    )
                }
            }

            // Instructions
            item {
                InstructionsCard()
            }
        }
    }
}

@Composable
private fun PipelineControlCard(
    processorState: String,
    isAdmin: Boolean,
    isLoading: Boolean,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onSingleStep: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isPaused = processorState.lowercase() == "paused"
    val isRunning = processorState.lowercase() == "running" || processorState.lowercase() == "active"

    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Pipeline Control",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                // Status indicator
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    isPaused -> Color(0xFFF59E0B) // Yellow
                                    isRunning -> Color(0xFF10B981) // Green
                                    else -> Color.Gray
                                }
                            )
                    )
                    Text(
                        text = processorState.uppercase(),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = when {
                            isPaused -> Color(0xFFF59E0B)
                            isRunning -> Color(0xFF10B981)
                            else -> Color.Gray
                        }
                    )
                }
            }

            // Control buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onPause,
                    enabled = isAdmin && !isPaused && !isLoading,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFF59E0B)
                    )
                ) {
                    Text("Pause")
                }

                Button(
                    onClick = onResume,
                    enabled = isAdmin && isPaused && !isLoading,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF10B981)
                    )
                ) {
                    Text("Resume")
                }

                Button(
                    onClick = onSingleStep,
                    enabled = isAdmin && isPaused && !isLoading,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF3B82F6)
                    )
                ) {
                    Icon(
                        imageVector = Icons.Filled.PlayArrow,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Step")
                }
            }
        }
    }
}

@Composable
private fun PipelineStatusCard(
    cognitiveState: String,
    queueDepth: Int,
    currentStepPoint: String?,
    lastStepTime: Long?,
    tokensUsed: Int?,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Pipeline Status",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Cognitive State
                StatusMetric(
                    label = "Cognitive State",
                    value = cognitiveState,
                    color = getCognitiveStateColor(cognitiveState)
                )

                // Queue Depth
                StatusMetric(
                    label = "Queue Depth",
                    value = queueDepth.toString(),
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Current Step
                StatusMetric(
                    label = "Current Step",
                    value = currentStepPoint?.let { getStepDisplayName(it) } ?: "None",
                    color = Color(0xFF3B82F6)
                )

                // Step Time
                StatusMetric(
                    label = "Step Time",
                    value = lastStepTime?.let { "${it}ms" } ?: "N/A",
                    color = Color(0xFF10B981)
                )

                // Tokens
                StatusMetric(
                    label = "Tokens",
                    value = tokensUsed?.toString() ?: "N/A",
                    color = Color(0xFF8B5CF6)
                )
            }
        }
    }
}

@Composable
private fun StatusMetric(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun StreamStatusCard(
    isConnected: Boolean,
    updatesReceived: Int,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isConnected)
                Color(0xFF10B981).copy(alpha = 0.1f)
            else
                Color(0xFFEF4444).copy(alpha = 0.1f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Real-time Stream",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )

                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(if (isConnected) Color(0xFF10B981) else Color(0xFFEF4444))
                )

                Text(
                    text = if (isConnected) "CONNECTED" else "DISCONNECTED",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (isConnected) Color(0xFF10B981) else Color(0xFFEF4444)
                )
            }

            Text(
                text = "$updatesReceived updates",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun H3EREPipelineCard(
    currentStep: String?,
    completedSteps: List<String>,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "H3ERE Pipeline (11 Step Points)",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            // Pipeline steps visualization
            val steps = listOf(
                "START_ROUND" to "0. Start Round",
                "GATHER_CONTEXT" to "1. Gather Context",
                "PERFORM_DMAS" to "2. Perform DMAs",
                "PERFORM_ASPDMA" to "3. Perform ASPDMA",
                "CONSCIENCE_EXECUTION" to "4. Conscience Execution",
                "RECURSIVE_ASPDMA" to "3B. Recursive ASPDMA",
                "RECURSIVE_CONSCIENCE" to "4B. Recursive Conscience",
                "FINALIZE_ACTION" to "5. Finalize Action",
                "PERFORM_ACTION" to "6. Perform Action",
                "ACTION_COMPLETE" to "7. Action Complete",
                "ROUND_COMPLETE" to "8. Round Complete"
            )

            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                steps.forEach { (stepKey, stepName) ->
                    val isCurrent = currentStep == stepKey
                    val isCompleted = completedSteps.contains(stepKey)
                    val isRecursive = stepKey.contains("RECURSIVE")

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                if (isCurrent) Color(0xFF3B82F6).copy(alpha = 0.2f)
                                else if (isCompleted) Color(0xFF10B981).copy(alpha = 0.1f)
                                else Color.Transparent,
                                shape = RoundedCornerShape(4.dp)
                            )
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Status indicator
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    when {
                                        isCurrent -> Color(0xFF3B82F6)
                                        isCompleted -> Color(0xFF10B981)
                                        else -> Color.LightGray
                                    }
                                )
                        )

                        // Step name
                        Text(
                            text = stepName,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                            color = when {
                                isCurrent -> Color(0xFF3B82F6)
                                isCompleted -> Color(0xFF10B981)
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            }
                        )

                        // Conditional badge for recursive steps
                        if (isRecursive) {
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = Color(0xFFF97316).copy(alpha = 0.2f)
                            ) {
                                Text(
                                    text = "conditional",
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color(0xFFF97316)
                                )
                            }
                        }
                    }
                }
            }

            Text(
                text = "Note: Steps 3B & 4B are conditional - only executed when conscience evaluation fails.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun AdminWarningCard(
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFFF59E0B).copy(alpha = 0.1f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Filled.PlayArrow,
                contentDescription = null,
                tint = Color(0xFFF59E0B)
            )
            Column {
                Text(
                    text = "Admin Access Required",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFF59E0B)
                )
                Text(
                    text = "Runtime control operations require Administrator privileges. You can view the current state but cannot modify runtime execution.",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFFF59E0B).copy(alpha = 0.8f)
                )
            }
        }
    }
}

@Composable
private fun TaskCard(
    task: TrackedTask,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Task: ${task.taskId.take(12)}...",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold
                )

                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = when (task.status) {
                        "completed" -> Color(0xFF10B981).copy(alpha = 0.2f)
                        "processing" -> Color(0xFF3B82F6).copy(alpha = 0.2f)
                        "failed" -> Color(0xFFEF4444).copy(alpha = 0.2f)
                        else -> Color.Gray.copy(alpha = 0.2f)
                    }
                ) {
                    Text(
                        text = task.status.uppercase(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = when (task.status) {
                            "completed" -> Color(0xFF10B981)
                            "processing" -> Color(0xFF3B82F6)
                            "failed" -> Color(0xFFEF4444)
                            else -> Color.Gray
                        }
                    )
                }
            }

            Text(
                text = "${task.thoughtCount} thoughts | Updated: ${task.lastUpdated}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun StepDetailsCard(
    stepResult: StepResult,
    currentStep: String?,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Last Step Details",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                currentStep?.let { step ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = Color(0xFF3B82F6).copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = getStepDisplayName(step),
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = Color(0xFF3B82F6)
                        )
                    }
                }
            }

            stepResult.message?.let { message ->
                Text(
                    text = message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (stepResult.processingTimeMs != null || stepResult.tokensUsed != null) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    stepResult.processingTimeMs?.let { time ->
                        Text(
                            text = "Time: ${time}ms",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFF10B981)
                        )
                    }
                    stepResult.tokensUsed?.let { tokens ->
                        Text(
                            text = "Tokens: $tokens",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFF8B5CF6)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun InstructionsCard(
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF3B82F6).copy(alpha = 0.1f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "How to use Runtime Control",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF3B82F6)
            )

            val instructions = listOf(
                "Real-time Stream: Connects to reasoning stream for live updates",
                "H3ERE Pipeline: 11 step points (0-10) with conditional recursive steps",
                "Pause/Resume: Control processing while maintaining stream connection",
                "Single Step: Execute one pipeline step (when paused)",
                "Live Visualization: See reasoning process in real-time"
            )

            instructions.forEachIndexed { index, instruction ->
                Text(
                    text = "${index + 1}. $instruction",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF3B82F6).copy(alpha = 0.8f)
                )
            }
        }
    }
}

// Helper functions

private fun getCognitiveStateColor(state: String): Color {
    return when (state.uppercase()) {
        "WORK" -> Color(0xFF10B981) // Green
        "PLAY" -> Color(0xFF3B82F6) // Blue
        "SOLITUDE", "DREAM" -> Color(0xFFF59E0B) // Yellow
        "WAKEUP", "SHUTDOWN" -> Color(0xFFF97316) // Orange
        else -> Color.Gray
    }
}

private fun getStepDisplayName(step: String): String {
    val names = mapOf(
        "START_ROUND" to "0. Start Round",
        "GATHER_CONTEXT" to "1. Gather Context",
        "PERFORM_DMAS" to "2. Perform DMAs",
        "PERFORM_ASPDMA" to "3. Perform ASPDMA",
        "CONSCIENCE_EXECUTION" to "4. Conscience",
        "RECURSIVE_ASPDMA" to "3B. Recursive ASPDMA",
        "RECURSIVE_CONSCIENCE" to "4B. Recursive Conscience",
        "FINALIZE_ACTION" to "5. Finalize Action",
        "PERFORM_ACTION" to "6. Perform Action",
        "ACTION_COMPLETE" to "7. Action Complete",
        "ROUND_COMPLETE" to "8. Round Complete"
    )
    return names[step] ?: step
}

// Data classes

/**
 * Runtime data model
 */
data class RuntimeData(
    val processorState: String = "unknown",
    val cognitiveState: String = "WORK",
    val queueDepth: Int = 0,
    val currentStepPoint: String? = null,
    val lastStepTimeMs: Long? = null,
    val tokensUsed: Int? = null,
    val streamConnected: Boolean = false,
    val updatesReceived: Int = 0,
    val completedSteps: List<String> = emptyList(),
    val activeTasks: List<TrackedTask> = emptyList(),
    val lastStepResult: StepResult? = null
)

/**
 * Tracked task data
 */
data class TrackedTask(
    val taskId: String,
    val status: String,
    val thoughtCount: Int,
    val lastUpdated: String
)

/**
 * Step result data
 */
data class StepResult(
    val message: String? = null,
    val processingTimeMs: Long? = null,
    val tokensUsed: Int? = null,
    val stepPoint: String? = null
)
