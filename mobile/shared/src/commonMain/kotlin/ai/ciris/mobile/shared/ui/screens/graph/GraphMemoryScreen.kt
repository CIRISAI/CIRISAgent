package ai.ciris.mobile.shared.ui.screens.graph

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PlayArrow
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
import ai.ciris.api.models.GraphScope
import ai.ciris.api.models.NodeType
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/**
 * Graph visualization screen for memory exploration.
 *
 * Features:
 * - Force-directed graph layout
 * - Pan/zoom with gestures
 * - Node filtering by scope and type
 * - Node selection with details panel
 * - Multiple layout options
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GraphMemoryScreen(
    state: GraphDisplayState,
    filter: GraphFilter,
    stats: GraphStats,
    onRefresh: () -> Unit,
    onFilterChange: (GraphFilter) -> Unit,
    onLayoutChange: (GraphLayout) -> Unit,
    onNodeSelected: (String?) -> Unit,
    onViewportChange: (GraphViewport) -> Unit,
    onNodeDragStart: (String) -> Unit,
    onNodeDrag: (String, Float, Float) -> Unit,
    onNodeDragEnd: (String) -> Unit,
    onStartSimulation: () -> Unit,
    onStopSimulation: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showFilters by remember { mutableStateOf(false) }
    var showLayoutPicker by remember { mutableStateOf(false) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GraphColors.Background)
    ) {
        // Main graph canvas
        GraphCanvas(
            state = state,
            onViewportChange = onViewportChange,
            onNodeSelected = onNodeSelected,
            onNodeDragStart = onNodeDragStart,
            onNodeDrag = onNodeDrag,
            onNodeDragEnd = onNodeDragEnd,
            modifier = Modifier.fillMaxSize()
        )

        // Top app bar overlay
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            color = GraphColors.BackgroundLight.copy(alpha = 0.9f),
            shape = RoundedCornerShape(8.dp)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onNavigateBack) {
                    Icon(
                        imageVector = Icons.Filled.ArrowBack,
                        contentDescription = "Back",
                        tint = GraphColors.LabelColor
                    )
                }

                Text(
                    text = "Memory Graph",
                    style = MaterialTheme.typography.titleMedium,
                    color = GraphColors.LabelColor,
                    fontWeight = FontWeight.Bold
                )

                Row {
                    // Filter button
                    TextButton(onClick = { showFilters = !showFilters }) {
                        Text(
                            text = if (showFilters) "Hide" else "Filter",
                            color = GraphColors.LabelColor
                        )
                    }

                    // Layout picker
                    TextButton(onClick = { showLayoutPicker = true }) {
                        Text(
                            text = state.layout.displayName,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }

                    // Play/pause simulation
                    IconButton(
                        onClick = {
                            if (state.isSimulationRunning) onStopSimulation()
                            else onStartSimulation()
                        }
                    ) {
                        Icon(
                            imageVector = if (state.isSimulationRunning) Icons.Filled.Close
                            else Icons.Filled.PlayArrow,
                            contentDescription = if (state.isSimulationRunning) "Stop" else "Play",
                            tint = GraphColors.LabelColor
                        )
                    }

                    // Refresh
                    IconButton(onClick = onRefresh, enabled = !state.isLoading) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh",
                            tint = GraphColors.LabelColor
                        )
                    }
                }
            }
        }

        // Filters panel
        if (showFilters) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 64.dp)
                    .padding(horizontal = 8.dp),
                color = GraphColors.BackgroundLight.copy(alpha = 0.95f),
                shape = RoundedCornerShape(8.dp)
            ) {
                GraphFiltersPanel(
                    filter = filter,
                    onFilterChange = onFilterChange,
                    onClose = { showFilters = false }
                )
            }
        }

        // Stats overlay (bottom-left)
        Surface(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(8.dp),
            color = GraphColors.BackgroundLight.copy(alpha = 0.9f),
            shape = RoundedCornerShape(8.dp)
        ) {
            Column(
                modifier = Modifier.padding(12.dp)
            ) {
                Text(
                    text = "Nodes: ${stats.totalNodes}",
                    style = MaterialTheme.typography.labelMedium,
                    color = GraphColors.LabelColor
                )
                Text(
                    text = "Edges: ${stats.totalEdges}",
                    style = MaterialTheme.typography.labelMedium,
                    color = GraphColors.LabelColorMuted
                )
                if (state.isSimulationRunning) {
                    Text(
                        text = "Simulating...",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }
        }

        // Zoom indicator (bottom-right)
        Surface(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(8.dp),
            color = GraphColors.BackgroundLight.copy(alpha = 0.9f),
            shape = RoundedCornerShape(8.dp)
        ) {
            Text(
                text = "%.0f%%".format(state.viewport.scale * 100),
                modifier = Modifier.padding(8.dp),
                style = MaterialTheme.typography.labelMedium,
                color = GraphColors.LabelColorMuted
            )
        }

        // Selected node details (bottom sheet style)
        state.selectedNode?.let { node ->
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(8.dp),
                color = GraphColors.BackgroundLight.copy(alpha = 0.95f),
                shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp)
            ) {
                NodeDetailsPanel(
                    node = node,
                    onClose = { onNodeSelected(null) }
                )
            }
        }

        // Loading indicator
        if (state.isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.align(Alignment.Center),
                color = MaterialTheme.colorScheme.primary
            )
        }

        // Empty state message when no nodes
        if (!state.isLoading && state.nodes.isEmpty()) {
            Surface(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(32.dp),
                color = GraphColors.BackgroundLight.copy(alpha = 0.95f),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "No Graph Data Yet",
                        style = MaterialTheme.typography.titleMedium,
                        color = GraphColors.LabelColor,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "The memory graph begins forming 6-12 hours after your first interaction as CIRIS processes and connects concepts.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = GraphColors.LabelColorMuted,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                    Text(
                        text = "Try adjusting the time filter to see older memories.",
                        style = MaterialTheme.typography.bodySmall,
                        color = GraphColors.LabelColorMuted,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                }
            }
        }

        // Error message
        state.error?.let { error ->
            Surface(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 80.dp)
                    .padding(horizontal = 16.dp),
                color = MaterialTheme.colorScheme.errorContainer,
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = error,
                    modifier = Modifier.padding(12.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }

        // Layout picker dialog
        if (showLayoutPicker) {
            AlertDialog(
                onDismissRequest = { showLayoutPicker = false },
                title = { Text("Select Layout") },
                text = {
                    Column {
                        GraphLayout.entries.forEach { layout ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        onLayoutChange(layout)
                                        showLayoutPicker = false
                                    }
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                RadioButton(
                                    selected = state.layout == layout,
                                    onClick = {
                                        onLayoutChange(layout)
                                        showLayoutPicker = false
                                    }
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(layout.displayName)
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { showLayoutPicker = false }) {
                        Text("Cancel")
                    }
                }
            )
        }
    }
}

@Composable
private fun GraphFiltersPanel(
    filter: GraphFilter,
    onFilterChange: (GraphFilter) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Filters",
                style = MaterialTheme.typography.titleSmall,
                color = GraphColors.LabelColor,
                fontWeight = FontWeight.Bold
            )
            IconButton(onClick = onClose) {
                Icon(
                    imageVector = Icons.Filled.Close,
                    contentDescription = "Close",
                    tint = GraphColors.LabelColorMuted
                )
            }
        }

        // Scope filter (one scope at a time - cross-scope edges not supported)
        Text(
            text = "Scope",
            style = MaterialTheme.typography.labelMedium,
            color = GraphColors.LabelColorMuted
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            GraphScope.entries.forEach { scope ->
                FilterChip(
                    selected = filter.scope == scope,
                    onClick = { onFilterChange(filter.copy(scope = scope)) },
                    label = { Text(scope.value.uppercase()) }
                )
            }
        }

        // Time range
        Text(
            text = "Time Range",
            style = MaterialTheme.typography.labelMedium,
            color = GraphColors.LabelColorMuted
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            listOf(6 to "6h", 24 to "24h", 48 to "2 days", 168 to "1 week").forEach { (hours, label) ->
                FilterChip(
                    selected = filter.hours == hours,
                    onClick = { onFilterChange(filter.copy(hours = hours)) },
                    label = { Text(label) }
                )
            }
        }
    }
}

@Composable
private fun NodeDetailsPanel(
    node: GraphNodeDisplay,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Type badge
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(4.dp))
                        .background(node.color)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = node.type.value.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White
                    )
                }
                Text(
                    text = node.scope.value.uppercase(),
                    style = MaterialTheme.typography.labelSmall,
                    color = GraphColors.LabelColorMuted
                )
            }
            IconButton(onClick = onClose) {
                Icon(
                    imageVector = Icons.Filled.Close,
                    contentDescription = "Close",
                    tint = GraphColors.LabelColorMuted
                )
            }
        }

        // Node ID
        Text(
            text = "ID: ${node.id}",
            style = MaterialTheme.typography.labelSmall,
            color = GraphColors.LabelColorMuted
        )

        // Label/content
        Text(
            text = node.label,
            style = MaterialTheme.typography.bodyMedium,
            color = GraphColors.LabelColor,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis
        )

        // Original node details if available
        node.originalNode?.let { original ->
            original.attributes.description?.let { desc ->
                if (desc.isNotEmpty() && desc != node.label) {
                    Text(
                        text = desc,
                        style = MaterialTheme.typography.bodySmall,
                        color = GraphColors.LabelColorMuted,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
            original.updatedAt?.let { time ->
                Text(
                    text = "Updated: ${formatTimestamp(time)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = GraphColors.LabelColorMuted
                )
            }
        }
    }
}

/**
 * Format ISO timestamp for display.
 */
private fun formatTimestamp(timestamp: String): String {
    return try {
        val date = timestamp.substringBefore("T")
        val time = timestamp.substringAfter("T").substringBefore(".").substringBefore("Z")
        "$date $time"
    } catch (e: Exception) {
        timestamp
    }
}
