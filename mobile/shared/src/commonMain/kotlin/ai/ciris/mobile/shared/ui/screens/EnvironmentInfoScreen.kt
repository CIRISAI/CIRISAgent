package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.EnrichmentCacheStatsData
import ai.ciris.mobile.shared.api.EnvironmentGraphNodeData
import ai.ciris.mobile.shared.api.ItemCategory
import ai.ciris.mobile.shared.api.ItemCondition
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.EnvironmentInfoScreenState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Environment Info screen - Shopping list style UI for environment items.
 *
 * Features:
 * - Category filter chips (Want/Need/Have/Can Borrow/Can Barter)
 * - Item cards with quantity, condition, and community share toggle
 * - Add new item dialog
 * - Context enrichment section (expandable)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EnvironmentInfoScreen(
    state: EnvironmentInfoScreenState,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    onCategorySelected: (String?) -> Unit,
    onAddItem: () -> Unit,
    onCreateItem: (name: String, category: String, quantity: Int, condition: String, notes: String?) -> Unit,
    onDeleteItem: (String) -> Unit,
    onDismissAddDialog: () -> Unit,
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("My Environment") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_environment_back") { onNavigateBack() }
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
                        modifier = Modifier.testableClickable("btn_environment_refresh") { onRefresh() }
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
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onAddItem,
                modifier = Modifier.testableClickable("btn_add_item") { onAddItem() }
            ) {
                Icon(Icons.Filled.Add, contentDescription = "Add Item")
            }
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
            if (state.isLoading && state.items.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
            }

            // Error state
            state.error?.let { error ->
                item {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Close,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.error
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.onErrorContainer
                            )
                        }
                    }
                }
            }

            // Category filter chips
            item {
                CategoryFilterChips(
                    selectedCategory = state.selectedCategory,
                    categoryCounts = state.categoryCounts,
                    onCategorySelected = onCategorySelected
                )
            }

            // Items header with count
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = if (state.selectedCategory == null) {
                            "All Items (${state.items.size})"
                        } else {
                            "${getCategoryDisplayName(state.selectedCategory)} (${state.filteredItems.size})"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            // Item cards
            if (state.filteredItems.isEmpty() && !state.isLoading) {
                item {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Info,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "No items yet. Tap + to add your first item.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            } else {
                items(state.filteredItems) { item ->
                    ItemCard(
                        item = item,
                        onDelete = { onDeleteItem(item.id) }
                    )
                }
            }

            // Context Enrichment section
            if (state.contextEnrichment.isNotEmpty()) {
                item {
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Context Enrichment (${state.contextEnrichment.size} sources)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(state.contextEnrichment.entries.toList()) { (key, value) ->
                    EnrichmentCard(key = key, value = value.toString())
                }
            }

            // Cache stats
            state.cacheStats?.let { stats ->
                item {
                    CacheStatsCard(stats = stats)
                }
            }

            // Community sharing note
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                    )
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Info,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Community sharing depends on community invitation system, coming soon.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                        )
                    }
                }
            }
        }
    }

    // Add item dialog
    if (state.showAddDialog) {
        AddItemDialog(
            isCreating = state.isCreating,
            onDismiss = onDismissAddDialog,
            onCreate = onCreateItem
        )
    }
}

@Composable
private fun CategoryFilterChips(
    selectedCategory: String?,
    categoryCounts: Map<String, Int>,
    onCategorySelected: (String?) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // "All" chip
        FilterChip(
            selected = selectedCategory == null,
            onClick = { onCategorySelected(null) },
            label = { Text("All") }
        )

        // Category chips
        listOf("want", "need", "have", "can_borrow", "can_barter").forEach { category ->
            val count = categoryCounts[category] ?: 0
            FilterChip(
                selected = selectedCategory == category,
                onClick = { onCategorySelected(category) },
                label = { Text("${getCategoryDisplayName(category)} ($count)") }
            )
        }
    }
}

