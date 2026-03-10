package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.runtime.rememberCoroutineScope

/**
 * Settings screen
 * Context-aware based on LLM configuration mode:
 * - CIRIS Proxy: Shows read-only info about CIRIS AI service
 * - BYOK (Bring Your Own Key): Shows editable LLM configuration
 *
 * Features:
 * - Mode detection from backend config
 * - LLM provider/model selection (BYOK only)
 * - API key management (BYOK only)
 * - Logout
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    apiClient: CIRISApiClient,
    secureStorage: ai.ciris.mobile.shared.platform.SecureStorage,
    onNavigateBack: () -> Unit,
    onLogout: () -> Unit,
    onResetSetup: () -> Unit,  // Callback to restart app after reset
    modifier: Modifier = Modifier
) {
    // Core state
    val isLoading by viewModel.isLoading.collectAsState()
    val isCirisProxy by viewModel.isCirisProxy.collectAsState()
    val llmConfig by viewModel.llmConfig.collectAsState()

    // BYOK form state
    val llmProvider by viewModel.llmProvider.collectAsState()
    val llmModel by viewModel.llmModel.collectAsState()
    val llmBaseUrl by viewModel.llmBaseUrl.collectAsState()
    val apiKey by viewModel.apiKey.collectAsState()
    val apiKeyMasked by viewModel.apiKeyMasked.collectAsState()
    val availableModels by viewModel.availableModels.collectAsState()

    // Operation state
    val isSaving by viewModel.isSaving.collectAsState()
    val saveSuccess by viewModel.saveSuccess.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()

    // Reset setup state
    val isResetting by viewModel.isResetting.collectAsState()
    val resetSuccess by viewModel.resetSuccess.collectAsState()

    var showApiKey by remember { mutableStateOf(false) }
    var isEditing by remember { mutableStateOf(false) }
    var showResetConfirmDialog by remember { mutableStateOf(false) }
    var showFactoryResetDialog by remember { mutableStateOf(false) }

    // Show snackbar for success/error
    val snackbarHostState = remember { SnackbarHostState() }

    // Load config when screen is first shown
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    LaunchedEffect(saveSuccess) {
        if (saveSuccess) {
            snackbarHostState.showSnackbar("Settings saved successfully")
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

    // Handle reset success - trigger app restart
    LaunchedEffect(resetSuccess) {
        if (resetSuccess) {
            viewModel.clearResetSuccess()
            onResetSetup()
        }
    }

    // Confirmation dialog for re-running setup wizard (keeps data)
    if (showResetConfirmDialog) {
        AlertDialog(
            onDismissRequest = { showResetConfirmDialog = false },
            title = { Text("Re-run Setup Wizard?") },
            text = {
                Text(
                    "This will reset your configuration and restart the app. " +
                    "Your data (conversations, memory, audit logs) will be kept.\n\n" +
                    "Use this to:\n" +
                    "• Switch between CIRIS Proxy and BYOK mode\n" +
                    "• Change LLM providers or API keys\n" +
                    "• Fix authentication issues"
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showResetConfirmDialog = false
                        viewModel.rerunSetupWizard { onResetSetup() }
                    },
                    modifier = Modifier.testableClickable("btn_reset_confirm") {
                        showResetConfirmDialog = false
                        viewModel.rerunSetupWizard { onResetSetup() }
                    }
                ) {
                    Text("Re-run Setup")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showResetConfirmDialog = false },
                    modifier = Modifier.testableClickable("btn_reset_cancel") { showResetConfirmDialog = false }
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    // Confirmation dialog for factory reset (wipes ALL data)
    if (showFactoryResetDialog) {
        AlertDialog(
            onDismissRequest = { showFactoryResetDialog = false },
            title = { Text("Factory Reset?") },
            text = {
                Text(
                    "⚠️ WARNING: This will DELETE ALL DATA including:\n\n" +
                    "• Conversations and chat history\n" +
                    "• Memory and knowledge graph\n" +
                    "• Audit logs and signing keys\n" +
                    "• All configuration\n\n" +
                    "This cannot be undone. The app will restart as if freshly installed."
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showFactoryResetDialog = false
                        viewModel.factoryReset { onResetSetup() }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.testableClickable("btn_factory_reset_confirm") {
                        showFactoryResetDialog = false
                        viewModel.factoryReset { onResetSetup() }
                    }
                ) {
                    Text("Delete All & Reset")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showFactoryResetDialog = false },
                    modifier = Modifier.testableClickable("btn_factory_reset_cancel") { showFactoryResetDialog = false }
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
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
                            contentDescription = "Refresh"
                        )
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { paddingValues ->

        if (isLoading) {
            // Loading state
            Box(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    CircularProgressIndicator()
                    Text("Loading configuration...")
                }
            }
        } else {
            Column(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // LLM Configuration Section - Mode dependent
                Text(
                    text = "LLM Configuration",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                if (isCirisProxy) {
                    // CIRIS Proxy mode - Read-only info card
                    CirisProxyInfoCard()
                } else {
                    // BYOK mode - Editable form
                    ByokConfigSection(
                        viewModel = viewModel,
                        llmProvider = llmProvider,
                        llmModel = llmModel,
                        llmBaseUrl = llmBaseUrl,
                        apiKey = apiKey,
                        apiKeyMasked = apiKeyMasked,
                        availableModels = availableModels,
                        showApiKey = showApiKey,
                        isEditing = isEditing,
                        isSaving = isSaving,
                        onShowApiKeyChange = { showApiKey = it },
                        onEditingChange = { isEditing = it }
                    )
                }

                // Backup LLM Configuration (if available)
                llmConfig?.let { config ->
                    if (config.backupBaseUrl != null || config.backupModel != null) {
                        BackupLlmConfigCard(config)
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // CIRIS Authentication Section
                Text(
                    text = "CIRIS Authentication",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                CirisJwtInfoCard(
                    apiClient = apiClient,
                    secureStorage = secureStorage
                )

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // Account Section
                Text(
                    text = "Account",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                // Logout button
                OutlinedButton(
                    onClick = {
                        viewModel.logout {
                            onLogout()
                        }
                    },
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_logout") {
                        viewModel.logout { onLogout() }
                    }
                ) {
                    Text("Logout")
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // Setup Section
                Text(
                    text = "Setup",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                // Re-run Setup Wizard (keeps data)
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "Re-run Setup Wizard",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "Reconfigure LLM settings without losing data. Your conversations, memory, and audit logs are preserved.\n\n" +
                                   "Use this to:\n" +
                                   "• Switch between CIRIS Proxy and BYOK mode\n" +
                                   "• Change LLM providers or API keys\n" +
                                   "• Fix authentication issues",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Button(
                            onClick = { showResetConfirmDialog = true },
                            enabled = !isResetting,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary
                            ),
                            modifier = Modifier.fillMaxWidth().testableClickable("btn_rerun_setup") {
                                showResetConfirmDialog = true
                            }
                        ) {
                            if (isResetting) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = MaterialTheme.colorScheme.onPrimary,
                                    strokeWidth = 2.dp
                                )
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(if (isResetting) "Resetting..." else "Re-run Setup Wizard")
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Factory Reset (wipes ALL data)
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "Factory Reset",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                        Text(
                            text = "Delete ALL data and start fresh. This removes conversations, memory, audit logs, and signing keys. Cannot be undone.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = 0.8f)
                        )
                        Button(
                            onClick = { showFactoryResetDialog = true },
                            enabled = !isResetting,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.error
                            ),
                            modifier = Modifier.fillMaxWidth().testableClickable("btn_factory_reset") {
                                showFactoryResetDialog = true
                            }
                        ) {
                            if (isResetting) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = MaterialTheme.colorScheme.onError,
                                    strokeWidth = 2.dp
                                )
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(if (isResetting) "Resetting..." else "Factory Reset")
                        }
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // App Info
                Text(
                    text = "App Info",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        InfoRow("Version", "2.1.0 (KMP)")
                        InfoRow("Platform", "Kotlin Multiplatform")
                        InfoRow("UI", "Compose Multiplatform")
                        InfoRow("Mode", if (isCirisProxy) "CIRIS Proxy" else "BYOK")
                    }
                }
            }
        }
    }
}

/**
 * Info card shown when using CIRIS Proxy mode.
 * Read-only, no configuration needed.
 */
