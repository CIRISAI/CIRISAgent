package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.EdgeHalfReading
import ai.ciris.mobile.shared.models.IngestReading
import ai.ciris.mobile.shared.models.NodeExplain
import ai.ciris.mobile.shared.models.NodeOperatorState
import ai.ciris.mobile.shared.models.NodeStateReadout
import ai.ciris.mobile.shared.models.OperatorBand
import ai.ciris.mobile.shared.models.OperatorMessage
import ai.ciris.mobile.shared.models.OperatorSource
import ai.ciris.mobile.shared.models.TracePlaneReading
import ai.ciris.mobile.shared.models.TracePlaneStanding
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
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
 * - **The operator surface (`GET /v1/node/state`)** — CIRISServer#356/#369/#370
 *
 * The node-state band is the FIRST thing on this screen, above the telemetry,
 * and it is never replaced by the telemetry spinner. That placement is the
 * lesson of `FSD/RCA_INGEST_REJECTION_2026-08-05.md`: the trace plane was dead
 * for 71 hours while every layer was individually right, because the one
 * reading that would have said so rendered nowhere a human looked.
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
    modifier: Modifier = Modifier,
    /**
     * The composed operator surface. Defaults to [NodeStateReadout.Loading] so
     * an un-wired caller renders "still asking" rather than a fabricated
     * healthy zero — the collapse this whole surface exists to prevent.
     */
    nodeState: NodeStateReadout = NodeStateReadout.Loading
) {
    var showConfirmDialog by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.nav_system")) },
                navigationIcon = {
                    // Suppressed on compact viewports — the global 3-state
                    // overlay button in CIRISApp handles back navigation
                    // there to avoid the prior "back arrow + signet stacked"
                    // bug. Wider viewports (tablet/desktop) keep this arrow.
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onNavigateBack,
                            modifier = Modifier.testableClickable("btn_system_back") { onNavigateBack() }
                        ) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("mobile.common_back")
                            )
                        }
                    } else {
                        // Reserve the global signet/back overlay's footprint so the
                        // TopAppBar title doesn't slide underneath it on compact.
                        Spacer(Modifier.width(56.dp))
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
        // ONE LazyColumn, always. The telemetry spinner used to REPLACE this
        // whole list, which would have hidden the node-state band behind a
        // spinner — "we are still asking" rendered as "nothing to say" is the
        // exact collapse #369 exists to prevent. The spinner is now an item
        // among items, and the band is always the first thing on the screen.
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // ── The operator surface, above everything and never drilled into ──
            item {
                NodeStateSection(nodeState)
            }

            if (isLoading && systemData.health == null) {
                item {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 48.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
            } else {
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

// ─────────────────────────────────────────────────────────────────────────────
// The operator surface — GET /v1/node/state (CIRISServer#356 / #369 / #370).
//
// THE RULE EVERY COMPOSABLE BELOW OBEYS:
//
//   A zero renders as ITS OWN state, with its own words and its own colour.
//   "We could not ask the corpus" and "the corpus holds nothing" and "it holds
//   traces, none recent" are three facts. A dash, a spinner or one shared empty
//   state for all three recreates the defect this surface exists to cure —
//   FSD/RCA_INGEST_REJECTION_2026-08-05.md, 71 hours of a dead trace plane that
//   every layer reported correctly and no instrument said out loud.
//
// And: `unknown` is never drawn like `green`. An uncomputed signal is not a
// healthy one. `unreachable` is never drawn like `red` — red is a real reading
// from a node that answered.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Resolve a server `{id, text}` pair: the localization bundle first, the
 * English `text` only as a marked fallback.
 *
 * [ai.ciris.mobile.shared.localization.LocalizationManager.getString] returns
 * the KEY itself when it cannot resolve, so an unresolved id is detected by
 * identity — that is the whole fallback test, and it is why no English sentence
 * is ever hardcoded here.
 */
@Composable
private fun operatorText(msg: OperatorMessage?): String {
    if (msg == null) return ""
    if (msg.id.isBlank()) return msg.text
    val resolved = localizedString(msg.id)
    return if (resolved == msg.id) msg.text else resolved
}

/** The colour for a band. `unknown` gets its OWN colour — never green's. */
private fun bandColor(band: OperatorBand?): Color {
    val semantic = SemanticColors.Default
    return when (band) {
        OperatorBand.GREEN -> semantic.success
        OperatorBand.YELLOW -> semantic.warning
        OperatorBand.RED -> semantic.error
        // Blue, not a pale green and not grey-as-absence: "could not be
        // computed" is a reading in its own right and must read as one.
        OperatorBand.UNKNOWN -> semantic.info
        // A token this app does not know. The node is ahead of the app; treat
        // it as uncomputed, never as healthy.
        null -> semantic.accentTertiary
    }
}

/**
 * The wire token as a chip: persist's own vocabulary, never paraphrased.
 *
 * The token is also published to the test-automation tree as the element's
 * `text`, because the distinctions this surface exists to keep (`never_admitted`
 * vs `unreadable` vs `dark`; `not_exercised` vs `idle`) are exactly what a QA
 * walk has to be able to read back. Without it a walk can only see THAT a pill
 * rendered, not WHICH standing it carries — and "a pill rendered" is true for
 * every one of the states that must not be confused with each other.
 */
@Composable
private fun BandPill(band: OperatorBand?, token: String, testTagName: String) {
    val color = bandColor(band)
    Surface(
        color = color.copy(alpha = 0.18f),
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier
            .border(1.dp, color.copy(alpha = 0.55f), RoundedCornerShape(6.dp))
            .testable(testTagName, token)
    ) {
        Text(
            text = token.replace('_', ' ').uppercase(),
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = color
        )
    }
}

/**
 * The age of the last admitted trace, at the server's own read instant.
 *
 * Formatted from the server's `age_seconds` rather than from this device's
 * clock: the band was computed against the node's clock and a second clock
 * would be a second answer to one question.
 */
@Composable
private fun ageLabel(seconds: Long): String {
    if (seconds < 0) {
        return localizedString("operator_ui.age_future", mapOf("v" to ageLabel(-seconds)))
    }
    val days = seconds / 86_400
    val hours = (seconds % 86_400) / 3_600
    val minutes = (seconds % 3_600) / 60
    return when {
        days > 0 -> localizedString(
            "operator_ui.age_days",
            mapOf("d" to days.toString(), "h" to hours.toString())
        )
        hours > 0 -> localizedString(
            "operator_ui.age_hours",
            mapOf("h" to hours.toString(), "m" to minutes.toString())
        )
        minutes > 0 -> localizedString("operator_ui.age_minutes", mapOf("m" to minutes.toString()))
        else -> localizedString("operator_ui.age_seconds", mapOf("s" to seconds.toString()))
    }
}

/**
 * A label/value line. The value is a fact, never a placeholder dash.
 *
 * [testTagName] is optional but load-bearing for the rows whose PRESENCE is the
 * assertion: an `unreadable` trace plane must show neither an arrival instant
 * nor a row count, while `never_admitted` must show the row count and cannot
 * show an instant. A walk can only check that if the rows are addressable, so
 * the trace-plane rows pass a tag and carry their value as the element text.
 */
@Composable
private fun OperatorFactRow(
    label: String,
    value: String,
    valueColor: Color? = null,
    testTagName: String? = null
) {
    Row(
        modifier = (testTagName?.let { Modifier.testable(it, value) } ?: Modifier)
            .fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * The whole operator surface, top of the System screen.
 *
 * Five arms, and the four non-[NodeStateReadout.Present] ones are deliberately
 * NOT drawn as bands: an unreachable node has no band, and dressing it as red
 * would be a fabricated reading.
 */
@Composable
private fun NodeStateSection(readout: NodeStateReadout, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = localizedString("operator_ui.title"),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )
        when (readout) {
            is NodeStateReadout.Loading -> NotABandCard(
                title = localizedString("operator_ui.reading_title"),
                body = localizedString("operator_ui.reading_body"),
                detail = null,
                testTagName = "node_state_loading"
            )
            is NodeStateReadout.Unreachable -> NotABandCard(
                title = localizedString("operator_ui.unreachable_title"),
                body = localizedString("operator_ui.unreachable_body"),
                detail = readout.detail,
                testTagName = "node_state_unreachable"
            )
            is NodeStateReadout.Refused -> NotABandCard(
                title = localizedString("operator_ui.refused_title"),
                body = localizedString("operator_ui.refused_body"),
                detail = "HTTP ${readout.status} — ${readout.detail}",
                testTagName = "node_state_refused"
            )
            is NodeStateReadout.NotOffered -> NotABandCard(
                title = localizedString("operator_ui.not_offered_title"),
                body = localizedString("operator_ui.not_offered_body"),
                detail = null,
                testTagName = "node_state_not_offered"
            )
            is NodeStateReadout.Malformed -> NotABandCard(
                title = localizedString("operator_ui.malformed_title"),
                body = localizedString("operator_ui.malformed_body"),
                detail = readout.detail,
                testTagName = "node_state_malformed"
            )
            is NodeStateReadout.Present -> NodeStatePresent(readout.state)
        }
    }
}

/**
 * A read that produced NO band: still loading, not reached, refused, or not
 * understood.
 *
 * Outlined and neutral on purpose — it must not be mistaken for any of the four
 * bands, least of all for `red`, which is a real reading from a node that
 * answered. This is "no answer", and it says so in words.
 */
@Composable
private fun NotABandCard(title: String, body: String, detail: String?, testTagName: String) {
    val neutral = MaterialTheme.colorScheme.onSurfaceVariant
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, neutral.copy(alpha = 0.45f), RoundedCornerShape(12.dp))
            .testable(testTagName),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = CIRISIcons.question,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                    tint = neutral
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = neutral
                )
            }
            Text(
                text = body,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            detail?.takeIf { it.isNotBlank() }?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = neutral.copy(alpha = 0.8f)
                )
            }
        }
    }
}