@Composable
private fun ItemCard(
    item: EnvironmentGraphNodeData,
    onDelete: () -> Unit
) {
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = item.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Category badge
                        AssistChip(
                            onClick = {},
                            label = { Text(getCategoryDisplayName(item.category)) },
                            colors = AssistChipDefaults.assistChipColors(
                                containerColor = getCategoryColor(item.category)
                            )
                        )
                        // Quantity
                        if (item.quantity > 1) {
                            Text(
                                text = "x${item.quantity}",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        // Condition
                        Text(
                            text = getConditionDisplayName(item.condition),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                // Actions
                Row {
                    // Community share toggle (grayed out)
                    Switch(
                        checked = item.communityShared,
                        onCheckedChange = null,
                        enabled = false,
                        colors = SwitchDefaults.colors(
                            disabledCheckedThumbColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.38f),
                            disabledUncheckedThumbColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.38f)
                        )
                    )

                    // Delete button
                    IconButton(onClick = { showDeleteConfirm = true }) {
                        Icon(
                            imageVector = Icons.Filled.Delete,
                            contentDescription = "Delete",
                            tint = MaterialTheme.colorScheme.error.copy(alpha = 0.7f)
                        )
                    }
                }
            }

            // Notes
            item.notes?.let { notes ->
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = notes,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }

    // Delete confirmation dialog
    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("Delete Item") },
            text = { Text("Are you sure you want to delete \"${item.name}\"?") },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    onDelete()
                }) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddItemDialog(
    isCreating: Boolean,
    onDismiss: () -> Unit,
    onCreate: (name: String, category: String, quantity: Int, condition: String, notes: String?) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("have") }
    var quantity by remember { mutableStateOf("1") }
    var condition by remember { mutableStateOf("good") }
    var notes by remember { mutableStateOf("") }
    var expandedCategory by remember { mutableStateOf(false) }
    var expandedCondition by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = { if (!isCreating) onDismiss() },
        title = { Text("Add Item") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Item Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                // Category dropdown
                ExposedDropdownMenuBox(
                    expanded = expandedCategory,
                    onExpandedChange = { expandedCategory = it }
                ) {
                    OutlinedTextField(
                        value = getCategoryDisplayName(category),
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedCategory) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(
                        expanded = expandedCategory,
                        onDismissRequest = { expandedCategory = false }
                    ) {
                        listOf("want", "need", "have", "can_borrow", "can_barter").forEach { cat ->
                            DropdownMenuItem(
                                text = { Text(getCategoryDisplayName(cat)) },
                                onClick = {
                                    category = cat
                                    expandedCategory = false
                                }
                            )
                        }
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = quantity,
                        onValueChange = { quantity = it.filter { c -> c.isDigit() } },
                        label = { Text("Qty") },
                        singleLine = true,
                        modifier = Modifier.weight(1f)
                    )

                    // Condition dropdown
                    ExposedDropdownMenuBox(
                        expanded = expandedCondition,
                        onExpandedChange = { expandedCondition = it },
                        modifier = Modifier.weight(2f)
                    ) {
                        OutlinedTextField(
                            value = getConditionDisplayName(condition),
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Condition") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedCondition) },
                            modifier = Modifier.menuAnchor().fillMaxWidth()
                        )
                        ExposedDropdownMenu(
                            expanded = expandedCondition,
                            onDismissRequest = { expandedCondition = false }
                        ) {
                            listOf("new", "good", "fair", "poor", "broken").forEach { cond ->
                                DropdownMenuItem(
                                    text = { Text(getConditionDisplayName(cond)) },
                                    onClick = {
                                        condition = cond
                                        expandedCondition = false
                                    }
                                )
                            }
                        }
                    }
                }

                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onCreate(
                        name,
                        category,
                        quantity.toIntOrNull() ?: 1,
                        condition,
                        notes.takeIf { it.isNotBlank() }
                    )
                },
                enabled = name.isNotBlank() && !isCreating
            ) {
                if (isCreating) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Add")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isCreating
            ) {
                Text("Cancel")
            }
        }
    )
}

@Composable
private fun EnrichmentCard(key: String, value: String) {
    var expanded by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = key,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = FontFamily.Monospace
                )
                TextButton(onClick = { expanded = !expanded }) {
                    Text(if (expanded) "Collapse" else "Expand")
                }
            }

            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = value,
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            } else {
                Text(
                    text = if (value.length > 100) value.take(100) + "..." else value,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2
                )
            }
        }
    }
}

@Composable
private fun CacheStatsCard(stats: EnrichmentCacheStatsData) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "Cache Statistics",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatItem("Entries", stats.entries.toString())
                StatItem("Hits", stats.hits.toString())
                StatItem("Misses", stats.misses.toString())
                StatItem("Hit Rate", "${stats.hitRatePct}%")
            }
        }
    }
}

@Composable
private fun StatItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

private fun getCategoryDisplayName(category: String): String = when (category) {
    "want" -> "Want"
    "need" -> "Need"
    "have" -> "Have"
    "can_borrow" -> "Can Borrow"
    "can_barter" -> "Can Barter"
    else -> category.replaceFirstChar { it.uppercase() }
}

private fun getConditionDisplayName(condition: String): String = when (condition) {
    "new" -> "New"
    "good" -> "Good"
    "fair" -> "Fair"
    "poor" -> "Poor"
    "broken" -> "Broken"
    else -> condition.replaceFirstChar { it.uppercase() }
}

@Composable
private fun getCategoryColor(category: String) = when (category) {
    "want" -> MaterialTheme.colorScheme.tertiaryContainer
    "need" -> MaterialTheme.colorScheme.errorContainer
    "have" -> MaterialTheme.colorScheme.primaryContainer
    "can_borrow" -> MaterialTheme.colorScheme.secondaryContainer
    "can_barter" -> MaterialTheme.colorScheme.surfaceVariant
    else -> MaterialTheme.colorScheme.surfaceVariant
}
