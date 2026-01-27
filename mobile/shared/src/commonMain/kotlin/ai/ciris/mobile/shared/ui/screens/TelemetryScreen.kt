package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
 * Telemetry screen for system metrics and service health
 * Based on TelemetryFragment.kt
 *
 * Features:
 * - Service status overview
 * - Resource usage (CPU, Memory, Disk)
 * - Cognitive state display
 * - Activity metrics (messages, tasks, errors)
 * - Auto-refresh every 5 seconds
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TelemetryScreen(
    telemetryData: TelemetryData,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("System Telemetry") },
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
            // Services overview
            item {
                ServicesOverviewCard(
                    healthyServices = telemetryData.healthyServices,
                    totalServices = telemetryData.totalServices,
                    cognitiveState = telemetryData.cognitiveState
                )
            }

            // Resource usage
            item {
                Text(
                    text = "Resource Usage",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            item {
                ResourceUsageCard(
                    cpuPercent = telemetryData.cpuPercent,
                    memoryMb = telemetryData.memoryMb,
                    diskUsedMb = telemetryData.diskUsedMb
                )
            }

            // Activity metrics
            item {
                Text(
                    text = "Activity (24h)",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            item {
                ActivityMetricsCard(
                    messagesProcessed = telemetryData.messagesProcessed24h,
                    tasksCompleted = telemetryData.tasksCompleted24h,
                    errors = telemetryData.errors24h
                )
            }

            // Service health list
            if (telemetryData.serviceHealthItems.isNotEmpty()) {
                item {
                    Text(
                        text = "Service Health",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(telemetryData.serviceHealthItems) { item ->
                    ServiceHealthRow(item = item)
                }
            }
        }
    }
}

@Composable
private fun ServicesOverviewCard(
    healthyServices: Int,
    totalServices: Int,
    cognitiveState: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            // Services online
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "$healthyServices/$totalServices",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (healthyServices == totalServices)
                        Color(0xFF10B981) // Green
                    else
                        Color(0xFFF59E0B) // Yellow
                )
                Text(
                    text = "Services Online",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }

            Divider(
                modifier = Modifier
                    .height(60.dp)
                    .width(1.dp)
            )

            // Cognitive state
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = cognitiveState,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = getCognitiveStateColor(cognitiveState)
                )
                Text(
                    text = "State",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}

@Composable
private fun ResourceUsageCard(
    cpuPercent: Int,
    memoryMb: Int,
    diskUsedMb: Double,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // CPU
            ResourceUsageRow(
                label = "CPU",
                value = "$cpuPercent%",
                progress = cpuPercent / 100f,
                color = getUsageColor(cpuPercent)
            )

            // Memory (assume 4GB max)
            val memoryPercent = (memoryMb * 100 / 4096).coerceIn(0, 100)
            ResourceUsageRow(
                label = "Memory",
                value = "$memoryMb MB",
                progress = memoryPercent / 100f,
                color = getUsageColor(memoryPercent)
            )

            // Disk
            val diskGb = diskUsedMb / 1024.0
            val diskPercent = ((diskUsedMb / 10240.0) * 100).toInt().coerceIn(0, 100)
            ResourceUsageRow(
                label = "Disk",
                value = if (diskGb >= 1.0) "${((diskGb * 10).toInt() / 10.0)} GB" else "${diskUsedMb.toInt()} MB",
                progress = diskPercent / 100f,
                color = getUsageColor(diskPercent)
            )
        }
    }
}

@Composable
private fun ResourceUsageRow(
    label: String,
    value: String,
    progress: Float,
    color: Color,
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
                color = color
            )
        }
        LinearProgressIndicator(
            progress = progress.coerceIn(0f, 1f),
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp),
            color = color,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
    }
}

@Composable
private fun ActivityMetricsCard(
    messagesProcessed: Int,
    tasksCompleted: Int,
    errors: Int,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            MetricRow("Messages Processed", messagesProcessed.toString())
            MetricRow("Tasks Completed", tasksCompleted.toString())
            MetricRow(
                "Errors",
                errors.toString(),
                valueColor = if (errors > 0) Color(0xFFEF4444) else Color.Unspecified
            )
        }
    }
}

@Composable
private fun MetricRow(
    label: String,
    value: String,
    valueColor: Color = Color.Unspecified,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            color = valueColor
        )
    }
}

@Composable
private fun ServiceHealthRow(
    item: ServiceHealthItem,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Status dot
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(
                        if (item.healthy) Color(0xFF10B981) else Color(0xFFEF4444)
                    )
            )

            // Service name
            Text(
                text = item.name,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f)
            )

            // Status
            Text(
                text = item.status,
                style = MaterialTheme.typography.bodyMedium,
                color = if (item.healthy)
                    Color(0xFF10B981)
                else
                    Color(0xFFEF4444)
            )
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

private fun getUsageColor(percent: Int): Color {
    return when {
        percent < 50 -> Color(0xFF10B981) // Green
        percent < 80 -> Color(0xFFF59E0B) // Yellow
        else -> Color(0xFFEF4444) // Red
    }
}

// Data classes

/**
 * Telemetry data model
 * Matches SystemOverviewData from TelemetryFragment.kt
 */
data class TelemetryData(
    val healthyServices: Int = 0,
    val totalServices: Int = 0,
    val cognitiveState: String = "WORK",
    val cpuPercent: Int = 0,
    val memoryMb: Int = 0,
    val diskUsedMb: Double = 0.0,
    val messagesProcessed24h: Int = 0,
    val tasksCompleted24h: Int = 0,
    val errors24h: Int = 0,
    val serviceHealthItems: List<ServiceHealthItem> = emptyList()
)

data class ServiceHealthItem(
    val name: String,
    val healthy: Boolean,
    val status: String
)
