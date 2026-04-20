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
                title = { Text(localizedString("mobile.env_title")) },
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
                Icon(Icons.Filled.Add, contentDescription = localizedString("mobile.env_add_item"))
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
                            localizedString("mobile.env_all_items").replace("{count}", state.items.size.toString())
                        } else {
                            localizedString("mobile.env_items_count")
                                .replace("{name}", getCategoryDisplayName(state.selectedCategory))
                                .replace("{count}", state.filteredItems.size.toString())
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
                                text = localizedString("mobile.env_no_items"),
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
                        text = localizedString("mobile.env_context_enrichment").replace("{count}", state.contextEnrichment.size.toString()),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(state.contextEnrichment.entries.toList()) { (key, value) ->
                    SmartEnrichmentCard(key = key, value = value.toString())
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
                            text = localizedString("mobile.env_community_note"),
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
            label = { Text(localizedString("mobile.env_filter_all")) }
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
                            contentDescription = localizedString("mobile.env_delete"),
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
            title = { Text(localizedString("mobile.env_delete_item")) },
            text = { Text(localizedString("mobile.env_delete_confirm").replace("{name}", item.name)) },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    onDelete()
                }) {
                    Text(localizedString("mobile.env_delete"), color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text(localizedString("mobile.env_cancel"))
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
        title = { Text(localizedString("mobile.env_add_item")) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text(localizedString("mobile.env_item_name")) },
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
                        label = { Text(localizedString("mobile.env_category")) },
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
                        label = { Text(localizedString("mobile.env_qty")) },
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
                            label = { Text(localizedString("mobile.env_condition")) },
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
                    label = { Text(localizedString("mobile.env_notes_optional")) },
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
                    Text(localizedString("mobile.env_add"))
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isCreating
            ) {
                Text(localizedString("mobile.env_cancel"))
            }
        }
    )
}

/**
 * Smart enrichment card that auto-detects data structure and displays it nicely.
 * Handles: entity lists, player lists, weather, wallet status, etc.
 */
