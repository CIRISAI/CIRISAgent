package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.WAStatusData
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Wise Authority screen for managing deferrals and viewing WA status
 *
 * Features:
 * - WA service status overview
 * - Pending deferrals list
 * - Deferral details and resolution
 * - Auto-refresh every 10 seconds
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WiseAuthorityScreen(
    waStatus: WAStatusData?,
    deferrals: List<DeferralData>,
    isLoading: Boolean,
    isResolving: Boolean,
    onResolveDeferral: (deferralId: String, resolution: String, guidance: String) -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var selectedDeferral by remember { mutableStateOf<DeferralData?>(null) }
    var showResolveDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_human_deferrals")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_wa_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onRefresh,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_wa_refresh") { onRefresh() }
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
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
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
            // WA Status Overview
            item {
                WAStatusCard(waStatus = waStatus)
            }

            // Deferrals Section Header
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = localizedString("wa_pending"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    if (isLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            strokeWidth = 2.dp
                        )
                    }
                }
            }

            // Deferrals List
            if (deferrals.isEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = localizedString("wa_no_pending"),
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            } else {
                items(deferrals) { deferral ->
                    DeferralCard(
                        deferral = deferral,
                        onClick = {
                            selectedDeferral = deferral
                            showResolveDialog = true
                        }
                    )
                }
            }
        }
    }

    // Resolve Deferral Dialog
    if (showResolveDialog && selectedDeferral != null) {
        ResolveDeferralDialog(
            deferral = selectedDeferral!!,
            isResolving = isResolving,
            onDismiss = {
                showResolveDialog = false
                selectedDeferral = null
            },
            onResolve = { resolution, guidance ->
                onResolveDeferral(selectedDeferral!!.deferralId, resolution, guidance)
                showResolveDialog = false
                selectedDeferral = null
            }
        )
    }
}

