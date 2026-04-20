package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
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
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import ai.ciris.mobile.shared.ui.theme.SemanticColors
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
                title = { Text(localizedString("mobile.screen_system_audit")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_audit_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    // Filter toggle
                    TextButton(
                        onClick = { showFilters = !showFilters },
                        modifier = Modifier.testableClickable("btn_audit_toggle_filters") { showFilters = !showFilters }
                    ) {
                        Text(if (showFilters) localizedString("settings_hide") + " " + localizedString("graph_filters") else localizedString("graph_filters"))
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !auditState.isLoading,
                        modifier = Modifier.testableClickable("btn_audit_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
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
                                    text = localizedString("audit_no_entries"),
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = localizedString("audit_try_filters"),
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
                                    .testableClickable("btn_audit_load_more") { onLoadMore() }
                                    .padding(16.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = localizedString("audit_load_more"),
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
                    text = localizedString("filter_severity"),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                FilterChip(
                    selected = filter.severity == null,
                    onClick = { onFilterChange(filter.copy(severity = null)) },
                    label = { Text(localizedString("filter_all")) },
                    modifier = Modifier.testableClickable("btn_filter_severity_all") { onFilterChange(filter.copy(severity = null)) }
                )
                FilterChip(
                    selected = filter.severity == "info",
                    onClick = { onFilterChange(filter.copy(severity = "info")) },
                    label = { Text(localizedString("filter_info")) },
                    modifier = Modifier.testableClickable("btn_filter_severity_info") { onFilterChange(filter.copy(severity = "info")) }
                )
                FilterChip(
                    selected = filter.severity == "warning",
                    onClick = { onFilterChange(filter.copy(severity = "warning")) },
                    label = { Text(localizedString("filter_warn")) },
                    modifier = Modifier.testableClickable("btn_filter_severity_warning") { onFilterChange(filter.copy(severity = "warning")) }
                )
                FilterChip(
                    selected = filter.severity == "error",
                    onClick = { onFilterChange(filter.copy(severity = "error")) },
                    label = { Text(localizedString("filter_error")) },
                    modifier = Modifier.testableClickable("btn_filter_severity_error") { onFilterChange(filter.copy(severity = "error")) }
                )
            }

            // Outcome filter
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("filter_outcome"),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                FilterChip(
                    selected = filter.outcome == null,
                    onClick = { onFilterChange(filter.copy(outcome = null)) },
                    label = { Text(localizedString("filter_all")) },
                    modifier = Modifier.testableClickable("btn_filter_outcome_all") { onFilterChange(filter.copy(outcome = null)) }
                )
                FilterChip(
                    selected = filter.outcome == "success",
                    onClick = { onFilterChange(filter.copy(outcome = "success")) },
                    label = { Text(localizedString("filter_success")) },
                    modifier = Modifier.testableClickable("btn_filter_outcome_success") { onFilterChange(filter.copy(outcome = "success")) }
                )
                FilterChip(
                    selected = filter.outcome == "failure",
                    onClick = { onFilterChange(filter.copy(outcome = "failure")) },
                    label = { Text(localizedString("filter_failure")) },
                    modifier = Modifier.testableClickable("btn_filter_outcome_failure") { onFilterChange(filter.copy(outcome = "failure")) }
                )
            }

            // Limit selector
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("filter_limit"),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.width(70.dp)
                )
                listOf(50, 100, 200).forEach { limit ->
                    FilterChip(
                        selected = filter.limit == limit,
                        onClick = { onFilterChange(filter.copy(limit = limit)) },
                        label = { Text("$limit") },
                        modifier = Modifier.testableClickable("btn_filter_limit_$limit") { onFilterChange(filter.copy(limit = limit)) }
                    )
                }
            }

            // Clear filters button
            TextButton(
                onClick = { onFilterChange(AuditFilter()) },
                modifier = Modifier.align(Alignment.End).testableClickable("btn_filter_clear") { onFilterChange(AuditFilter()) }
            ) {
                Text(localizedString("filter_clear"))
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
            text = localizedString("audit_showing").replace("{count}", displayedEntries.toString()),
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
                .testableClickable("item_audit_entry_${entry.id.take(8)}") { onToggleExpand() }
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
                    contentDescription = if (isExpanded) localizedString("interact_close") else localizedString("setup_details_expand"),
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

            // Summary line (ponder questions, tool results, etc.)
            entry.summaryLine?.let { summary ->
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = summary,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            // Expanded content
            if (isExpanded) {
                Spacer(modifier = Modifier.height(12.dp))
                Divider(color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.1f))
                Spacer(modifier = Modifier.height(12.dp))

                // Ponder questions (full list)
                if (!entry.ponderQuestions.isNullOrEmpty()) {
                    Text(
                        text = localizedString("audit_questions"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    entry.ponderQuestions.forEachIndexed { index, question ->
                        Text(
                            text = "${index + 1}. $question",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(start = 8.dp, bottom = 4.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Tool details
                if (!entry.toolName.isNullOrEmpty()) {
                    Text(
                        text = localizedString("audit_tool_execution"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    SecurityInfoRow(label = localizedString("interact_action_tool"), value = entry.toolName)
                    entry.toolParameters?.let { params ->
                        Text(
                            text = localizedString("audit_parameters"),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                        Surface(
                            modifier = Modifier.fillMaxWidth().padding(start = 8.dp),
                            color = MaterialTheme.colorScheme.surface,
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(
                                text = params,
                                modifier = Modifier.padding(8.dp),
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 10.sp
                            )
                        }
                    }
                    entry.toolResult?.let { result ->
                        Text(
                            text = localizedString("audit_result"),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 8.dp)
                        )
                        Text(
                            text = result,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(start = 8.dp, top = 4.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Security info
                if (entry.hashChain != null || entry.signature != null) {
                    Text(
                        text = localizedString("audit_security"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))

                    entry.hashChain?.let { hash ->
                        SecurityInfoRow(label = localizedString("audit_hash_chain"), value = hash.take(24) + "...")
                    }
                    entry.signature?.let { sig ->
                        SecurityInfoRow(label = localizedString("audit_signature"), value = sig.take(24) + "...")
                    }
                    entry.storageSources?.let { sources ->
                        SecurityInfoRow(label = "Storage", value = sources.joinToString(", "))
                    }

                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Context JSON
                if (entry.contextJson.isNotEmpty()) {
                    Text(
                        text = localizedString("audit_context"),
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
            SemanticColors.Default.surfaceWarning.copy(alpha = 0.3f)
        outcome.lowercase() == "start" ->
            SemanticColors.Default.surfaceInfo.copy(alpha = 0.3f)
        else -> MaterialTheme.colorScheme.surface
    }
}

private fun getActionBadgeColor(action: String): Color {
    return when {
        action.uppercase().contains("LOGIN") || action.uppercase().contains("LOGOUT") -> SemanticColors.Default.accentTertiary // Indigo/Purple
        action.uppercase().contains("CONFIG") -> SemanticColors.Default.warning // Amber
        action.uppercase().contains("EMERGENCY") || action.uppercase().contains("SHUTDOWN") -> SemanticColors.Default.error // Red
        action.uppercase().contains("PAUSE") || action.uppercase().contains("RESUME") -> SemanticColors.Default.info // Blue
        action.uppercase().contains("MEMORIZE") || action.uppercase().contains("RECALL") -> SemanticColors.Default.accentSecondary // Purple
        action.uppercase().contains("SPEAK") -> SemanticColors.Default.success // Green
        action.uppercase().contains("FORGET") -> Color(0xFFF97316) // Orange
        action.uppercase().contains("PONDER") -> Color(0xFF8B5CF6) // Violet - thoughtful/reflective
        action.uppercase().contains("TOOL") -> Color(0xFF0EA5E9) // Sky blue - action/execution
        action.uppercase().contains("DEFER") -> Color(0xFFF59E0B) // Amber - waiting/deferred
        action.uppercase().contains("REJECT") -> Color(0xFFEF4444) // Red - rejection
        action.uppercase().contains("TASK_COMPLETE") -> SemanticColors.Default.success // Green - completion
        else -> SemanticColors.Default.inactive // Gray
    }
}

private fun getOutcomeColor(outcome: String): Color {
    return when (outcome.lowercase()) {
        "success" -> SemanticColors.Default.success // Green
        "start" -> SemanticColors.Default.info // Blue
        "error", "failure", "failed" -> SemanticColors.Default.error // Red
        else -> SemanticColors.Default.inactive // Gray
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
    val contextJson: String = "",
    // Extracted fields for timeline card display
    val ponderQuestions: List<String>? = null,
    val toolName: String? = null,
    val toolParameters: String? = null,
    val toolResult: String? = null,
    val speakContent: String? = null,
    val deferReason: String? = null,
    val completionReason: String? = null,
    val description: String? = null
) {
    val actionDisplay: String
        get() = action
            .replace("AuditEventType.HANDLER_ACTION_", "")
            .replace("AuditEventType.", "")

    /**
     * Get a summary line for the timeline card (non-expanded view)
     */
    val summaryLine: String?
        get() = when {
            !ponderQuestions.isNullOrEmpty() -> "Questions: ${ponderQuestions.joinToString("; ").take(100)}${if (ponderQuestions.joinToString("; ").length > 100) "..." else ""}"
            !toolName.isNullOrEmpty() -> {
                val result = toolResult?.take(80)?.let { " → $it" } ?: ""
                "Tool: $toolName$result"
            }
            !speakContent.isNullOrEmpty() -> speakContent.take(100) + if (speakContent.length > 100) "..." else ""
            !deferReason.isNullOrEmpty() -> "Deferred: ${deferReason.take(80)}"
            !completionReason.isNullOrEmpty() -> completionReason.take(80)
            !description.isNullOrEmpty() -> description.take(100)
            else -> null
        }

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
