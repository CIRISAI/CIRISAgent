package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import kotlinx.coroutines.launch

/**
 * System logs viewer screen.
 * Based on CIRISGUI-Standalone/apps/agui/app/logs/page.tsx
 *
 * Features:
 * - Real-time system logs viewing
 * - Filtering by log level and service
 * - Search functionality
 * - Auto-scroll to latest logs
 * - Expandable log entries for metadata
 * - Color-coded log levels
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogsScreen(
    logsState: LogsScreenState,
    onRefresh: () -> Unit,
    onFilterChange: (LogsFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onToggleAutoScroll: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
    // Existing backend mode (clientMode in CIRISApp). When the backend is a bare
    // node (no cognitive brain) the "Agent" log source is unavailable and the
    // dropdown item is disabled/grayed.
    isNodeMode: Boolean = true,
) {
    var showFilters by remember { mutableStateOf(false) }
    var expandedLogId by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()
    val coroutineScope = rememberCoroutineScope()

    // Auto-scroll to bottom when new logs arrive
    LaunchedEffect(logsState.logs.size, logsState.autoScroll) {
        if (logsState.autoScroll && logsState.logs.isNotEmpty()) {
            listState.animateScrollToItem(logsState.logs.size - 1)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_system_logs")) },
                navigationIcon = {
                    // Suppressed on compact viewports — the global 3-state
                    // overlay button in CIRISApp handles back navigation
                    // there to avoid the prior "back arrow + signet stacked"
                    // bug. Wider viewports (tablet/desktop) keep this arrow.
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onNavigateBack,
                            modifier = Modifier.testableClickable("btn_logs_back") { onNavigateBack() }
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
                    // Filter toggle
                    TextButton(
                        onClick = { showFilters = !showFilters },
                        modifier = Modifier.testableClickable("btn_logs_toggle_filters") { showFilters = !showFilters }
                    ) {
                        Text(if (showFilters) localizedString("mobile.logs_hide_filters") else localizedString("mobile.logs_show_filters"))
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !logsState.isLoading,
                        modifier = Modifier.testableClickable("btn_logs_refresh") { onRefresh() }
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
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Log source selector (Node / Agent) at the top of the screen.
            LogsSourceSelector(
                isNodeMode = isNodeMode,
                onSourceSelected = { _ ->
                    // Node uses the existing getSystemLogs → /v1/telemetry/logs
                    // path. Agent is only reachable when an agent is present;
                    // either way we re-trigger the existing fetch.
                    onRefresh()
                }
            )

            // Filters section
            if (showFilters) {
                LogsFiltersSection(
                    filter = logsState.filter,
                    searchQuery = logsState.searchQuery,
                    services = logsState.availableServices,
                    autoScroll = logsState.autoScroll,
                    onFilterChange = onFilterChange,
                    onSearchChange = onSearchChange,
                    onToggleAutoScroll = onToggleAutoScroll
                )
            }

            // Error message
            logsState.error?.let { error ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = error,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            // Stats bar
            LogsStatsBar(
                totalLogs = logsState.logs.size,
                autoScroll = logsState.autoScroll,
                refreshInterval = logsState.refreshIntervalSeconds
            )

            // Logs list with dark terminal-like background
            Surface(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 4.dp),
                color = MaterialTheme.colorScheme.surfaceContainerLowest,
                shape = MaterialTheme.shapes.small
            ) {
                if (logsState.isLoading && logsState.logs.isEmpty()) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = MaterialTheme.colorScheme.onSurface)
                    }
                } else if (logsState.logs.isEmpty()) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = localizedString("mobile.logs_no_matching"),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                } else {
                    LazyColumn(
                        state = listState,
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        items(logsState.logs) { log ->
                            LogEntryRow(
                                log = log,
                                isExpanded = expandedLogId == log.id,
                                onToggleExpand = {
                                    expandedLogId = if (expandedLogId == log.id) null else log.id
                                }
                            )
                        }
                    }
                }
            }

            // Auto-refresh indicator
            if (logsState.refreshIntervalSeconds > 0) {
                Text(
                    text = localizedString("mobile.logs_auto_refresh", mapOf("seconds" to logsState.refreshIntervalSeconds.toString())),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Source dropdown (Node / Agent) shown at the top of the Logs screen.
 *
 * Defaults to Node. The Agent item is disabled (and visually grayed by
 * Material3's `enabled = false`) whenever the backend is in node mode, since a
 * bare node has no cognitive brain to stream agent logs. Selecting Node queries
 * node logs via the existing getSystemLogs path.
 */
