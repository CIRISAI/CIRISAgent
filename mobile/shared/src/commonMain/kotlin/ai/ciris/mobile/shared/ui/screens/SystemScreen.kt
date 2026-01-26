package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
                title = { Text("System Status") },
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
                        text = "Resource Usage",
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
                        text = "Environmental Impact",
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
                        text = "Main Processor",
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
                            text = "Services Health (${systemData.services.size} Services)",
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
                            text = "Active Communication Channels",
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
            title = { Text(if (action == "pause") "Pause Runtime" else "Resume Runtime") },
            text = {
                Text(
                    if (action == "pause")
                        "Are you sure you want to pause the runtime? This will temporarily stop all message processing."
                    else
                        "Are you sure you want to resume the runtime? Message processing will continue."
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (action == "pause") onPauseRuntime() else onResumeRuntime()
                        showConfirmDialog = null
                    }
                ) {
                    Text("Confirm")
                }
            },
            dismissButton = {
                TextButton(onClick = { showConfirmDialog = null }) {
                    Text("Cancel")
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
                        Text(
                            text = getHealthIcon(health),
                            style = MaterialTheme.typography.titleMedium
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
                    text = "Overall Health",
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
                    text = "Uptime",
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
                label = "CPU Usage",
                value = "$cpuPercent%",
                progress = cpuPercent / 100f,
                color = getUsageColor(cpuPercent)
            )

            // Memory
            ResourceBar(
                label = "Memory Usage",
                value = "$memoryMb MB",
                progress = memoryPercent / 100f,
                color = getUsageColor(memoryPercent),
                subtitle = "$memoryPercent% utilized"
            )

            // Disk
            val diskGb = diskUsedMb / 1024.0
            val diskDisplay = if (diskGb >= 1.0) "%.1f GB".format(diskGb) else "%.0f MB".format(diskUsedMb)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Disk Usage",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = diskDisplay,
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color(0xFF10B981)
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
                    icon = "\uD83C\uDF0D", // Earth
                    value = "%.3f kg".format(carbonGrams / 1000),
                    label = "CO2 Last Hour",
                    color = Color(0xFF10B981)
                )

                // Energy
                ImpactCard(
                    icon = "\u26A1", // Lightning
                    value = "%.4f kWh".format(energyKwh),
                    label = "Energy Last Hour",
                    color = Color(0xFF3B82F6)
                )

                // Cost
                ImpactCard(
                    icon = "\uD83D\uDCB2", // Dollar
                    value = "$%.2f".format(costCents / 100),
                    label = "Cost Last Hour",
                    color = Color(0xFF8B5CF6)
                )
            }

            HorizontalDivider()

            // Token usage
            Text(
                text = "Token Usage Details",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Medium
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                TokenMetric(label = "Total Tokens (24h)", value = tokens24h)
                TokenMetric(label = "Tokens/Hour", value = tokensLastHour)
            }
        }
    }
}

@Composable
private fun ImpactCard(
    icon: String,
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
            Text(
                text = icon,
                style = MaterialTheme.typography.titleLarge
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
                    Surface(
                        color = if (isPaused) Color(0xFFF59E0B).copy(alpha = 0.2f) else Color(0xFF10B981).copy(alpha = 0.2f),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text(
                            text = if (isPaused) "PAUSED" else "RUNNING",
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (isPaused) Color(0xFFF59E0B) else Color(0xFF10B981)
                        )
                    }
                    Text(
                        text = "Processor Status",
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
                        text = "Cognitive State",
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
                        text = "Queue Depth",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Control button
            Button(
                onClick = if (isPaused) onResume else onPause,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isPaused) Color(0xFF10B981) else Color(0xFFF59E0B)
                )
            ) {
                Text(if (isPaused) "Resume Runtime" else "Pause Runtime")
            }

            // Info note
            Surface(
                color = Color(0xFF3B82F6).copy(alpha = 0.1f),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "The CIRIS system has one main processor that cycles through cognitive states. Pausing affects the entire processor.",
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF1E40AF)
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
                StatusLegendItem(color = Color(0xFF10B981), label = "Healthy")
                StatusLegendItem(color = Color(0xFFF59E0B), label = "Degraded")
                StatusLegendItem(color = Color(0xFFEF4444), label = "Unhealthy")
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
    val color = when {
        service.healthy -> Color(0xFF10B981)
        service.available -> Color(0xFFF59E0B)
        else -> Color(0xFFEF4444)
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
                    text = "Type: ${channel.channelType}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "Messages: ${channel.messageCount}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(if (channel.isActive) Color(0xFF10B981) else Color.Gray)
            )
        }
    }
}

// Helper functions
private fun getHealthColor(health: String?): Color {
    return when (health?.lowercase()) {
        "healthy" -> Color(0xFF10B981)
        "degraded" -> Color(0xFFF59E0B)
        "unhealthy" -> Color(0xFFEF4444)
        else -> Color.Gray
    }
}

private fun getHealthIcon(health: String?): String {
    return when (health?.lowercase()) {
        "healthy" -> "\u2713" // Checkmark
        "degraded" -> "!"
        "unhealthy" -> "\u2717" // X
        else -> "?"
    }
}

private fun getUsageColor(percent: Int): Color {
    return when {
        percent < 50 -> Color(0xFF10B981)
        percent < 80 -> Color(0xFFF59E0B)
        else -> Color(0xFFEF4444)
    }
}

private fun getCognitiveStateColor(state: String): Color {
    return when (state.uppercase()) {
        "WORK" -> Color(0xFF10B981)
        "PLAY" -> Color(0xFF3B82F6)
        "SOLITUDE", "DREAM" -> Color(0xFFF59E0B)
        "WAKEUP", "SHUTDOWN" -> Color(0xFFF97316)
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