@Composable
private fun WAStatusCard(
    waStatus: WAStatusData?,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp)
        ) {
            // Header with health indicator
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("wa_service_status"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(
                                if (waStatus?.serviceHealthy == true)
                                    SemanticColors.Default.success
                                else
                                    SemanticColors.Default.error
                            )
                    )
                    Text(
                        text = if (waStatus?.serviceHealthy == true) localizedString("telemetry_online") else localizedString("status_offline"),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Stats Grid
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatItem(
                    label = "Active WAs",
                    value = waStatus?.activeWAs?.toString() ?: "-",
                    color = SemanticColors.Default.info
                )
                StatItem(
                    label = localizedString("status_pending"),
                    value = waStatus?.pendingDeferrals?.toString() ?: "-",
                    color = if ((waStatus?.pendingDeferrals ?: 0) > 0)
                        SemanticColors.Default.warning
                    else
                        SemanticColors.Default.success
                )
                StatItem(
                    label = "24h Total",
                    value = waStatus?.deferrals24h?.toString() ?: "-",
                    color = Color(0xFF8B5CF6) // Purple - theme accent
                )
            }

            if (waStatus != null && waStatus.averageResolutionTimeMinutes > 0) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = localizedString("wa_avg_resolution").replace("{time}", ((waStatus.averageResolutionTimeMinutes * 10).toInt() / 10.0).toString()),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                )
            }

            // Subscribers Section
            if (waStatus != null && waStatus.subscribers.isNotEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f))
                Spacer(modifier = Modifier.height(12.dp))

                Text(
                    text = localizedString("wa_bus_subscribers"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Display subscribers as chips in a flow row
                @OptIn(ExperimentalLayoutApi::class)
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    waStatus.subscribers.forEach { subscriber ->
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                        ) {
                            Text(
                                text = subscriber,
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatItem(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onPrimaryContainer
        )
    }
}

@Composable
private fun DeferralCard(
    deferral: DeferralData,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val priorityColor = when (deferral.priority.lowercase()) {
        "high", "critical" -> SemanticColors.Default.error
        "medium" -> SemanticColors.Default.warning
        else -> SemanticColors.Default.success
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testableClickable("item_deferral_${deferral.deferralId.take(8)}") { onClick() },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            // Header row with priority badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = deferral.deferralId.take(12) + "...",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = priorityColor.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = deferral.priority.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = priorityColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Question or Reason
            Text(
                text = deferral.question ?: deferral.reason,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Metadata row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = localizedString("wa_from").replace("{user}", deferral.deferredBy),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = formatTimestamp(deferral.createdAt),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Status row
            if (deferral.status != "pending") {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = localizedString("wa_status").replace("{status}", deferral.status),
                    style = MaterialTheme.typography.bodySmall,
                    color = when (deferral.status) {
                        "resolved" -> SemanticColors.Default.success
                        "rejected" -> SemanticColors.Default.error
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }
                )
            }
        }
    }
}

@Composable
private fun ResolveDeferralDialog(
    deferral: DeferralData,
    isResolving: Boolean,
    onDismiss: () -> Unit,
    onResolve: (resolution: String, guidance: String) -> Unit
) {
    var guidance by remember { mutableStateOf("") }
    var selectedResolution by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = { if (!isResolving) onDismiss() },
        title = {
            Text(localizedString("wa_resolve"))
        },
        text = {
            Column(
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Question/Reason
                Text(
                    text = deferral.question ?: deferral.reason,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )

                // Context if available
                deferral.context?.let { context ->
                    if (context.isNotEmpty()) {
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant
                            )
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp)
                            ) {
                                Text(
                                    text = localizedString("wa_context"),
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                context.forEach { (key, value) ->
                                    Text(
                                        text = "$key: $value",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    }
                }

                HorizontalDivider()

                // Guidance input FIRST (so buttons stay visible when keyboard opens)
                Text(
                    text = localizedString("wa_guidance"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )

                OutlinedTextField(
                    value = guidance,
                    onValueChange = { guidance = it },
                    placeholder = { Text(localizedString("wa_guidance_placeholder")) },
                    modifier = Modifier.fillMaxWidth().testable("input_wisdom_guidance"),
                    minLines = 2,
                    maxLines = 4,
                    enabled = !isResolving
                )

                HorizontalDivider()

                // Resolution options - NOW BELOW text field
                Text(
                    text = localizedString("wa_decision"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )

                // Use Column instead of Row for better visibility
                Column(
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Button(
                            onClick = {
                                if (guidance.isNotBlank()) {
                                    onResolve("approve", guidance)
                                }
                            },
                            enabled = guidance.isNotBlank() && !isResolving,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SemanticColors.Default.success
                            ),
                            modifier = Modifier
                                .weight(1f)
                                .testableClickable("btn_resolution_approve") {
                                    if (guidance.isNotBlank()) onResolve("approve", guidance)
                                }
                        ) {
                            Icon(Icons.Filled.Check, contentDescription = null, Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(localizedString("wa_approve"))
                        }
                        Button(
                            onClick = {
                                if (guidance.isNotBlank()) {
                                    onResolve("reject", guidance)
                                }
                            },
                            enabled = guidance.isNotBlank() && !isResolving,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SemanticColors.Default.error
                            ),
                            modifier = Modifier
                                .weight(1f)
                                .testableClickable("btn_resolution_reject") {
                                    if (guidance.isNotBlank()) onResolve("reject", guidance)
                                }
                        ) {
                            Icon(Icons.Filled.Close, contentDescription = null, Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(localizedString("wa_reject"))
                        }
                    }

                    OutlinedButton(
                        onClick = {
                            if (guidance.isNotBlank()) {
                                onResolve("modify", guidance)
                            }
                        },
                        enabled = guidance.isNotBlank() && !isResolving,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_resolution_modify") {
                                if (guidance.isNotBlank()) onResolve("modify", guidance)
                            }
                    ) {
                        Text(localizedString("wa_modify"))
                    }
                }

                if (isResolving) {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp
                        )
                    }
                }
            }
        },
        confirmButton = {
            // Empty - buttons are now inline
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isResolving,
                modifier = Modifier.testableClickable("btn_resolve_cancel") { onDismiss() }
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        }
    )
}

// Helper function to format timestamp
private fun formatTimestamp(timestamp: String): String {
    // Simple formatting - in production you'd use kotlinx-datetime
    return try {
        if (timestamp.length > 16) {
            timestamp.substring(0, 16).replace("T", " ")
        } else {
            timestamp
        }
    } catch (e: Exception) {
        timestamp
    }
}
