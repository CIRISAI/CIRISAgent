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
import ai.ciris.mobile.shared.viewmodels.LlmAdapterItem
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import kotlinx.coroutines.launch
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
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
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
    val adaptersExpanded by llmViewModel.adaptersExpanded.collectAsState()
    val providersExpanded by llmViewModel.providersExpanded.collectAsState()
    val addProviderExpanded by llmViewModel.addProviderExpanded.collectAsState()
    val localServersExpanded by llmViewModel.localServersExpanded.collectAsState()
    val advancedExpanded by llmViewModel.advancedExpanded.collectAsState()
    var authExpanded by remember { mutableStateOf(false) }

    // LLM-capable adapters
    val llmAdapters by llmViewModel.llmAdapters.collectAsState()

    // Provider delete confirmation
    val providerPendingDelete by llmViewModel.providerPendingDelete.collectAsState()

    // Operation state
    val operationInProgress by llmViewModel.operationInProgress.collectAsState()

    // CIRIS Services state
    val cirisServicesEnabled by llmViewModel.cirisServicesEnabled.collectAsState()

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
        llmViewModel.loadStatus()  // Refresh LLM Bus status and providers
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

    // Confirmation dialog for deleting system providers
    if (providerPendingDelete != null) {
        AlertDialog(
            onDismissRequest = { llmViewModel.cancelDeleteProvider() },
            icon = { Icon(CIRISIcons.warning, contentDescription = null) },
            title = { Text("Delete System Provider?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("\"${providerPendingDelete}\" is a CIRIS-managed provider.")
                    Text(
                        "Deleting it will disable CIRIS proxy functionality until you re-run the setup wizard.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = { llmViewModel.confirmDeleteProvider() },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Delete Anyway")
                }
            },
            dismissButton = {
                TextButton(onClick = { llmViewModel.cancelDeleteProvider() }) {
                    Text("Cancel")
                }
            }
        )
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
                            imageVector = CIRISIcons.arrowBack,
                            contentDescription = localizedString("mobile.settings_back")
                        )
                    }
                },
                actions = {
                    // Show loading indicator when operation in progress
                    if (operationInProgress) {
                        CircularProgressIndicator(
                            modifier = Modifier
                                .padding(end = 8.dp)
                                .size(20.dp),
                            strokeWidth = 2.dp
                        )
                    }
                    IconButton(
                        onClick = {
                            viewModel.refresh()
                            llmViewModel.loadStatus()
                        },
                        modifier = Modifier.testableClickable("btn_refresh") { viewModel.refresh() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
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

                // Section 2: Adapters (Collapsible)
                CollapsibleSection(
                    title = "Adapters",
                    subtitle = "${llmAdapters.size} loaded",
                    icon = CIRISMaterialIcons.Filled.Extension,
                    expanded = adaptersExpanded,
                    onToggle = { llmViewModel.toggleAdaptersExpanded() }
                ) {
                    AdaptersContent(
                        adapters = llmAdapters,
                        llmViewModel = llmViewModel,
                        operationInProgress = operationInProgress
                    )
                }

                // Section 3: Providers (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_providers"),
                    subtitle = localizedString("mobile.llm_settings_providers_count", "count", llmProviders.size.toString()),
                    icon = CIRISIcons.settings,
                    expanded = providersExpanded,
                    onToggle = { llmViewModel.toggleProvidersExpanded() }
                ) {
                    // Show registered providers with full CRUD
                    RegisteredProvidersContent(
                        isCirisProxy = isCirisProxy,
                        llmProviders = llmProviders,
                        llmViewModel = llmViewModel,
                        apiClient = apiClient,
                        availableProviders = viewModel.availableProviders,
                        cirisServicesEnabled = cirisServicesEnabled
                    )
                }

                // Section 4: Add Provider (Collapsible)
                CollapsibleSection(
                    title = "Add Provider",
                    subtitle = when {
                        discoveredServers.isNotEmpty() -> "${discoveredServers.size} server${if (discoveredServers.size > 1) "s" else ""} found"
                        localInferenceCapability.isReady -> "On-device available"
                        else -> "Local, Server, or Cloud"
                    },
                    icon = CIRISIcons.add,
                    expanded = addProviderExpanded,
                    onToggle = { llmViewModel.toggleAddProviderExpanded() }
                ) {
                    AddProviderContent(
                        viewModel = viewModel,
                        llmViewModel = llmViewModel,
                        apiClient = apiClient,
                        discoveredServers = discoveredServers,
                        selectedServer = selectedServer,
                        isDiscovering = isDiscovering,
                        localInferenceCapability = localInferenceCapability,
                        discoveryState = discoveryState,
                        availableProviders = viewModel.availableProviders,
                        onEditingChange = { isEditing = it }
                    )
                }

                // Section 5: Advanced Settings (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_advanced"),
                    subtitle = llmBusStatus?.distributionStrategyLabel ?: localizedString("mobile.llm_distribution_latency"),
                    icon = CIRISMaterialIcons.Filled.Tune,
                    expanded = advancedExpanded,
                    onToggle = { llmViewModel.toggleAdvancedExpanded() }
                ) {
                    AdvancedSettingsContent(
                        llmViewModel = llmViewModel,
                        llmBusStatus = llmBusStatus,
                        llmProviders = llmProviders
                    )
                }

                // Section 6: Authentication (Collapsible)
                CollapsibleSection(
                    title = localizedString("mobile.llm_settings_auth"),
                    subtitle = localizedString("mobile.settings_ciris_access_token"),
                    icon = CIRISIcons.person,
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
                    imageVector = CIRISMaterialIcons.Filled.Analytics,
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
                    value = llmBusStatus?.let { "${((it.errorRate * 1000).toInt() / 10.0)}%" } ?: "-",
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
                            imageVector = if (allHealthy) CIRISIcons.checkCircle else CIRISIcons.warning,
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
// Section 2: Adapters Content
// ============================================================================

/**
 * Shows LLM-capable adapters with reload/remove CRUD operations.
 */
@Composable
private fun AdaptersContent(
    adapters: List<LlmAdapterItem>,
    llmViewModel: LLMSettingsViewModel,
    operationInProgress: Boolean
) {
    val semantic = SemanticColors.Default

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (adapters.isEmpty()) {
            Text(
                text = "No LLM-capable adapters loaded",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        } else {
            adapters.forEach { adapter ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = if (adapter.isRunning)
                            MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                        else
                            semantic.surfaceError.copy(alpha = 0.3f)
                    ),
                    border = BorderStroke(
                        1.dp,
                        if (adapter.isRunning)
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.3f)
                        else
                            semantic.error.copy(alpha = 0.3f)
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(12.dp),
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
                                Icon(
                                    imageVector = if (adapter.isRunning) CIRISIcons.checkCircle else CIRISMaterialIcons.Filled.Error,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp),
                                    tint = if (adapter.isRunning) semantic.success else semantic.error
                                )
                                Column {
                                    Text(
                                        text = adapter.adapterId,
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Medium
                                    )
                                    Text(
                                        text = adapter.description,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                    )
                                }
                            }

                            // Status badge
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = if (adapter.isRunning)
                                    semantic.surfaceSuccess
                                else
                                    semantic.surfaceError
                            ) {
                                Text(
                                    text = if (adapter.isRunning) "Running" else "Stopped",
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = if (adapter.isRunning) semantic.onSuccess else semantic.onError,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }

                        // Adapter type chip
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = MaterialTheme.colorScheme.surfaceVariant
                        ) {
                            Text(
                                text = adapter.adapterType,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }

                        // Action buttons
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedButton(
                                onClick = { llmViewModel.reloadAdapter(adapter.adapterId) },
                                enabled = !operationInProgress,
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                            ) {
                                Icon(
                                    imageVector = CIRISIcons.refresh,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(Modifier.width(4.dp))
                                Text("Reload", fontSize = 12.sp)
                            }

                            // Only show Remove for non-essential adapters
                            if (adapter.adapterType !in listOf("api")) {
                                OutlinedButton(
                                    onClick = { llmViewModel.removeAdapter(adapter.adapterId) },
                                    enabled = !operationInProgress,
                                    colors = ButtonDefaults.outlinedButtonColors(
                                        contentColor = semantic.error
                                    ),
                                    modifier = Modifier.weight(1f),
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    Icon(
                                        imageVector = CIRISIcons.delete,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(Modifier.width(4.dp))
                                    Text("Remove", fontSize = 12.sp)
                                }
                            }
                        }
                    }
                }
            }
        }

        // Note about adapters vs providers
        Text(
            text = "Adapters register providers. Remove an adapter to remove all providers it registered.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
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
                    imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
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
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    availableProviders: List<Pair<String, String>>,
    cirisServicesEnabled: Boolean = true
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
                    imageVector = CIRISIcons.check,
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
                                imageVector = if (provider.healthy) CIRISIcons.checkCircle else CIRISMaterialIcons.Filled.Error,
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
                                        text = "${metrics.totalRequests} requests - ${metrics.averageLatencyMs.toInt()}ms avg",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                                    )
                                }
                            }
                        }

                        // Delete button for all providers
                        // System providers (ciris_primary, local_primary) show confirmation dialog
                        IconButton(
                            onClick = { llmViewModel.requestDeleteProvider(provider.name) },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = CIRISIcons.delete,
                                contentDescription = "Remove provider",
                                tint = semantic.error,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                    }
                }
            }
        }

        // CIRIS Services Toggle Card
        if (isCirisProxy) {
            Spacer(Modifier.height(12.dp))
            CirisServicesCard(
                enabled = cirisServicesEnabled,
                onDisable = { llmViewModel.disableCirisServices() },
                onReenableInfo = { llmViewModel.showCirisServicesReenableInfo() }
            )
        }
    }
}

