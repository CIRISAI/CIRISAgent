package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Audit trail viewer screen for system audit entries.
 * Based on CIRISGUI-Standalone/apps/agui/app/audit/page.tsx
 *
 * Features:
 * - System audit trail viewing
 * - Filtering by service, action, and outcome
 * - Expandable entry details with JSON context
 * - Security information (hash chain, signature)
 * - Color-coded severity and outcome badges
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AuditScreen(
    auditState: AuditScreenState,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onFilterChange: (AuditFilter) -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showFilters by remember { mutableStateOf(false) }
    var expandedEntryId by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("System Audit Trail") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    // Filter toggle
                    TextButton(onClick = { showFilters = !showFilters }) {
                        Text(if (showFilters) "Hide Filters" else "Filters")
                    }
                    IconButton(onClick = onRefresh, enabled = !auditState.isLoading) {
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
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Filters section
            if (showFilters) {
                AuditFiltersSection(
                    filter = auditState.filter,
                    onFilterChange = onFilterChange
                )
            }

            // Error message
            auditState.error?.let { error ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
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

            // Stats bar
            AuditStatsBar(
                totalEntries = auditState.totalEntries,
                displayedEntries = auditState.entries.size
            )

            // Entries list
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (auditState.isLoading && auditState.entries.isEmpty()) {
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
                } else if (auditState.entries.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    text = "No audit entries found",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = "Try adjusting your filters",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                )
                            }
                        }
                    }
                } else {
                    items(auditState.entries) { entry ->
                        AuditEntryCard(
                            entry = entry,
                            isExpanded = expandedEntryId == entry.id,
                            onToggleExpand = {
                                expandedEntryId = if (expandedEntryId == entry.id) null else entry.id
                            }
                        )
                    }

                    // Load more indicator
                    if (auditState.hasMore && !auditState.isLoading) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onLoadMore() }
                                    .padding(16.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "Load more entries...",
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }
                        }
                    }

                    if (auditState.isLoading && auditState.entries.isNotEmpty()) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AuditFiltersSection(
    filter: AuditFilter,
    onFilterChange: (AuditFilter) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(8.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Severity filter
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Severity:",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                FilterChip(
                    selected = filter.severity == null,
                    onClick = { onFilterChange(filter.copy(severity = null)) },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = filter.severity == "info",
                    onClick = { onFilterChange(filter.copy(severity = "info")) },
                    label = { Text("Info") }
                )
                FilterChip(
                    selected = filter.severity == "warning",
                    onClick = { onFilterChange(filter.copy(severity = "warning")) },
                    label = { Text("Warn") }
                )
                FilterChip(
                    selected = filter.severity == "error",
                    onClick = { onFilterChange(filter.copy(severity = "error")) },
                    label = { Text("Error") }
                )
            }

            // Outcome filter
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Outcome:",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                FilterChip(
                    selected = filter.outcome == null,
                    onClick = { onFilterChange(filter.copy(outcome = null)) },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = filter.outcome == "success",
                    onClick = { onFilterChange(filter.copy(outcome = "success")) },
                    label = { Text("Success") }
                )
                FilterChip(
                    selected = filter.outcome == "failure",
                    onClick = { onFilterChange(filter.copy(outcome = "failure")) },
                    label = { Text("Failure") }
                )
            }

            // Limit selector
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Limit:",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                listOf(50, 100, 200).forEach { limit ->
                    FilterChip(
                        selected = filter.limit == limit,
                        onClick = { onFilterChange(filter.copy(limit = limit)) },
                        label = { Text("$limit") }
                    )
                }
            }

            // Clear filters button
            TextButton(
                onClick = { onFilterChange(AuditFilter()) },
                modifier = Modifier.align(Alignment.End)
            ) {
                Text("Clear Filters")
            }
        }
    }
}

