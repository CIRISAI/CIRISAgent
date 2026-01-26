package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
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
    modifier: Modifier = Modifier
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
                title = { Text("System Logs") },
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
                        Text(if (showFilters) "Hide" else "Filter")
                    }
                    IconButton(onClick = onRefresh, enabled = !logsState.isLoading) {
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
                color = Color(0xFF1A1A1A),
                shape = MaterialTheme.shapes.small
            ) {
                if (logsState.isLoading && logsState.logs.isEmpty()) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = Color.White)
                    }
                } else if (logsState.logs.isEmpty()) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No logs matching current filters",
                            color = Color(0xFF666666),
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
                    text = "Auto-refreshing every ${logsState.refreshIntervalSeconds}s",
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
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Search logs...") },
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
                    text = "Level:",
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
                            label = { Text(level, fontSize = 11.sp) }
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
                        text = "Service:",
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
                            label = { Text("All", fontSize = 11.sp) }
                        )
                        services.take(5).forEach { service ->
                            FilterChip(
                                selected = filter.service == service,
                                onClick = { onFilterChange(filter.copy(service = service)) },
                                label = { Text(service.take(12), fontSize = 11.sp) }
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
                        text = "Limit:",
                        style = MaterialTheme.typography.bodySmall
                    )
                    listOf(50, 100, 200).forEach { limit ->
                        FilterChip(
                            selected = filter.limit == limit,
                            onClick = { onFilterChange(filter.copy(limit = limit)) },
                            label = { Text("$limit", fontSize = 11.sp) }
                        )
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Switch(
                        checked = autoScroll,
                        onCheckedChange = { onToggleAutoScroll() }
                    )
                    Text(
                        text = "Auto-scroll",
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
            text = "Logs ($totalLogs entries)",
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Medium
        )
        if (autoScroll) {
            Text(
                text = "Auto-scroll ON",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFF10B981)
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
            .background(Color(0xFF2A2A2A), MaterialTheme.shapes.small)
            .clickable(enabled = hasMetadata) { onToggleExpand() }
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
                color = Color(0xFF888888),
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
                color = Color(0xFF66D9EF),
                fontSize = 10.sp
            )

            // Message
            Text(
                text = log.message,
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = Color(0xFFE5E5E5),
                fontSize = 11.sp,
                modifier = Modifier.weight(1f),
                maxLines = if (isExpanded) Int.MAX_VALUE else 2,
                overflow = TextOverflow.Ellipsis
            )

            // Expand indicator
            if (hasMetadata) {
                Icon(
                    imageVector = if (isExpanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = Color(0xFF888888),
                    modifier = Modifier.size(16.dp)
                )
            }
        }

        // Expanded metadata
        if (isExpanded && hasMetadata) {
            Spacer(modifier = Modifier.height(8.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = Color(0xFF1A1A1A),
                shape = MaterialTheme.shapes.small
            ) {
                Text(
                    text = log.metadata,
                    modifier = Modifier.padding(8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = Color(0xFF999999),
                    fontSize = 10.sp
                )
            }
        }
    }
}

private fun getLogLevelColor(level: String): Color {
    return when (level.uppercase()) {
        "ERROR", "CRITICAL" -> Color(0xFFEF4444) // Red
        "WARN", "WARNING" -> Color(0xFFF59E0B) // Amber
        "INFO" -> Color(0xFF3B82F6) // Blue
        "DEBUG" -> Color(0xFF6B7280) // Gray
        else -> Color(0xFF6B7280) // Gray
    }
}

// Data classes

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