/**
 * Card for toggling CIRIS services on/off.
 */
@Composable
private fun CirisServicesCard(
    enabled: Boolean,
    onDisable: () -> Unit,
    onReenableInfo: () -> Unit
) {
    val semantic = SemanticColors.Default

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (enabled)
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            else
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        ),
        border = BorderStroke(
            1.dp,
            if (enabled) MaterialTheme.colorScheme.primary.copy(alpha = 0.3f)
            else MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = if (enabled) CIRISIcons.checkCircle else CIRISMaterialIcons.Filled.Cancel,
                    contentDescription = null,
                    tint = if (enabled) semantic.success else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = "CIRIS Services",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium
                )
            }

            Text(
                text = if (enabled)
                    "Using CIRIS proxy for LLM requests"
                else
                    "CIRIS services are disabled. Using BYOK providers only.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            if (enabled) {
                Text(
                    text = "Disable to use only your own API keys. Both CIRIS providers will be removed.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )

                OutlinedButton(
                    onClick = onDisable,
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        imageVector = CIRISMaterialIcons.Filled.PowerOff,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("Disable CIRIS Services")
                }
            } else {
                OutlinedButton(
                    onClick = onReenableInfo,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        imageVector = CIRISIcons.info,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("How to Re-enable")
                }
            }
        }
    }
}

