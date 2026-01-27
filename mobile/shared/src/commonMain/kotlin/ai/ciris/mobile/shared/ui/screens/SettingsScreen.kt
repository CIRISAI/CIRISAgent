package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

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

    // Confirmation dialog for resetting setup
    if (showResetConfirmDialog) {
        AlertDialog(
            onDismissRequest = { showResetConfirmDialog = false },
            title = { Text("Re-run Setup Wizard?") },
            text = {
                Text(
                    "This will reset your configuration and restart the app. " +
                    "You'll need to set up CIRIS again.\n\n" +
                    "Choose this if you want to:\n" +
                    "• Use your own API key (BYOK mode)\n" +
                    "• Switch LLM providers\n" +
                    "• Change your configuration"
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showResetConfirmDialog = false
                        viewModel.resetSetup { onResetSetup() }
                    }
                ) {
                    Text("Reset & Restart")
                }
            },
            dismissButton = {
                TextButton(onClick = { showResetConfirmDialog = false }) {
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
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.refresh() }) {
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
                    CirisProxyInfoCard(
                        isResetting = isResetting,
                        onResetClick = { showResetConfirmDialog = true }
                    )
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
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Logout")
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
                        InfoRow("Version", "2.0.0 (KMP)")
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
private fun CirisProxyInfoCard(
    isResetting: Boolean,
    onResetClick: () -> Unit
) {
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
                text = "Using CIRIS AI",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )

            Text(
                text = "Your AI requests are routed through CIRIS proxy services. " +
                       "No additional configuration is needed.",
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

    // Switch to BYOK mode button
    OutlinedButton(
        onClick = onResetClick,
        enabled = !isResetting,
        modifier = Modifier.fillMaxWidth()
    ) {
        if (isResetting) {
            CircularProgressIndicator(
                modifier = Modifier.size(16.dp),
                strokeWidth = 2.dp
            )
            Spacer(Modifier.width(8.dp))
        }
        Text(if (isResetting) "Resetting..." else "Switch to BYOK Mode (Use Own API Key)")
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
            modifier = Modifier.fillMaxWidth(),
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
                TextButton(onClick = { onShowApiKeyChange(!showApiKey) }) {
                    Text(if (showApiKey) "Hide" else "Show")
                }
            },
            modifier = Modifier.fillMaxWidth()
        )
    }

    // Save button
    Button(
        onClick = { viewModel.saveSettings() },
        enabled = !isSaving && isEditing,
        modifier = Modifier.fillMaxWidth()
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