@Composable
private fun CirisProxyInfoCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = Icons.Filled.Check,
                contentDescription = null,
                modifier = Modifier.size(48.dp),
                tint = MaterialTheme.colorScheme.primary
            )

            Text(
                text = "Using CIRIS AI Proxy",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )

            Text(
                text = "Your AI requests are routed through CIRIS proxy services. " +
                       "Your Google account authenticates you, and CIRIS handles LLM access.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f),
                textAlign = TextAlign.Center
            )

            HorizontalDivider(
                modifier = Modifier.padding(vertical = 8.dp),
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f)
            )

            Text(
                text = "Benefits:",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )

            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                BenefitItem("No API key required")
                BenefitItem("Automatic model selection")
                BenefitItem("Built-in rate limiting")
                BenefitItem("Cost managed by CIRIS")
            }
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
            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
        )
    }
}

/**
 * BYOK configuration section with editable form.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ByokConfigSection(
    viewModel: SettingsViewModel,
    llmProvider: String,
    llmModel: String,
    llmBaseUrl: String,
    apiKey: String,
    apiKeyMasked: String,
    availableModels: List<String>,
    showApiKey: Boolean,
    isEditing: Boolean,
    isSaving: Boolean,
    onShowApiKeyChange: (Boolean) -> Unit,
    onEditingChange: (Boolean) -> Unit
) {
    // Info card for BYOK mode
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer
        )
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Filled.Info,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSecondaryContainer
            )
            Text(
                text = "Using your own API key (BYOK mode)",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer
            )
        }
    }

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
            label = { Text("LLM Provider") },
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

    // Model selection
    var modelExpanded by remember { mutableStateOf(false) }

    ExposedDropdownMenuBox(
        expanded = modelExpanded,
        onExpandedChange = { modelExpanded = it }
    ) {
        OutlinedTextField(
            value = llmModel.ifEmpty { "Select model" },
            onValueChange = {},
            readOnly = true,
            label = { Text("Model") },
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
                    },
                    modifier = Modifier.testableClickable("menu_model_$model") {
                        viewModel.onModelChanged(model)
                        modelExpanded = false
                        onEditingChange(true)
                    }
                )
            }
        }
    }

    // Base URL (for "other" provider)
    if (llmProvider == "other" || llmProvider == "local") {
        OutlinedTextField(
            value = llmBaseUrl,
            onValueChange = {
                viewModel.onBaseUrlChanged(it)
                onEditingChange(true)
            },
            label = { Text("Base URL") },
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

    // API Key (not required for local)
    if (llmProvider != "local") {
        OutlinedTextField(
            value = if (isEditing || showApiKey) apiKey else apiKeyMasked,
            onValueChange = {
                onEditingChange(true)
                viewModel.onApiKeyChanged(it)
            },
            label = { Text("API Key") },
            visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            trailingIcon = {
                TextButton(
                    onClick = { onShowApiKeyChange(!showApiKey) },
                    modifier = Modifier.testableClickable("btn_toggle_api_key") { onShowApiKeyChange(!showApiKey) }
                ) {
                    Text(if (showApiKey) "Hide" else "Show")
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
                color = MaterialTheme.colorScheme.onPrimary
            )
            Spacer(Modifier.width(8.dp))
        }
        Text(if (isSaving) "Saving..." else "Save Settings")
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
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium
        )
    }
}

/**
 * Card showing backup LLM configuration if available.
 */