/**
 * Card for adding a new cloud provider.
 * Fetches available models from the provider's API after key entry.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddProviderCard(
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    availableProviders: List<Pair<String, String>>
) {
    var isExpanded by remember { mutableStateOf(false) }
    var selectedProvider by remember { mutableStateOf("openai") }
    var apiKey by remember { mutableStateOf("") }
    var showApiKey by remember { mutableStateOf(false) }

    // Model fetching state
    var isFetchingModels by remember { mutableStateOf(false) }
    var fetchedModels by remember { mutableStateOf<List<ai.ciris.mobile.shared.viewmodels.ModelInfo>>(emptyList()) }
    var selectedModel by remember { mutableStateOf<String?>(null) }
    var fetchError by remember { mutableStateOf<String?>(null) }

    val coroutineScope = rememberCoroutineScope()

    // Filter to cloud providers that need API keys (exclude local/mobile/other)
    val cloudProviders = availableProviders.filter { (id, _) ->
        id !in listOf("mobile_local", "local_inference", "local", "openai_compatible", "other")
    }

    // Reset models when provider changes
    LaunchedEffect(selectedProvider) {
        fetchedModels = emptyList()
        selectedModel = null
        fetchError = null
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_add_provider"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        ),
        onClick = { isExpanded = !isExpanded }
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = CIRISIcons.add,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(24.dp)
                    )
                    Text(
                        text = "Add Cloud Provider",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium
                    )
                }
                Icon(
                    imageVector = if (isExpanded) CIRISMaterialIcons.Filled.ExpandLess else CIRISMaterialIcons.Filled.ExpandMore,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (isExpanded) {
                Spacer(Modifier.height(16.dp))

                // Provider dropdown
                var dropdownExpanded by remember { mutableStateOf(false) }
                ExposedDropdownMenuBox(
                    expanded = dropdownExpanded,
                    onExpandedChange = { dropdownExpanded = it }
                ) {
                    OutlinedTextField(
                        value = cloudProviders.find { it.first == selectedProvider }?.second ?: selectedProvider,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Provider") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = dropdownExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                            .testable("input_add_provider_type")
                    )
                    ExposedDropdownMenu(
                        expanded = dropdownExpanded,
                        onDismissRequest = { dropdownExpanded = false }
                    ) {
                        cloudProviders.forEach { (id, name) ->
                            DropdownMenuItem(
                                text = { Text(name) },
                                onClick = {
                                    selectedProvider = id
                                    dropdownExpanded = false
                                },
                                modifier = Modifier.testable("menu_provider_$id")
                            )
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))

                // API Key input
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = {
                        apiKey = it
                        // Clear models when key changes
                        fetchedModels = emptyList()
                        selectedModel = null
                        fetchError = null
                    },
                    label = { Text("API Key") },
                    placeholder = { Text("sk-...") },
                    visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        IconButton(onClick = { showApiKey = !showApiKey }) {
                            Icon(
                                imageVector = if (showApiKey) CIRISMaterialIcons.Filled.VisibilityOff else CIRISMaterialIcons.Filled.Visibility,
                                contentDescription = if (showApiKey) "Hide" else "Show"
                            )
                        }
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_add_provider_api_key")
                )

                Spacer(Modifier.height(8.dp))

                // Fetch Models button - show when key is entered but models not yet fetched
                if (apiKey.isNotBlank() && fetchedModels.isEmpty() && !isFetchingModels) {
                    OutlinedButton(
                        onClick = {
                            isFetchingModels = true
                            fetchError = null
                            coroutineScope.launch {
                                try {
                                    val models = apiClient.listModels(
                                        provider = selectedProvider,
                                        apiKey = apiKey,
                                        baseUrl = null
                                    )
                                    fetchedModels = models
                                    // Auto-select recommended or first model
                                    if (models.isNotEmpty()) {
                                        val best = models.firstOrNull { it.cirisRecommended }
                                            ?: models.firstOrNull { it.cirisCompatible }
                                            ?: models.first()
                                        selectedModel = best.id
                                    }
                                } catch (e: Exception) {
                                    fetchError = e.message ?: "Failed to fetch models"
                                } finally {
                                    isFetchingModels = false
                                }
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testable("btn_fetch_models")
                    ) {
                        Icon(
                            imageVector = CIRISIcons.search,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("Fetch Available Models")
                    }
                }

                // Loading indicator
                if (isFetchingModels) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            strokeWidth = 2.dp
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("Fetching models...", style = MaterialTheme.typography.bodySmall)
                    }
                }

                // Error message
                fetchError?.let { error ->
                    Text(
                        text = error,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(vertical = 4.dp)
                    )
                }

                // Model dropdown - show when models are fetched
                if (fetchedModels.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))

                    var modelDropdownExpanded by remember { mutableStateOf(false) }
                    val displayModel = fetchedModels.find { it.id == selectedModel }

                    ExposedDropdownMenuBox(
                        expanded = modelDropdownExpanded,
                        onExpandedChange = { modelDropdownExpanded = it }
                    ) {
                        OutlinedTextField(
                            value = displayModel?.displayName ?: selectedModel ?: "Select a model",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Model") },
                            trailingIcon = {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    if (displayModel?.cirisRecommended == true) {
                                        Icon(CIRISIcons.star, contentDescription = "Recommended", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
                                    }
                                    ExposedDropdownMenuDefaults.TrailingIcon(expanded = modelDropdownExpanded)
                                }
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor()
                                .testable("input_add_provider_model")
                        )
                        ExposedDropdownMenu(
                            expanded = modelDropdownExpanded,
                            onDismissRequest = { modelDropdownExpanded = false }
                        ) {
                            // Sort: recommended first, then compatible, then others
                            val sortedModels = fetchedModels.sortedByDescending {
                                when {
                                    it.cirisRecommended -> 2
                                    it.cirisCompatible -> 1
                                    else -> 0
                                }
                            }
                            sortedModels.forEach { model ->
                                DropdownMenuItem(
                                    text = {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Column(modifier = Modifier.weight(1f)) {
                                                Text(
                                                    text = model.displayName,
                                                    fontWeight = if (model.cirisRecommended) FontWeight.Bold else FontWeight.Normal
                                                )
                                                model.contextWindow?.let { ctx ->
                                                    Text(
                                                        text = "${ctx / 1000}K context",
                                                        style = MaterialTheme.typography.bodySmall,
                                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                                    )
                                                }
                                            }
                                            if (model.cirisRecommended) {
                                                Surface(
                                                    shape = RoundedCornerShape(4.dp),
                                                    color = MaterialTheme.colorScheme.primaryContainer
                                                ) {
                                                    Text(
                                                        "[*] Best",
                                                        style = MaterialTheme.typography.labelSmall,
                                                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                                    )
                                                }
                                            } else if (model.cirisCompatible) {
                                                Surface(
                                                    shape = RoundedCornerShape(4.dp),
                                                    color = MaterialTheme.colorScheme.tertiaryContainer
                                                ) {
                                                    Text(
                                                        "Compatible",
                                                        style = MaterialTheme.typography.labelSmall,
                                                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                                    )
                                                }
                                            }
                                        }
                                    },
                                    onClick = {
                                        selectedModel = model.id
                                        modelDropdownExpanded = false
                                    },
                                    modifier = Modifier.testable("menu_model_${model.id.replace("/", "_").replace(":", "_")}")
                                )
                            }
                        }
                    }

                    Text(
                        text = "[*] = Recommended for CIRIS",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }

                Spacer(Modifier.height(12.dp))

                // Add button - enabled when key is provided and (models fetched with selection OR no models needed)
                val canAdd = apiKey.isNotBlank() && (fetchedModels.isEmpty() || selectedModel != null)
                Button(
                    onClick = {
                        if (apiKey.isNotBlank()) {
                            llmViewModel.addCloudProvider(selectedProvider, apiKey, model = selectedModel)
                            apiKey = ""
                            fetchedModels = emptyList()
                            selectedModel = null
                            isExpanded = false
                        }
                    },
                    enabled = canAdd && !isFetchingModels,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("btn_add_provider_submit")
                ) {
                    Icon(
                        imageVector = CIRISIcons.add,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(if (fetchedModels.isEmpty()) "Add Provider" else "Add Provider with Model")
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
                imageVector = CIRISIcons.check,
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
                    imageVector = if (isActive) CIRISMaterialIcons.Filled.Circle else CIRISMaterialIcons.Filled.RadioButtonUnchecked,
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
                    imageVector = CIRISMaterialIcons.Filled.Speed,
                    contentDescription = "Active",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}

// ============================================================================
// Section 4: Add Provider Content (3 Cards)
// ============================================================================

/**
 * Combined Add Provider section with 3 cards:
 * 1. Local (On-Device) - For devices capable of local inference
 * 2. Server (Network Discovery) - Find LLM servers on LAN
 * 3. Cloud (API Key) - Add cloud provider with API key
 */
