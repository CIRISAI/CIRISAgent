package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.LocalCurrency
import ai.ciris.mobile.shared.localization.LocalLocalization
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.theme.BrightnessPreference
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_CURRENCIES
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_LANGUAGES
import ai.ciris.mobile.shared.platform.getOAuthProviderName
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
import androidx.compose.material.icons.filled.ArrowForward
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
    onNavigateToDataManagement: () -> Unit = {},  // Navigate to Data Management screen
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

    // Show snackbar for success/error
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
            title = { Text(localizedString("mobile.settings_rerun_setup_confirm_title")) },
            text = {
                Text(
                    localizedString("mobile.settings_rerun_setup_confirm_message")
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
                    Text(localizedString("mobile.settings_rerun_setup_button"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showResetConfirmDialog = false },
                    modifier = Modifier.testableClickable("btn_reset_cancel") { showResetConfirmDialog = false }
                ) {
                    Text(localizedString("mobile.settings_cancel"))
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.settings_title")) },
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
                    Text(localizedString("mobile.settings_loading_config"))
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
                    text = localizedString("mobile.settings_ai_config"),
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

                // Preferences Section (Language & Currency)
                PreferencesSection()

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // Display Settings Section
                DisplaySettingsSection(viewModel = viewModel)

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // CIRIS Authentication Section
                Text(
                    text = localizedString("mobile.settings_ciris_auth"),
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
                    text = localizedString("mobile.settings_account"),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                // Explain that OAuth login IS the API key
                val providerName = getOAuthProviderName()
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text(
                            text = localizedString("mobile.settings_authentication"),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = localizedString("mobile.settings_authentication_desc", "provider", providerName),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                        )
                    }
                }

                Spacer(Modifier.height(4.dp))

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
                    Text(localizedString("mobile.settings_logout"))
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // Setup Section
                Text(
                    text = localizedString("mobile.settings_setup"),
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
                            text = localizedString("mobile.settings_rerun_setup_wizard"),
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = localizedString("mobile.settings_rerun_setup_desc"),
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
                            Text(if (isResetting) localizedString("mobile.settings_resetting") else localizedString("mobile.settings_rerun_setup_wizard"))
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Data Management - Navigate to DSAR self-service screen
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onNavigateToDataManagement() }
                        .testableClickable("btn_data_management") { onNavigateToDataManagement() },
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Row(
                        modifier = Modifier
                            .padding(16.dp)
                            .fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = localizedString("mobile.settings_data_management"),
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = localizedString("mobile.settings_data_management_desc"),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Icon(
                            imageVector = Icons.Filled.ArrowForward,
                            contentDescription = localizedString("mobile.settings_data_management_goto"),
                            tint = MaterialTheme.colorScheme.primary
                        )
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

                // App Info
                Text(
                    text = localizedString("mobile.settings_app_info"),
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
                        InfoRow(localizedString("mobile.settings_version"), "2.1.0 (KMP)")
                        InfoRow(localizedString("mobile.settings_platform"), "Kotlin Multiplatform")
                        InfoRow(localizedString("mobile.settings_ui"), "Compose Multiplatform")
                        InfoRow(localizedString("mobile.settings_mode"), if (isCirisProxy) localizedString("mobile.settings_mode_proxy") else localizedString("mobile.settings_mode_byok"))
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
                text = localizedString("mobile.settings_using_proxy"),
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )

            val provider = getOAuthProviderName()
            Text(
                text = localizedString("mobile.settings_proxy_desc", "provider", provider),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f),
                textAlign = TextAlign.Center
            )

            HorizontalDivider(
                modifier = Modifier.padding(vertical = 8.dp),
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f)
            )

            Text(
                text = localizedString("mobile.settings_benefits"),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )

            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                BenefitItem(localizedString("mobile.settings_benefit_signin_is_key"))
                BenefitItem(localizedString("mobile.settings_benefit_auto_model"))
                BenefitItem(localizedString("mobile.settings_benefit_rate_limiting"))
                BenefitItem(localizedString("mobile.settings_benefit_cost_managed"))
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
                text = localizedString("mobile.settings_using_byok"),
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
                color = MaterialTheme.colorScheme.onPrimary
            )
            Spacer(Modifier.width(8.dp))
        }
        Text(if (isSaving) localizedString("mobile.settings_saving") else localizedString("mobile.settings_save"))
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
                    text = localizedString("mobile.settings_backup_llm"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onTertiaryContainer
                )
            }

            Text(
                text = localizedString("mobile.settings_backup_llm_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.8f)
            )

            HorizontalDivider(
                modifier = Modifier.padding(vertical = 4.dp),
                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.2f)
            )

            config.backupBaseUrl?.let { url ->
                val provider = when {
                    url.contains("groq.com") -> localizedString("mobile.settings_provider_groq")
                    url.contains("together") -> localizedString("mobile.settings_provider_together")
                    url.contains("openai.com") -> localizedString("mobile.settings_provider_openai")
                    url.contains("anthropic") -> localizedString("mobile.settings_provider_anthropic")
                    url.contains("ciris.ai") -> "CIRIS Proxy"
                    else -> url.take(30)
                }
                InfoRowTertiary(localizedString("mobile.settings_provider"), provider)
            }

            config.backupModel?.let { model ->
                InfoRowTertiary(localizedString("mobile.settings_model"), model)
            }

            InfoRowTertiary(localizedString("mobile.settings_api_key"), if (config.backupApiKeySet) localizedString("mobile.settings_configured") else localizedString("mobile.settings_not_set"))
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
                    text = localizedString("mobile.settings_ciris_access_token"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
            }

            // Explanation
            Text(
                text = localizedString("mobile.settings_token_info_desc"),
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
                        text = localizedString("mobile.settings_loading_token"),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            } else if (tokenInfo != null) {
                val info = tokenInfo!!

                // Token format indicator
                val semantic = SemanticColors.Default
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

                Spacer(modifier = Modifier.height(4.dp))

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
                    InfoRow(localizedString("mobile.settings_issuer"), info.issuer)
                }

                // Warning for old/problematic tokens
                if (info.isExpired || info.hasSigningKeyIssue) {
                    Spacer(modifier = Modifier.height(8.dp))
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

        // Base64url decode using kotlin.io.encoding (KMP-compatible)
        @OptIn(kotlin.io.encoding.ExperimentalEncodingApi::class)
        val payloadJson = try {
            val bytes = kotlin.io.encoding.Base64.UrlSafe.decode(paddedPayload)
            bytes.decodeToString()
        } catch (e: Exception) {
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
            @OptIn(kotlin.io.encoding.ExperimentalEncodingApi::class)
            try {
                kotlin.io.encoding.Base64.UrlSafe.decode(headerPadded).decodeToString()
            } catch (e: Exception) { "{}" }
        })

        val expTimestamp = expMatch?.groupValues?.get(1)?.toLongOrNull()
        val issuer = issMatch?.groupValues?.get(1)

        // Check if expired
        val now = kotlinx.datetime.Clock.System.now().epochSeconds
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

