package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.ui.theme.SemanticColors

/**
 * System management and control screen
 * Based on CIRISGUI-Standalone/apps/agui/app/system/page.tsx
 *
 * Features:
 * - System health overview
 * - Resource usage (CPU, Memory, Disk)
 * - Environmental impact metrics
 * - Services health grid
 * - Processor management (pause/resume)
 * - Active channels display
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SystemScreen(
    systemData: SystemScreenData,
    isLoading: Boolean,
    onPauseRuntime: () -> Unit,
    onResumeRuntime: () -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showConfirmDialog by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.nav_system")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_system_back") { onNavigateBack() }
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
                        modifier = Modifier.testableClickable("btn_system_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("mobile.common_refresh")
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        if (isLoading && systemData.health == null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // System Overview
                item {
                    SystemOverviewCard(
                        health = systemData.health,
                        uptime = systemData.uptime,
                        memoryMb = systemData.memoryMb,
                        cpuPercent = systemData.cpuPercent
                    )
                }

                // Resource Usage
                item {
                    Text(
                        text = localizedString("mobile.system_resource"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                item {
                    ResourceUsageCard(
                        cpuPercent = systemData.cpuPercent,
                        memoryMb = systemData.memoryMb,
                        memoryPercent = systemData.memoryPercent,
                        diskUsedMb = systemData.diskUsedMb
                    )
                }

                // Environmental Impact
                item {
                    Text(
                        text = localizedString("mobile.system_environmental"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                item {
                    EnvironmentalImpactCard(
                        carbonGrams = systemData.carbonGrams,
                        energyKwh = systemData.energyKwh,
                        costCents = systemData.costCents,
                        tokensLastHour = systemData.tokensLastHour,
                        tokens24h = systemData.tokens24h
                    )
                }

                // Main Processor
                item {
                    Text(
                        text = localizedString("mobile.system_processor"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                item {
                    ProcessorControlCard(
                        isPaused = systemData.isPaused,
                        cognitiveState = systemData.cognitiveState,
                        queueDepth = systemData.queueDepth,
                        onPause = { showConfirmDialog = "pause" },
                        onResume = { showConfirmDialog = "resume" }
                    )
                }

                // Services Health
                if (systemData.services.isNotEmpty()) {
                    item {
                        Text(
                            text = localizedString("mobile.system_services_health", mapOf("count" to systemData.services.size.toString())),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    item {
                        ServicesHealthGrid(services = systemData.services)
                    }
                }

                // Active Channels
                if (systemData.channels.isNotEmpty()) {
                    item {
                        Text(
                            text = localizedString("mobile.system_channels"),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    items(systemData.channels) { channel ->
                        ChannelCard(channel = channel)
                    }
                }

                item {
                    Spacer(modifier = Modifier.height(16.dp))
                }
            }
        }
    }

    // Confirmation dialogs
    showConfirmDialog?.let { action ->
        AlertDialog(
            onDismissRequest = { showConfirmDialog = null },
            title = { Text(if (action == "pause") localizedString("mobile.runtime_pause") else localizedString("mobile.runtime_resume")) },
            text = {
                Text(
                    if (action == "pause")
                        localizedString("mobile.system_pause_confirm")
                    else
                        localizedString("mobile.system_resume_confirm")
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (action == "pause") onPauseRuntime() else onResumeRuntime()
                        showConfirmDialog = null
                    },
                    modifier = Modifier.testableClickable("btn_runtime_confirm") {
                        if (action == "pause") onPauseRuntime() else onResumeRuntime()
                        showConfirmDialog = null
                    }
                ) {
                    Text(localizedString("mobile.common_confirm"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showConfirmDialog = null },
                    modifier = Modifier.testableClickable("btn_runtime_cancel") { showConfirmDialog = null }
                ) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }
}

@Composable
private fun SystemOverviewCard(
    health: String?,
    uptime: String?,
    memoryMb: Int,
    cpuPercent: Int,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            // Health status
            Column(
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                val healthColor = getHealthColor(health)
                Surface(
                    color = healthColor.copy(alpha = 0.2f),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            getHealthIcon(health),
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                            tint = healthColor
                        )
                        Text(
                            text = health?.uppercase() ?: "UNKNOWN",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = healthColor
                        )
                    }
                }
                Text(
                    text = localizedString("mobile.system_overall_health"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Uptime
            Column(
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = uptime ?: "N/A",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = localizedString("mobile.system_uptime"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun ResourceUsageCard(
    cpuPercent: Int,
    memoryMb: Int,
    memoryPercent: Int,
    diskUsedMb: Double,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // CPU
            ResourceBar(
                label = localizedString("mobile.telemetry_cpu_usage"),
                value = "$cpuPercent%",
                progress = cpuPercent / 100f,
                color = getUsageColor(cpuPercent)
            )

            // Memory
            ResourceBar(
                label = localizedString("mobile.telemetry_memory_usage"),
                value = "$memoryMb MB",
                progress = memoryPercent / 100f,
                color = getUsageColor(memoryPercent),
                subtitle = "$memoryPercent% utilized"
            )

            // Disk
            val diskGb = diskUsedMb / 1024.0
            val diskDisplay = if (diskGb >= 1.0) "${((diskGb * 10).toInt() / 10.0)} GB" else "${diskUsedMb.toInt()} MB"
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = localizedString("mobile.system_disk"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = diskDisplay,
                    style = MaterialTheme.typography.bodyMedium,
                    color = SemanticColors.Default.success
                )
            }
        }
    }
}

@Composable
private fun ResourceBar(
    label: String,
    value: String,
    progress: Float,
    color: Color,
    subtitle: String? = null,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = value,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = color
            )
        }
        LinearProgressIndicator(
            progress = { progress.coerceIn(0f, 1f) },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(RoundedCornerShape(4.dp)),
            color = color,
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
        subtitle?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun EnvironmentalImpactCard(
    carbonGrams: Double,
    energyKwh: Double,
    costCents: Double,
    tokensLastHour: Int,
    tokens24h: Int,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Impact metrics row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // CO2
                ImpactCard(
                    icon = CIRISIcons.globe,  // Earth/Globe
                    value = "${formatDecimal(carbonGrams / 1000, 3)} kg",
                    label = localizedString("mobile.telemetry_co2_hour"),
                    color = SemanticColors.Default.success
                )

                // Energy
                ImpactCard(
                    icon = CIRISIcons.lightning,  // Lightning bolt
                    value = "${formatDecimal(energyKwh, 4)} kWh",
                    label = localizedString("mobile.telemetry_energy_hour"),
                    color = SemanticColors.Default.info
                )

                // Cost
                ImpactCard(
                    icon = CIRISIcons.wallet,  // Dollar/Wallet
                    value = "$${formatDecimal(costCents / 100, 2)}",
                    label = localizedString("mobile.telemetry_cost_hour"),
                    color = SemanticColors.Default.accentTertiary
                )
            }

            HorizontalDivider()

            // Token usage
            Text(
                text = localizedString("mobile.system_token_details"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Medium
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                TokenMetric(label = localizedString("mobile.telemetry_tokens_24h"), value = tokens24h)
                TokenMetric(label = localizedString("mobile.telemetry_tokens_hour"), value = tokensLastHour)
            }
        }
    }
}

@Composable
private fun ImpactCard(
    icon: ImageVector,
    value: String,
    label: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        color = color.copy(alpha = 0.1f),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(24.dp),
                tint = color
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
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
private fun TokenMetric(
    label: String,
    value: Int,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = value.toString(),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
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
private fun ProcessorControlCard(
    isPaused: Boolean,
    cognitiveState: String,
    queueDepth: Int,
    onPause: () -> Unit,
    onResume: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Status
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val statusColor = if (isPaused) SemanticColors.Default.warning else SemanticColors.Default.success
                    Surface(
                        color = statusColor.copy(alpha = 0.2f),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text(
                            text = if (isPaused) localizedString("mobile.runtime_paused") else localizedString("mobile.runtime_running"),
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = statusColor
                        )
                    }
                    Text(
                        text = localizedString("mobile.system_processor_status"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Cognitive state
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = cognitiveState,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = getCognitiveStateColor(cognitiveState)
                    )
                    Text(
                        text = localizedString("mobile.system_cognitive_state"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Queue depth
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = queueDepth.toString(),
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = localizedString("mobile.system_queue_depth"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Control button
            Button(
                onClick = if (isPaused) onResume else onPause,
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable(if (isPaused) "btn_resume_runtime" else "btn_pause_runtime") {
                        if (isPaused) onResume() else onPause()
                    },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isPaused) SemanticColors.Default.success else SemanticColors.Default.warning
                )
            ) {
                Text(if (isPaused) localizedString("mobile.runtime_resume") else localizedString("mobile.runtime_pause"))
            }

            // Info note
            Surface(
                color = SemanticColors.Default.surfaceInfo,
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = localizedString("mobile.system_processor_note"),
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = SemanticColors.Default.onInfo
                )
            }
        }
    }
}

@Composable
private fun ServicesHealthGrid(
    services: List<SystemServiceInfo>,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Status legend
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                StatusLegendItem(color = SemanticColors.Default.success, label = localizedString("mobile.services_healthy"))
                StatusLegendItem(color = SemanticColors.Default.warning, label = localizedString("mobile.services_degraded"))
                StatusLegendItem(color = SemanticColors.Default.error, label = localizedString("mobile.services_unhealthy"))
            }

            HorizontalDivider()

            // Services grid (2 columns)
            val chunkedServices = services.chunked(2)
            chunkedServices.forEach { row ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    row.forEach { service ->
                        ServiceChip(
                            service = service,
                            modifier = Modifier.weight(1f)
                        )
                    }
                    // Fill empty space if odd number
                    if (row.size == 1) {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusLegendItem(
    color: Color,
    label: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(color)
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun ServiceChip(
    service: SystemServiceInfo,
    modifier: Modifier = Modifier
) {
    val semantic = SemanticColors.Default
    val color = when {
        service.healthy -> semantic.success
        service.available -> semantic.warning
        else -> semantic.error
    }

    Surface(
        modifier = modifier,
        color = color.copy(alpha = 0.1f),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(color)
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = service.name,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1
                )
                service.serviceType?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1
                    )
                }
            }
        }
    }
}

@Composable
private fun ChannelCard(
    channel: SystemChannelInfo,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = channel.displayName,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = localizedString("mobile.system_channel_type", mapOf("type" to channel.channelType)),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = localizedString("mobile.system_channel_messages", mapOf("count" to channel.messageCount.toString())),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(if (channel.isActive) SemanticColors.Default.online else SemanticColors.Default.inactive)
            )
        }
    }
}

// Helper functions
private fun getHealthColor(health: String?): Color {
    val semantic = SemanticColors.Default
    return when (health?.lowercase()) {
        "healthy" -> semantic.success
        "degraded" -> semantic.warning
        "unhealthy" -> semantic.error
        else -> Color.Gray
    }
}

private fun getHealthIcon(health: String?): ImageVector {
    return when (health?.lowercase()) {
        "healthy" -> CIRISIcons.check
        "degraded" -> CIRISIcons.warning
        "unhealthy" -> CIRISIcons.xmark
        else -> CIRISIcons.question
    }
}

private fun getUsageColor(percent: Int): Color {
    val semantic = SemanticColors.Default
    return when {
        percent < 50 -> semantic.success
        percent < 80 -> semantic.warning
        else -> semantic.error
    }
}

private fun getCognitiveStateColor(state: String): Color {
    val semantic = SemanticColors.Default
    return when (state.uppercase()) {
        "WORK" -> semantic.success
        "PLAY" -> semantic.info
        "SOLITUDE", "DREAM" -> semantic.warning
        "WAKEUP", "SHUTDOWN" -> Color(0xFFF97316) // Orange for transitional states
        else -> Color.Gray
    }
}

// Data classes

data class SystemScreenData(
    val health: String? = null,
    val uptime: String? = null,
    val memoryMb: Int = 0,
    val memoryPercent: Int = 0,
    val cpuPercent: Int = 0,
    val diskUsedMb: Double = 0.0,
    val carbonGrams: Double = 0.0,
    val energyKwh: Double = 0.0,
    val costCents: Double = 0.0,
    val tokensLastHour: Int = 0,
    val tokens24h: Int = 0,
    val isPaused: Boolean = false,
    val cognitiveState: String = "WORK",
    val queueDepth: Int = 0,
    val services: List<SystemServiceInfo> = emptyList(),
    val channels: List<SystemChannelInfo> = emptyList()
)

data class SystemServiceInfo(
    val name: String,
    val healthy: Boolean,
    val available: Boolean,
    val serviceType: String? = null,
    val capabilities: List<String> = emptyList()
)

data class SystemChannelInfo(
    val channelId: String,
    val displayName: String,
    val channelType: String,
    val isActive: Boolean,
    val messageCount: Int = 0,
    val lastActivity: String? = null
)

/**
 * Format a double value with the specified number of decimal places.
 * KMP-compatible replacement for String.format("%.Xf", value)
 */
private fun formatDecimal(value: Double, decimals: Int): String {
    val multiplier = when (decimals) {
        1 -> 10.0
        2 -> 100.0
        3 -> 1000.0
        4 -> 10000.0
        5 -> 100000.0
        else -> 10.0.let { base -> (1..decimals).fold(1.0) { acc, _ -> acc * base } }
    }
    val rounded = (value * multiplier).toLong() / multiplier
    val str = rounded.toString()
    // Ensure we have enough decimal places
    val dotIndex = str.indexOf('.')
    return if (dotIndex < 0) {
        "$str.${"0".repeat(decimals)}"
    } else {
        val currentDecimals = str.length - dotIndex - 1
        if (currentDecimals < decimals) {
            str + "0".repeat(decimals - currentDecimals)
        } else {
            str
        }
    }
}