@Composable
private fun AddProviderContent(
    viewModel: SettingsViewModel,
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    discoveredServers: List<DiscoveredLlmServer>,
    selectedServer: DiscoveredLlmServer?,
    isDiscovering: Boolean,
    localInferenceCapability: LocalInferenceCapability,
    discoveryState: ai.ciris.mobile.shared.ui.components.LocalLlmDiscoveryState,
    availableProviders: List<Pair<String, String>>,
    onEditingChange: (Boolean) -> Unit
) {
    val semantic = SemanticColors.Default

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        // Card 1: Local (On-Device)
        AddProviderCardLocal(
            localInferenceCapability = localInferenceCapability,
            discoveryState = discoveryState,
            apiClient = apiClient,
            llmViewModel = llmViewModel
        )

        // Card 2: Server (Network Discovery)
        AddProviderCardServer(
            viewModel = viewModel,
            llmViewModel = llmViewModel,
            apiClient = apiClient,
            discoveredServers = discoveredServers,
            isDiscovering = isDiscovering,
            localInferenceCapability = localInferenceCapability,
            discoveryState = discoveryState,
            onEditingChange = onEditingChange
        )

        // Card 3: Cloud (API Key)
        AddProviderCard(
            llmViewModel = llmViewModel,
            apiClient = apiClient,
            availableProviders = availableProviders
        )
    }
}