@Composable
private fun SmartEnrichmentCard(key: String, value: String) {
    var expanded by remember { mutableStateOf(true) }

    // Parse the data structure
    val parsedData = remember(value) { parseEnrichmentData(value) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Header with icon and title
            Row(
                modifier = Modifier.fillMaxWidth().testableClickable("enrichment_$key") {
                    expanded = !expanded
                },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        getEnrichmentIcon(key),
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = getEnrichmentTitle(key),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = parsedData.summary,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Icon(
                    if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                    contentDescription = if (expanded) "Collapse" else "Expand"
                )
            }

            if (expanded) {
                Spacer(modifier = Modifier.height(12.dp))

                when (parsedData) {
                    is ParsedEnrichmentData.ItemList -> {
                        // Group items if they have a grouping field
                        if (parsedData.groupedItems.isNotEmpty()) {
                            parsedData.groupedItems.forEach { (group, items) ->
                                ItemGroupSection(group = group, items = items)
                                Spacer(modifier = Modifier.height(8.dp))
                            }
                        } else {
                            // Flat list
                            parsedData.items.forEach { item ->
                                SmartItemRow(item = item)
                            }
                        }
                    }
                    is ParsedEnrichmentData.KeyValueData -> {
                        KeyValueSection(data = parsedData.pairs)
                    }
                    is ParsedEnrichmentData.RawJson -> {
                        Surface(
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = parsedData.formatted,
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace,
                                modifier = Modifier.padding(8.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Parsed enrichment data - can be item list, key-value pairs, or raw JSON
 */
private sealed class ParsedEnrichmentData(open val summary: String) {
    data class ItemList(
        val items: List<EnrichmentItem>,
        val groupedItems: Map<String, List<EnrichmentItem>>,
        override val summary: String
    ) : ParsedEnrichmentData(summary)

    data class KeyValueData(
        val pairs: List<Pair<String, String>>,
        override val summary: String
    ) : ParsedEnrichmentData(summary)

    data class RawJson(
        val formatted: String,
        override val summary: String
    ) : ParsedEnrichmentData(summary)
}

/**
 * Single enrichment item (entity, player, etc.)
 */
private data class EnrichmentItem(
    val name: String,
    val state: String?,
    val id: String?,
    val group: String?,
    val extraFields: Map<String, String>
)

/**
 * Parse enrichment JSON into structured data
 */
private fun parseEnrichmentData(json: String): ParsedEnrichmentData {
    val trimmed = json.trim()

    // Try to find arrays of items
    val arrayKeys = listOf("entities", "players", "items", "data", "results")
    for (arrayKey in arrayKeys) {
        val items = extractItemsFromArray(trimmed, arrayKey)
        if (items.isNotEmpty()) {
            // Group by domain/type if available
            val grouped = items.filter { it.group != null }.groupBy { it.group!! }
            val summary = "(${items.size} items)"
            return ParsedEnrichmentData.ItemList(items, grouped.toList().sortedBy { it.first }.toMap(), summary)
        }
    }

    // Try to extract key-value pairs for simple responses
    val kvPairs = extractKeyValuePairs(trimmed)
    if (kvPairs.isNotEmpty() && kvPairs.size <= 10) {
        val success = kvPairs.any { it.first == "success" && it.second == "true" }
        val summary = if (success) "[v] Success" else "${kvPairs.size} fields"
        return ParsedEnrichmentData.KeyValueData(kvPairs, summary)
    }

    // Fall back to formatted JSON
    val (formatted, _) = formatJsonValue(trimmed)
    return ParsedEnrichmentData.RawJson(formatted, "JSON data")
}

/**
 * Extract items from a JSON array field
 */
private fun extractItemsFromArray(json: String, arrayKey: String): List<EnrichmentItem> {
    val items = mutableListOf<EnrichmentItem>()

    // Find the array content
    val pattern = "\"$arrayKey\"\\s*:\\s*\\["
    val startMatch = Regex(pattern).find(json) ?: return emptyList()
    val arrayStart = startMatch.range.last + 1

    // Extract objects from the array (simplified parsing)
    var depth = 1
    var objStart = -1
    var i = arrayStart

    while (i < json.length && depth > 0) {
        when (json[i]) {
            '[' -> depth++
            ']' -> depth--
            '{' -> {
                if (objStart == -1) objStart = i
            }
            '}' -> {
                if (objStart != -1) {
                    val objJson = json.substring(objStart, i + 1)
                    parseItemObject(objJson)?.let { items.add(it) }
                    objStart = -1
                }
            }
        }
        i++
    }

    return items
}

/**
 * Parse a single item object
 */
private fun parseItemObject(json: String): EnrichmentItem? {
    // Extract common fields
    val name = extractJsonString(json, "friendly_name")
        .ifEmpty { extractJsonString(json, "name") }
        .ifEmpty { extractJsonString(json, "title") }
        .ifEmpty { extractJsonString(json, "entity_id").substringAfter(".") }

    if (name.isEmpty()) return null

    val state = extractJsonString(json, "state").ifEmpty { null }
    val id = extractJsonString(json, "entity_id").ifEmpty {
        extractJsonString(json, "id").ifEmpty { null }
    }
    val group = extractJsonString(json, "domain").ifEmpty {
        extractJsonString(json, "type").ifEmpty {
            extractJsonString(json, "category").ifEmpty { null }
        }
    }

    // Extract extra display fields
    val extraFields = mutableMapOf<String, String>()
    if (json.contains("\"volume_level\"")) {
        extractJsonNumber(json, "volume_level")?.let {
            extraFields["Volume"] = "${(it * 100).toInt()}%"
        }
    }
    if (json.contains("\"media_title\"")) {
        extractJsonString(json, "media_title").takeIf { it.isNotEmpty() }?.let {
            extraFields["Playing"] = it
        }
    }
    if (json.contains("\"media_artist\"")) {
        extractJsonString(json, "media_artist").takeIf { it.isNotEmpty() }?.let {
            extraFields["Artist"] = it
        }
    }

    return EnrichmentItem(name, state, id, group, extraFields)
}

/**
 * Extract key-value pairs from JSON
 */
private fun extractKeyValuePairs(json: String): List<Pair<String, String>> {
    val pairs = mutableListOf<Pair<String, String>>()
    // Note: -? allows optional negative sign for numbers like longitude (-88.08341)
    val pattern = Regex("\"([^\"]+)\"\\s*:\\s*(?:\"([^\"]*)\"|(-?[0-9.]+|true|false|null))")

    pattern.findAll(json).forEach { match ->
        val key = match.groupValues[1]
        val value = match.groupValues[2].ifEmpty { match.groupValues[3] }
        if (!key.startsWith("_") && value.isNotEmpty()) {
            pairs.add(key to value)
        }
    }

    return pairs.take(10) // Limit to 10 pairs
}

private fun extractJsonNumber(json: String, key: String): Double? {
    val pattern = "\"$key\"\\s*:\\s*([0-9.]+)"
    val regex = Regex(pattern)
    return regex.find(json)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
}

@Composable
private fun getEnrichmentIcon(key: String) = when {
    key.contains("entities") || key.contains("ha_") -> Icons.Filled.Home
    key.contains("players") || key.contains("ma_") -> Icons.Filled.Speaker
    key.contains("weather") -> Icons.Filled.WbSunny
    key.contains("wallet") || key.contains("balance") -> Icons.Filled.AccountBalance
    key.contains("location") || key.contains("navigation") -> Icons.Filled.LocationOn
    else -> Icons.Filled.DataObject
}

private fun getEnrichmentTitle(key: String): String {
    return when {
        key.contains("ha_list_entities") -> "Home Assistant"
        key.contains("ma_players") -> "Music Players"
        key.contains("ma_play") -> "Music Assistant"
        key.contains("weather") -> "Weather"
        key.contains("wallet") -> "Wallet"
        key.contains("location") -> "Location"
        else -> key.substringAfter(":").replace("_", " ").replaceFirstChar { it.uppercase() }
    }
}

@Composable
private fun ItemGroupSection(group: String, items: List<EnrichmentItem>) {
    var expanded by remember { mutableStateOf(false) }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = RoundedCornerShape(6.dp)
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().testableClickable("group_$group") {
                    expanded = !expanded
                },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        getDomainIcon(group),
                        contentDescription = group,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = group.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "(${items.size})",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Icon(
                    if (expanded) Icons.Filled.Remove else Icons.Filled.Add,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    modifier = Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
            }

            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))
                items.forEach { item ->
                    SmartItemRow(item = item)
                }
            }
        }
    }
}

@Composable
private fun SmartItemRow(item: EnrichmentItem) {
    var showDetails by remember { mutableStateOf(false) }

    Column(modifier = Modifier.padding(start = 26.dp, top = 4.dp, bottom = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().testableClickable("item_${item.id ?: item.name}") {
                showDetails = !showDetails
            },
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f)
            ) {
                // State indicator
                item.state?.let { state ->
                    val stateColor = getStateColor(state)
                    Icon(
                        Icons.Filled.Circle,
                        contentDescription = state,
                        modifier = Modifier.size(8.dp),
                        tint = stateColor
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Text(
                    text = item.name,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1
                )
            }
            item.state?.let { state ->
                Text(
                    text = state,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        // Extra fields (volume, now playing, etc.)
        if (item.extraFields.isNotEmpty()) {
            item.extraFields.forEach { (label, value) ->
                Text(
                    text = "$label: $value",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.padding(start = 16.dp),
                    maxLines = 1
                )
            }
        }

        // Show ID on expand
        if (showDetails && item.id != null) {
            Surface(
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(4.dp),
                modifier = Modifier.padding(top = 4.dp)
            ) {
                Text(
                    text = item.id,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(4.dp)
                )
            }
        }
    }
}

@Composable
private fun getStateColor(state: String) = when (state.lowercase()) {
    "on", "playing", "home", "open" -> MaterialTheme.colorScheme.primary
    "off", "idle", "closed", "locked", "paused" -> MaterialTheme.colorScheme.onSurfaceVariant
    "unavailable", "unknown" -> MaterialTheme.colorScheme.error
    else -> MaterialTheme.colorScheme.tertiary
}

@Composable
private fun KeyValueSection(data: List<Pair<String, String>>) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = RoundedCornerShape(6.dp)
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            data.forEach { (key, value) ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = value,
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        }
    }
}

/**
 * Format a JSON string with proper indentation, or return raw value if not JSON.
 */
private fun formatJsonValue(value: String): Pair<String, Boolean> {
    val trimmed = value.trim()
    if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
        return value to false
    }

    return try {
        // Simple JSON formatter without external dependencies
        val formatted = buildString {
            var indent = 0
            var inString = false
            var escape = false

            for (char in trimmed) {
                when {
                    escape -> {
                        append(char)
                        escape = false
                    }
                    char == '\\' && inString -> {
                        append(char)
                        escape = true
                    }
                    char == '"' -> {
                        inString = !inString
                        append(char)
                    }
                    !inString && (char == '{' || char == '[') -> {
                        append(char)
                        indent++
                        append('\n')
                        repeat(indent * 2) { append(' ') }
                    }
                    !inString && (char == '}' || char == ']') -> {
                        indent--
                        append('\n')
                        repeat(indent * 2) { append(' ') }
                        append(char)
                    }
                    !inString && char == ',' -> {
                        append(char)
                        append('\n')
                        repeat(indent * 2) { append(' ') }
                    }
                    !inString && char == ':' -> {
                        append(": ")
                    }
                    !inString && char.isWhitespace() -> {
                        // Skip whitespace outside strings
                    }
                    else -> append(char)
                }
            }
        }
        formatted to true
    } catch (e: Exception) {
        value to false
    }
}

/**
 * Get a human-readable summary of JSON content.
 */
private fun getJsonSummary(value: String, isJson: Boolean): String {
    if (!isJson) {
        return if (value.length > 100) value.take(100) + "..." else value
    }

    val trimmed = value.trim()

    // Try to extract key info from common patterns
    return try {
        when {
            // Tool response: {"success":true, "tool_name":"xxx", ...}
            trimmed.contains("\"tool_name\"") -> {
                val toolName = extractJsonString(trimmed, "tool_name")
                val success = trimmed.contains("\"success\":true") || trimmed.contains("\"success\": true")
                val status = if (success) "[v]" else "[!]"
                "$status Tool: $toolName"
            }
            // Players list: {"success":true, "players":[...]}
            trimmed.contains("\"players\"") -> {
                val count = trimmed.split("\"entity_id\"").size - 1
                "[v] $count player(s) found"
            }
            // Generic success response
            trimmed.contains("\"success\":true") || trimmed.contains("\"success\": true") -> {
                val desc = extractJsonString(trimmed, "description")
                if (desc.isNotEmpty()) "[v] $desc" else "[v] Success"
            }
            // Error response
            trimmed.contains("\"error\"") -> {
                val error = extractJsonString(trimmed, "error")
                "[!] Error: ${error.take(50)}"
            }
            // Array response
            trimmed.startsWith("[") -> {
                val count = trimmed.count { it == '{' }
                "$count item(s)"
            }
            else -> {
                // Just show first meaningful key-value
                val firstKey = extractFirstKey(trimmed)
                if (firstKey.isNotEmpty()) "$firstKey: ..." else "JSON Object"
            }
        }
    } catch (e: Exception) {
        if (value.length > 100) value.take(100) + "..." else value
    }
}

private fun extractJsonString(json: String, key: String): String {
    val pattern = "\"$key\"\\s*:\\s*\"([^\"]*)\""
    val regex = Regex(pattern)
    return regex.find(json)?.groupValues?.getOrNull(1) ?: ""
}

private fun extractFirstKey(json: String): String {
    val pattern = "\"([^\"]+)\"\\s*:"
    val regex = Regex(pattern)
    return regex.find(json)?.groupValues?.getOrNull(1) ?: ""
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
                text = localizedString("mobile.env_cache_stats"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatItem(localizedString("mobile.env_stat_entries"), stats.entries.toString())
                StatItem(localizedString("mobile.env_stat_hits"), stats.hits.toString())
                StatItem(localizedString("mobile.env_stat_misses"), stats.misses.toString())
                StatItem(localizedString("mobile.env_stat_hit_rate"), "${stats.hitRatePct}%")
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

/**
 * Entity data class for HA entities
 */
private data class EntityInfo(
    val entityId: String,
    val friendlyName: String,
    val state: String,
    val domain: String
)

/**
 * Parse ha_list_entities JSON response into grouped entities
 */
private fun parseEntities(json: String): Map<String, List<EntityInfo>> {
    val entities = mutableListOf<EntityInfo>()

    // Simple regex-based parsing for entity objects
    val entityPattern = Regex(
        "\\{[^{}]*\"entity_id\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"state\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"friendly_name\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"domain\"\\s*:\\s*\"([^\"]+)\"[^{}]*\\}",
        RegexOption.DOT_MATCHES_ALL
    )

    // Also try alternate field order
    val altPattern = Regex(
        "\\{[^{}]*\"entity_id\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"friendly_name\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"state\"\\s*:\\s*\"([^\"]+)\"[^{}]*\"domain\"\\s*:\\s*\"([^\"]+)\"[^{}]*\\}",
        RegexOption.DOT_MATCHES_ALL
    )

    entityPattern.findAll(json).forEach { match ->
        entities.add(EntityInfo(
            entityId = match.groupValues[1],
            state = match.groupValues[2],
            friendlyName = match.groupValues[3],
            domain = match.groupValues[4]
        ))
    }

    // Try alternate pattern if no matches
    if (entities.isEmpty()) {
        altPattern.findAll(json).forEach { match ->
            entities.add(EntityInfo(
                entityId = match.groupValues[1],
                friendlyName = match.groupValues[2],
                state = match.groupValues[3],
                domain = match.groupValues[4]
            ))
        }
    }

    // If still no matches, try a more flexible approach
    if (entities.isEmpty()) {
        // Extract individual field values
        val entityIds = Regex("\"entity_id\"\\s*:\\s*\"([^\"]+)\"").findAll(json).map { it.groupValues[1] }.toList()
        val states = Regex("\"state\"\\s*:\\s*\"([^\"]+)\"").findAll(json).map { it.groupValues[1] }.toList()
        val names = Regex("\"friendly_name\"\\s*:\\s*\"([^\"]+)\"").findAll(json).map { it.groupValues[1] }.toList()
        val domains = Regex("\"domain\"\\s*:\\s*\"([^\"]+)\"").findAll(json).map { it.groupValues[1] }.toList()

        val minSize = minOf(entityIds.size, states.size, names.size, domains.size)
        for (i in 0 until minSize) {
            entities.add(EntityInfo(
                entityId = entityIds[i],
                state = states[i],
                friendlyName = names[i],
                domain = domains[i]
            ))
        }
    }

    return entities.groupBy { it.domain }.toList().sortedBy { it.first }.toMap()
}

/**
 * Domain icon mapping
 */
@Composable
private fun getDomainIcon(domain: String) = when (domain) {
    "light" -> Icons.Filled.Lightbulb
    "switch" -> Icons.Filled.ToggleOn
    "media_player" -> Icons.Filled.Speaker
    "climate" -> Icons.Filled.Thermostat
    "sensor" -> Icons.Filled.Sensors
    "binary_sensor" -> Icons.Filled.RadioButtonChecked
    "cover" -> Icons.Filled.Blinds
    "fan" -> Icons.Filled.Air
    "lock" -> Icons.Filled.Lock
    "camera" -> Icons.Filled.CameraAlt
    "automation" -> Icons.Filled.AutoMode
    "person" -> Icons.Filled.Person
    else -> Icons.Filled.Devices
}

/**
 * Specialized card for ha_list_entities data - groups by domain with expandable items
 */
@Composable
private fun EntityEnrichmentCard(key: String, value: String) {
    val entities = remember(value) { parseEntities(value) }
    val totalCount = entities.values.sumOf { it.size }
    var cardExpanded by remember { mutableStateOf(true) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth().testableClickable("enrichment_header_$key") {
                    cardExpanded = !cardExpanded
                },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Filled.Home,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Home Assistant",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "($totalCount entities)",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Icon(
                    if (cardExpanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                    contentDescription = if (cardExpanded) "Collapse" else "Expand"
                )
            }

            if (cardExpanded) {
                Spacer(modifier = Modifier.height(12.dp))

                // Domain groups
                entities.forEach { (domain, domainEntities) ->
                    DomainSection(domain = domain, entities = domainEntities)
                    Spacer(modifier = Modifier.height(8.dp))
                }
            }
        }
    }
}

@Composable
private fun DomainSection(domain: String, entities: List<EntityInfo>) {
    var expanded by remember { mutableStateOf(false) }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = RoundedCornerShape(6.dp)
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            // Domain header
            Row(
                modifier = Modifier.fillMaxWidth().testableClickable("domain_$domain") {
                    expanded = !expanded
                },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        getDomainIcon(domain),
                        contentDescription = domain,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = domain.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "(${entities.size})",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Icon(
                    if (expanded) Icons.Filled.Remove else Icons.Filled.Add,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    modifier = Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
            }

            // Entity list when expanded
            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))
                entities.forEach { entity ->
                    EntityRow(entity = entity)
                }
            }
        }
    }
}