@Composable
private fun AuditStatsBar(
    totalEntries: Int,
    displayedEntries: Int,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = "Showing $displayedEntries entries",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        if (totalEntries > displayedEntries) {
            Text(
                text = "of $totalEntries total",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun AuditEntryCard(
    entry: AuditEntryData,
    isExpanded: Boolean,
    onToggleExpand: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = getEntryBackgroundColor(entry.outcome, entry.action)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { onToggleExpand() }
                .padding(12.dp)
        ) {
            // Header row: timestamp, action badge, outcome
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Timestamp
                Column {
                    Text(
                        text = entry.formattedDate,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = entry.formattedTime,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Expand/collapse icon
                Icon(
                    imageVector = if (isExpanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Action and actor row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Action badge
                Surface(
                    color = getActionBadgeColor(entry.action),
                    shape = MaterialTheme.shapes.small
                ) {
                    Text(
                        text = entry.actionDisplay,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White
                    )
                }

                // Actor
                Text(
                    text = entry.actor,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                // Outcome badge
                Surface(
                    color = getOutcomeColor(entry.outcome),
                    shape = MaterialTheme.shapes.small
                ) {
                    Text(
                        text = entry.outcome,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White
                    )
                }
            }

            // Expanded content
            if (isExpanded) {
                Spacer(modifier = Modifier.height(12.dp))
                Divider(color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.1f))
                Spacer(modifier = Modifier.height(12.dp))

                // Security info
                if (entry.hashChain != null || entry.signature != null) {
                    Text(
                        text = "Security",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))

                    entry.hashChain?.let { hash ->
                        SecurityInfoRow(label = "Hash Chain", value = hash.take(24) + "...")
                    }
                    entry.signature?.let { sig ->
                        SecurityInfoRow(label = "Signature", value = sig.take(24) + "...")
                    }
                    entry.storageSources?.let { sources ->
                        SecurityInfoRow(label = "Storage", value = sources.joinToString(", "))
                    }

                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Context JSON
                if (entry.contextJson.isNotEmpty()) {
                    Text(
                        text = "Context",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = MaterialTheme.colorScheme.surface,
                        shape = MaterialTheme.shapes.small
                    ) {
                        Text(
                            text = entry.contextJson,
                            modifier = Modifier.padding(8.dp),
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            fontSize = 10.sp
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SecurityInfoRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(
            text = "$label:",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(80.dp)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

// Helper functions for colors

@Composable
private fun getEntryBackgroundColor(outcome: String, action: String): Color {
    return when {
        outcome.lowercase() in listOf("error", "failure", "failed") ->
            MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
        action.uppercase().contains("EMERGENCY") || action.uppercase().contains("SHUTDOWN") ->
            MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.2f)
        action.uppercase().contains("CONFIG") || action.uppercase().contains("RESTORE") ->
            Color(0xFFFFF3CD).copy(alpha = 0.3f)
        outcome.lowercase() == "start" ->
            Color(0xFFDBEAFE).copy(alpha = 0.3f)
        else -> MaterialTheme.colorScheme.surface
    }
}

private fun getActionBadgeColor(action: String): Color {
    return when {
        action.uppercase().contains("LOGIN") || action.uppercase().contains("LOGOUT") -> Color(0xFF6366F1) // Indigo
        action.uppercase().contains("CONFIG") -> Color(0xFFF59E0B) // Amber
        action.uppercase().contains("EMERGENCY") || action.uppercase().contains("SHUTDOWN") -> Color(0xFFEF4444) // Red
        action.uppercase().contains("PAUSE") || action.uppercase().contains("RESUME") -> Color(0xFF3B82F6) // Blue
        action.uppercase().contains("MEMORIZE") || action.uppercase().contains("RECALL") -> Color(0xFF8B5CF6) // Purple
        action.uppercase().contains("SPEAK") -> Color(0xFF10B981) // Green
        action.uppercase().contains("FORGET") -> Color(0xFFF97316) // Orange
        else -> Color(0xFF6B7280) // Gray
    }
}

private fun getOutcomeColor(outcome: String): Color {
    return when (outcome.lowercase()) {
        "success" -> Color(0xFF10B981) // Green
        "start" -> Color(0xFF3B82F6) // Blue
        "error", "failure", "failed" -> Color(0xFFEF4444) // Red
        else -> Color(0xFF6B7280) // Gray
    }
}

// Data classes

/**
 * State for the Audit screen
 */
data class AuditScreenState(
    val entries: List<AuditEntryData> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
    val filter: AuditFilter = AuditFilter(),
    val totalEntries: Int = 0,
    val hasMore: Boolean = false
)

/**
 * Filter options for audit entries
 */
data class AuditFilter(
    val severity: String? = null,
    val outcome: String? = null,
    val actor: String? = null,
    val eventType: String? = null,
    val limit: Int = 100,
    val offset: Int = 0
)

/**
 * Audit entry data model for display
 */
data class AuditEntryData(
    val id: String,
    val action: String,
    val actor: String,
    val timestamp: String,
    val outcome: String,
    val hashChain: String? = null,
    val signature: String? = null,
    val storageSources: List<String>? = null,
    val contextJson: String = ""
) {
    val actionDisplay: String
        get() = action
            .replace("AuditEventType.HANDLER_ACTION_", "")
            .replace("AuditEventType.", "")

    val formattedDate: String
        get() = try {
            // Simple date extraction from ISO format
            timestamp.substringBefore("T")
        } catch (e: Exception) {
            timestamp
        }

    val formattedTime: String
        get() = try {
            // Simple time extraction from ISO format
            timestamp.substringAfter("T").substringBefore(".")
        } catch (e: Exception) {
            ""
        }
}