/**
 * Card for adding on-device local inference.
 */
@Composable
private fun AddProviderCardLocal(
    localInferenceCapability: LocalInferenceCapability,
    discoveryState: ai.ciris.mobile.shared.ui.components.LocalLlmDiscoveryState,
    apiClient: CIRISApiClient,
    llmViewModel: LLMSettingsViewModel
) {
    val semantic = SemanticColors.Default

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = CIRISMaterialIcons.Filled.PhoneAndroid,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp)
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Local (On-Device)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = "Run inference directly on this device",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
            }

            if (localInferenceCapability.isReady) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = semantic.surfaceSuccess.copy(alpha = 0.3f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = CIRISIcons.checkCircle,
                            contentDescription = null,
                            tint = semantic.success,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = "Device capable",
                            style = MaterialTheme.typography.labelMedium,
                            color = semantic.success
                        )
                    }
                }

                Text(
                    text = localInferenceCapability.reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                )
                // On-device server start is handled by LocalLlmServerDiscovery below
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
                            imageVector = CIRISMaterialIcons.Filled.Schedule,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.tertiary,
                            modifier = Modifier.size(16.dp)
                        )
                        Column {
                            Text(
                                text = "Coming Soon",
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
            } else {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = CIRISIcons.info,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = "Requires 64-bit Android with 6GB+ RAM",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Card for discovering LLM servers on the network.
 */
@Composable
private fun AddProviderCardServer(
    viewModel: SettingsViewModel,
    llmViewModel: LLMSettingsViewModel,
    apiClient: CIRISApiClient,
    discoveredServers: List<DiscoveredLlmServer>,
    isDiscovering: Boolean,
    localInferenceCapability: LocalInferenceCapability,
    discoveryState: ai.ciris.mobile.shared.ui.components.LocalLlmDiscoveryState,
    onEditingChange: (Boolean) -> Unit
) {
    val semantic = SemanticColors.Default

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = CIRISMaterialIcons.Filled.Wifi,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp)
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Server (Network Discovery)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = "Find LLM servers on your local network",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
            }

            Text(
                text = "Supports Ollama, llama.cpp, vLLM, LM Studio",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )

            // Use LocalLlmServerDiscovery for network servers
            LocalLlmServerDiscovery(
                state = discoveryState,
                apiClient = apiClient,
                localInferenceCapability = localInferenceCapability,
                onServerSelected = { server ->
                    viewModel.selectServer(server)
                    onEditingChange(true)
                },
                onAddAsProvider = { server, selectedModel ->
                    llmViewModel.addDiscoveredServerAsProvider(server, selectedModel = selectedModel)
                },
                primaryColor = MaterialTheme.colorScheme.primary,
                surfaceColor = MaterialTheme.colorScheme.surfaceVariant,
                textColor = MaterialTheme.colorScheme.onSurface,
                secondaryTextColor = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// ============================================================================
// Local Servers Content (Legacy - kept for reference)
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
                        imageVector = CIRISIcons.checkCircle,
                        contentDescription = null,
                        tint = SemanticColors.Default.success,
                        modifier = Modifier.size(20.dp)
                    )
                    Column(modifier = Modifier.weight(1f)) {
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
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = localizedString("mobile.llm_local_inference_performance_warning"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                            fontSize = 11.sp,
                            fontStyle = androidx.compose.ui.text.font.FontStyle.Italic
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
                        imageVector = CIRISMaterialIcons.Filled.Schedule,
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
            onAddAsProvider = { server, selectedModel ->
                // Add the discovered server as a provider to the LLM Bus
                llmViewModel.addDiscoveredServerAsProvider(server, selectedModel = selectedModel)
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

        HorizontalDivider(
            modifier = Modifier.padding(vertical = 8.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
        )

        // CIRIS Services Toggle (Danger Zone)
        CirisServicesToggle(llmViewModel = llmViewModel)
    }
}

/**
 * Toggle to disable CIRIS services (switch to BYOK mode).
 * Shows a warning that re-enabling requires re-running the setup wizard.
 */
@Composable
private fun CirisServicesToggle(llmViewModel: LLMSettingsViewModel) {
    val semantic = SemanticColors.Default
    var showDisableDialog by remember { mutableStateOf(false) }
    val isCirisServicesEnabled by llmViewModel.cirisServicesEnabled.collectAsState()

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_ciris_services"),
        colors = CardDefaults.cardColors(
            containerColor = semantic.surfaceError.copy(alpha = 0.1f)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "CIRIS Services",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = if (isCirisServicesEnabled) "Using CIRIS proxy for LLM requests"
                               else "Disabled - using your own API keys",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
                Switch(
                    checked = isCirisServicesEnabled,
                    onCheckedChange = { enabled ->
                        if (!enabled) {
                            showDisableDialog = true
                        } else {
                            // Re-enabling requires wizard - just show info
                            llmViewModel.showCirisServicesReenableInfo()
                        }
                    },
                    modifier = Modifier.testable("switch_ciris_services")
                )
            }

            if (!isCirisServicesEnabled) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = CIRISIcons.warning,
                        contentDescription = null,
                        tint = semantic.warning,
                        modifier = Modifier.size(14.dp)
                    )
                    Text(
                        text = "Re-enabling requires re-running the setup wizard",
                        style = MaterialTheme.typography.labelSmall,
                        color = semantic.warning
                    )
                }
            }
        }
    }

    // Confirmation dialog for disabling
    if (showDisableDialog) {
        AlertDialog(
            onDismissRequest = { showDisableDialog = false },
            icon = {
                Icon(
                    imageVector = CIRISIcons.warning,
                    contentDescription = null,
                    tint = semantic.warning,
                    modifier = Modifier.size(32.dp)
                )
            },
            title = { Text("Disable CIRIS Services?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("This will switch you to BYOK (Bring Your Own Key) mode.")
                    Text("You'll need to provide your own API keys for OpenAI, Anthropic, or other providers.")
                    Text(
                        text = "To re-enable CIRIS services later, you'll need to re-run the setup wizard.",
                        fontWeight = FontWeight.Medium
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        llmViewModel.disableCirisServices()
                        showDisableDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = semantic.error
                    ),
                    modifier = Modifier.testable("btn_confirm_disable_ciris")
                ) {
                    Text("Disable")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showDisableDialog = false },
                    modifier = Modifier.testable("btn_cancel_disable_ciris")
                ) {
                    Text("Cancel")
                }
            }
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
                        ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED -> CIRISIcons.checkCircle
                        ai.ciris.mobile.shared.models.CircuitBreakerState.OPEN -> CIRISMaterialIcons.Filled.Error
                        ai.ciris.mobile.shared.models.CircuitBreakerState.HALF_OPEN -> CIRISMaterialIcons.Filled.Schedule
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