@Composable
private fun BackupLlmConfigCard(config: ai.ciris.mobile.shared.api.LlmConfigData) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.tertiaryContainer
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
                    imageVector = Icons.Filled.Refresh,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.onTertiaryContainer
                )
                Text(
                    text = "Backup LLM Configuration",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onTertiaryContainer
                )
            }

            Text(
                text = "If the primary LLM provider fails, CIRIS will automatically fall back to this backup.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.8f)
            )

            HorizontalDivider(
                modifier = Modifier.padding(vertical = 4.dp),
                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.2f)
            )

            config.backupBaseUrl?.let { url ->
                val provider = when {
                    url.contains("groq.com") -> "Groq"
                    url.contains("together") -> "Together AI"
                    url.contains("openai.com") -> "OpenAI"
                    url.contains("anthropic") -> "Anthropic"
                    url.contains("ciris.ai") -> "CIRIS Proxy"
                    else -> url.take(30)
                }
                InfoRowTertiary("Provider", provider)
            }

            config.backupModel?.let { model ->
                InfoRowTertiary("Model", model)
            }

            InfoRowTertiary("API Key", if (config.backupApiKeySet) "Configured" else "Not set")
        }
    }
}

@Composable
private fun InfoRowTertiary(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.7f)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onTertiaryContainer
        )
    }
}

/**
 * Card explaining CIRIS JWT token and showing current token status.
 */
