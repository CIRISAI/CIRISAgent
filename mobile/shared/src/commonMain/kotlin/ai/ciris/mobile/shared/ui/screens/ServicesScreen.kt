package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
                title = { Text("Service Management") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    IconButton(onClick = onDiagnose, enabled = !isLoading) {
                        Icon(
                            imageVector = Icons.Filled.Warning,
                            contentDescription = "Diagnose Issues"
                        )
                    }
                    IconButton(onClick = onRefresh, enabled = !isLoading) {
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
                            text = "Global Services",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    servicesData.globalServices.forEach { (serviceType, providers) ->
                        item {
                            ServiceTypeCard(
                                serviceType = serviceType,
                                providers = providers,
                                scope = "global"
                            )
                        }
                    }
                }

                // Handler-Specific Services Section
                if (servicesData.handlerServices.isNotEmpty()) {
                    item {
                        Text(
                            text = "Handler-Specific Services",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    servicesData.handlerServices.forEach { (handler, serviceTypes) ->
                        item {
                            HandlerServicesCard(
                                handler = handler,
                                serviceTypes = serviceTypes
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
                                    text = "No Services Found",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = "Services information is currently unavailable",
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
            title = { Text("Reset Circuit Breakers") },
            text = {
                Text(
                    if (selectedResetType != null) {
                        "Reset circuit breakers for $selectedResetType services?"
                    } else {
                        "Reset all circuit breakers? This will clear any tripped breakers and allow services to attempt reconnection."
                    }
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        onResetCircuitBreakers(selectedResetType)
                        showResetDialog = false
                    }
                ) {
                    Text("Reset")
                }
            },
            dismissButton = {
                TextButton(onClick = { showResetDialog = false }) {
                    Text("Cancel")
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
                text = "Service Health Overview",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                // Overall Health
                HealthMetricItem(
                    label = "Overall Health",
                    value = overallHealth.uppercase(),
                    color = when (overallHealth.lowercase()) {
                        "healthy" -> Color(0xFF10B981)
                        "degraded" -> Color(0xFFF59E0B)
                        else -> Color(0xFFEF4444)
                    }
                )

                // Total Services
                HealthMetricItem(
                    label = "Total",
                    value = totalServices.toString(),
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )

                // Healthy Services
                HealthMetricItem(
                    label = "Healthy",
                    value = healthyServices.toString(),
                    color = Color(0xFF10B981)
                )

                // Unhealthy Services
                HealthMetricItem(
                    label = "Unhealthy",
                    value = unhealthyServices.toString(),
                    color = if (unhealthyServices > 0) Color(0xFFEF4444) else Color(0xFF10B981)
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
                text = "Circuit Breaker Management",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Text(
                text = "Reset circuit breakers to restore service connectivity",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onResetAll,
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Reset All")
                }

                Box(modifier = Modifier.weight(1f)) {
                    OutlinedButton(
                        onClick = { expanded = true },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Reset by Type")
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
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when (diagnostics.overallHealth.lowercase()) {
                "healthy" -> Color(0xFF10B981).copy(alpha = 0.1f)
                "degraded" -> Color(0xFFF59E0B).copy(alpha = 0.1f)
                else -> Color(0xFFEF4444).copy(alpha = 0.1f)
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
                    text = "Diagnostics Results",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )

                Text(
                    text = "${diagnostics.issuesFound} issues found",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (diagnostics.issuesFound > 0) Color(0xFFEF4444) else Color(0xFF10B981),
                    fontWeight = FontWeight.Medium
                )
            }

            // Issues
            if (diagnostics.issues.isNotEmpty()) {
                Text(
                    text = "Issues:",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                diagnostics.issues.forEach { issue ->
                    Text(
                        text = "- $issue",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFFEF4444)
                    )
                }
            }

            // Recommendations
            if (diagnostics.recommendations.isNotEmpty()) {
                Text(
                    text = "Recommendations:",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                diagnostics.recommendations.forEach { rec ->
                    Text(
                        text = "- $rec",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFF3B82F6)
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
                    text = serviceType.uppercase(),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "${providers.size} provider${if (providers.size != 1) "s" else ""}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            providers.forEach { provider ->
                ServiceProviderRow(provider = provider)
            }
        }
    }
}

@Composable
private fun ServiceProviderRow(
    provider: ServiceProvider,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Circuit breaker status dot
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .clip(CircleShape)
                    .background(
                        when (provider.circuitBreakerState.lowercase()) {
                            "closed" -> Color(0xFF10B981)
                            "half_open" -> Color(0xFFF59E0B)
                            else -> Color(0xFFEF4444)
                        }
                    )
            )

            Column {
                Text(
                    text = provider.name,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = "Priority: ${provider.priority} | Group: ${provider.priorityGroup} | ${provider.strategy}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        // Circuit breaker state badge
        Surface(
            shape = MaterialTheme.shapes.small,
            color = when (provider.circuitBreakerState.lowercase()) {
                "closed" -> Color(0xFF10B981).copy(alpha = 0.2f)
                "half_open" -> Color(0xFFF59E0B).copy(alpha = 0.2f)
                else -> Color(0xFFEF4444).copy(alpha = 0.2f)
            }
        ) {
            Text(
                text = provider.circuitBreakerState.uppercase(),
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                style = MaterialTheme.typography.labelSmall,
                color = when (provider.circuitBreakerState.lowercase()) {
                    "closed" -> Color(0xFF10B981)
                    "half_open" -> Color(0xFFF59E0B)
                    else -> Color(0xFFEF4444)
                }
            )
        }
    }
}

@Composable
private fun HandlerServicesCard(
    handler: String,
    serviceTypes: Map<String, List<ServiceProvider>>,
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
                text = "Handler: $handler",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            serviceTypes.forEach { (serviceType, providers) ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = serviceType.uppercase(),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary
                    )

                    providers.forEach { provider ->
                        ServiceProviderRow(provider = provider)
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
