package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.AdapterDetailsData
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.utils.DisplayNames
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh as RefreshIcon
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Adapters screen for managing communication adapters
 * Based on AdaptersFragment.kt
 *
 * Features:
 * - List of active adapters
 * - Adapter status (running/stopped)
 * - Reload/remove adapters
 * - Add new adapters (platform-specific implementation)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdaptersScreen(
    adapters: List<AdapterItem>,
    isConnected: Boolean,
    isLoading: Boolean,
    expandedAdapterIds: Set<String>,
    adapterDetails: Map<String, AdapterDetailsData>,
    onReloadAdapter: (String) -> Unit,
    onRemoveAdapter: (String) -> Unit,
    onToggleExpanded: (String) -> Unit,
    onEditConfig: (String) -> Unit,
    onAddAdapter: () -> Unit,
    onImportSkill: () -> Unit = {},
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showRemoveDialog by remember { mutableStateOf<AdapterItem?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.nav_adapters")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_adapters_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onImportSkill,
                        modifier = Modifier.testableClickable("btn_import_skill") { onImportSkill() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Download,
                            contentDescription = "Import Skill"
                        )
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_adapters_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.RefreshIcon,
                            contentDescription = localizedString("mobile.common_refresh")
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onAddAdapter,
                containerColor = MaterialTheme.colorScheme.primary,
                modifier = Modifier.testableClickable("btn_add_adapter") { onAddAdapter() }
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = localizedString("mobile.adapter_tap_add")
                )
            }
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Status header
            AdapterStatusHeader(
                isConnected = isConnected,
                adapterCount = adapters.size
            )

            // Adapter list
            if (adapters.isEmpty() && !isLoading) {
                // Empty state
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = localizedString("mobile.adapter_no_adapters"),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = localizedString("mobile.adapter_tap_add"),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(adapters) { adapter ->
                        AdapterCard(
                            adapter = adapter,
                            isExpanded = adapter.id in expandedAdapterIds,
                            details = adapterDetails[adapter.id],
                            onToggleExpand = { onToggleExpanded(adapter.id) },
                            onReload = { onReloadAdapter(adapter.id) },
                            onRemove = { showRemoveDialog = adapter },
                            onEditConfig = { onEditConfig(adapter.type.lowercase()) }
                        )
                    }
                }
            }

            if (isLoading && adapters.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
        }
    }

    // Remove confirmation dialog
    showRemoveDialog?.let { adapter ->
        AlertDialog(
            onDismissRequest = { showRemoveDialog = null },
            title = { Text(localizedString("mobile.adapter_remove_title")) },
            text = { Text(localizedString("mobile.adapter_remove_confirm", mapOf("name" to adapter.name))) },
            confirmButton = {
                Button(
                    onClick = {
                        onRemoveAdapter(adapter.id)
                        showRemoveDialog = null
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text(localizedString("mobile.common_remove"))
                }
            },
            dismissButton = {
                TextButton(onClick = { showRemoveDialog = null }) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }
}

@Composable
private fun AdapterStatusHeader(
    isConnected: Boolean,
    adapterCount: Int,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .clip(CircleShape)
                        .background(
                            if (isConnected) SemanticColors.Default.success else SemanticColors.Default.error
                        )
                )
                Text(
                    text = localizedString(if (isConnected) "mobile.interact_connected" else "mobile.interact_disconnected"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    color = if (isConnected) SemanticColors.Default.success else SemanticColors.Default.error
                )
            }

            Text(
                text = "$adapterCount ${localizedString("mobile.nav_adapters").lowercase()}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun AdapterCard(
    adapter: AdapterItem,
    isExpanded: Boolean,
    details: AdapterDetailsData?,
    onToggleExpand: () -> Unit,
    onReload: () -> Unit,
    onRemove: () -> Unit,
    onEditConfig: () -> Unit,
    modifier: Modifier = Modifier
) {
    val rotationAngle by animateFloatAsState(
        targetValue = if (isExpanded) 180f else 0f,
        label = "chevron_rotation"
    )

    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth()
        ) {
            // Header (clickable to expand/collapse)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggleExpand() }
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(
                                if (adapter.isHealthy) SemanticColors.Default.success else SemanticColors.Default.error
                            )
                    )

                    Column {
                        Text(
                            text = adapter.name,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = adapter.type,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = DisplayNames.humanizeStatus(adapter.status),
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (adapter.isHealthy) SemanticColors.Default.success else SemanticColors.Default.error
                    )
                    Icon(
                        imageVector = Icons.Filled.KeyboardArrowDown,
                        contentDescription = if (isExpanded) localizedString("mobile.interact_close") else localizedString("mobile.interact_attach_file"),
                        modifier = Modifier.rotate(rotationAngle),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Expandable details section
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                        .padding(bottom = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Adapter ID
                    Text(
                        text = localizedString("mobile.adapter_id", mapOf("id" to adapter.id)),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )

                    HorizontalDivider()

                    // Configuration section
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = localizedString("mobile.adapter_config"),
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Medium
                        )
                        TextButton(
                            onClick = onEditConfig,
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Edit,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(localizedString("mobile.common_edit"))
                        }
                    }

                    val configMap = details?.configParams?.toDisplayMap() ?: emptyMap()
                    if (configMap.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            configMap.entries.forEach { (key, value) ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = DisplayNames.humanizeConfigKey(key),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = if (value.length > 30) value.take(27) + "..." else value,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    } else {
                        Text(
                            text = localizedString("mobile.adapter_no_config"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    HorizontalDivider()

                    // Services section
                    Text(
                        text = localizedString("mobile.adapter_services"),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Medium
                    )
                    val services = details?.servicesRegistered ?: emptyList()
                    if (services.isNotEmpty()) {
                        // Use Column with Rows to wrap chips properly
                        Column(
                            modifier = Modifier.fillMaxWidth(),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            // Group services into rows of 3 for better wrapping
                            services.chunked(3).forEach { rowServices ->
                                Row(
                                    modifier = Modifier.wrapContentHeight(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    rowServices.forEach { service ->
                                        SuggestionChip(
                                            onClick = {},
                                            label = {
                                                Text(
                                                    text = DisplayNames.humanizeServiceName(service),
                                                    style = MaterialTheme.typography.labelSmall
                                                )
                                            }
                                        )
                                    }
                                }
                            }
                        }
                    } else {
                        Text(
                            text = localizedString("mobile.common_none"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    HorizontalDivider()

                    // Tools section
                    Text(
                        text = localizedString("mobile.adapter_tools"),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Medium
                    )
                    val tools = details?.tools ?: emptyList()
                    if (tools.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            tools.forEach { tool ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Text(
                                        text = tool.name,
                                        style = MaterialTheme.typography.bodySmall,
                                        fontWeight = FontWeight.Medium
                                    )
                                    Text(
                                        text = tool.description,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    } else {
                        Text(
                            text = localizedString("mobile.common_none"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    // Metrics section (if available)
                    details?.metrics?.let { metrics ->
                        HorizontalDivider()
                        Text(
                            text = localizedString("mobile.adapter_metrics"),
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Medium
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            MetricChip(
                                label = "${metrics.messagesProcessed} msgs",
                                color = MaterialTheme.colorScheme.surfaceVariant
                            )
                            MetricChip(
                                label = "${metrics.errorsCount} errors",
                                color = if (metrics.errorsCount > 0)
                                    MaterialTheme.colorScheme.errorContainer
                                else
                                    MaterialTheme.colorScheme.surfaceVariant
                            )
                            MetricChip(
                                label = DisplayNames.formatUptime(metrics.uptimeSeconds),
                                color = MaterialTheme.colorScheme.surfaceVariant
                            )
                        }
                    }
                }
            }

            // Actions row (always visible)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .padding(bottom = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = onReload,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(
                        imageVector = Icons.Filled.RefreshIcon,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(localizedString("mobile.adapter_reload"))
                }

                OutlinedButton(
                    onClick = onRemove,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Icon(
                        imageVector = Icons.Filled.Delete,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(localizedString("mobile.common_remove"))
                }
            }
        }
    }
}

@Composable
private fun MetricChip(
    label: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = color,
        modifier = modifier
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
        )
    }
}

// Data classes

/**
 * Adapter item data model
 * Matches AdapterItem from AdaptersFragment.kt
 */
data class AdapterItem(
    val id: String,
    val name: String,
    val type: String,
    val status: String,
    val isHealthy: Boolean
)