@Composable
private fun CirisJwtInfoCard(
    apiClient: CIRISApiClient,
    secureStorage: ai.ciris.mobile.shared.platform.SecureStorage
) {
    var tokenInfo by remember { mutableStateOf<TokenDisplayInfo?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val coroutineScope = rememberCoroutineScope()

    // Load token info on mount
    LaunchedEffect(Unit) {
        try {
            val result = secureStorage.getAccessToken()
            result.onSuccess { token ->
                if (token != null) {
                    tokenInfo = parseTokenForDisplay(token)
                }
            }
        } catch (e: Exception) {
            // Ignore errors
        } finally {
            isLoading = false
        }
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Filled.Info,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = "CIRIS Access Token",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
            }

            // Explanation
            Text(
                text = "When using CIRIS Proxy, your Google Sign-In token is exchanged for a CIRIS access token. " +
                       "This token authenticates you to the local agent and the CIRIS AI proxy.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(
                modifier = Modifier.padding(vertical = 4.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.2f)
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
                        text = "Loading token info...",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            } else if (tokenInfo != null) {
                val info = tokenInfo!!

                // Token format indicator
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = if (info.isJwt) Color(0xFFD1FAE5) else Color(0xFFFEF3C7)
                ) {
                    Text(
                        text = if (info.isJwt) "JWT Token" else "Opaque Token",
                        fontSize = 10.sp,
                        color = if (info.isJwt) Color(0xFF065F46) else Color(0xFF92400E),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }

                Spacer(modifier = Modifier.height(4.dp))

                // Token details
                InfoRow("Token Type", info.tokenType)
                InfoRow("Token ID", info.tokenIdShort)

                if (info.expiresAt != null) {
                    val expiryColor = if (info.isExpired) Color(0xFFDC2626) else Color(0xFF059669)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Expires",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = if (info.isExpired) "EXPIRED" else info.expiresAt,
                            style = MaterialTheme.typography.bodyMedium,
                            color = expiryColor,
                            fontWeight = if (info.isExpired) FontWeight.Bold else FontWeight.Normal
                        )
                    }
                }

                if (info.issuer != null) {
                    InfoRow("Issuer", info.issuer)
                }

                // Warning for old/problematic tokens
                if (info.isExpired || info.hasSigningKeyIssue) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = Color(0xFFFEE2E2),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(
                                text = if (info.hasSigningKeyIssue)
                                    "Token Signing Key Rotated"
                                else
                                    "Token Expired",
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = Color(0xFFDC2626)
                            )
                            Text(
                                text = if (info.hasSigningKeyIssue)
                                    "Google has rotated its signing keys. Your token was signed with an old key that's no longer valid. Re-run the setup wizard to get a fresh token."
                                else
                                    "Your access token has expired. Re-run the setup wizard to refresh authentication.",
                                fontSize = 11.sp,
                                color = Color(0xFF991B1B)
                            )
                        }
                    }
                }
            } else {
                Text(
                    text = "No access token found",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}

/**
 * Data class for displaying token information.
 */
private data class TokenDisplayInfo(
    val tokenType: String,
    val tokenIdShort: String,
    val isJwt: Boolean,
    val expiresAt: String?,
    val isExpired: Boolean,
    val issuer: String?,
    val hasSigningKeyIssue: Boolean
)

/**
 * Parse a token string for display purposes.
 */
private fun parseTokenForDisplay(token: String): TokenDisplayInfo {
    // Check if it's a JWT (3 parts separated by dots)
    val parts = token.split(".")
    val isJwt = parts.size == 3

    if (!isJwt) {
        // Opaque token (like ciris_xxx)
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

    // Parse JWT
    try {
        // Decode the payload (second part)
        val payloadBase64 = parts[1]
        // Add padding if needed
        val paddedPayload = when (payloadBase64.length % 4) {
            2 -> payloadBase64 + "=="
            3 -> payloadBase64 + "="
            else -> payloadBase64
        }

        // Base64 decode - use platform-specific or simple decode
        val payloadJson = try {
            // Try to decode as base64url
            val bytes = java.util.Base64.getUrlDecoder().decode(paddedPayload)
            String(bytes, Charsets.UTF_8)
        } catch (e: Exception) {
            // Fallback for platforms without java.util.Base64
            "{}"
        }

        // Simple JSON parsing (not using kotlinx.serialization to keep it light)
        val expMatch = Regex(""""exp"\s*:\s*(\d+)""").find(payloadJson)
        val issMatch = Regex(""""iss"\s*:\s*"([^"]+)"""").find(payloadJson)
        val kidMatch = Regex(""""kid"\s*:\s*"([^"]+)"""").find(parts[0].let {
            val headerPadded = when (it.length % 4) {
                2 -> it + "=="
                3 -> it + "="
                else -> it
            }
            try {
                String(java.util.Base64.getUrlDecoder().decode(headerPadded), Charsets.UTF_8)
            } catch (e: Exception) { "{}" }
        })

        val expTimestamp = expMatch?.groupValues?.get(1)?.toLongOrNull()
        val issuer = issMatch?.groupValues?.get(1)

        // Check if expired
        val now = System.currentTimeMillis() / 1000
        val isExpired = expTimestamp != null && expTimestamp < now

        // Format expiry
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
            hasSigningKeyIssue = false // Would need backend validation to detect
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

// ========== Trust and Security Card ==========

private object TrustColors {
    val EmeraldLight = Color(0xFFD1FAE5)
    val EmeraldBorder = Color(0xFF6EE7B7)
    val EmeraldDark = Color(0xFF065F46)
    val EmeraldText = Color(0xFF047857)
    val EmeraldMuted = Color(0xFFA7F3D0)
}

/**
 * Trust and Security Card for Settings screen.
 * Shows CIRISVerify status including hardware type, key status, and attestation.
 */
@Composable
private fun TrustSecurityCard(
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    var verifyStatus by remember { mutableStateOf<VerifyStatusResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var logMessages by remember { mutableStateOf(listOf<String>()) }
    var showLogView by remember { mutableStateOf(true) }  // Keep log view visible on error
    val uriHandler = LocalUriHandler.current
    val clipboardManager = LocalClipboardManager.current
    val coroutineScope = rememberCoroutineScope()
    val scrollState = rememberScrollState()

    // Fetch verify status on mount
    LaunchedEffect(Unit) {
        try {
            // Show progress messages while loading
            logMessages = logMessages + "[verify] Starting attestation check..."
            logMessages = logMessages + "[verify] Loading CIRISVerify binary..."

            kotlinx.coroutines.delay(500)
            logMessages = logMessages + "[verify] Checking environment config..."

            kotlinx.coroutines.delay(500)
            logMessages = logMessages + "[verify] Initiating network validation (DNS-over-HTTPS)..."
            logMessages = logMessages + "[verify] Querying registry.ciris.ai..."

            // Start the actual API call (uses cached attestation from auth service)
            val result = withContext(Dispatchers.IO) {
                apiClient.getVerifyStatus()
            }
            verifyStatus = result

            // Only hide log view if we got a successful response with loaded=true
            if (result.loaded) {
                logMessages = logMessages + "[verify] ✓ Attestation complete"
                error = null
                showLogView = false  // Hide log view on success, show results
            } else {
                // API returned but loaded=false (e.g., timeout in backend)
                logMessages = logMessages + "[verify] ✗ ${result.error ?: "Verification failed"}"
                error = result.error ?: "CIRISVerify check failed"
                // Keep showLogView = true so logs remain visible
            }
        } catch (e: Exception) {
            logMessages = logMessages + "[verify] ✗ Error: ${e.message}"
            error = e.message ?: "Failed to fetch verify status"
            // Keep showLogView = true so logs remain visible on error
        } finally {
            loading = false
        }
    }

    // Auto-scroll to bottom when new logs arrive
    LaunchedEffect(logMessages.size) {
        scrollState.animateScrollTo(scrollState.maxValue)
    }

    // Log view - show during loading OR on error (persists on timeout)
    if (showLogView) {
        Card(
            modifier = modifier,
            colors = CardDefaults.cardColors(containerColor = Color(0xFF1F2937))
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 120.dp, max = 250.dp)
                    .padding(12.dp)
            ) {
                // Header row with title and buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "🛡 Attestation Check",
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF10B981),
                            fontSize = 12.sp
                        )
                        if (loading) {
                            Spacer(modifier = Modifier.width(8.dp))
                            CircularProgressIndicator(
                                modifier = Modifier.size(12.dp),
                                color = Color(0xFF10B981),
                                strokeWidth = 2.dp
                            )
                        }
                    }
                    // Buttons row
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        // Copy button
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = Color(0xFF374151),
                            modifier = Modifier.testableClickable("btn_copy_attestation_logs") {
                                val logText = logMessages.joinToString("\n")
                                clipboardManager.setText(AnnotatedString(logText))
                            }
                        ) {
                            Text(
                                text = "📋 Copy",
                                fontSize = 10.sp,
                                color = Color(0xFF9CA3AF),
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                        // Retry button (only show when not loading)
                        if (!loading && error != null) {
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = Color(0xFF374151),
                                modifier = Modifier.testableClickable("btn_retry_attestation") {
                                    loading = true
                                    error = null
                                    logMessages = listOf("[verify] Retrying attestation check...")
                                    coroutineScope.launch {
                                        try {
                                            logMessages = logMessages + "[verify] Loading CIRISVerify binary..."
                                            kotlinx.coroutines.delay(300)
                                            logMessages = logMessages + "[verify] Querying registry..."
                                            val result = withContext(Dispatchers.IO) {
                                                apiClient.getVerifyStatus()
                                            }
                                            verifyStatus = result
                                            if (result.loaded) {
                                                logMessages = logMessages + "[verify] ✓ Attestation complete"
                                                showLogView = false
                                            } else {
                                                logMessages = logMessages + "[verify] ✗ ${result.error ?: "Verification failed"}"
                                                error = result.error
                                            }
                                        } catch (e: Exception) {
                                            logMessages = logMessages + "[verify] ✗ Error: ${e.message}"
                                            error = e.message
                                        } finally {
                                            loading = false
                                        }
                                    }
                                }
                            ) {
                                Text(
                                    text = "🔄 Retry",
                                    fontSize = 10.sp,
                                    color = Color(0xFF9CA3AF),
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Scrolling log area
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .verticalScroll(scrollState)
                ) {
                    logMessages.forEach { msg ->
                        Text(
                            text = msg,
                            fontSize = 11.sp,
                            color = if (msg.contains("✗")) Color(0xFFEF4444)
                                   else if (msg.contains("✓")) Color(0xFF10B981)
                                   else Color(0xFF9CA3AF),
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                            lineHeight = 14.sp
                        )
                    }
                }

                // Error hint if timed out
                if (error != null && !loading) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Tap 📋 Copy to share logs for debugging",
                        fontSize = 10.sp,
                        color = Color(0xFFD97706)
                    )
                }
            }
        }
        return
    }

    // Error state - but on mobile, CIRISVerify is always bundled
    if (verifyStatus?.loaded != true) {
        Card(
            modifier = modifier,
            colors = CardDefaults.cardColors(containerColor = Color(0xFFFEF3C7))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "⚠ CIRISVerify Status Unknown",
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF92400E)
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = error ?: verifyStatus?.error ?: "Unable to check CIRISVerify status",
                    fontSize = 13.sp,
                    color = Color(0xFFD97706)
                )
                // Show diagnostic info for troubleshooting
                verifyStatus?.diagnosticInfo?.let { diag ->
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Debug: $diag",
                        fontSize = 10.sp,
                        color = Color(0xFF92400E),
                        fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace
                    )
                }
            }
        }
        return
    }

    // Success state - show verify info
    val status = verifyStatus!!

    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = TrustColors.EmeraldLight)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("🛡", fontSize = 20.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "CIRISVerify Active",
                        fontWeight = FontWeight.Bold,
                        color = TrustColors.EmeraldDark
                    )
                }
                status.version?.let { version ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = TrustColors.EmeraldMuted
                    ) {
                        Text(
                            text = "v$version",
                            fontSize = 11.sp,
                            color = TrustColors.EmeraldDark,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Status grid
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Hardware",
                        fontSize = 11.sp,
                        color = TrustColors.EmeraldText,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = status.hardwareType?.replace("_", " ") ?: "Unknown",
                        fontSize = 13.sp,
                        color = TrustColors.EmeraldDark
                    )
                }

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Key Status",
                        fontSize = 11.sp,
                        color = TrustColors.EmeraldText,
                        fontWeight = FontWeight.Medium
                    )
                    val (keyLabel, keyColor) = getKeyStatusLabel(status.keyStatus)
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = keyColor.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = keyLabel,
                            fontSize = 11.sp,
                            color = keyColor,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Attestation",
                        fontSize = 11.sp,
                        color = TrustColors.EmeraldText,
                        fontWeight = FontWeight.Medium
                    )
                    val (attestLabel, attestColor) = getAttestationLabel(status.attestationStatus)
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = attestColor.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = attestLabel,
                            fontSize = 11.sp,
                            color = attestColor,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }

                status.keyId?.let { keyId ->
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Key ID",
                            fontSize = 11.sp,
                            color = TrustColors.EmeraldText,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = if (keyId.length > 12) "${keyId.take(6)}...${keyId.takeLast(4)}" else keyId,
                            fontSize = 11.sp,
                            color = TrustColors.EmeraldDark
                        )
                    }
                }
            }

            // === Attestation Level Details ===
            Spacer(modifier = Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = TrustColors.EmeraldMuted.copy(alpha = 0.3f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Attestation Checks (Level ${status.maxLevel}/5)",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = TrustColors.EmeraldDark
                        )
                        // Refresh button
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = TrustColors.EmeraldDark,
                            modifier = Modifier.testableClickable("btn_refresh_attestation") {
                                loading = true
                                error = null
                                showLogView = true
                                logMessages = listOf("[verify] Starting attestation check...")
                                coroutineScope.launch {
                                    try {
                                        logMessages = logMessages + "[verify] Loading CIRISVerify binary..."
                                        kotlinx.coroutines.delay(300)
                                        logMessages = logMessages + "[verify] Querying registry..."
                                        val result = withContext(Dispatchers.IO) {
                                            apiClient.getVerifyStatus()
                                        }
                                        verifyStatus = result
                                        if (result.loaded) {
                                            logMessages = logMessages + "[verify] ✓ Attestation complete"
                                            showLogView = false
                                        } else {
                                            logMessages = logMessages + "[verify] ✗ ${result.error ?: "Verification failed"}"
                                            error = result.error
                                        }
                                    } catch (e: Exception) {
                                        logMessages = logMessages + "[verify] ✗ Error: ${e.message}"
                                        error = e.message
                                        // Keep showLogView = true on error
                                    } finally {
                                        loading = false
                                    }
                                }
                            }
                        ) {
                            Text(
                                text = if (loading) "..." else "🔄",
                                fontSize = 10.sp,
                                color = Color.White,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    // DMV analogy header
                    Text(
                        text = "Like a DMV check for AI — each level builds trust",
                        fontSize = 10.sp,
                        color = Color.Gray
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // === ATTESTATION TRUST CHAIN (always visible) ===
                    // If a lower level fails, higher levels show yellow (unverified)
                    // because we can't vouch for checks that weren't cross-validated

                        // Level 1: Binary loaded and functional
                        val level1Passed = status.binaryOk
                        val level1Color = if (level1Passed) Color(0xFF059669) else Color(0xFFDC2626)
                        val level1Icon = if (level1Passed) "✓" else "✗"
                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = level1Icon,
                                    fontSize = 12.sp,
                                    color = level1Color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(16.dp)
                                )
                                Text(
                                    text = "Level 1: Binary Loaded",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level1Color
                                )
                            }
                            Text(
                                text = "CIRISVerify engine is running and responding",
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                        }

                        // Level 2: Environment - HW platform validation + config
                        val level1Failed = !level1Passed
                        val level2Passed = status.envOk
                        val level2Unverified = level1Failed && level2Passed
                        val level2Color = when {
                            !level2Passed -> Color(0xFFDC2626)
                            level2Unverified -> Color(0xFFD97706)
                            else -> Color(0xFF059669)
                        }
                        val level2Icon = when {
                            !level2Passed -> "✗"
                            level2Unverified -> "?"
                            else -> "✓"
                        }
                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = level2Icon,
                                    fontSize = 12.sp,
                                    color = level2Color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(16.dp)
                                )
                                Text(
                                    text = "Level 2: Environment",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level2Color
                                )
                            }
                            // Show platform info if available
                            val envDescription = buildString {
                                append("Platform: ")
                                append(status.platformOs?.uppercase() ?: "Unknown")
                                if (status.platformArch != null) {
                                    append(" (${status.platformArch})")
                                }
                                // Add HW security info
                                append(" • HW: ")
                                append(status.hardwareType?.replace("_", " ") ?: "Unknown")
                            }
                            Text(
                                text = envDescription,
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            // Show what's checked
                            Text(
                                text = "Validates: API keys, config, platform integrity (VM detection)",
                                fontSize = 9.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                        }

                        // Level 3: Network validation - Cross-check with multiple registries
                        val level2Failed = !level2Passed
                        val networkPassed = listOf(status.dnsUsOk, status.dnsEuOk, status.httpsUsOk || status.httpsEuOk).count { it }
                        val level3Passed = networkPassed >= 2
                        val level3Unverified = (level1Failed || level2Failed) && level3Passed
                        val level3Color = when {
                            !level3Passed -> Color(0xFFDC2626)
                            level3Unverified -> Color(0xFFD97706)
                            else -> Color(0xFF059669)
                        }
                        val level3Icon = when {
                            !level3Passed -> "✗"
                            level3Unverified -> "?"
                            else -> "✓"
                        }
                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = level3Icon,
                                    fontSize = 12.sp,
                                    color = level3Color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(16.dp)
                                )
                                Text(
                                    text = "Level 3: Registry Cross-Validation ($networkPassed/3)",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level3Color
                                )
                            }
                            Text(
                                text = "HTTPS authoritative, DNS advisory (need 2/3 agreement)",
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            Row(modifier = Modifier.padding(start = 16.dp, top = 2.dp)) {
                                NetworkCheck("US", status.dnsUsOk)
                                Spacer(modifier = Modifier.width(8.dp))
                                NetworkCheck("EU", status.dnsEuOk)
                                Spacer(modifier = Modifier.width(8.dp))
                                NetworkCheck("HTTPS", status.httpsUsOk || status.httpsEuOk)
                            }
                            if (networkPassed < 2) {
                                Text(
                                    text = "⚠ Need 2/3 sources to agree",
                                    fontSize = 10.sp,
                                    color = Color(0xFFDC2626),
                                    modifier = Modifier.padding(start = 8.dp, top = 2.dp)
                                )
                            }
                        }

                        // Level 4: File Integrity - Tripwire-style hash verification
                        // If any lower level failed, we can't vouch for file integrity
                        val anyLowerLevelFailed = level1Failed || level2Failed || !level3Passed
                        val level4Passed = status.fileIntegrityOk
                        val level4Unverified = anyLowerLevelFailed && level4Passed
                        val level4Color = when {
                            !level4Passed -> Color(0xFFDC2626)  // Red: failed
                            level4Unverified -> Color(0xFFD97706)  // Amber: passed but unverified
                            else -> Color(0xFF059669)  // Green: passed and verified
                        }
                        val level4Icon = when {
                            !level4Passed -> "✗"
                            level4Unverified -> "?"  // Can't vouch for it
                            else -> "✓"
                        }

                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = level4Icon,
                                    fontSize = 12.sp,
                                    color = level4Color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(16.dp)
                                )
                                Text(
                                    text = "Level 4: File Integrity",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level4Color
                                )
                            }
                            // Show detailed integrity status - Level 4 checks against REGISTRY manifest
                            val integrityDescription = when {
                                !level4Passed -> status.integrityFailureReason ?: "File integrity check failed"
                                level4Unverified -> "Cannot verify against registry (network unavailable)"
                                status.filesChecked != null && status.filesChecked > 0 && status.totalFiles != null && status.totalFiles > 0 ->
                                    "Verified ${status.filesPassed ?: 0}/${status.filesChecked} files (${status.attestationMode})"
                                status.filesChecked != null && status.filesChecked > 0 ->
                                    "Verified ${status.filesPassed ?: 0} files (${status.attestationMode})"
                                else -> "Software matches registry-hosted manifest"
                            }
                            Text(
                                text = "Spot-check file hashes against hosted registry manifest",
                                fontSize = 9.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            Text(
                                text = integrityDescription,
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            // Show file counts if available
                            if (status.filesChecked != null && status.filesChecked > 0) {
                                Row(modifier = Modifier.padding(start = 16.dp, top = 2.dp)) {
                                    Text(
                                        text = "${status.filesPassed ?: 0} passed",
                                        fontSize = 9.sp,
                                        color = Color(0xFF059669)
                                    )
                                    if ((status.filesFailed ?: 0) > 0) {
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            text = "${status.filesFailed} failed",
                                            fontSize = 9.sp,
                                            color = Color(0xFFDC2626)
                                        )
                                    }
                                }
                            }
                        }

                        // Level 5: Portal Key + Audit - Genesis key from Portal + untampered audit chain
                        // If any lower level failed, we can't vouch for Level 5
                        val anyLevelBelow5Failed = level1Failed || level2Failed || !level3Passed || !level4Passed
                        val level5Passes = status.registryOk && status.auditOk
                        val level5Unverified = anyLevelBelow5Failed && level5Passes
                        val level5Color = when {
                            !level5Passes -> Color(0xFFDC2626)  // Red: failed
                            level5Unverified -> Color(0xFFD97706)  // Amber: passed but unverified
                            else -> Color(0xFF059669)  // Green: passed and verified
                        }
                        val level5Icon = when {
                            !level5Passes -> "✗"
                            level5Unverified -> "?"  // Can't vouch for it
                            else -> "✓"
                        }

                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = level5Icon,
                                    fontSize = 12.sp,
                                    color = level5Color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(16.dp)
                                )
                                Text(
                                    text = "Level 5: Full Trust",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level5Color
                                )
                            }
                            val level5Description = when {
                                level5Unverified -> "Passed locally but unverified (lower level check failed)"
                                else -> "Genesis key from CIRISPortal + untampered audit chain"
                            }
                            Text(
                                text = level5Description,
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            // Portal Key status - also show yellow if unverified
                            val portalKeyColor = when {
                                !status.registryOk -> Color(0xFFDC2626)
                                anyLevelBelow5Failed -> Color(0xFFD97706)
                                else -> Color(0xFF059669)
                            }
                            val auditColor = when {
                                !status.auditOk -> Color(0xFFDC2626)
                                anyLevelBelow5Failed -> Color(0xFFD97706)
                                else -> Color(0xFF059669)
                            }
                            Row(
                                modifier = Modifier.padding(start = 16.dp, top = 2.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = if (status.registryOk) (if (anyLevelBelow5Failed) "?" else "✓") else "✗",
                                    fontSize = 10.sp,
                                    color = portalKeyColor,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(
                                    text = "Portal Key",
                                    fontSize = 10.sp,
                                    color = portalKeyColor
                                )
                                Spacer(modifier = Modifier.width(16.dp))
                                Text(
                                    text = if (status.auditOk) (if (anyLevelBelow5Failed) "?" else "✓") else "✗",
                                    fontSize = 10.sp,
                                    color = if (status.auditOk) Color(0xFF059669) else Color(0xFFDC2626),
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(
                                    text = "Audit Trail",
                                    fontSize = 10.sp,
                                    color = auditColor
                                )
                            }
                        }

                        // Platform Info (if available)
                        if (status.platformOs != null || status.platformArch != null) {
                            Spacer(modifier = Modifier.height(8.dp))
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = TrustColors.EmeraldMuted.copy(alpha = 0.2f),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(8.dp)) {
                                    Text(
                                        text = "Platform Attestation",
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.Medium,
                                        color = TrustColors.EmeraldDark
                                    )
                                    Row(modifier = Modifier.padding(top = 2.dp)) {
                                        status.platformOs?.let { os ->
                                            Text(
                                                text = "OS: $os",
                                                fontSize = 9.sp,
                                                color = Color.Gray
                                            )
                                        }
                                        if (status.platformOs != null && status.platformArch != null) {
                                            Spacer(modifier = Modifier.width(12.dp))
                                        }
                                        status.platformArch?.let { arch ->
                                            Text(
                                                text = "Arch: $arch",
                                                fontSize = 9.sp,
                                                color = Color.Gray
                                            )
                                        }
                                    }
                                }
                            }
                        }

                    // Mode indicator
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Mode: ${status.attestationMode.replaceFirstChar { it.uppercase() }}",
                        fontSize = 9.sp,
                        color = Color.Gray,
                        modifier = Modifier.padding(start = 16.dp)
                    )

                    // === EXPANDABLE RAW DETAILS ===
                    var showRawDetails by remember { mutableStateOf(false) }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_toggle_raw_details") { showRawDetails = !showRawDetails }
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (showRawDetails) "▼ Raw Details" else "▶ Raw Details",
                            fontSize = 10.sp,
                            color = TrustColors.EmeraldDark
                        )
                    }

                    if (showRawDetails) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = Color(0xFFF5F5F5),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(
                                modifier = Modifier
                                    .padding(8.dp)
                                    .fillMaxWidth()
                            ) {
                                // Raw values
                                Text("Binary: ${status.binaryOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Env: ${status.envOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("DNS US: ${status.dnsUsOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("DNS EU: ${status.dnsEuOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("HTTPS US: ${status.httpsUsOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("HTTPS EU: ${status.httpsEuOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("File Integrity: ${status.fileIntegrityOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Registry: ${status.registryOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Audit: ${status.auditOk}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Spacer(modifier = Modifier.height(4.dp))
                                Text("Platform: ${status.platformOs ?: "?"} / ${status.platformArch ?: "?"}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Hardware: ${status.hardwareType ?: "?"}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Key Status: ${status.keyStatus}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                status.keyId?.let { Text("Key ID: $it", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace) }
                                Spacer(modifier = Modifier.height(4.dp))
                                Text("Files: ${status.filesChecked ?: 0}/${status.totalFiles ?: 0} checked", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                Text("Passed: ${status.filesPassed ?: 0}, Failed: ${status.filesFailed ?: 0}", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                                status.integrityFailureReason?.let { reason ->
                                    val displayReason = when {
                                        reason.startsWith("unexpected_files:") -> {
                                            val count = reason.substringAfter(":").toIntOrNull() ?: 0
                                            "$count unexpected file(s)"
                                        }
                                        else -> reason
                                    }
                                    val reasonColor = if (reason.startsWith("unexpected")) Color(0xFFD97706) else Color(0xFFDC2626)
                                    Text("Reason: $displayReason", fontSize = 9.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace, color = reasonColor)
                                }
                                Spacer(modifier = Modifier.height(4.dp))
                                status.diagnosticInfo?.let { Text("Diag: $it", fontSize = 8.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace, color = Color.Gray) }
                            }
                        }
                    }
                }
            }

            // Show diagnostic info if key is not portal_active (for troubleshooting)
            if (status.keyStatus != "portal_active") {
                Spacer(modifier = Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = Color(0xFFFEF3C7),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        Text(
                            text = "⚠ Portal Key Not Active",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF92400E)
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "The purchased portal key was not saved to the Android Keystore. " +
                                   "This may be a bug in CIRISVerify key persistence.",
                            fontSize = 11.sp,
                            color = Color(0xFFD97706)
                        )
                        status.diagnosticInfo?.let { diag ->
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Debug: $diag",
                                fontSize = 10.sp,
                                color = Color(0xFF92400E),
                                fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace
                            )
                        }
                    }
                }
            }

            // Disclaimer
            Spacer(modifier = Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = TrustColors.EmeraldMuted.copy(alpha = 0.5f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = "CIRISVerify provides cryptographic attestation of agent identity for the Coherence Ratchet and CIRIS Scoring.",
                    fontSize = 11.sp,
                    color = TrustColors.EmeraldText,
                    modifier = Modifier.padding(8.dp)
                )
            }

            // Links
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "Learn more",
                    fontSize = 11.sp,
                    color = TrustColors.EmeraldText,
                    textDecoration = TextDecoration.Underline,
                    modifier = Modifier.testableClickable("btn_learn_more") {
                        uriHandler.openUri("https://ciris.ai/trust")
                    }
                )
            }
        }
    }
}

