package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
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
 * Memory/Graph database viewer screen.
 * Based on CIRISGUI-Standalone/apps/agui/app/memory/page.tsx
 *
 * Features:
 * - Memory graph exploration
 * - Search functionality for nodes
 * - Filtering by scope and node type
 * - Node details view with attributes
 * - Memory statistics overview
 * - Timeline-based browsing
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemoryScreen(
    memoryState: MemoryScreenState,
    onRefresh: () -> Unit,
    onSearch: (String) -> Unit,
    onFilterChange: (MemoryFilter) -> Unit,
    onNodeSelect: (String) -> Unit,
    onClearSelection: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var searchQuery by remember { mutableStateOf("") }
    var showFilters by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Memory Graph Explorer") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    TextButton(onClick = { showFilters = !showFilters }) {
                        Text(if (showFilters) "Hide" else "Filter")
                    }
                    IconButton(onClick = onRefresh, enabled = !memoryState.isLoading) {
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
            // Search bar
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                placeholder = { Text("Search thoughts, tasks, observations...") },
                leadingIcon = {
                    Icon(Icons.Filled.Search, contentDescription = "Search")
                },
                trailingIcon = {
                    if (searchQuery.isNotEmpty()) {
                        IconButton(onClick = {
                            searchQuery = ""
                            onSearch("")
                        }) {
                            Icon(Icons.Filled.Close, contentDescription = "Clear")
                        }
                    }
                },
                singleLine = true,
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(
                    onDone = { onSearch(searchQuery) }
                )
            )

            // Filters section
            if (showFilters) {
                MemoryFiltersSection(
                    filter = memoryState.filter,
                    stats = memoryState.stats,
                    onFilterChange = onFilterChange
                )
            }

            // Error message
            memoryState.error?.let { error ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 4.dp),
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

            // Statistics summary
            if (memoryState.stats != null) {
                MemoryStatsCard(stats = memoryState.stats)
            }

            // Content area - either selected node details or search results
            if (memoryState.selectedNode != null) {
                // Node details view
                NodeDetailsCard(
                    node = memoryState.selectedNode,
                    onClose = onClearSelection
                )
            } else if (memoryState.searchResults.isNotEmpty()) {
                // Search results
                Text(
                    text = "Search Results (${memoryState.searchResults.size})",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                LazyVerticalGrid(
                    columns = GridCells.Fixed(1),
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(8.dp)
                ) {
                    items(memoryState.searchResults) { node ->
                        MemoryNodeCard(
                            node = node,
                            onClick = { onNodeSelect(node.id) }
                        )
                    }
                }
            } else if (memoryState.timelineNodes.isNotEmpty()) {
                // Timeline view
                Text(
                    text = "Recent Memories",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(8.dp)
                ) {
                    items(memoryState.timelineNodes) { node ->
                        MemoryNodeCard(
                            node = node,
                            onClick = { onNodeSelect(node.id) }
                        )
                    }
                }
            } else if (memoryState.isLoading) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            } else {
                // Empty state
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "No memories found",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Try searching or adjusting filters",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MemoryFiltersSection(
    filter: MemoryFilter,
    stats: MemoryStatsData?,
    onFilterChange: (MemoryFilter) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Scope filter
            Text(
                text = "Scope",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium
            )
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                MEMORY_SCOPES.forEach { scope ->
                    FilterChip(
                        selected = filter.scope == scope.value,
                        onClick = { onFilterChange(filter.copy(scope = scope.value)) },
                        label = { Text(scope.label) }
                    )
                }
            }

            // Node type filter
            Text(
                text = "Node Type",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium
            )
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = filter.nodeType == null,
                    onClick = { onFilterChange(filter.copy(nodeType = null)) },
                    label = { Text("All") }
                )
                NODE_TYPES.forEach { type ->
                    FilterChip(
                        selected = filter.nodeType == type,
                        onClick = { onFilterChange(filter.copy(nodeType = type)) },
                        label = { Text(type.replace("_", " ").uppercase()) }
                    )
                }
            }

            // Time range filter
            Text(
                text = "Time Range",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium
            )
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                TIME_RANGES.forEach { (label, hours) ->
                    FilterChip(
                        selected = filter.hours == hours,
                        onClick = { onFilterChange(filter.copy(hours = hours)) },
                        label = { Text(label) }
                    )
                }
            }
        }
    }
}