@Composable
private fun LogsSourceSelector(
    isNodeMode: Boolean,
    onSourceSelected: (LogsSource) -> Unit,
    modifier: Modifier = Modifier
) {
    var selectedSource by remember { mutableStateOf(LogsSource.NODE) }
    var expanded by remember { mutableStateOf(false) }

    // If the backend reports node mode, never leave Agent selected.
    LaunchedEffect(isNodeMode) {
        if (isNodeMode && selectedSource == LogsSource.AGENT) {
            selectedSource = LogsSource.NODE
        }
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = localizedString("mobile.logs_source_label"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Box {
            FilterChip(
                selected = true,
                onClick = { expanded = !expanded },
                label = {
                    Text(
                        text = when (selectedSource) {
                            LogsSource.NODE -> localizedString("mobile.source_node")
                            LogsSource.AGENT -> localizedString("mobile.source_agent")
                        }
                    )
                },
                trailingIcon = {
                    Icon(
                        imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                },
                modifier = Modifier.testableClickable("dropdown_logs_source") { expanded = !expanded }
            )
            DropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false }
            ) {
                DropdownMenuItem(
                    text = { Text(localizedString("mobile.source_node")) },
                    onClick = {
                        selectedSource = LogsSource.NODE
                        expanded = false
                        onSourceSelected(LogsSource.NODE)
                    },
                    modifier = Modifier.testableClickable("menu_logs_source_node") {
                        selectedSource = LogsSource.NODE
                        expanded = false
                        onSourceSelected(LogsSource.NODE)
                    }
                )
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(localizedString("mobile.source_agent"))
                            if (isNodeMode) {
                                Text(
                                    text = localizedString("mobile.source_agent_unavailable"),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    },
                    enabled = !isNodeMode,
                    onClick = {
                        selectedSource = LogsSource.AGENT
                        expanded = false
                        onSourceSelected(LogsSource.AGENT)
                    },
                    modifier = Modifier.testableClickable("menu_logs_source_agent") {
                        if (!isNodeMode) {
                            selectedSource = LogsSource.AGENT
                            expanded = false
                            onSourceSelected(LogsSource.AGENT)
                        }
                    }
                )
            }
        }
    }
}

@Composable
private fun LogsFiltersSection(
    filter: LogsFilter,
    searchQuery: String,
    services: List<String>,
    autoScroll: Boolean,
    onFilterChange: (LogsFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onToggleAutoScroll: () -> Unit,
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
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Search field
            OutlinedTextField(
                value = searchQuery,
                onValueChange = onSearchChange,
                modifier = Modifier.fillMaxWidth().testable("input_logs_search"),
                placeholder = { Text(localizedString("mobile.logs_search_placeholder")) },
                singleLine = true,
                textStyle = MaterialTheme.typography.bodySmall
            )

            // Log level filter
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("mobile.logs_level_label"),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.width(50.dp)
                )
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    listOf("ALL", "ERROR", "WARN", "INFO", "DEBUG").forEach { level ->
                        FilterChip(
                            selected = filter.level == level || (filter.level == null && level == "ALL"),
                            onClick = {
                                onFilterChange(filter.copy(level = if (level == "ALL") null else level))
                            },
                            label = { Text(level, fontSize = 11.sp) },
                            modifier = Modifier.testableClickable("chip_logs_level_${level.lowercase()}") {
                                onFilterChange(filter.copy(level = if (level == "ALL") null else level))
                            }
                        )
                    }
                }
            }

            // Service filter
            if (services.isNotEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = localizedString("mobile.logs_service_label"),
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.width(50.dp)
                    )
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        FilterChip(
                            selected = filter.service == null,
                            onClick = { onFilterChange(filter.copy(service = null)) },
                            label = { Text(localizedString("mobile.common_all"), fontSize = 11.sp) },
                            modifier = Modifier.testableClickable("chip_logs_service_all") {
                                onFilterChange(filter.copy(service = null))
                            }
                        )
                        services.take(5).forEach { service ->
                            FilterChip(
                                selected = filter.service == service,
                                onClick = { onFilterChange(filter.copy(service = service)) },
                                label = { Text(service.take(12), fontSize = 11.sp) },
                                modifier = Modifier.testableClickable("chip_logs_service_${service.lowercase().replace(" ", "_")}") {
                                    onFilterChange(filter.copy(service = service))
                                }
                            )
                        }
                    }
                }
            }

            // Limit and auto-scroll
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = localizedString("mobile.logs_limit_label"),
                        style = MaterialTheme.typography.bodySmall
                    )
                    listOf(50, 100, 200).forEach { limit ->
                        FilterChip(
                            selected = filter.limit == limit,
                            onClick = { onFilterChange(filter.copy(limit = limit)) },
                            label = { Text("$limit", fontSize = 11.sp) },
                            modifier = Modifier.testableClickable("chip_logs_limit_$limit") {
                                onFilterChange(filter.copy(limit = limit))
                            }
                        )
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Switch(
                        checked = autoScroll,
                        onCheckedChange = { onToggleAutoScroll() },
                        modifier = Modifier.testableClickable("switch_logs_auto_scroll") { onToggleAutoScroll() }
                    )
                    Text(
                        text = localizedString("mobile.logs_auto_scroll"),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }
}

