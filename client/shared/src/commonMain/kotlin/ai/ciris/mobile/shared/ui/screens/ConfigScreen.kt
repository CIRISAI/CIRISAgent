package ai.ciris.mobile.shared.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.localization.localizedString

/**
 * Configuration management screen
 * Based on CIRISGUI-Standalone/apps/agui/app/config/page.tsx
 *
 * Features:
 * - Configuration sections grouped by prefix
 * - Search and filter configurations
 * - Edit configuration values
 * - Category filtering (adapters, services, security, etc.)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfigScreen(
    configData: ConfigScreenData,
    isLoading: Boolean,
    searchQuery: String,
    selectedCategory: String?,
    expandedSections: Set<String>,
    onSearchQueryChange: (String) -> Unit,
    onCategorySelect: (String?) -> Unit,
    onToggleSection: (String) -> Unit,
    onUpdateConfig: (String, String) -> Unit,
    onDeleteConfig: (String) -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showDeleteDialog by remember { mutableStateOf<String?>(null) }
    var editingConfig by remember { mutableStateOf<Pair<String, String>?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_configuration")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_config_back") { onNavigateBack() }
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
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_config_refresh") { onRefresh() }
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
        if (isLoading && configData.sections.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            Column(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues)
            ) {
                // Search bar
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = onSearchQueryChange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                        .testable("input_config_search"),
                    placeholder = { Text(localizedString("mobile.config_search_placeholder")) },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Filled.Search,
                            contentDescription = localizedString("mobile.tools_search_placeholder")
                        )
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp)
                )

                // Category chips
                CategoryChips(
                    categories = CONFIG_CATEGORIES,
                    selectedCategory = selectedCategory,
                    onCategorySelect = onCategorySelect,
                    modifier = Modifier.padding(horizontal = 16.dp)
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Configuration sections
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val filteredSections = configData.sections
                        .filter { section ->
                            (selectedCategory == null || section.category == selectedCategory) &&
                            (searchQuery.isEmpty() ||
                             section.name.contains(searchQuery, ignoreCase = true) ||
                             section.items.any { it.key.contains(searchQuery, ignoreCase = true) })
                        }

                    if (filteredSections.isEmpty()) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(32.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = localizedString("mobile.config_no_found"),
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    } else {
                        items(filteredSections, key = { it.name }) { section ->
                            ConfigSectionCard(
                                section = section,
                                isExpanded = expandedSections.contains(section.name),
                                onToggle = { onToggleSection(section.name) },
                                onEditConfig = { key, value -> editingConfig = key to value },
                                onDeleteConfig = { showDeleteDialog = it }
                            )
                        }
                    }

                    item {
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }
            }
        }
    }

    // Edit dialog
    editingConfig?.let { (key, currentValue) ->
        EditConfigDialog(
            configKey = key,
            currentValue = currentValue,
            onConfirm = { newValue ->
                onUpdateConfig(key, newValue)
                editingConfig = null
            },
            onDismiss = { editingConfig = null }
        )
    }

    // Delete confirmation dialog
    showDeleteDialog?.let { key ->
        AlertDialog(
            onDismissRequest = { showDeleteDialog = null },
            title = { Text(localizedString("mobile.config_delete_title")) },
            text = { Text(localizedString("mobile.config_delete_confirm").replace("{key}", key)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDeleteConfig(key)
                        showDeleteDialog = null
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.testableClickable("btn_config_confirm_delete") {
                        onDeleteConfig(key)
                        showDeleteDialog = null
                    }
                ) {
                    Text(localizedString("mobile.common_delete"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showDeleteDialog = null },
                    modifier = Modifier.testableClickable("btn_config_cancel_delete") { showDeleteDialog = null }
                ) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }
}

@Composable
private fun CategoryChips(
    categories: List<ConfigCategory>,
    selectedCategory: String?,
    onCategorySelect: (String?) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        FilterChip(
            selected = selectedCategory == null,
            onClick = { onCategorySelect(null) },
            label = { Text(localizedString("mobile.common_all")) },
            modifier = Modifier.testableClickable("chip_config_category_all") {
                onCategorySelect(null)
            }
        )
        categories.take(3).forEach { category ->
            FilterChip(
                selected = selectedCategory == category.id,
                onClick = { onCategorySelect(category.id) },
                label = { Text(category.label) },
                modifier = Modifier.testableClickable("chip_config_category_${category.id}") {
                    onCategorySelect(category.id)
                }
            )
        }
    }
}

@Composable
private fun ConfigSectionCard(
    section: ConfigSection,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onEditConfig: (String, String) -> Unit,
    onDeleteConfig: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable("item_config_section_${section.name.lowercase().replace(" ", "_")}") { onToggle() }
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = if (isExpanded) Icons.Filled.KeyboardArrowDown else Icons.Filled.KeyboardArrowRight,
                    contentDescription = null
                )
                Column {
                    Text(
                        text = section.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${section.items.size} items",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            section.category?.let { categoryId ->
                CONFIG_CATEGORIES.find { it.id == categoryId }?.let { category ->
                    Surface(
                        color = category.color.copy(alpha = 0.2f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = category.label,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = category.color
                        )
                    }
                }
            }
        }

        // Expanded content
        AnimatedVisibility(visible = isExpanded) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .padding(bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                section.items.forEach { item ->
                    ConfigItemRow(
                        item = item,
                        onEdit = { onEditConfig(item.key, item.displayValue) },
                        onDelete = { onDeleteConfig(item.key) }
                    )
                }
            }
        }
    }
}

@Composable
private fun ConfigItemRow(
    item: ConfigItem,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = item.key,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    if (item.isSensitive) {
                        Surface(
                            color = SemanticColors.Default.warning.copy(alpha = 0.2f),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = localizedString("mobile.config_sensitive"),
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = SemanticColors.Default.warning
                            )
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(
                        onClick = onEdit,
                        modifier = Modifier.testableClickable("btn_config_edit_${item.key.lowercase().replace(" ", "_")}") { onEdit() }
                    ) {
                        Text(localizedString("mobile.common_edit"), style = MaterialTheme.typography.labelMedium)
                    }
                    TextButton(
                        onClick = onDelete,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = MaterialTheme.colorScheme.error
                        ),
                        modifier = Modifier.testableClickable("btn_config_delete_${item.key.lowercase().replace(" ", "_")}") { onDelete() }
                    ) {
                        Text(localizedString("mobile.common_delete"), style = MaterialTheme.typography.labelMedium)
                    }
                }
            }

            // Value display
            Surface(
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(4.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = if (item.isSensitive) "********" else item.displayValue,
                    modifier = Modifier.padding(8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 3
                )
            }

            // Metadata
            Text(
                text = localizedString("mobile.config_updated")
                    .replace("{date}", item.updatedAt)
                    .replace("{user}", item.updatedBy),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun EditConfigDialog(
    configKey: String,
    currentValue: String,
    onConfirm: (String) -> Unit,
    onDismiss: () -> Unit
) {
    var editedValue by remember { mutableStateOf(currentValue) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString("mobile.common_edit") + " " + localizedString("mobile.screen_configuration")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(
                    text = configKey,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                OutlinedTextField(
                    value = editedValue,
                    onValueChange = { editedValue = it },
                    modifier = Modifier.fillMaxWidth().testable("input_config_edit_value"),
                    label = { Text(localizedString("mobile.tickets_notes_hint")) },
                    minLines = 2,
                    maxLines = 5
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(editedValue) },
                enabled = editedValue != currentValue,
                modifier = Modifier.testableClickable("btn_config_dialog_save") { onConfirm(editedValue) }
            ) {
                Text(localizedString("mobile.common_save"))
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_config_dialog_cancel") { onDismiss() }
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        }
    )
}

// Data classes

data class ConfigScreenData(
    val sections: List<ConfigSection> = emptyList(),
    val totalConfigs: Int = 0
)

data class ConfigSection(
    val name: String,
    val items: List<ConfigItem>,
    val category: String? = null
)

data class ConfigItem(
    val key: String,
    val displayValue: String,
    val updatedAt: String,
    val updatedBy: String,
    val isSensitive: Boolean = false
)

data class ConfigCategory(
    val id: String,
    val label: String,
    val description: String,
    val color: Color
)

val CONFIG_CATEGORIES = listOf(
    ConfigCategory("adapters", "Adapters", "Communication adapter configurations", SemanticColors.Default.accentSecondary),
    ConfigCategory("services", "Services", "Service-specific settings", SemanticColors.Default.info),
    ConfigCategory("security", "Security", "Security and authentication settings", SemanticColors.Default.error),
    ConfigCategory("database", "Database", "Database connection settings", SemanticColors.Default.success),
    ConfigCategory("limits", "Limits", "Rate limits and constraints", SemanticColors.Default.warning),
    ConfigCategory("workflow", "Workflow", "Task and workflow settings", SemanticColors.Default.accentTertiary),
    ConfigCategory("telemetry", "Telemetry", "Monitoring and telemetry", Color(0xFFF97316)) // Orange - no direct semantic equivalent
)