/** A real reading from a reachable node. Only here does a band mean anything. */
@Composable
private fun NodeStatePresent(state: NodeOperatorState) {
    // The roll-up headline. persist's band, carried; the sentence is the
    // server's own localized message, resolved by id.
    Card(
        modifier = Modifier.fillMaxWidth().testable("node_state_headline"),
        colors = CardDefaults.cardColors(
            containerColor = bandColor(state.parsedBand).copy(alpha = 0.10f)
        )
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                BandPill(state.parsedBand, state.band, "node_state_band")
                Spacer(Modifier.width(10.dp))
                Text(
                    text = localizedString("operator_ui.as_of", mapOf("t" to state.asOf)),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(
                text = operatorText(state.headline),
                style = MaterialTheme.typography.bodySmall
            )
            if (state.parsedBand == null) {
                Text(
                    text = localizedString(
                        "operator_ui.unrecognized_reading",
                        mapOf("token" to state.band)
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = bandColor(null)
                )
            }
        }
    }

    // CIRISServer#369 — the reading whose absence cost 71 hours, first.
    TracePlaneCard(state.tracePlane)

    // CIRISServer#370 — read beside the trace plane on purpose: dark + stuck
    // producer is the 2026-08-05 condition; dark + clean is "nothing is even
    // reaching this node".
    IngestCard(state.ingest)

    // Every uncomputed signal, named. A red roll-up OUTRANKS an unknown, so
    // without this list an uncomputed signal disappears behind a red headline.
    if (state.unknown.isNotEmpty()) {
        Card(
            modifier = Modifier.fillMaxWidth().testable("node_state_unknown_list"),
            colors = CardDefaults.cardColors(
                containerColor = SemanticColors.Default.info.copy(alpha = 0.10f)
            )
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = localizedString(
                        "operator_ui.uncomputed",
                        mapOf("count" to state.unknown.size.toString())
                    ),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = SemanticColors.Default.info
                )
                state.unknown.forEach { signal ->
                    Text(
                        text = signal,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }

    // The two edge halves, at reading granularity. Their zeroes divide the same
    // way and get the same treatment.
    state.carriage?.let {
        EdgeHalfCard(localizedString("operator_ui.carriage"), it, "node_state_carriage")
    }
    state.receive?.let {
        EdgeHalfCard(localizedString("operator_ui.receive"), it, "node_state_receive")
    }

    // persist's six signals, each with its own narrowed token. Two tokens may
    // share one band on purpose (never_drilled vs stale) — so the token shows.
    state.nodeExplains?.takeIf { it.isNotEmpty() }?.let { explains ->
        NodeSignalsCard(explains)
    }

    // A source that contributed nothing says so, with its reason. Never an
    // absent key, never a healthy default.
    val absent = listOfNotNull(
        state.sources?.nodeState?.takeIf { !it.present },
        state.sources?.edgeMetrics?.takeIf { !it.present },
        state.sources?.traceCorpus?.takeIf { !it.present },
        state.sources?.ingestRefusals?.takeIf { !it.present }
    )
    if (absent.isNotEmpty()) {
        AbsentSourcesCard(absent)
    }
}

/**
 * **CIRISServer#369 — is the trace plane alive.**
 *
 * Every standing is its own arm, and the four zero-ish ones never share a
 * rendering:
 *
 * - `unreadable`   → no instant, no row count, and the words "could not ask".
 * - `never_admitted` → an explicit "nothing has ever been admitted", plus the
 *   row count that makes it checkable. Not a dash.
 * - `future_dated` → the instant IS shown, flagged as the producer's clock.
 * - `dark` / `quiet` / `live` → the instant, its age, and the band edges.
 */
@Composable
private fun TracePlaneCard(reading: TracePlaneReading?) {
    if (reading == null) {
        // The key was absent from the payload entirely. That is not a healthy
        // plane and not an empty one — it is a surface this app could not read.
        NotABandCard(
            title = localizedString("operator_ui.trace_plane"),
            body = localizedString("operator_ui.reading_absent"),
            detail = null,
            testTagName = "node_state_trace_absent"
        )
        return
    }
    val band = reading.parsedBand
    val color = bandColor(band)
    val standing = reading.parsedStanding
    Card(
        modifier = Modifier
            .fillMaxWidth()
            // A dark plane is the loudest thing on this screen: thicker border,
            // filled container. It is the one reading this node exists for.
            .border(
                if (band == OperatorBand.RED) 2.dp else 1.dp,
                color.copy(alpha = if (band == OperatorBand.RED) 0.9f else 0.35f),
                RoundedCornerShape(12.dp)
            )
            .testable("node_state_trace_plane"),
        colors = CardDefaults.cardColors(
            containerColor = color.copy(alpha = if (band == OperatorBand.RED) 0.18f else 0.08f)
        )
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = localizedString("operator_ui.trace_plane"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                BandPill(band, reading.standing, "node_state_trace_standing")
            }
            // The server's own sentence for THIS standing, resolved by id.
            Text(
                text = operatorText(reading.explains),
                style = MaterialTheme.typography.bodySmall
            )
            if (standing == null) {
                Text(
                    text = localizedString(
                        "operator_ui.unrecognized_reading",
                        mapOf("token" to reading.standing)
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = bandColor(null)
                )
            }

            // ── The distinct zeroes, one arm each ──
            when (standing) {
                TracePlaneStanding.UNREADABLE -> {
                    // No instant and NO row count: both would be inventions.
                    Text(
                        text = localizedString("operator_ui.corpus_unread"),
                        style = MaterialTheme.typography.bodySmall,
                        color = color
                    )
                    reading.unavailable?.let {
                        Text(
                            text = operatorText(it),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    reading.detail?.takeIf { it.isNotBlank() }?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                TracePlaneStanding.NEVER_ADMITTED -> {
                    // The corpus WAS read. It holds nothing. Both halves said.
                    Text(
                        text = localizedString("operator_ui.no_arrival_instant"),
                        style = MaterialTheme.typography.bodySmall,
                        color = color
                    )
                    OperatorFactRow(
                        label = localizedString("operator_ui.traces_held"),
                        value = (reading.rows ?: 0L).toString(),
                        testTagName = "trace_rows"
                    )
                }
                else -> {
                    // live / quiet / dark / future_dated / unrecognised: there
                    // is an instant, so show it and its age.
                    if (reading.lastAdmittedAt != null) {
                        OperatorFactRow(
                            label = localizedString("operator_ui.last_admitted"),
                            value = reading.lastAdmittedAt!!,
                            testTagName = "trace_last_admitted"
                        )
                        reading.ageSeconds?.let { secs ->
                            OperatorFactRow(
                                label = localizedString("operator_ui.age"),
                                value = ageLabel(secs),
                                valueColor = color,
                                testTagName = "trace_age"
                            )
                        }
                    } else {
                        // A standing that implies an instant, with none on the
                        // wire. Say that, rather than print an empty value.
                        Text(
                            text = localizedString("operator_ui.no_arrival_instant"),
                            style = MaterialTheme.typography.bodySmall,
                            color = color
                        )
                    }
                    reading.rows?.let {
                        OperatorFactRow(
                            label = localizedString("operator_ui.traces_held"),
                            value = it.toString(),
                            testTagName = "trace_rows"
                        )
                    }
                }
            }

            reading.bands?.let { b ->
                Text(
                    text = localizedString(
                        "operator_ui.thresholds",
                        mapOf(
                            "green" to b.greenMaxHours.toString(),
                            "yellow" to b.yellowMaxHours.toString()
                        )
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            // The limit of the reading, carried IN the payload — render it.
            reading.note?.let {
                Text(
                    text = operatorText(it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * **CIRISServer#370 — is the admission gate working overtime, and for whom.**
 *
 * The inverse reading: every refusal here may be individually CORRECT and the
 * aggregate still be a fault report about somebody upstream. `unattributed` is
 * its own arm because zero distinct signers is not a small stable identity set.
 */
@Composable
private fun IngestCard(reading: IngestReading?) {
    if (reading == null) {
        NotABandCard(
            title = localizedString("operator_ui.ingest"),
            body = localizedString("operator_ui.reading_absent"),
            detail = null,
            testTagName = "node_state_ingest_absent"
        )
        return
    }
    val band = reading.parsedBand
    val color = bandColor(band)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, color.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
            .testable("node_state_ingest"),
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.08f))
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = localizedString("operator_ui.ingest"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                BandPill(band, reading.standing, "node_state_ingest_standing")
            }
            Text(
                text = operatorText(reading.explains),
                style = MaterialTheme.typography.bodySmall
            )
            if (reading.parsedStanding == null) {
                Text(
                    text = localizedString(
                        "operator_ui.unrecognized_reading",
                        mapOf("token" to reading.standing)
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = bandColor(null)
                )
            }

            if (reading.unavailable != null) {
                // Unreadable ledger: NOT "nothing was refused". No counts at
                // all here — printing zeroes would be the collapse itself.
                Text(
                    text = operatorText(reading.unavailable),
                    style = MaterialTheme.typography.bodySmall,
                    color = color
                )
            } else {
                reading.refusalsPerHour?.let {
                    OperatorFactRow(
                        label = localizedString("operator_ui.refusals_per_hour"),
                        value = formatDecimal(it, 1),
                        valueColor = color
                    )
                }
                // The load-bearing dimension: two identities is a stuck client,
                // eight thousand at the same rate is a probe.
                reading.distinctSigners?.let {
                    OperatorFactRow(
                        label = localizedString("operator_ui.distinct_signers"),
                        value = it.toString()
                    )
                }
                reading.unattributedInWindow?.let {
                    OperatorFactRow(
                        label = localizedString("operator_ui.named_no_signer"),
                        value = it.toString()
                    )
                }
                if (reading.acceptedTotal != null || reading.refusedTotal != null) {
                    Text(
                        text = localizedString(
                            "operator_ui.accepted_refused",
                            mapOf(
                                "a" to (reading.acceptedTotal ?: 0L).toString(),
                                "r" to (reading.refusedTotal ?: 0L).toString()
                            )
                        ),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (reading.topSigners.isNotEmpty()) {
                    Text(
                        text = localizedString("operator_ui.top_signers"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    reading.topSigners.forEach { signer ->
                        OperatorFactRow(
                            label = signer.signerId,
                            value = signer.refusals.toString(),
                            valueColor = color
                        )
                    }
                }
                if (reading.windowTruncated) {
                    Text(
                        text = localizedString("operator_ui.window_floor"),
                        style = MaterialTheme.typography.bodySmall,
                        color = SemanticColors.Default.warning
                    )
                }
            }
            reading.note?.let {
                Text(
                    text = operatorText(it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/** One edge half — serving (carriage) or applying (receive). */
@Composable
private fun EdgeHalfCard(title: String, reading: EdgeHalfReading, testTagName: String) {
    val color = bandColor(reading.parsedBand)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, color.copy(alpha = 0.30f), RoundedCornerShape(12.dp))
            .testable(testTagName),
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.06f))
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                BandPill(reading.parsedBand, reading.standing, "${testTagName}_standing")
            }
            Text(
                text = operatorText(reading.explains),
                style = MaterialTheme.typography.bodySmall
            )
            reading.unavailable?.let {
                Text(
                    text = operatorText(it),
                    style = MaterialTheme.typography.bodySmall,
                    color = color
                )
            }
            // Counters only when the half was readable — a zero from an
            // unreadable counter bag is not a zero.
            if (reading.unavailable == null) {
                reading.withholdsTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.withholds"), it.toString())
                }
                reading.servedTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.served"), it.toString())
                }
                reading.roundsTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.rounds"), it.toString())
                }
                reading.applyRefusalsTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.apply_refusals"), it.toString())
                }
                // CIRISEdge#457 — the accepted-apply axes. Without these the
                // receive half showed refusals only, so "refused 1 of 50" and
                // "refused the only row it was ever offered" rendered alike.
                reading.appliedTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.applied"), it.toString())
                }
                reading.duplicateTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.duplicates"), it.toString())
                }
                // The denominator, last — every count above divides it.
                reading.decidedTotal?.let {
                    OperatorFactRow(localizedString("operator_ui.decided"), it.toString())
                }
            }
            reading.note?.let {
                Text(
                    text = operatorText(it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * persist's own signals, each carrying a NARROWED token beside its band.
 *
 * The token is shown because two tokens deliberately share one band —
 * `never_drilled` and `stale` are both red, and which one it is decides what an
 * operator does next.
 */
@Composable
private fun NodeSignalsCard(explains: List<NodeExplain>) {
    Card(
        modifier = Modifier.fillMaxWidth().testable("node_state_signals"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(
                text = localizedString("operator_ui.node_signals"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )
            explains.forEach { e ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = e.signal,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.weight(1f)
                        )
                        BandPill(e.parsedBand, e.token, "node_signal_${e.signal}")
                    }
                    Text(
                        text = operatorText(e.message),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/** Sources that contributed nothing, each with the reason it contributed nothing. */
@Composable
private fun AbsentSourcesCard(absent: List<OperatorSource>) {
    Card(
        modifier = Modifier.fillMaxWidth().testable("node_state_absent_sources"),
        colors = CardDefaults.cardColors(
            containerColor = SemanticColors.Default.info.copy(alpha = 0.08f)
        )
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                text = localizedString("operator_ui.sources_absent"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = SemanticColors.Default.info
            )
            absent.forEach { source ->
                Text(
                    text = source.producedBy,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = operatorText(source.unavailable),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                source.detail?.takeIf { it.isNotBlank() }?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
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
