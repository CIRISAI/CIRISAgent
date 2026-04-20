package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.ToolInfoData
import ai.ciris.mobile.shared.api.ToolsMetadataData
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.ToolsScreenState
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Tools screen showing all available tools from all providers.
 *
 * Features:
 * - List of all tools with provider info
 * - Expandable cards with parameters and when_to_use
 * - Filter by category and provider
 * - Search functionality
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ToolsScreen(
    state: ToolsScreenState,
    filteredTools: List<ToolInfoData>,
    categories: List<String>,
    providers: List<String>,
    onRefresh: () -> Unit,
    onSearchQueryChange: (String) -> Unit,
    onCategoryFilter: (String?) -> Unit,
    onProviderFilter: (String?) -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var expandedToolId by remember { mutableStateOf<String?>(null) }
    var showCategoryDropdown by remember { mutableStateOf(false) }
    var showProviderDropdown by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.nav_tools")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_tools_back") { onNavigateBack() }
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
                        enabled = !state.isLoading && !state.isRefreshing,
                        modifier = Modifier.testableClickable("btn_tools_refresh") { onRefresh() }
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
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Loading state
            if (state.isLoading || state.isRefreshing) {
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
            }

            // Error message
            state.error?.let { error ->
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
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
            }

            // Stats Card
            state.metadata?.let { metadata ->
                item {
                    ToolsStatsCard(metadata = metadata)
                }
            }

            // Search and Filters
            item {
                Column(
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Search
                    OutlinedTextField(
                        value = state.searchQuery,
                        onValueChange = onSearchQueryChange,
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text(localizedString("mobile.tools_search_placeholder")) },
                        leadingIcon = {
                            Icon(Icons.Filled.Search, contentDescription = null)
                        },
                        singleLine = true
                    )

                    // Filters Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        // Category Filter
                        Box(modifier = Modifier.weight(1f)) {
                            FilterChip(
                                selected = state.selectedCategory != null,
                                onClick = { showCategoryDropdown = !showCategoryDropdown },
                                label = {
                                    Text(state.selectedCategory ?: localizedString("mobile.common_category"))
                                },
                                modifier = Modifier.fillMaxWidth()
                            )
                            DropdownMenu(
                                expanded = showCategoryDropdown,
                                onDismissRequest = { showCategoryDropdown = false }
                            ) {
                                DropdownMenuItem(
                                    text = { Text(localizedString("mobile.tools_all_categories")) },
                                    onClick = {
                                        onCategoryFilter(null)
                                        showCategoryDropdown = false
                                    }
                                )
                                categories.forEach { category ->
                                    DropdownMenuItem(
                                        text = { Text(category) },
                                        onClick = {
                                            onCategoryFilter(category)
                                            showCategoryDropdown = false
                                        }
                                    )
                                }
                            }
                        }

                        // Provider Filter
                        Box(modifier = Modifier.weight(1f)) {
                            FilterChip(
                                selected = state.selectedProvider != null,
                                onClick = { showProviderDropdown = !showProviderDropdown },
                                label = {
                                    Text(
                                        text = state.selectedProvider?.take(15) ?: localizedString("mobile.common_provider"),
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                },
                                modifier = Modifier.fillMaxWidth()
                            )
                            DropdownMenu(
                                expanded = showProviderDropdown,
                                onDismissRequest = { showProviderDropdown = false }
                            ) {
                                DropdownMenuItem(
                                    text = { Text(localizedString("mobile.tools_all_providers")) },
                                    onClick = {
                                        onProviderFilter(null)
                                        showProviderDropdown = false
                                    }
                                )
                                providers.forEach { provider ->
                                    DropdownMenuItem(
                                        text = { Text(provider) },
                                        onClick = {
                                            onProviderFilter(provider)
                                            showProviderDropdown = false
                                        }
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // Tools Count
            item {
                Text(
                    text = localizedString("mobile.tools_count", mapOf("count" to filteredTools.size.toString())),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Tools List
            items(filteredTools, key = { it.name }) { tool ->
                ToolCard(
                    tool = tool,
                    isExpanded = expandedToolId == tool.name,
                    onToggleExpand = {
                        expandedToolId = if (expandedToolId == tool.name) null else tool.name
                    }
                )
            }

            // Empty state
            if (filteredTools.isEmpty() && !state.isLoading && state.error == null) {
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
                                text = if (state.searchQuery.isNotBlank() || state.selectedCategory != null || state.selectedProvider != null) {
                                    localizedString("mobile.tools_no_match")
                                } else {
                                    localizedString("mobile.tools_no_tools")
                                },
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ToolsStatsCard(
    metadata: ToolsMetadataData,
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
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            StatColumn(
                label = localizedString("mobile.tools_total"),
                value = metadata.totalTools.toString(),
                color = SemanticColors.Default.success
            )
            StatColumn(
                label = localizedString("mobile.tools_providers"),
                value = metadata.providerCount.toString(),
                color = SemanticColors.Default.info
            )
        }
    }
}

@Composable
private fun StatColumn(
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
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onPrimaryContainer
        )
    }
}

@Composable
private fun ToolCard(
    tool: ToolInfoData,
    isExpanded: Boolean,
    onToggleExpand: () -> Unit,
    modifier: Modifier = Modifier
) {
    val categoryColor = when (tool.category.lowercase()) {
        "secrets" -> Color(0xFFE91E63)      // Pink - special/sensitive
        "memory" -> Color(0xFF9C27B0)        // Purple - cognitive
        "communication" -> SemanticColors.Default.info  // Blue
        "system" -> Color(0xFF607D8B)        // Blue-gray - system
        "general" -> SemanticColors.Default.success    // Green
        else -> Color(0xFF795548)            // Brown - other
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testableClickable("tool_${tool.name}") { onToggleExpand() },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            // Header Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Build,
                        contentDescription = null,
                        tint = categoryColor,
                        modifier = Modifier.size(20.dp)
                    )
                    Column {
                        Text(
                            text = tool.name,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = tool.provider,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Category Badge
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = categoryColor.copy(alpha = 0.15f)
                    ) {
                        Text(
                            text = tool.category,
                            style = MaterialTheme.typography.labelSmall,
                            color = categoryColor,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }

                    // Expand Icon
                    Icon(
                        imageVector = if (isExpanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                        contentDescription = if (isExpanded) localizedString("mobile.common_collapse") else localizedString("mobile.common_expand"),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Description
            if (tool.description.isNotBlank()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = tool.description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = if (isExpanded) Int.MAX_VALUE else 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            // Expanded Content
            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    HorizontalDivider()

                    // Cost
                    if (tool.cost > 0) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = localizedString("mobile.tools_cost"),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "${tool.cost} credits",
                                style = MaterialTheme.typography.bodyMedium,
                                color = SemanticColors.Default.warning
                            )
                        }
                    }

                    // When to Use
                    tool.whenToUse?.let { whenToUse ->
                        Column {
                            Text(
                                text = localizedString("mobile.tools_when_to_use"),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = whenToUse,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    // Parameters
                    tool.parameters?.let { params ->
                        if (params.isNotEmpty()) {
                            Column {
                                Text(
                                    text = localizedString("mobile.tools_parameters"),
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = MaterialTheme.colorScheme.surfaceVariant
                                ) {
                                    Column(
                                        modifier = Modifier.padding(12.dp),
                                        verticalArrangement = Arrangement.spacedBy(4.dp)
                                    ) {
                                        params.forEach { (key, value) ->
                                            Row {
                                                Text(
                                                    text = "$key: ",
                                                    style = MaterialTheme.typography.bodySmall,
                                                    fontWeight = FontWeight.Medium,
                                                    fontFamily = FontFamily.Monospace
                                                )
                                                Text(
                                                    text = value,
                                                    style = MaterialTheme.typography.bodySmall,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                    fontFamily = FontFamily.Monospace
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
