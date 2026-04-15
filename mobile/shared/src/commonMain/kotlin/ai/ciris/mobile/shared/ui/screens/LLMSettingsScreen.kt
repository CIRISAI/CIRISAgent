package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.LocalInferenceCapability
import ai.ciris.mobile.shared.platform.getOAuthProviderName
import ai.ciris.mobile.shared.platform.probeLocalInferenceCapability
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.LocalLlmServerDiscovery
import ai.ciris.mobile.shared.ui.components.rememberLocalLlmDiscoveryState
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.viewmodels.DiscoveredLlmServer
import ai.ciris.mobile.shared.viewmodels.LLMSettingsViewModel
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * LLM Settings screen for comprehensive LLMBus configuration.
 *
 * Card-based collapsible sections following the FSD pattern:
 * 1. Status Overview - Always visible real-time metrics
 * 2. Providers - Multi-provider management with priority
 * 3. Local Servers - Discovery and management
 * 4. Advanced Settings - Distribution strategy, circuit breakers
 * 5. Authentication - CIRIS JWT token info
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LLMSettingsScreen(
    viewModel: SettingsViewModel,
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    secureStorage: ai.ciris.mobile.shared.platform.SecureStorage,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    // Core state from SettingsViewModel (config editing)
    val isLoading by viewModel.isLoading.collectAsState()
    val isCirisProxy by viewModel.isCirisProxy.collectAsState()
    val llmConfig by viewModel.llmConfig.collectAsState()

    // BYOK form state from SettingsViewModel
    val llmProvider by viewModel.llmProvider.collectAsState()
    val llmModel by viewModel.llmModel.collectAsState()
    val llmBaseUrl by viewModel.llmBaseUrl.collectAsState()
    val apiKey by viewModel.apiKey.collectAsState()
    val apiKeyMasked by viewModel.apiKeyMasked.collectAsState()
    val availableModels by viewModel.availableModels.collectAsState()

    // Local inference server discovery state from LLMSettingsViewModel
    val discoveredServers by llmViewModel.discoveredServers.collectAsState()
    val selectedServer by viewModel.selectedServer.collectAsState()
    val isDiscovering by llmViewModel.isDiscovering.collectAsState()

    // LLM Bus status state from LLMSettingsViewModel
    val llmBusStatus by llmViewModel.llmBusStatus.collectAsState()
    val llmProviders by llmViewModel.llmProviders.collectAsState()
    val isLoadingLlmBus by llmViewModel.isLoading.collectAsState()

    // Operation state from SettingsViewModel
    val isSaving by viewModel.isSaving.collectAsState()
    val saveSuccess by viewModel.saveSuccess.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()

    // LLM ViewModel messages
    val llmErrorMessage by llmViewModel.errorMessage.collectAsState()
    val llmSuccessMessage by llmViewModel.successMessage.collectAsState()

    // Section expansion state from LLMSettingsViewModel
    val statusExpanded by llmViewModel.statusExpanded.collectAsState()
    val providersExpanded by llmViewModel.providersExpanded.collectAsState()
    val localServersExpanded by llmViewModel.localServersExpanded.collectAsState()
    val advancedExpanded by llmViewModel.advancedExpanded.collectAsState()
    var authExpanded by remember { mutableStateOf(false) }

    // On-device local inference capability
    val localInferenceCapability: LocalInferenceCapability = remember { probeLocalInferenceCapability() }
    val discoveryState = rememberLocalLlmDiscoveryState()

    // Editing state
    var showApiKey by remember { mutableStateOf(false) }
    var isEditing by remember { mutableStateOf(false) }

    // Snackbar
    val snackbarHostState = remember { SnackbarHostState() }

    // Load config when screen is first shown
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    val savedSuccessMessage = localizedString("mobile.settings_saved_successfully")
    LaunchedEffect(saveSuccess) {
        if (saveSuccess) {
            snackbarHostState.showSnackbar(savedSuccessMessage)
            viewModel.clearSuccess()
            isEditing = false
        }
    }

    LaunchedEffect(errorMessage) {
        errorMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearError()
        }
    }

    // Show LLM ViewModel messages
    LaunchedEffect(llmSuccessMessage) {
        llmSuccessMessage?.let {
            snackbarHostState.showSnackbar(it)
            llmViewModel.clearSuccessMessage()
        }
    }

    LaunchedEffect(llmErrorMessage) {
        llmErrorMessage?.let {
            snackbarHostState.showSnackbar(it)
            llmViewModel.clearErrorMessage()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.llm_settings_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.settings_back")
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.refresh() },
                        modifier = Modifier.testableClickable("btn_refresh") { viewModel.refresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = localizedString("mobile.settings_refresh")
                        )
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { paddingValues ->

        if (isLoading) {
            Box(
                modifier = modifier
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
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Section 1: Status Overview (Always Visible)
                StatusOverviewCard(
                    isCirisProxy = isCirisProxy,
                    llmConfig = llmConfig,
                    llmBusStatus = llmBusStatus,
                    llmProviders = llmProviders,
                    discoveredServersCount = discoveredServers.size,
                    isLoading = isLoadingLlmBus
                )

                // Section 2: Providers (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_providers"),
                    subtitle = localizedString("mobile.llm_settings_providers_count", "count", llmProviders.size.toString()),
                    icon = Icons.Filled.Settings,
                    expanded = providersExpanded,
                    onToggle = { llmViewModel.toggleProvidersExpanded() }
                ) {
                    // Always show the registered providers list
                    RegisteredProvidersContent(
                        isCirisProxy = isCirisProxy,
                        llmProviders = llmProviders,
                        llmViewModel = llmViewModel
                    )

                    // Only show BYOK editing UI when not using CIRIS Proxy
                    if (!isCirisProxy) {
                        HorizontalDivider(
                            modifier = Modifier.padding(vertical = 12.dp),
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
                        )
                        ProvidersContent(
                            viewModel = viewModel,
                            llmProvider = llmProvider,
                            llmModel = llmModel,
                            llmBaseUrl = llmBaseUrl,
                            apiKey = apiKey,
                            apiKeyMasked = apiKeyMasked,
                            availableModels = availableModels,
                            discoveredServers = discoveredServers,
                            selectedServer = selectedServer,
                            isDiscovering = isDiscovering,
                            showApiKey = showApiKey,
                            isEditing = isEditing,
                            isSaving = isSaving,
                            llmConfig = llmConfig,
                            onShowApiKeyChange = { showApiKey = it },
                            onEditingChange = { isEditing = it }
                        )
                    }
                }

                // Section 3: Local Servers (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_local_servers"),
                    subtitle = if (discoveredServers.isNotEmpty()) {
                        localizedString("mobile.llm_settings_local_detected", "count", discoveredServers.size.toString())
                    } else if (localInferenceCapability.isReady) {
                        localizedString("mobile.llm_on_device_available")
                    } else {
                        localizedString("mobile.llm_settings_local_none")
                    },
                    icon = Icons.Filled.Wifi,
                    expanded = localServersExpanded,
                    onToggle = { llmViewModel.toggleLocalServersExpanded() }
                ) {
                    LocalServersContent(
                        viewModel = viewModel,
                        llmViewModel = llmViewModel,
                        apiClient = apiClient,
                        discoveredServers = discoveredServers,
                        selectedServer = selectedServer,
                        isDiscovering = isDiscovering,
                        localInferenceCapability = localInferenceCapability,
                        discoveryState = discoveryState,
                        onEditingChange = { isEditing = it }
                    )
                }

                // Section 4: Advanced Settings (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_advanced"),
                    subtitle = llmBusStatus?.distributionStrategyLabel ?: localizedString("mobile.llm_distribution_latency"),
                    icon = Icons.Filled.Tune,
                    expanded = advancedExpanded,
                    onToggle = { llmViewModel.toggleAdvancedExpanded() }
                ) {
                    AdvancedSettingsContent(
                        llmViewModel = llmViewModel,
                        llmBusStatus = llmBusStatus,
                        llmProviders = llmProviders
                    )
                }

                // Section 5: Authentication (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_auth"),
                    subtitle = localizedString("mobile.settings_ciris_access_token"),
                    icon = Icons.Filled.Key,
                    expanded = authExpanded,
                    onToggle = { authExpanded = !authExpanded }
                ) {
                    AuthenticationContent(
                        apiClient = apiClient,
                        secureStorage = secureStorage
                    )
                }
            }
        }
    }
}

