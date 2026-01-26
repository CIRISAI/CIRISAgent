package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.WAStatusData
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
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
                title = { Text("Wise Authority") },
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
                        text = "Pending Deferrals",
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
                                text = "No pending deferrals",
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
                    text = "WA Service Status",
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
                                    Color(0xFF10B981) // Green
                                else
                                    Color(0xFFEF4444) // Red
                            )
                    )
                    Text(
                        text = if (waStatus?.serviceHealthy == true) "Healthy" else "Unhealthy",
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
                    color = Color(0xFF3B82F6) // Blue
                )
                StatItem(
                    label = "Pending",
                    value = waStatus?.pendingDeferrals?.toString() ?: "-",
                    color = if ((waStatus?.pendingDeferrals ?: 0) > 0)
                        Color(0xFFF59E0B) // Yellow
                    else
                        Color(0xFF10B981) // Green
                )
                StatItem(
                    label = "24h Total",
                    value = waStatus?.deferrals24h?.toString() ?: "-",
                    color = Color(0xFF8B5CF6) // Purple
                )
            }

            if (waStatus != null && waStatus.averageResolutionTimeMinutes > 0) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = "Avg resolution: ${String.format("%.1f", waStatus.averageResolutionTimeMinutes)} min",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                )
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
        "high", "critical" -> Color(0xFFEF4444) // Red
        "medium" -> Color(0xFFF59E0B) // Yellow
        else -> Color(0xFF10B981) // Green
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
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
                    text = "From: ${deferral.deferredBy}",
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
                    text = "Status: ${deferral.status}",
                    style = MaterialTheme.typography.bodySmall,
                    color = when (deferral.status) {
                        "resolved" -> Color(0xFF10B981)
                        "rejected" -> Color(0xFFEF4444)
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
            Text("Resolve Deferral")
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp)
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
                                    text = "Context",
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

                Divider()

                // Resolution options
                Text(
                    text = "Resolution",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = selectedResolution == "approve",
                        onClick = { selectedResolution = "approve" },
                        label = { Text("Approve") },
                        leadingIcon = if (selectedResolution == "approve") {
                            { Icon(Icons.Filled.Check, contentDescription = null, Modifier.size(16.dp)) }
                        } else null
                    )
                    FilterChip(
                        selected = selectedResolution == "reject",
                        onClick = { selectedResolution = "reject" },
                        label = { Text("Reject") },
                        leadingIcon = if (selectedResolution == "reject") {
                            { Icon(Icons.Filled.Close, contentDescription = null, Modifier.size(16.dp)) }
                        } else null
                    )
                    FilterChip(
                        selected = selectedResolution == "modify",
                        onClick = { selectedResolution = "modify" },
                        label = { Text("Modify") }
                    )
                }

                // Guidance input
                OutlinedTextField(
                    value = guidance,
                    onValueChange = { guidance = it },
                    label = { Text("Wisdom Guidance") },
                    placeholder = { Text("Provide guidance for this decision...") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    enabled = !isResolving
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    selectedResolution?.let { resolution ->
                        onResolve(resolution, guidance)
                    }
                },
                enabled = selectedResolution != null && guidance.isNotBlank() && !isResolving
            ) {
                if (isResolving) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                } else {
                    Text("Resolve")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isResolving
            ) {
                Text("Cancel")
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