@Composable
private fun LogsStatsBar(
    totalLogs: Int,
    autoScroll: Boolean,
    refreshInterval: Int,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
            .padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = localizedString("mobile.logs_entries", mapOf("count" to totalLogs.toString())),
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Medium
        )
        if (autoScroll) {
            Text(
                text = localizedString("mobile.logs_auto_scroll_on"),
                style = MaterialTheme.typography.labelSmall,
                color = SemanticColors.Default.success
            )
        }
    }
}

@Composable
private fun LogEntryRow(
    log: LogEntryData,
    isExpanded: Boolean,
    onToggleExpand: () -> Unit,
    modifier: Modifier = Modifier
) {
    val levelColor = getLogLevelColor(log.level)
    val hasMetadata = log.metadata.isNotEmpty()

    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceContainer, MaterialTheme.shapes.small)
            .then(
                if (hasMetadata) Modifier.testableClickable("item_log_entry_${log.id}") { onToggleExpand() }
                else Modifier
            )
            .padding(8.dp)
    ) {
        // Log level indicator bar
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(2.dp)
                .background(levelColor)
        )

        Spacer(modifier = Modifier.height(4.dp))

        // Main log row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.Top
        ) {
            // Timestamp
            Text(
                text = log.formattedTime,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 10.sp
            )

            // Level badge
            Text(
                text = "[${log.level}]",
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
                color = levelColor,
                fontSize = 10.sp
            )

            // Service
            Text(
                text = "[${log.service}]",
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = SemanticColors.Default.info,
                fontSize = 10.sp
            )

            // Message
            Text(
                text = log.message,
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 11.sp,
                modifier = Modifier.weight(1f),
                maxLines = if (isExpanded) Int.MAX_VALUE else 2,
                overflow = TextOverflow.Ellipsis
            )

            // Expand indicator
            if (hasMetadata) {
                Icon(
                    imageVector = if (isExpanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
                    contentDescription = if (isExpanded) localizedString("mobile.logs_collapse") else localizedString("mobile.logs_expand"),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp)
                )
            }
        }

        // Expanded metadata
        if (isExpanded && hasMetadata) {
            Spacer(modifier = Modifier.height(8.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surfaceContainerLowest,
                shape = MaterialTheme.shapes.small
            ) {
                Text(
                    text = log.metadata,
                    modifier = Modifier.padding(8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp
                )
            }
        }
    }
}

private fun getLogLevelColor(level: String): Color {
    val colors = SemanticColors.Default
    return when (level.uppercase()) {
        "ERROR", "CRITICAL" -> colors.error
        "WARN", "WARNING" -> colors.warning
        "INFO" -> colors.info
        "DEBUG" -> colors.inactive
        else -> colors.inactive
    }
}

// Data classes

/**
 * Log source for the top-of-screen dropdown. NODE = the local node's system
 * logs (getSystemLogs → /v1/telemetry/logs). AGENT = the CIRIS agent's logs,
 * only available when the backend is a full agent (not a bare node).
 */
enum class LogsSource { NODE, AGENT }

/**
 * State for the Logs screen
 */
data class LogsScreenState(
    val logs: List<LogEntryData> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
    val filter: LogsFilter = LogsFilter(),
    val searchQuery: String = "",
    val autoScroll: Boolean = true,
    val availableServices: List<String> = emptyList(),
    val refreshIntervalSeconds: Int = 5
)

/**
 * Filter options for logs
 */
data class LogsFilter(
    val level: String? = null,
    val service: String? = null,
    val limit: Int = 100
)

/**
 * Log entry data model for display
 */
data class LogEntryData(
    val id: String,
    val timestamp: String,
    val level: String,
    val service: String,
    val message: String,
    val metadata: String = "",
    val traceId: String? = null
) {
    val formattedTime: String
        get() = try {
            // Extract time from ISO format
            val time = timestamp.substringAfter("T").substringBefore("+").substringBefore("Z")
            // Include milliseconds if present
            if (time.contains(".")) {
                time.substringBefore(".") + "." + time.substringAfter(".").take(3)
            } else {
                time
            }
        } catch (e: Exception) {
            timestamp
        }
}