// ============================================================================
// Section 1: Status Overview
// ============================================================================

@Composable
private fun StatusOverviewCard(
    isCirisProxy: Boolean,
    llmConfig: ai.ciris.mobile.shared.api.LlmConfigData?,
    llmBusStatus: ai.ciris.mobile.shared.models.LlmBusStatus?,
    llmProviders: List<ai.ciris.mobile.shared.models.LlmProviderStatus>,
    discoveredServersCount: Int,
    isLoading: Boolean
) {
    val semantic = SemanticColors.Default

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Filled.Analytics,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Text(
                    text = localizedString("mobile.llm_settings_status"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }

            HorizontalDivider(
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f)
            )

            // Status grid - Row 1
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatusItem(
                    label = localizedString("mobile.settings_mode"),
                    value = if (isCirisProxy) "CIRIS Proxy" else "BYOK",
                    modifier = Modifier.weight(1f)
                )
                StatusItem(
                    label = "Distribution",
                    value = llmBusStatus?.distributionStrategyLabel ?: "Automatic",
                    modifier = Modifier.weight(1f)
                )
            }

            // Status grid - Row 2
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatusItem(
                    label = "Providers",
                    value = "${llmBusStatus?.providersAvailable ?: 0}/${llmBusStatus?.providersTotal ?: 0} healthy",
                    modifier = Modifier.weight(1f)
                )
                StatusItem(
                    label = "Avg Latency",
                    value = llmBusStatus?.let { "${it.averageLatencyMs.toInt()}ms" } ?: "-",
                    modifier = Modifier.weight(1f)
                )
            }

            // Status grid - Row 3
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatusItem(
                    label = "Uptime",
                    value = llmBusStatus?.uptimeDisplay ?: "-",
                    modifier = Modifier.weight(1f)
                )
                StatusItem(
                    label = "Error Rate",
                    value = llmBusStatus?.let { "${(it.errorRate * 100).let { r -> "%.1f".format(r) }}%" } ?: "-",
                    modifier = Modifier.weight(1f)
                )
            }

            // Circuit breaker status
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                val allHealthy = llmBusStatus?.allCircuitBreakersHealthy ?: true
                val openCount = llmBusStatus?.circuitBreakersOpen ?: 0

                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = if (allHealthy) semantic.surfaceSuccess else semantic.surfaceWarning
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = if (allHealthy) Icons.Filled.CheckCircle else Icons.Filled.Warning,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = if (allHealthy) semantic.onSuccess else semantic.onWarning
                        )
                        Text(
                            text = if (allHealthy)
                                localizedString("mobile.llm_circuit_closed")
                            else
                                "$openCount provider(s) paused",
                            fontSize = 11.sp,
                            color = if (allHealthy) semantic.onSuccess else semantic.onWarning
                        )
                    }
                }
                Text(
                    text = llmBusStatus?.distributionStrategyLabel ?: localizedString("mobile.llm_distribution_latency"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun StatusItem(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.6f)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onPrimaryContainer
        )
    }
}