@Composable
private fun MemoryStatsCard(
    stats: MemoryStatsData,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Total nodes
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Total Nodes",
                    style = MaterialTheme.typography.labelMedium
                )
                Text(
                    text = stats.totalNodes.toString(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
            }

            // Nodes by type (horizontal chips)
            if (stats.nodesByType.isNotEmpty()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    stats.nodesByType.forEach { (type, count) ->
                        Surface(
                            color = getNodeTypeColor(type).copy(alpha = 0.2f),
                            shape = MaterialTheme.shapes.small
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(8.dp)
                                        .clip(CircleShape)
                                        .background(getNodeTypeColor(type))
                                )
                                Text(
                                    text = "$type: $count",
                                    style = MaterialTheme.typography.labelSmall
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MemoryNodeCard(
    node: MemoryNodeData,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Header: type badge and scope
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Type badge
                Surface(
                    color = getNodeTypeColor(node.type),
                    shape = MaterialTheme.shapes.small
                ) {
                    Text(
                        text = node.type.replace("_", " ").uppercase(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White
                    )
                }

                // Scope
                Text(
                    text = node.scope,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Content preview
            Text(
                text = node.contentPreview,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis
            )

            // Timestamp
            Text(
                text = node.formattedDate,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Click hint
            Text(
                text = "Tap to view details",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}

@Composable
private fun NodeDetailsCard(
    node: MemoryNodeData,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(16.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Node Details",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                IconButton(onClick = onClose) {
                    Icon(Icons.Filled.Close, contentDescription = "Close")
                }
            }

            Divider()

            // Node info
            NodeInfoRow(label = "ID", value = node.id)
            NodeInfoRow(label = "Type", value = node.type)
            NodeInfoRow(label = "Scope", value = node.scope)
            NodeInfoRow(label = "Created", value = node.formattedDate)
            node.updatedAt?.let { updated ->
                NodeInfoRow(label = "Updated", value = updated)
            }

            // Attributes
            if (node.attributesJson.isNotEmpty()) {
                Divider()
                Text(
                    text = "Attributes",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.small
                ) {
                    Text(
                        text = node.attributesJson,
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

@Composable
private fun NodeInfoRow(
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
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(70.dp)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
    }
}

// Helper function
private fun getNodeTypeColor(type: String): Color {
    return when (type.lowercase()) {
        "concept" -> Color(0xFFF97316) // Orange
        "observation" -> Color(0xFFEC4899) // Pink
        "identity" -> Color(0xFF6366F1) // Indigo
        "config" -> Color(0xFFF59E0B) // Amber
        "tsdb_data" -> Color(0xFF06B6D4) // Cyan
        "audit_entry" -> Color(0xFF6B7280) // Gray
        else -> Color(0xFF6B7280) // Gray
    }
}

// Constants
private val MEMORY_SCOPES = listOf(
    ScopeOption("local", "LOCAL"),
    ScopeOption("identity", "IDENTITY"),
    ScopeOption("environment", "ENVIRONMENT"),
    ScopeOption("community", "COMMUNITY")
)

private val NODE_TYPES = listOf(
    "concept",
    "observation",
    "identity",
    "config",
    "tsdb_data"
)

private val TIME_RANGES = listOf(
    "6h" to 6,
    "24h" to 24,
    "2 days" to 48,
    "1 week" to 168
)

private data class ScopeOption(val value: String, val label: String)

// Data classes

/**
 * State for the Memory screen
 */
data class MemoryScreenState(
    val searchResults: List<MemoryNodeData> = emptyList(),
    val timelineNodes: List<MemoryNodeData> = emptyList(),
    val selectedNode: MemoryNodeData? = null,
    val stats: MemoryStatsData? = null,
    val isLoading: Boolean = false,
    val isSearching: Boolean = false,
    val error: String? = null,
    val filter: MemoryFilter = MemoryFilter()
)

/**
 * Filter options for memory queries
 */
data class MemoryFilter(
    val scope: String = "local",
    val nodeType: String? = null,
    val hours: Int = 24
)

/**
 * Memory statistics data
 */
data class MemoryStatsData(
    val totalNodes: Int = 0,
    val nodesByType: Map<String, Int> = emptyMap(),
    val nodesByScope: Map<String, Int> = emptyMap(),
    val recentNodes24h: Int = 0
)

/**
 * Memory node data model for display
 */
data class MemoryNodeData(
    val id: String,
    val type: String,
    val scope: String,
    val contentPreview: String,
    val attributesJson: String = "",
    val createdAt: String? = null,
    val updatedAt: String? = null
) {
    val formattedDate: String
        get() = try {
            createdAt?.let {
                val date = it.substringBefore("T")
                val time = it.substringAfter("T").substringBefore(".").substringBefore("Z")
                "$date $time"
            } ?: "Unknown"
        } catch (e: Exception) {
            createdAt ?: "Unknown"
        }
}