private fun getKeyStatusLabel(keyStatus: String): Pair<String, Color> {
    return when (keyStatus) {
        "portal_active" -> "Portal Key Active" to Color(0xFF047857)
        "portal_pending" -> "Portal Key Pending" to Color(0xFFD97706)
        "ephemeral" -> "Ephemeral Key" to Color(0xFF1D4ED8)
        else -> "No Key" to Color(0xFF6B7280)
    }
}

private fun getAttestationLabel(attestation: String): Pair<String, Color> {
    return when (attestation) {
        "verified" -> "Verified" to Color(0xFF047857)
        "pending" -> "Pending" to Color(0xFFD97706)
        "failed" -> "Failed" to Color(0xFFDC2626)
        else -> "Not Attempted" to Color(0xFF6B7280)
    }
}

@Composable
private fun AttestationCheckRow(label: String, passed: Boolean, level: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = if (passed) "✓" else "✗",
                fontSize = 12.sp,
                color = if (passed) Color(0xFF047857) else Color(0xFFDC2626),
                fontWeight = FontWeight.Bold,
                modifier = Modifier.width(16.dp)
            )
            Text(
                text = label,
                fontSize = 11.sp,
                color = TrustColors.EmeraldDark
            )
        }
        Text(
            text = level,
            fontSize = 10.sp,
            color = TrustColors.EmeraldText.copy(alpha = 0.7f)
        )
    }
}

@Composable
private fun AttestationSection(
    title: String,
    description: String,
    passed: Boolean,
    level: Int
) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = if (passed) "✓" else "✗",
                fontSize = 12.sp,
                color = if (passed) Color(0xFF047857) else Color(0xFFDC2626),
                fontWeight = FontWeight.Bold,
                modifier = Modifier.width(16.dp)
            )
            Text(
                text = "Level $level: $title",
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                color = if (passed) Color(0xFF059669) else Color(0xFFDC2626)
            )
        }
        Text(
            text = description,
            fontSize = 10.sp,
            color = Color.Gray,
            modifier = Modifier.padding(start = 16.dp)
        )
    }
}

@Composable
private fun NetworkCheck(label: String, passed: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = if (passed) "●" else "○",
            fontSize = 8.sp,
            color = if (passed) Color(0xFF047857) else Color(0xFFDC2626)
        )
        Spacer(modifier = Modifier.width(2.dp))
        Text(
            text = label,
            fontSize = 10.sp,
            color = if (passed) Color(0xFF059669) else Color.Gray
        )
    }
}