// ============================================================================
// Collapsible Section Component
// ============================================================================

@Composable
private fun CollapsibleSection(
    title: String,
    subtitle: String,
    icon: ImageVector,
    expanded: Boolean,
    onToggle: () -> Unit,
    content: @Composable () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column {
            // Header (always visible, clickable to expand)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggle() }
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Column {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = subtitle,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                        )
                    }
                }
                Icon(
                    imageVector = if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Expandable content
            AnimatedVisibility(
                visible = expanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                Column(
                    modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
                ) {
                    HorizontalDivider(
                        modifier = Modifier.padding(bottom = 12.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
                    )
                    content()
                }
            }
        }
    }
}

// ============================================================================
// Section 2: Providers Content
// ============================================================================

/**
 * Shows all registered LLM providers from the LLMBus.
 * This is shown in both CIRIS Proxy mode and BYOK mode.
 */
@Composable
private fun RegisteredProvidersContent(
    isCirisProxy: Boolean,
    llmProviders: List<ai.ciris.mobile.shared.models.LlmProviderStatus>,
    llmViewModel: LLMSettingsViewModel
) {
    val semantic = SemanticColors.Default

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Show proxy info if using CIRIS Proxy
        if (isCirisProxy) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Filled.Check,
                    contentDescription = null,
                    modifier = Modifier.size(24.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
                Column {
                    Text(
                        text = localizedString("mobile.settings_using_proxy"),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    val provider = getOAuthProviderName()
                    Text(
                        text = localizedString("mobile.settings_proxy_desc", "provider", provider),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
        }

        // Show all registered providers
        if (llmProviders.isEmpty()) {
            Text(
                text = "No providers registered",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        } else {
            Text(
                text = "Registered Providers (${llmProviders.size})",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Medium
            )

            llmProviders.forEach { provider ->
                val cb = provider.circuitBreaker
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = if (provider.healthy)
                            MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                        else
                            semantic.surfaceError.copy(alpha = 0.3f)
                    ),
                    border = if (provider.healthy)
                        BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.3f))
                    else
                        BorderStroke(1.dp, semantic.error.copy(alpha = 0.3f))
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.weight(1f)
                        ) {
                            // Health indicator
                            Icon(
                                imageVector = if (provider.healthy) Icons.Filled.CheckCircle else Icons.Filled.Error,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                                tint = if (provider.healthy) semantic.success else semantic.error
                            )
                            Column {
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = provider.name,
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Medium
                                    )
                                    // Priority badge
                                    Surface(
                                        shape = RoundedCornerShape(4.dp),
                                        color = when (provider.priority) {
                                            ai.ciris.mobile.shared.models.ProviderPriority.CRITICAL -> semantic.surfaceError
                                            ai.ciris.mobile.shared.models.ProviderPriority.HIGH -> MaterialTheme.colorScheme.primaryContainer
                                            ai.ciris.mobile.shared.models.ProviderPriority.NORMAL -> MaterialTheme.colorScheme.secondaryContainer
                                            ai.ciris.mobile.shared.models.ProviderPriority.LOW -> MaterialTheme.colorScheme.tertiaryContainer
                                            ai.ciris.mobile.shared.models.ProviderPriority.FALLBACK -> MaterialTheme.colorScheme.surfaceVariant
                                        }
                                    ) {
                                        Text(
                                            text = provider.priorityLabel.uppercase(),
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Medium,
                                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                        )
                                    }
                                }
                                Text(
                                    text = provider.statusMessage,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                )
                                // Show metrics summary
                                val metrics = provider.metrics
                                if (metrics.totalRequests > 0) {
                                    Text(
                                        text = "${metrics.totalRequests} requests • ${metrics.averageLatencyMs.toInt()}ms avg",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                                    )
                                }
                            }
                        }

                        // Delete button for runtime-added providers (not CIRIS providers)
                        if (!provider.name.startsWith("ciris_")) {
                            IconButton(
                                onClick = { llmViewModel.deleteProvider(provider.name) },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Filled.Delete,
                                    contentDescription = "Remove provider",
                                    tint = semantic.error,
                                    modifier = Modifier.size(18.dp)
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
private fun CirisProxyContent() {
    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Proxy benefits
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Filled.Check,
                contentDescription = null,
                modifier = Modifier.size(32.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            Column {
                Text(
                    text = localizedString("mobile.settings_using_proxy"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                val provider = getOAuthProviderName()
                Text(
                    text = localizedString("mobile.settings_proxy_desc", "provider", provider),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                )
            }
        }

        // Benefits list
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            BenefitItem(localizedString("mobile.settings_benefit_signin_is_key"))
            BenefitItem(localizedString("mobile.settings_benefit_model_routing"))
            BenefitItem(localizedString("mobile.settings_benefit_rate_limiting"))
            BenefitItem(localizedString("mobile.settings_benefit_failover"))
        }
    }
}

@Composable
private fun BenefitItem(text: String) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "•",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.primary
        )
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProvidersContent(
    viewModel: SettingsViewModel,
    llmProvider: String,
    llmModel: String,
    llmBaseUrl: String,
    apiKey: String,
    apiKeyMasked: String,
    availableModels: List<String>,
    discoveredServers: List<DiscoveredLlmServer>,
    selectedServer: DiscoveredLlmServer?,
    isDiscovering: Boolean,
    showApiKey: Boolean,
    isEditing: Boolean,
    isSaving: Boolean,
    llmConfig: ai.ciris.mobile.shared.api.LlmConfigData?,
    onShowApiKeyChange: (Boolean) -> Unit,
    onEditingChange: (Boolean) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Primary Provider Card
        ProviderCard(
            title = localizedString("mobile.settings_primary_provider"),
            priority = localizedString("mobile.llm_priority_high"),
            provider = viewModel.getProviderDisplayName(llmProvider),
            model = llmModel,
            isActive = true
        )

        // Backup Provider (if configured)
        llmConfig?.let { config ->
            if (config.backupBaseUrl != null || config.backupModel != null) {
                ProviderCard(
                    title = localizedString("mobile.settings_backup_llm"),
                    priority = localizedString("mobile.llm_priority_fallback"),
                    provider = when {
                        config.backupBaseUrl?.contains("groq") == true -> "Groq"
                        config.backupBaseUrl?.contains("together") == true -> "Together"
                        else -> "Backup"
                    },
                    model = config.backupModel ?: "-",
                    isActive = false
                )
            }
        }

        HorizontalDivider(
            modifier = Modifier.padding(vertical = 4.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
        )

        // Edit Primary Provider
        Text(
            text = localizedString("mobile.llm_edit_provider"),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Medium
        )

        // Provider selection
        var providerExpanded by remember { mutableStateOf(false) }

        ExposedDropdownMenuBox(
            expanded = providerExpanded,
            onExpandedChange = { providerExpanded = it }
        ) {
            OutlinedTextField(
                value = viewModel.getProviderDisplayName(llmProvider),
                onValueChange = {},
                readOnly = true,
                label = { Text(localizedString("mobile.settings_llm_provider")) },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = providerExpanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor()
                    .testable("input_llm_provider")
            )

            ExposedDropdownMenu(
                expanded = providerExpanded,
                onDismissRequest = { providerExpanded = false }
            ) {
                viewModel.availableProviders.forEach { (key, label) ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            viewModel.onProviderChanged(key)
                            providerExpanded = false
                            onEditingChange(true)
                        },
                        modifier = Modifier.testableClickable("menu_provider_$key") {
                            viewModel.onProviderChanged(key)
                            providerExpanded = false
                            onEditingChange(true)
                        }
                    )
                }
            }
        }

        // Model selection (only show if not local_inference OR if a server is selected)
        if (llmProvider != "local_inference" || selectedServer != null) {
            var modelExpanded by remember { mutableStateOf(false) }

            ExposedDropdownMenuBox(
                expanded = modelExpanded,
                onExpandedChange = { modelExpanded = it }
            ) {
                OutlinedTextField(
                    value = llmModel.ifEmpty { localizedString("mobile.settings_select_model") },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text(localizedString("mobile.settings_model")) },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = modelExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                        .testable("input_llm_model")
                )

                ExposedDropdownMenu(
                    expanded = modelExpanded,
                    onDismissRequest = { modelExpanded = false }
                ) {
                    availableModels.forEach { model ->
                        DropdownMenuItem(
                            text = { Text(model) },
                            onClick = {
                                viewModel.onModelChanged(model)
                                modelExpanded = false
                                onEditingChange(true)
                            }
                        )
                    }
                }
            }
        }

        // Base URL (for local/custom providers)
        if (llmProvider == "other" || llmProvider == "local" || llmProvider == "openai_compatible") {
            OutlinedTextField(
                value = llmBaseUrl,
                onValueChange = {
                    viewModel.onBaseUrlChanged(it)
                    onEditingChange(true)
                },
                label = { Text(localizedString("mobile.settings_base_url")) },
                placeholder = {
                    Text(
                        if (llmProvider == "local") "http://localhost:11434/v1"
                        else "https://api.example.com/v1"
                    )
                },
                modifier = Modifier.fillMaxWidth().testable("input_base_url"),
                singleLine = true
            )
        }

        // API Key (not for local providers)
        if (llmProvider != "local" && llmProvider != "mobile_local") {
            OutlinedTextField(
                value = if (isEditing || showApiKey) apiKey else apiKeyMasked,
                onValueChange = {
                    onEditingChange(true)
                    viewModel.onApiKeyChanged(it)
                },
                label = { Text(localizedString("mobile.settings_api_key")) },
                visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                trailingIcon = {
                    TextButton(
                        onClick = { onShowApiKeyChange(!showApiKey) }
                    ) {
                        Text(if (showApiKey) localizedString("mobile.settings_hide") else localizedString("mobile.settings_show"))
                    }
                },
                modifier = Modifier.fillMaxWidth().testable("input_api_key")
            )
        }

        // Save button
        Button(
            onClick = { viewModel.saveSettings() },
            enabled = !isSaving && isEditing,
            modifier = Modifier.fillMaxWidth().testableClickable("btn_save_settings") { viewModel.saveSettings() }
        ) {
            if (isSaving) {
                CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                    strokeWidth = 2.dp
                )
                Spacer(Modifier.width(8.dp))
            }
            Text(if (isSaving) localizedString("mobile.settings_saving") else localizedString("mobile.settings_save"))
        }
    }
}