@Composable
private fun EntityRow(entity: EntityInfo) {
    var showDetails by remember { mutableStateOf(false) }

    Column(modifier = Modifier.padding(start = 26.dp, top = 4.dp, bottom = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().testableClickable("entity_${entity.entityId}") {
                showDetails = !showDetails
            },
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f)
            ) {
                // State indicator
                val stateColor = when (entity.state.lowercase()) {
                    "on", "playing", "home", "open" -> MaterialTheme.colorScheme.primary
                    "off", "idle", "closed", "locked" -> MaterialTheme.colorScheme.onSurfaceVariant
                    "unavailable", "unknown" -> MaterialTheme.colorScheme.error
                    else -> MaterialTheme.colorScheme.tertiary
                }
                Icon(
                    Icons.Filled.Circle,
                    contentDescription = entity.state,
                    modifier = Modifier.size(8.dp),
                    tint = stateColor
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = entity.friendlyName,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1
                )
            }
            Text(
                text = entity.state,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        // Expandable details
        if (showDetails) {
            Surface(
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(4.dp),
                modifier = Modifier.padding(top = 4.dp)
            ) {
                Text(
                    text = entity.entityId,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(4.dp)
                )
            }
        }
    }
}

@Composable
private fun getCategoryDisplayName(category: String): String = when (category) {
    "want" -> localizedString("mobile.env_cat_want")
    "need" -> localizedString("mobile.env_cat_need")
    "have" -> localizedString("mobile.env_cat_have")
    "can_borrow" -> localizedString("mobile.env_cat_can_borrow")
    "can_barter" -> localizedString("mobile.env_cat_can_barter")
    else -> category.replaceFirstChar { it.uppercase() }
}

@Composable
private fun getConditionDisplayName(condition: String): String = when (condition) {
    "new" -> localizedString("mobile.env_cond_new")
    "good" -> localizedString("mobile.env_cond_good")
    "fair" -> localizedString("mobile.env_cond_fair")
    "poor" -> localizedString("mobile.env_cond_poor")
    "broken" -> localizedString("mobile.env_cond_broken")
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
