package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
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
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Services screen for service status management
 * Based on ~/CIRISGUI-Standalone/apps/agui/app/services/page.tsx
 *
 * Features:
 * - Service health overview (healthy/unhealthy counts)
 * - Handler-specific and global services listing
 * - Service priority and circuit breaker status display
 * - Priority management controls
 * - Circuit breaker reset functionality
 * - Service diagnostics
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ServicesScreen(
    servicesData: ServicesData,
    isLoading: Boolean,
    expandedServiceIds: Set<String> = emptySet(),
    onToggleServiceExpanded: (String) -> Unit = {},
    onRefresh: () -> Unit,
    onDiagnose: () -> Unit,
    onResetCircuitBreakers: (serviceType: String?) -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showResetDialog by remember { mutableStateOf(false) }
    var selectedResetType by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_service_management")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_services_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onDiagnose,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_services_diagnose") { onDiagnose() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Warning,
                            contentDescription = localizedString("mobile.services_diagnostics")
                        )
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_services_refresh") { onRefresh() }
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
        if (isLoading && servicesData.globalServices.isEmpty() && servicesData.handlerServices.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Service Health Overview
                item {
                    ServiceHealthOverviewCard(
                        overallHealth = servicesData.overallHealth,
                        totalServices = servicesData.totalServices,
                        healthyServices = servicesData.healthyServices,
                        unhealthyServices = servicesData.unhealthyServices
                    )
                }

                // Circuit Breaker Management
                item {
                    CircuitBreakerCard(
                        onResetAll = { showResetDialog = true; selectedResetType = null },
                        onResetByType = { type -> showResetDialog = true; selectedResetType = type }
                    )
                }

                // Diagnostics Results (if available)
                if (servicesData.diagnostics != null) {
                    item {
                        DiagnosticsCard(diagnostics = servicesData.diagnostics)
                    }
                }

                // Global Services Section
                if (servicesData.globalServices.isNotEmpty()) {
                    item {
                        Text(
                            text = localizedString("mobile.services_global"),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    servicesData.globalServices.forEach { (serviceType, providers) ->
                        item {
                            ServiceTypeCard(
                                serviceType = serviceType,
                                providers = providers,
                                scope = "global",
                                expandedServiceIds = expandedServiceIds,
                                onToggleServiceExpanded = onToggleServiceExpanded
                            )
                        }
                    }
                }

                // Handler-Specific Services Section
                if (servicesData.handlerServices.isNotEmpty()) {
                    item {
                        Text(
                            text = localizedString("mobile.services_handler"),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    servicesData.handlerServices.forEach { (handler, serviceTypes) ->
                        item {
                            HandlerServicesCard(
                                handler = handler,
                                serviceTypes = serviceTypes,
                                expandedServiceIds = expandedServiceIds,
                                onToggleServiceExpanded = onToggleServiceExpanded
                            )
                        }
                    }
                }

                // Empty state
                if (servicesData.globalServices.isEmpty() && servicesData.handlerServices.isEmpty()) {
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(32.dp),
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = localizedString("mobile.services_no_services"),
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = localizedString("mobile.services_unavailable"),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // Reset Circuit Breakers Dialog
    if (showResetDialog) {
        AlertDialog(
            onDismissRequest = { showResetDialog = false },
            title = { Text(localizedString("mobile.services_reset_title")) },
            text = {
                Text(
                    if (selectedResetType != null) {
                        localizedString("mobile.services_reset_title") + " for $selectedResetType services?"
                    } else {
                        localizedString("mobile.services_circuit_hint")
                    }
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        onResetCircuitBreakers(selectedResetType)
                        showResetDialog = false
                    },
                    modifier = Modifier.testableClickable("btn_reset_confirm") {
                        onResetCircuitBreakers(selectedResetType)
                        showResetDialog = false
                    }
                ) {
                    Text(localizedString("mobile.services_reset"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showResetDialog = false },
                    modifier = Modifier.testableClickable("btn_reset_cancel") { showResetDialog = false }
                ) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }
}

@Composable
private fun ServiceHealthOverviewCard(
    overallHealth: String,
    totalServices: Int,
    healthyServices: Int,
    unhealthyServices: Int,
    modifier: Modifier = Modifier
) {
    val semantic = SemanticColors.Default
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.services_health"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Overall Health
                HealthMetricItem(
                    label = localizedString("status.all_operational"),
                    value = overallHealth.uppercase(),
                    color = when (overallHealth.lowercase()) {
                        "healthy" -> semantic.success
                        "degraded" -> semantic.warning
                        else -> semantic.error
                    }
                )

                // Total Services
                HealthMetricItem(
                    label = localizedString("mobile.common_all"),
                    value = totalServices.toString(),
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )

                // Healthy Services
                HealthMetricItem(
                    label = localizedString("status.online"),
                    value = healthyServices.toString(),
                    color = semantic.success
                )

                // Unhealthy Services
                HealthMetricItem(
                    label = localizedString("status.offline"),
                    value = unhealthyServices.toString(),
                    color = if (unhealthyServices > 0) semantic.error else semantic.success
                )
            }
        }
    }
}

@Composable
private fun HealthMetricItem(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
        )
    }
}

@Composable
private fun CircuitBreakerCard(
    onResetAll: () -> Unit,
    onResetByType: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }

    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.services_circuit_breaker"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Text(
                text = localizedString("mobile.services_circuit_hint"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onResetAll,
                    modifier = Modifier.weight(1f).testableClickable("btn_reset_all") { onResetAll() }
                ) {
                    Text(localizedString("mobile.services_reset_all"))
                }

                Box(modifier = Modifier.weight(1f)) {
                    OutlinedButton(
                        onClick = { expanded = true },
                        modifier = Modifier.fillMaxWidth().testableClickable("btn_reset_by_type") { expanded = true }
                    ) {
                        Text(localizedString("mobile.services_reset_type"))
                    }

                    DropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false }
                    ) {
                        val serviceTypes = listOf("llm", "communication", "memory", "audit", "tool", "wise_authority")
                        serviceTypes.forEach { type ->
                            DropdownMenuItem(
                                text = { Text(type.uppercase()) },
                                onClick = {
                                    expanded = false
                                    onResetByType(type)
                                },
                                modifier = Modifier.testableClickable("menu_reset_${type}") {
                                    expanded = false
                                    onResetByType(type)
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DiagnosticsCard(
    diagnostics: ServiceDiagnostics,
    modifier: Modifier = Modifier
) {
    val semantic = SemanticColors.Default
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when (diagnostics.overallHealth.lowercase()) {
                "healthy" -> semantic.surfaceSuccess
                "degraded" -> semantic.surfaceWarning
                else -> semantic.surfaceError
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("mobile.services_diagnostics"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                Text(
                    text = "${diagnostics.issuesFound} ${localizedString("mobile.services_issues")}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (diagnostics.issuesFound > 0) semantic.error else semantic.success,
                    fontWeight = FontWeight.Medium
                )
            }

            // Issues
            if (diagnostics.issues.isNotEmpty()) {
                Text(
                    text = localizedString("mobile.services_issues"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                diagnostics.issues.forEach { issue ->
                    Text(
                        text = "- $issue",
                        style = MaterialTheme.typography.bodySmall,
                        color = semantic.error
                    )
                }
            }

            // Recommendations
            if (diagnostics.recommendations.isNotEmpty()) {
                Text(
                    text = localizedString("mobile.services_recommendations"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                diagnostics.recommendations.forEach { rec ->
                    Text(
                        text = "- $rec",
                        style = MaterialTheme.typography.bodySmall,
                        color = semantic.info
                    )
                }
            }
        }
    }
}

@Composable
private fun ServiceTypeCard(
    serviceType: String,
    providers: List<ServiceProvider>,
    scope: String,
    expandedServiceIds: Set<String>,
    onToggleServiceExpanded: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = DisplayNames.humanizeCategory(serviceType),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "${providers.size} provider${if (providers.size != 1) "s" else ""}", // Keep English for technical term
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            providers.forEach { provider ->
                val serviceId = "${serviceType}_${provider.name}"
                ServiceProviderRow(
                    provider = provider,
                    isExpanded = serviceId in expandedServiceIds,
                    onToggleExpand = { onToggleServiceExpanded(serviceId) }
                )
            }
        }
    }
}

@Composable
private fun ServiceProviderRow(
    provider: ServiceProvider,
    isExpanded: Boolean = false,
    onToggleExpand: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val rotationAngle by animateFloatAsState(
        targetValue = if (isExpanded) 180f else 0f,
        label = "chevron_rotation"
    )

    val semantic = SemanticColors.Default
    val statusColor = when (provider.circuitBreakerState.lowercase()) {
        "closed" -> semantic.success
        "half_open" -> semantic.warning
        else -> semantic.error
    }

    Column(modifier = modifier.fillMaxWidth()) {
        // Header row (clickable to expand)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { onToggleExpand() }
                .padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f)
            ) {
                // Circuit breaker status dot
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(statusColor)
                )

                // Human-friendly service name
                Text(
                    text = DisplayNames.humanizeServiceName(provider.name),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
            }

            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Human-friendly status badge
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = statusColor.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = DisplayNames.humanizeStatus(provider.circuitBreakerState),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = statusColor
                    )
                }

                // Expand chevron
                Icon(
                    imageVector = Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (isExpanded) "Collapse" else "Expand", // Keep English for accessibility
                    modifier = Modifier
                        .size(20.dp)
                        .rotate(rotationAngle),
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
                    .padding(start = 18.dp, bottom = 8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                // Priority info
                DetailRow(label = "Priority", value = provider.priority) // Keep English for technical term

                // Priority group (only show if non-zero)
                if (provider.priorityGroup > 0) {
                    DetailRow(label = "Priority Group", value = provider.priorityGroup.toString()) // Keep English for technical term
                }

                // Strategy
                DetailRow(label = "Strategy", value = DisplayNames.humanizeStrategy(provider.strategy)) // Keep English for technical term

                // Capabilities (if any)
                if (provider.capabilities.isNotEmpty()) {
                    Text(
                        text = localizedString("mobile.services_capabilities"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.padding(top = 2.dp)
                    ) {
                        provider.capabilities.take(4).forEach { capability ->
                            SuggestionChip(
                                onClick = {},
                                label = {
                                    Text(
                                        text = capability,
                                        style = MaterialTheme.typography.labelSmall
                                    )
                                }
                            )
                        }
                        if (provider.capabilities.size > 4) {
                            Text(
                                text = "+${provider.capabilities.size - 4}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(start = 4.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun HandlerServicesCard(
    handler: String,
    serviceTypes: Map<String, List<ServiceProvider>>,
    expandedServiceIds: Set<String>,
    onToggleServiceExpanded: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.services_handler_label", "handler", handler),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            serviceTypes.forEach { (serviceType, providers) ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = DisplayNames.humanizeCategory(serviceType),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary
                    )

                    providers.forEach { provider ->
                        val serviceId = "${handler}_${serviceType}_${provider.name}"
                        ServiceProviderRow(
                            provider = provider,
                            isExpanded = serviceId in expandedServiceIds,
                            onToggleExpand = { onToggleServiceExpanded(serviceId) }
                        )
                    }
                }

                if (serviceType != serviceTypes.keys.last()) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                }
            }
        }
    }
}

// Data classes

/**
 * Complete services data model
 */
data class ServicesData(
    val overallHealth: String = "unknown",
    val totalServices: Int = 0,
    val healthyServices: Int = 0,
    val unhealthyServices: Int = 0,
    val globalServices: Map<String, List<ServiceProvider>> = emptyMap(),
    val handlerServices: Map<String, Map<String, List<ServiceProvider>>> = emptyMap(),
    val diagnostics: ServiceDiagnostics? = null
)

/**
 * Service provider data
 */
data class ServiceProvider(
    val name: String,
    val priority: String,
    val priorityGroup: Int,
    val strategy: String,
    val circuitBreakerState: String,
    val capabilities: List<String> = emptyList()
)

/**
 * Service diagnostics results
 */
data class ServiceDiagnostics(
    val overallHealth: String,
    val issuesFound: Int,
    val globalServices: Int,
    val handlerServices: Int,
    val issues: List<String>,
    val recommendations: List<String>
)