// TrustColors derived from SemanticColors for consistency
private object TrustColors {
    private val semantic = SemanticColors.Default
    val EmeraldLight = semantic.surfaceSuccess
    val EmeraldBorder = semantic.success
    val EmeraldDark = semantic.onSuccess
    val EmeraldText = semantic.success
    val EmeraldMuted = semantic.surfaceSuccess
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

    val semantic = SemanticColors.Default

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
                            text = localizedString("mobile.settings_attestation_check"),
                            fontWeight = FontWeight.Bold,
                            color = semantic.success,
                            fontSize = 12.sp
                        )
                        if (loading) {
                            Spacer(modifier = Modifier.width(8.dp))
                            CircularProgressIndicator(
                                modifier = Modifier.size(12.dp),
                                color = semantic.success,
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
                            color = if (msg.contains("✗")) semantic.error
                                   else if (msg.contains("✓")) semantic.success
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
                        text = localizedString("mobile.settings_copy_logs"),
                        fontSize = 10.sp,
                        color = semantic.warning
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
            colors = CardDefaults.cardColors(containerColor = semantic.surfaceWarning)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = localizedString("mobile.settings_verify_status_unknown"),
                    fontWeight = FontWeight.Bold,
                    color = semantic.onWarning
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = error ?: verifyStatus?.error ?: localizedString("mobile.settings_unable_check_verify"),
                    fontSize = 13.sp,
                    color = semantic.warning
                )
                // Show diagnostic info for troubleshooting
                verifyStatus?.diagnosticInfo?.let { diag ->
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = localizedString("mobile.settings_debug", "info", diag),
                        fontSize = 10.sp,
                        color = semantic.onWarning,
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
                        text = localizedString("mobile.settings_verify_active"),
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
                        text = localizedString("mobile.settings_hardware"),
                        fontSize = 11.sp,
                        color = TrustColors.EmeraldText,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = status.hardwareType?.replace("_", " ") ?: localizedString("mobile.settings_unknown"),
                        fontSize = 13.sp,
                        color = TrustColors.EmeraldDark
                    )
                }

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = localizedString("mobile.settings_key_status"),
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
                        text = localizedString("mobile.settings_attestation"),
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
                            text = localizedString("mobile.settings_key_id"),
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
                            text = localizedString("mobile.settings_attestation_checks", "level", status.maxLevel.toString()),
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
                        text = localizedString("mobile.settings_attestation_levels_desc"),
                        fontSize = 10.sp,
                        color = Color.Gray
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // === ATTESTATION TRUST CHAIN (always visible) ===
                    // If a lower level fails, higher levels show yellow (unverified)
                    // because we can't vouch for checks that weren't cross-validated

                        // Level 1: Binary loaded and functional
                        val level1Passed = status.binaryOk
                        val level1Color = if (level1Passed) semantic.success else semantic.error
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
                                    text = localizedString("mobile.settings_level_1"),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level1Color
                                )
                            }
                            Text(
                                text = localizedString("mobile.settings_verify_running"),
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
                            !level2Passed -> semantic.error
                            level2Unverified -> semantic.warning
                            else -> semantic.success
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
                                    text = localizedString("mobile.settings_level_2"),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level2Color
                                )
                            }
                            // Show platform info if available
                            val envDescription = buildString {
                                append(localizedString("mobile.settings_platform_label"))
                                append(status.platformOs?.uppercase() ?: localizedString("mobile.settings_unknown"))
                                if (status.platformArch != null) {
                                    append(" (${status.platformArch})")
                                }
                                // Add HW security info
                                append(" • HW: ")
                                append(status.hardwareType?.replace("_", " ") ?: localizedString("mobile.settings_unknown"))
                            }
                            Text(
                                text = envDescription,
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            // Show what's checked
                            Text(
                                text = localizedString("mobile.settings_level_2_desc"),
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
                            !level3Passed -> semantic.error
                            level3Unverified -> semantic.warning
                            else -> semantic.success
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
                                    text = localizedString("mobile.settings_level_3", "passed", networkPassed.toString()),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level3Color
                                )
                            }
                            Text(
                                text = localizedString("mobile.settings_https_authoritative"),
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
                                    text = localizedString("mobile.settings_level_3_desc"),
                                    fontSize = 10.sp,
                                    color = semantic.error,
                                    modifier = Modifier.padding(start = 8.dp, top = 2.dp)
                                )
                            }
                        }

                        // Level 4: Module Integrity - Cross-validated hash verification
                        // Uses moduleIntegrityOk which correctly excludes server-only files
                        val anyLowerLevelFailed = level1Failed || level2Failed || !level3Passed
                        val level4Passed = status.moduleIntegrityOk
                        val level4Unverified = anyLowerLevelFailed && level4Passed
                        val level4Color = when {
                            !level4Passed -> semantic.error    // Red: failed
                            level4Unverified -> semantic.warning  // Amber: passed but unverified
                            else -> semantic.success   // Green: passed and verified
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
                                    text = localizedString("mobile.settings_level_4"),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level4Color
                                )
                            }
                            // Show detailed integrity status - Level 4 checks against REGISTRY manifest
                            val integrityDescription = when {
                                !level4Passed -> status.integrityFailureReason ?: localizedString("mobile.settings_integrity_failed")
                                level4Unverified -> localizedString("mobile.settings_integrity_unverified")
                                status.filesChecked != null && status.filesChecked > 0 && status.totalFiles != null && status.totalFiles > 0 ->
                                    localizedString("mobile.settings_integrity_verified_count", mapOf("passed" to "${status.filesPassed ?: 0}", "checked" to "${status.filesChecked}", "mode" to status.attestationMode))
                                status.filesChecked != null && status.filesChecked > 0 ->
                                    localizedString("mobile.settings_integrity_verified", mapOf("passed" to "${status.filesPassed ?: 0}", "mode" to status.attestationMode))
                                else -> localizedString("mobile.settings_integrity_matches")
                            }
                            Text(
                                text = localizedString("mobile.settings_level_4_desc"),
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
                                        color = semantic.success
                                    )
                                    if ((status.filesFailed ?: 0) > 0) {
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            text = "${status.filesFailed} failed",
                                            fontSize = 9.sp,
                                            color = semantic.error
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
                            !level5Passes -> semantic.error    // Red: failed
                            level5Unverified -> semantic.warning  // Amber: passed but unverified
                            else -> semantic.success   // Green: passed and verified
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
                                    text = localizedString("mobile.settings_level_5"),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = level5Color
                                )
                            }
                            val level5Description = when {
                                level5Unverified -> localizedString("mobile.settings_level_5_unverified")
                                else -> localizedString("mobile.settings_level_5_desc")
                            }
                            Text(
                                text = level5Description,
                                fontSize = 10.sp,
                                color = Color.Gray,
                                modifier = Modifier.padding(start = 16.dp)
                            )
                            // Portal Key status - also show yellow if unverified
                            val portalKeyColor = when {
                                !status.registryOk -> semantic.error
                                anyLevelBelow5Failed -> semantic.warning
                                else -> semantic.success
                            }
                            val auditColor = when {
                                !status.auditOk -> semantic.error
                                anyLevelBelow5Failed -> semantic.warning
                                else -> semantic.success
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
                                    text = localizedString("mobile.settings_portal_key"),
                                    fontSize = 10.sp,
                                    color = portalKeyColor
                                )
                                Spacer(modifier = Modifier.width(16.dp))
                                Text(
                                    text = if (status.auditOk) (if (anyLevelBelow5Failed) "?" else "✓") else "✗",
                                    fontSize = 10.sp,
                                    color = if (status.auditOk) semantic.success else semantic.error,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(
                                    text = localizedString("mobile.settings_audit_trail"),
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
                                        text = localizedString("mobile.settings_platform_attestation"),
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.Medium,
                                        color = TrustColors.EmeraldDark
                                    )
                                    Row(modifier = Modifier.padding(top = 2.dp)) {
                                        status.platformOs?.let { os ->
                                            Text(
                                                text = localizedString("mobile.settings_os", "os", os),
                                                fontSize = 9.sp,
                                                color = Color.Gray
                                            )
                                        }
                                        if (status.platformOs != null && status.platformArch != null) {
                                            Spacer(modifier = Modifier.width(12.dp))
                                        }
                                        status.platformArch?.let { arch ->
                                            Text(
                                                text = localizedString("mobile.settings_arch", "arch", arch),
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
                        text = localizedString("mobile.settings_mode_label", "mode", status.attestationMode.replaceFirstChar { it.uppercase() }),
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
                                    val reasonColor = if (reason.startsWith("unexpected")) semantic.warning else semantic.error
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
                    color = semantic.surfaceWarning,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        Text(
                            text = localizedString("mobile.settings_portal_key_not_active"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = semantic.onWarning
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = localizedString("mobile.settings_portal_key_not_active_desc"),
                            fontSize = 11.sp,
                            color = semantic.warning
                        )
                        status.diagnosticInfo?.let { diag ->
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = localizedString("mobile.settings_debug", "info", diag),
                                fontSize = 10.sp,
                                color = semantic.onWarning,
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
                    text = localizedString("mobile.settings_verify_description"),
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
                    text = localizedString("mobile.settings_learn_more"),
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

@Composable
private fun getKeyStatusLabel(keyStatus: String): Pair<String, Color> {
    val semantic = SemanticColors.Default
    return when (keyStatus) {
        "portal_active" -> localizedString("mobile.settings_portal_key_active") to semantic.success
        "portal_pending" -> localizedString("mobile.settings_portal_key_pending") to semantic.warning
        "ephemeral" -> localizedString("mobile.settings_ephemeral_key") to semantic.info
        else -> localizedString("mobile.settings_no_key") to semantic.inactive
    }
}

@Composable
private fun getAttestationLabel(attestation: String): Pair<String, Color> {
    val semantic = SemanticColors.Default
    return when (attestation) {
        "verified" -> localizedString("mobile.settings_verified") to semantic.success
        "pending" -> localizedString("mobile.settings_pending") to semantic.warning
        "failed" -> localizedString("mobile.settings_failed") to semantic.error
        else -> localizedString("mobile.settings_not_attempted") to semantic.inactive
    }
}

@Composable
private fun AttestationCheckRow(label: String, passed: Boolean, level: String) {
    val semantic = SemanticColors.Default
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
                color = if (passed) semantic.success else semantic.error,
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
    val semantic = SemanticColors.Default
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = if (passed) "✓" else "✗",
                fontSize = 12.sp,
                color = if (passed) semantic.success else semantic.error,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.width(16.dp)
            )
            Text(
                text = "L$level: $title",
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                color = if (passed) semantic.success else semantic.error
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
    val semantic = SemanticColors.Default
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = if (passed) "●" else "○",
            fontSize = 8.sp,
            color = if (passed) semantic.success else semantic.error
        )
        Spacer(modifier = Modifier.width(2.dp))
        Text(
            text = label,
            fontSize = 10.sp,
            color = if (passed) semantic.success else semantic.inactive
        )
    }
}

/**
 * Theme settings section - all appearance options in one card.
 * Changes apply immediately to the app.
 */
@Composable
private fun DisplaySettingsSection(viewModel: SettingsViewModel) {
    val liveBackgroundEnabled by viewModel.liveBackgroundEnabled.collectAsState()
    val colorTheme by viewModel.colorTheme.collectAsState()
    val brightnessPreference by viewModel.brightnessPreference.collectAsState()

    Text(
        text = localizedString("mobile.settings_theme"),
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary
    )

    // Theme Card - all appearance settings together
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Live background toggle at top (most impactful setting)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = localizedString("mobile.settings_live_memory_bg"),
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = localizedString("mobile.settings_live_memory_bg_desc"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Switch(
                    checked = liveBackgroundEnabled,
                    onCheckedChange = { viewModel.toggleLiveBackground(it) },
                    modifier = Modifier.testable("switch_live_background")
                )
            }

            Spacer(modifier = Modifier.height(16.dp))
            HorizontalDivider()
            Spacer(modifier = Modifier.height(16.dp))

            // Color theme selection
            Text(
                text = localizedString("mobile.settings_color_palette"),
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.settings_color_palette_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(12.dp))

            // Color theme grid - 3 columns
            val themes = ColorTheme.entries.toList()
            val chunkedThemes = themes.chunked(3)

            chunkedThemes.forEach { row ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    row.forEach { theme ->
                        ColorThemeChip(
                            theme = theme,
                            isSelected = colorTheme == theme,
                            onClick = { viewModel.setColorTheme(theme) },
                            modifier = Modifier.weight(1f)
                        )
                    }
                    // Fill remaining space if row is incomplete
                    repeat(3 - row.size) {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
            }

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider()
            Spacer(modifier = Modifier.height(16.dp))

            // Brightness preference
            Text(
                text = localizedString("mobile.settings_brightness"),
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium
            )
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                BrightnessPreference.entries.forEach { pref ->
                    FilterChip(
                        selected = brightnessPreference == pref,
                        onClick = { viewModel.setBrightnessPreference(pref) },
                        label = { Text(pref.displayName) },
                        modifier = Modifier.testable("chip_brightness_${pref.name.lowercase()}")
                    )
                }
            }
        }
    }
}

/**
 * Color theme chip with color swatch preview.
 */
@Composable
private fun ColorThemeChip(
    theme: ColorTheme,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (isSelected) MaterialTheme.colorScheme.primaryContainer
               else MaterialTheme.colorScheme.surface,
        modifier = modifier
            .border(
                width = if (isSelected) 2.dp else 1.dp,
                color = if (isSelected) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.outline.copy(alpha = 0.5f),
                shape = RoundedCornerShape(8.dp)
            )
            .testableClickable("chip_color_${theme.name.lowercase()}") { onClick() }
    ) {
        Column(
            modifier = Modifier.padding(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Color swatches (3 circles showing primary, secondary, tertiary)
            Row(
                horizontalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                // Primary color circle
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(
                            color = theme.primary,
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                        .border(
                            width = 1.dp,
                            color = Color.Black.copy(alpha = 0.2f),
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                )
                // Secondary color circle
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(
                            color = theme.secondary,
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                        .border(
                            width = 1.dp,
                            color = Color.Black.copy(alpha = 0.2f),
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                )
                // Tertiary color circle
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(
                            color = theme.tertiary,
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                        .border(
                            width = 1.dp,
                            color = Color.Black.copy(alpha = 0.2f),
                            shape = androidx.compose.foundation.shape.CircleShape
                        )
                )
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Theme name
            Text(
                text = theme.displayName,
                fontSize = 10.sp,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                color = if (isSelected) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.onSurface,
                textAlign = TextAlign.Center,
                maxLines = 1
            )
        }
    }
}

/**
 * Preferences section - Language and Currency selection.
 * Changes apply immediately to the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PreferencesSection() {
    val localization = LocalLocalization.current
    val currency = LocalCurrency.current

    // Get current selections
    val currentLanguage by localization?.currentLanguageInfo?.collectAsState()
        ?: remember { mutableStateOf(SUPPORTED_LANGUAGES.first { it.code == "en" }) }
    val currentCurrency by currency?.currentCurrencyInfo?.collectAsState()
        ?: remember { mutableStateOf(SUPPORTED_CURRENCIES.first { it.code == "USD" }) }

    // Dropdown expanded states
    var languageExpanded by remember { mutableStateOf(false) }
    var currencyExpanded by remember { mutableStateOf(false) }

    Text(
        text = localizedString("mobile.settings_preferences"),
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary
    )

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Language selection
            Text(
                text = localizedString("mobile.settings_language"),
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.settings_language_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(8.dp))

            // Language dropdown
            ExposedDropdownMenuBox(
                expanded = languageExpanded,
                onExpandedChange = { languageExpanded = it },
                modifier = Modifier.fillMaxWidth()
            ) {
                OutlinedTextField(
                    value = "${currentLanguage.nativeName} (${currentLanguage.englishName})",
                    onValueChange = {},
                    readOnly = true,
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = languageExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                        .testable("dropdown_language")
                )
                ExposedDropdownMenu(
                    expanded = languageExpanded,
                    onDismissRequest = { languageExpanded = false }
                ) {
                    SUPPORTED_LANGUAGES.forEach { language ->
                        DropdownMenuItem(
                            text = {
                                Column {
                                    Text(language.nativeName, fontWeight = FontWeight.Medium)
                                    Text(
                                        language.englishName,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            },
                            onClick = {
                                localization?.setLanguage(language.code)
                                languageExpanded = false
                            },
                            leadingIcon = {
                                if (currentLanguage.code == language.code) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = localizedString("mobile.settings_selected"),
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                }
                            },
                            modifier = Modifier.testable("language_${language.code}")
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            HorizontalDivider()
            Spacer(modifier = Modifier.height(16.dp))

            // Currency selection
            Text(
                text = localizedString("mobile.settings_display_currency"),
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.settings_display_currency_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(8.dp))

            // Currency dropdown
            ExposedDropdownMenuBox(
                expanded = currencyExpanded,
                onExpandedChange = { currencyExpanded = it },
                modifier = Modifier.fillMaxWidth()
            ) {
                OutlinedTextField(
                    value = "${currentCurrency.symbol} ${currentCurrency.code} - ${currentCurrency.name}",
                    onValueChange = {},
                    readOnly = true,
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = currencyExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                        .testable("dropdown_currency")
                )
                ExposedDropdownMenu(
                    expanded = currencyExpanded,
                    onDismissRequest = { currencyExpanded = false }
                ) {
                    SUPPORTED_CURRENCIES.forEach { curr ->
                        DropdownMenuItem(
                            text = {
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = curr.symbol,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.width(24.dp)
                                    )
                                    Column {
                                        Text(curr.code, fontWeight = FontWeight.Medium)
                                        Text(
                                            curr.name,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            },
                            onClick = {
                                currency?.setCurrency(curr.code)
                                currencyExpanded = false
                            },
                            leadingIcon = {
                                if (currentCurrency.code == curr.code) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = localizedString("mobile.settings_selected"),
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                }
                            },
                            modifier = Modifier.testable("currency_${curr.code}")
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Exchange rate info
            Text(
                text = localizedString("mobile.settings_currency_disclaimer"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}