@Composable
private fun ProviderCard(
    title: String,
    priority: String,
    provider: String,
    model: String,
    isActive: Boolean
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isActive)
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f)
            else
                MaterialTheme.colorScheme.surface
        ),
        border = if (isActive)
            BorderStroke(1.dp, MaterialTheme.colorScheme.primary)
        else
            BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = if (isActive) Icons.Filled.Circle else Icons.Filled.RadioButtonUnchecked,
                    contentDescription = null,
                    modifier = Modifier.size(12.dp),
                    tint = if (isActive)
                        SemanticColors.Default.success
                    else
                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                )
                Column {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = provider,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = when {
                                priority.contains("High", ignoreCase = true) -> MaterialTheme.colorScheme.primaryContainer
                                priority.contains("Fallback", ignoreCase = true) -> MaterialTheme.colorScheme.tertiaryContainer
                                else -> MaterialTheme.colorScheme.secondaryContainer
                            }
                        ) {
                            Text(
                                text = priority.uppercase(),
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Medium,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    Text(
                        text = model,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
            }
            if (isActive) {
                Icon(
                    imageVector = Icons.Filled.Speed,
                    contentDescription = "Active",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}

// ============================================================================
// Section 3: Local Servers Content
// ============================================================================

@Composable
private fun LocalServersContent(
    viewModel: SettingsViewModel,
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    discoveredServers: List<DiscoveredLlmServer>,
    selectedServer: DiscoveredLlmServer?,
    isDiscovering: Boolean,
    localInferenceCapability: LocalInferenceCapability,
    discoveryState: ai.ciris.mobile.shared.ui.components.LocalLlmDiscoveryState,
    onEditingChange: (Boolean) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // On-device capability info
        if (localInferenceCapability.isReady) {
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = SemanticColors.Default.surfaceSuccess.copy(alpha = 0.3f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Filled.CheckCircle,
                        contentDescription = null,
                        tint = SemanticColors.Default.success,
                        modifier = Modifier.size(20.dp)
                    )
                    Column {
                        Text(
                            text = localizedString("mobile.llm_on_device_capable"),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Medium,
                            color = SemanticColors.Default.success
                        )
                        Text(
                            text = localInferenceCapability.reason,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                        )
                    }
                }
            }
        } else if (localInferenceCapability.isComingSoon) {
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.5f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Filled.Schedule,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.tertiary,
                        modifier = Modifier.size(20.dp)
                    )
                    Column {
                        Text(
                            text = localizedString("mobile.llm_on_device_coming_soon"),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = localInferenceCapability.reason,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                        )
                    }
                }
            }
        }

        // Use the unified LocalLlmServerDiscovery component
        // This handles both network discovery AND on-device "Start Local Server" option
        LocalLlmServerDiscovery(
            state = discoveryState,
            apiClient = apiClient,
            localInferenceCapability = localInferenceCapability,
            onServerSelected = { server ->
                viewModel.selectServer(server)
                onEditingChange(true)
            },
            onAddAsProvider = { server ->
                // Add the discovered server as a provider to the LLM Bus
                llmViewModel.addDiscoveredServerAsProvider(server)
            },
            primaryColor = MaterialTheme.colorScheme.primary,
            surfaceColor = MaterialTheme.colorScheme.surfaceVariant,
            textColor = MaterialTheme.colorScheme.onSurface,
            secondaryTextColor = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

// ============================================================================
// Section 4: Advanced Settings Content
// ============================================================================

@Composable
private fun AdvancedSettingsContent(
    llmViewModel: LLMSettingsViewModel,
    llmBusStatus: ai.ciris.mobile.shared.models.LlmBusStatus?,
    llmProviders: List<ai.ciris.mobile.shared.models.LlmProviderStatus>
) {
    val currentStrategy = llmBusStatus?.distributionStrategy
        ?: ai.ciris.mobile.shared.models.DistributionStrategy.LATENCY_BASED

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        // Distribution Strategy
        Text(
            text = "How should CIRIS pick providers?",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Medium
        )

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StrategyOption(
                name = "Automatic (Recommended)",
                description = "Picks the fastest available provider",
                selected = currentStrategy == ai.ciris.mobile.shared.models.DistributionStrategy.LATENCY_BASED,
                onClick = { llmViewModel.updateDistributionStrategy(ai.ciris.mobile.shared.models.DistributionStrategy.LATENCY_BASED) }
            )
            StrategyOption(
                name = "Round Robin",
                description = "Takes turns between providers",
                selected = currentStrategy == ai.ciris.mobile.shared.models.DistributionStrategy.ROUND_ROBIN,
                onClick = { llmViewModel.updateDistributionStrategy(ai.ciris.mobile.shared.models.DistributionStrategy.ROUND_ROBIN) }
            )
            StrategyOption(
                name = "Random",
                description = "Picks randomly to spread the load",
                selected = currentStrategy == ai.ciris.mobile.shared.models.DistributionStrategy.RANDOM,
                onClick = { llmViewModel.updateDistributionStrategy(ai.ciris.mobile.shared.models.DistributionStrategy.RANDOM) }
            )
            StrategyOption(
                name = "Least Loaded",
                description = "Picks provider with fewest active requests",
                selected = currentStrategy == ai.ciris.mobile.shared.models.DistributionStrategy.LEAST_LOADED,
                onClick = { llmViewModel.updateDistributionStrategy(ai.ciris.mobile.shared.models.DistributionStrategy.LEAST_LOADED) }
            )
        }

        HorizontalDivider(
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
        )

        // Per-Provider Circuit Breaker Status
        if (llmProviders.isNotEmpty()) {
            Text(
                text = "Provider Protection Status",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Medium
            )

            llmProviders.forEach { provider ->
                ProviderCircuitBreakerRow(
                    provider = provider,
                    onReset = { llmViewModel.resetCircuitBreaker(provider.name) },
                    onForceReset = { llmViewModel.resetCircuitBreaker(provider.name, force = true) },
                    onPriorityChange = { priority -> llmViewModel.updateProviderPriority(provider.name, priority) }
                )
            }
        }

        Text(
            text = "Protection automatically pauses providers that have too many errors, then tries them again after a short wait.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProviderCircuitBreakerRow(
    provider: ai.ciris.mobile.shared.models.LlmProviderStatus,
    onReset: () -> Unit,
    onForceReset: () -> Unit,
    onPriorityChange: (ai.ciris.mobile.shared.models.ProviderPriority) -> Unit
) {
    val cb = provider.circuitBreaker
    val semantic = SemanticColors.Default
    var priorityExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
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
                // Status indicator
                Icon(
                    imageVector = when (cb.state) {
                        ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED -> Icons.Filled.CheckCircle
                        ai.ciris.mobile.shared.models.CircuitBreakerState.OPEN -> Icons.Filled.Error
                        ai.ciris.mobile.shared.models.CircuitBreakerState.HALF_OPEN -> Icons.Filled.Schedule
                    },
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = when (cb.state) {
                        ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED -> semantic.success
                        ai.ciris.mobile.shared.models.CircuitBreakerState.OPEN -> semantic.error
                        ai.ciris.mobile.shared.models.CircuitBreakerState.HALF_OPEN -> semantic.warning
                    }
                )
                Column {
                    Text(
                        text = provider.name,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = when (cb.state) {
                            ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED -> "Active and protecting"
                            ai.ciris.mobile.shared.models.CircuitBreakerState.OPEN -> "Paused due to errors"
                            ai.ciris.mobile.shared.models.CircuitBreakerState.HALF_OPEN -> "Testing recovery..."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
            }

            // Reset button (only show when circuit is open or half-open)
            if (cb.state != ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED) {
                TextButton(onClick = onReset) {
                    Text("Reset")
                }
            }
        }

        // Priority dropdown
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Priority:",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            ExposedDropdownMenuBox(
                expanded = priorityExpanded,
                onExpandedChange = { priorityExpanded = it },
                modifier = Modifier.weight(1f)
            ) {
                OutlinedTextField(
                    value = provider.priorityLabel,
                    onValueChange = {},
                    readOnly = true,
                    textStyle = MaterialTheme.typography.bodySmall,
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = priorityExpanded) },
                    modifier = Modifier
                        .menuAnchor()
                        .height(48.dp)
                        .testable("priority_${provider.name}"),
                    colors = OutlinedTextFieldDefaults.colors(
                        unfocusedBorderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f)
                    )
                )

                ExposedDropdownMenu(
                    expanded = priorityExpanded,
                    onDismissRequest = { priorityExpanded = false }
                ) {
                    ai.ciris.mobile.shared.models.ProviderPriority.entries.forEach { priority ->
                        val label = when (priority) {
                            ai.ciris.mobile.shared.models.ProviderPriority.CRITICAL -> "Critical"
                            ai.ciris.mobile.shared.models.ProviderPriority.HIGH -> "Primary"
                            ai.ciris.mobile.shared.models.ProviderPriority.NORMAL -> "Standard"
                            ai.ciris.mobile.shared.models.ProviderPriority.LOW -> "Backup"
                            ai.ciris.mobile.shared.models.ProviderPriority.FALLBACK -> "Last Resort"
                        }
                        DropdownMenuItem(
                            text = { Text(label) },
                            onClick = {
                                onPriorityChange(priority)
                                priorityExpanded = false
                            },
                            modifier = Modifier.testableClickable("priority_${provider.name}_$priority") {
                                onPriorityChange(priority)
                                priorityExpanded = false
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StrategyOption(
    name: String,
    description: String,
    selected: Boolean,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        RadioButton(
            selected = selected,
            onClick = onClick
        )
        Column {
            Text(
                text = name,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = if (selected) FontWeight.Medium else FontWeight.Normal
            )
            Text(
                text = description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

// ============================================================================
// Section 5: Authentication Content
// ============================================================================

@Composable
private fun AuthenticationContent(
    apiClient: CIRISApiClient,
    secureStorage: ai.ciris.mobile.shared.platform.SecureStorage
) {
    var tokenInfo by remember { mutableStateOf<TokenDisplayInfo?>(null) }
    var isLoading by remember { mutableStateOf(true) }

    // Load token info
    LaunchedEffect(Unit) {
        try {
            val result = secureStorage.getAccessToken()
            result.onSuccess { token ->
                if (token != null) {
                    tokenInfo = parseTokenForDisplay(token)
                }
            }
        } catch (e: Exception) {
            // Ignore
        } finally {
            isLoading = false
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Explanation
        Text(
            text = localizedString("mobile.settings_token_info_desc"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
        )

        if (isLoading) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    strokeWidth = 2.dp
                )
                Text(
                    text = localizedString("mobile.settings_loading_token"),
                    style = MaterialTheme.typography.bodySmall
                )
            }
        } else if (tokenInfo != null) {
            val info = tokenInfo!!
            val semantic = SemanticColors.Default

            // Token type badge
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = if (info.isJwt) semantic.surfaceSuccess else semantic.surfaceWarning
            ) {
                Text(
                    text = if (info.isJwt) localizedString("mobile.settings_jwt_token") else localizedString("mobile.settings_opaque_token"),
                    fontSize = 10.sp,
                    color = if (info.isJwt) semantic.onSuccess else semantic.onWarning,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }

            // Token details
            InfoRow(localizedString("mobile.settings_token_type"), info.tokenType)
            InfoRow(localizedString("mobile.settings_token_id"), info.tokenIdShort)

            if (info.expiresAt != null) {
                val expiryColor = if (info.isExpired) semantic.error else semantic.success
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = localizedString("mobile.settings_expires"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                    Text(
                        text = if (info.isExpired) "EXPIRED" else info.expiresAt,
                        style = MaterialTheme.typography.bodySmall,
                        color = expiryColor,
                        fontWeight = if (info.isExpired) FontWeight.Bold else FontWeight.Normal
                    )
                }
            }

            info.issuer?.let { issuer ->
                InfoRow(localizedString("mobile.settings_issuer"), issuer)
            }

            // Warning for expired tokens
            if (info.isExpired || info.hasSigningKeyIssue) {
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = semantic.surfaceError,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = if (info.hasSigningKeyIssue)
                                localizedString("mobile.settings_token_key_rotated")
                            else
                                localizedString("mobile.settings_token_expired"),
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp,
                            color = semantic.error
                        )
                        Text(
                            text = if (info.hasSigningKeyIssue)
                                localizedString("mobile.settings_token_key_rotated_desc")
                            else
                                localizedString("mobile.settings_token_expired_desc"),
                            fontSize = 11.sp,
                            color = semantic.onError
                        )
                    }
                }
            }
        } else {
            Text(
                text = localizedString("mobile.settings_no_token"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error
            )
        }
    }
}

// ============================================================================
// Helper Types and Functions
// ============================================================================

private data class TokenDisplayInfo(
    val tokenType: String,
    val tokenIdShort: String,
    val isJwt: Boolean,
    val expiresAt: String?,
    val isExpired: Boolean,
    val issuer: String?,
    val hasSigningKeyIssue: Boolean
)

private fun parseTokenForDisplay(token: String): TokenDisplayInfo {
    val parts = token.split(".")
    val isJwt = parts.size == 3

    if (!isJwt) {
        val prefix = if (token.startsWith("ciris_")) "CIRIS" else "Unknown"
        return TokenDisplayInfo(
            tokenType = "$prefix Access Token",
            tokenIdShort = "${token.take(10)}...${token.takeLast(4)}",
            isJwt = false,
            expiresAt = null,
            isExpired = false,
            issuer = "CIRIS",
            hasSigningKeyIssue = false
        )
    }

    try {
        val payloadBase64 = parts[1]
        val paddedPayload = when (payloadBase64.length % 4) {
            2 -> payloadBase64 + "=="
            3 -> payloadBase64 + "="
            else -> payloadBase64
        }

        @OptIn(kotlin.io.encoding.ExperimentalEncodingApi::class)
        val payloadJson = try {
            val bytes = kotlin.io.encoding.Base64.UrlSafe.decode(paddedPayload)
            bytes.decodeToString()
        } catch (e: Exception) {
            "{}"
        }

        val expMatch = Regex(""""exp"\s*:\s*(\d+)""").find(payloadJson)
        val issMatch = Regex(""""iss"\s*:\s*"([^"]+)"""").find(payloadJson)

        val expTimestamp = expMatch?.groupValues?.get(1)?.toLongOrNull()
        val issuer = issMatch?.groupValues?.get(1)

        val now = kotlinx.datetime.Clock.System.now().epochSeconds
        val isExpired = expTimestamp != null && expTimestamp < now

        val expiresAt = expTimestamp?.let {
            val remaining = it - now
            when {
                remaining < 0 -> "Expired ${-remaining / 60}m ago"
                remaining < 60 -> "${remaining}s"
                remaining < 3600 -> "${remaining / 60}m"
                remaining < 86400 -> "${remaining / 3600}h"
                else -> "${remaining / 86400}d"
            }
        }

        return TokenDisplayInfo(
            tokenType = when {
                issuer?.contains("google") == true -> "Google ID Token"
                issuer?.contains("ciris") == true -> "CIRIS JWT"
                else -> "JWT Token"
            },
            tokenIdShort = "${token.take(20)}...${token.takeLast(10)}",
            isJwt = true,
            expiresAt = expiresAt,
            isExpired = isExpired,
            issuer = issuer?.let {
                when {
                    it.contains("google") -> "Google"
                    it.contains("ciris") -> "CIRIS"
                    else -> it.take(20)
                }
            },
            hasSigningKeyIssue = false
        )
    } catch (e: Exception) {
        return TokenDisplayInfo(
            tokenType = "JWT Token",
            tokenIdShort = "${token.take(20)}...",
            isJwt = true,
            expiresAt = null,
            isExpired = false,
            issuer = null,
            hasSigningKeyIssue = false
        )
    }
}
