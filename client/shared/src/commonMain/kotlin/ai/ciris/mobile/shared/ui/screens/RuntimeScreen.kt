package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
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
import ai.ciris.mobile.shared.ui.icons.*
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
                title = { Text(localizedString("mobile.screen_runtime_control")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_runtime_back") { onNavigateBack() }
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
                        modifier = Modifier.testableClickable("btn_runtime_refresh") { onRefresh() }
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
                        text = localizedString("mobile.runtime_active_tasks"),
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
                    text = localizedString("mobile.runtime_pipeline_control"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                // Status indicator
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val colors = SemanticColors.Default
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    isPaused -> colors.warning
                                    isRunning -> colors.success
                                    else -> colors.inactive
                                }
                            )
                    )
                    Text(
                        text = processorState.uppercase(),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = when {
                            isPaused -> colors.warning
                            isRunning -> colors.success
                            else -> colors.inactive
                        }
                    )
                }
            }

            // Control buttons
            val colors = SemanticColors.Default
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onPause,
                    enabled = isAdmin && !isPaused && !isLoading,
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_pipeline_pause") { onPause() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = colors.warning
                    )
                ) {
                    Text(localizedString("mobile.runtime_pause"))
                }

                Button(
                    onClick = onResume,
                    enabled = isAdmin && isPaused && !isLoading,
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_pipeline_resume") { onResume() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = colors.success
                    )
                ) {
                    Text(localizedString("mobile.runtime_resume"))
                }

                Button(
                    onClick = onSingleStep,
                    enabled = isAdmin && isPaused && !isLoading,
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_pipeline_step") { onSingleStep() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = colors.info
                    )
                ) {
                    Icon(
                        imageVector = CIRISIcons.play,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(localizedString("mobile.runtime_step"))
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
                text = localizedString("mobile.runtime_pipeline_status"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            val colors = SemanticColors.Default
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Cognitive State
                StatusMetric(
                    label = localizedString("system.system_cognitive_state"),
                    value = cognitiveState,
                    color = getCognitiveStateColor(cognitiveState)
                )

                // Queue Depth
                StatusMetric(
                    label = localizedString("system.system_queue_depth"),
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
                    label = localizedString("mobile.runtime_current_step"),
                    value = currentStepPoint?.let { getStepDisplayName(it) } ?: localizedString("mobile.common_none"),
                    color = colors.info
                )

                // Step Time
                StatusMetric(
                    label = localizedString("mobile.runtime_step_time"),
                    value = lastStepTime?.let { localizedString("mobile.runtime_time", mapOf("ms" to it.toString())) } ?: "N/A",
                    color = colors.success
                )

                // Tokens
                StatusMetric(
                    label = localizedString("mobile.runtime_tokens_label"),
                    value = tokensUsed?.toString() ?: "N/A",
                    color = colors.accent
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
    val colors = SemanticColors.Default
    val statusColor = if (isConnected) colors.success else colors.error
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = statusColor.copy(alpha = 0.1f)
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
                    text = localizedString("mobile.runtime_realtime"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )

                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(statusColor)
                )

                Text(
                    text = if (isConnected) localizedString("mobile.interact_connected") else localizedString("mobile.interact_disconnected"),
                    style = MaterialTheme.typography.bodySmall,
                    color = statusColor
                )
            }

            Text(
                text = localizedString("mobile.runtime_updates", mapOf("count" to updatesReceived.toString())),
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
    val colors = SemanticColors.Default
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.runtime_h3ere"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            // Pipeline steps visualization - 11 step points
            // H3ERE: 7 core steps + 2 optional recursive + setup + completion
            val steps = listOf(
                "START_ROUND" to localizedString("mobile.step_start_round"),
                "GATHER_CONTEXT" to localizedString("mobile.step_gather_context"),
                "PERFORM_DMAS" to localizedString("mobile.step_perform_dmas"),
                "PERFORM_ASPDMA" to localizedString("mobile.step_perform_aspdma"),
                "CONSCIENCE_EXECUTION" to localizedString("mobile.step_conscience_execution"),
                "RECURSIVE_ASPDMA" to localizedString("mobile.step_recursive_aspdma"),
                "RECURSIVE_CONSCIENCE" to localizedString("mobile.step_recursive_conscience"),
                "FINALIZE_ACTION" to localizedString("mobile.step_finalize_action"),
                "PERFORM_ACTION" to localizedString("mobile.step_perform_action"),
                "ACTION_COMPLETE" to localizedString("mobile.step_action_complete"),
                "ROUND_COMPLETE" to localizedString("mobile.step_round_complete")
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
                                if (isCurrent) colors.info.copy(alpha = 0.2f)
                                else if (isCompleted) colors.success.copy(alpha = 0.1f)
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
                                        isCurrent -> colors.info
                                        isCompleted -> colors.success
                                        else -> colors.inactive
                                    }
                                )
                        )

                        // Step name
                        Text(
                            text = stepName,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                            color = when {
                                isCurrent -> colors.info
                                isCompleted -> colors.success
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            }
                        )

                        // Conditional badge for recursive steps
                        if (isRecursive) {
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = colors.warning.copy(alpha = 0.2f)
                            ) {
                                Text(
                                    text = localizedString("mobile.runtime_conditional"),
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = colors.warning
                                )
                            }
                        }
                    }
                }
            }

            Text(
                text = localizedString("mobile.runtime_note"),
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
    val colors = SemanticColors.Default
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = colors.warning.copy(alpha = 0.1f)
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
                imageVector = CIRISIcons.play,
                contentDescription = null,
                tint = colors.warning
            )
            Column {
                Text(
                    text = localizedString("mobile.runtime_admin_required"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold,
                    color = colors.warning
                )
                Text(
                    text = localizedString("mobile.runtime_admin_hint"),
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.warning.copy(alpha = 0.8f)
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
    val colors = SemanticColors.Default
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
                    text = localizedString("mobile.runtime_task", mapOf("id" to task.taskId.take(12))),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold
                )

                val statusColor = when (task.status) {
                    "completed" -> colors.success
                    "processing" -> colors.info
                    "failed" -> colors.error
                    else -> colors.inactive
                }
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = statusColor.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = task.status.uppercase(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = statusColor
                    )
                }
            }

            Text(
                text = localizedString("mobile.runtime_task_info", mapOf("count" to task.thoughtCount.toString(), "updated" to task.lastUpdated)),
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
    val colors = SemanticColors.Default
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
                    text = localizedString("mobile.runtime_last_step"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                currentStep?.let { step ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = colors.info.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = getStepDisplayName(step),
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = colors.info
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
                            text = localizedString("mobile.runtime_time", mapOf("ms" to time.toString())),
                            style = MaterialTheme.typography.bodySmall,
                            color = colors.success
                        )
                    }
                    stepResult.tokensUsed?.let { tokens ->
                        Text(
                            text = localizedString("mobile.runtime_tokens", mapOf("count" to tokens.toString())),
                            style = MaterialTheme.typography.bodySmall,
                            color = colors.accent
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
    val colors = SemanticColors.Default
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = colors.info.copy(alpha = 0.1f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = localizedString("mobile.runtime_how_to"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = colors.info
            )

            val instructions = listOf(
                localizedString("mobile.runtime_instruction_1"),
                localizedString("mobile.runtime_instruction_2"),
                localizedString("mobile.runtime_instruction_3"),
                localizedString("mobile.runtime_instruction_4"),
                localizedString("mobile.runtime_instruction_5")
            )

            instructions.forEachIndexed { index, instruction ->
                Text(
                    text = "${index + 1}. $instruction",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.info.copy(alpha = 0.8f)
                )
            }
        }
    }
}

// Helper functions

private fun getCognitiveStateColor(state: String): Color {
    val colors = SemanticColors.Default
    return when (state.uppercase()) {
        "WORK" -> colors.success
        "PLAY" -> colors.info
        "SOLITUDE", "DREAM" -> colors.warning
        "WAKEUP", "SHUTDOWN" -> colors.warning
        else -> colors.inactive
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
