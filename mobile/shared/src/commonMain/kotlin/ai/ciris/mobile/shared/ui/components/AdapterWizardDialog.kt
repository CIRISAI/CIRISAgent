package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.ConfigFieldData
import ai.ciris.mobile.shared.models.ConfigSessionData
import ai.ciris.mobile.shared.models.DiscoveredItemData
import ai.ciris.mobile.shared.models.LoadableAdapterData
import ai.ciris.mobile.shared.models.LoadableAdaptersData
import ai.ciris.mobile.shared.models.SelectOptionData
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/**
 * Adapter configuration wizard dialog.
 *
 * Shows in two phases:
 * 1. Type selection - list of available adapter types
 * 2. Configuration steps - form fields for each step
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdapterWizardDialog(
    loadableAdapters: LoadableAdaptersData?,
    wizardSession: ConfigSessionData?,
    isLoading: Boolean,
    error: String?,
    discoveredItems: List<DiscoveredItemData> = emptyList(),
    discoveryExecuted: Boolean = false,
    oauthUrl: String? = null,
    awaitingOAuthCallback: Boolean = false,
    selectOptions: List<SelectOptionData> = emptyList(),
    onSelectType: (String) -> Unit,
    onLoadDirectly: (String) -> Unit,
    onSubmitStep: (Map<String, String>) -> Unit,
    onSelectDiscoveredItem: (DiscoveredItemData) -> Unit = {},
    onSubmitManualUrl: (String) -> Unit = {},
    onRetryDiscovery: () -> Unit = {},
    onInitiateOAuth: () -> Unit = {},
    onCheckOAuthStatus: () -> Unit = {},
    onBack: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(
            dismissOnBackPress = true,
            dismissOnClickOutside = false,
            usePlatformDefaultWidth = false
        )
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.9f),
            shape = MaterialTheme.shapes.large,
            tonalElevation = 6.dp
        ) {
            Column(
                modifier = Modifier.fillMaxSize()
            ) {
                // Top bar
                TopAppBar(
                    title = {
                        Text(
                            when {
                                wizardSession != null -> "Configure ${wizardSession.adapterType}"
                                else -> "Add Adapter"
                            }
                        )
                    },
                    navigationIcon = {
                        // On type selection (no session): X closes dialog
                        // On wizard step (has session): Back arrow goes to previous step
                        IconButton(
                            onClick = if (wizardSession != null) onBack else onDismiss,
                            modifier = Modifier.testableClickable(
                                if (wizardSession != null) "btn_wizard_back" else "btn_wizard_close"
                            ) { if (wizardSession != null) onBack() else onDismiss() }
                        ) {
                            Icon(
                                imageVector = if (wizardSession != null) Icons.Default.ArrowBack else Icons.Default.Close,
                                contentDescription = if (wizardSession != null) "Back" else "Close"
                            )
                        }
                    },
                    actions = {
                        if (wizardSession != null) {
                            IconButton(
                                onClick = onDismiss,
                                modifier = Modifier.testableClickable("btn_wizard_dismiss") { onDismiss() }
                            ) {
                                Icon(Icons.Default.Close, contentDescription = "Close")
                            }
                        }
                    }
                )

                // Content
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp)
                ) {
                    when {
                        isLoading -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.spacedBy(16.dp)
                                ) {
                                    CircularProgressIndicator()
                                    Text("Loading...")
                                }
                            }
                        }
                        wizardSession != null -> {
                            WizardStepContent(
                                session = wizardSession,
                                error = error,
                                discoveredItems = discoveredItems,
                                discoveryExecuted = discoveryExecuted,
                                isLoading = isLoading,
                                oauthUrl = oauthUrl,
                                awaitingOAuthCallback = awaitingOAuthCallback,
                                selectOptions = selectOptions,
                                onSubmit = onSubmitStep,
                                onSelectDiscoveredItem = onSelectDiscoveredItem,
                                onSubmitManualUrl = onSubmitManualUrl,
                                onRetryDiscovery = onRetryDiscovery,
                                onInitiateOAuth = onInitiateOAuth,
                                onCheckOAuthStatus = onCheckOAuthStatus
                            )
                        }
                        loadableAdapters != null -> {
                            TypeSelectionContent(
                                loadableAdapters = loadableAdapters,
                                error = error,
                                onSelectType = onSelectType,
                                onLoadDirectly = onLoadDirectly
                            )
                        }
                        else -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = error ?: "Unable to load adapter types",
                                    color = MaterialTheme.colorScheme.error
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
private fun TypeSelectionContent(
    loadableAdapters: LoadableAdaptersData,
    error: String?,
    onSelectType: (String) -> Unit,
    onLoadDirectly: (String) -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "Select Adapter Type",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )

        if (error != null) {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer
                )
            ) {
                Text(
                    text = error,
                    modifier = Modifier.padding(12.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }

        // Filter out adapters with missing dependencies - only show available ones
        val availableAdapters = loadableAdapters.adapters.filter { it.missingDependencies.isEmpty() }

        if (availableAdapters.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "No loadable adapters available",
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(availableAdapters) { adapter ->
                    AdapterTypeCard(
                        adapter = adapter,
                        onClick = {
                            if (adapter.requiresConfiguration) {
                                onSelectType(adapter.adapterType)
                            } else {
                                onLoadDirectly(adapter.adapterType)
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun AdapterTypeCard(
    adapter: LoadableAdapterData,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .wrapContentHeight()
            .testableClickable("item_adapter_type_${adapter.adapterType}") { onClick() },
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .wrapContentHeight()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = adapter.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                if (adapter.requiresConfiguration) {
                    Text(
                        text = "${adapter.stepCount} steps",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                } else if (!adapter.dependenciesAvailable) {
                    Text(
                        text = "Missing CLI",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                } else {
                    Text(
                        text = "Ready to load",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }

            Text(
                text = adapter.description,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Show workflow type / service types and OAuth requirement
            Row(
                modifier = Modifier.padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (adapter.requiresConfiguration && adapter.workflowType != null) {
                    SuggestionChip(
                        onClick = {},
                        label = { Text(adapter.workflowType, style = MaterialTheme.typography.labelSmall) }
                    )
                } else if (adapter.serviceTypes.isNotEmpty()) {
                    SuggestionChip(
                        onClick = {},
                        label = { Text(adapter.serviceTypes.first(), style = MaterialTheme.typography.labelSmall) }
                    )
                }
                if (adapter.requiresOauth) {
                    SuggestionChip(
                        onClick = {},
                        label = { Text("OAuth", style = MaterialTheme.typography.labelSmall) }
                    )
                }
            }

            // Show missing dependencies warning
            if (adapter.missingDependencies.isNotEmpty()) {
                Text(
                    text = "Missing: ${adapter.missingDependencies.joinToString(", ")}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }
    }
}

@Composable
private fun WizardStepContent(
    session: ConfigSessionData,
    error: String?,
    discoveredItems: List<DiscoveredItemData>,
    discoveryExecuted: Boolean,
    isLoading: Boolean,
    oauthUrl: String? = null,
    awaitingOAuthCallback: Boolean = false,
    selectOptions: List<SelectOptionData> = emptyList(),
    onSubmit: (Map<String, String>) -> Unit,
    onSelectDiscoveredItem: (DiscoveredItemData) -> Unit,
    onSubmitManualUrl: (String) -> Unit,
    onRetryDiscovery: () -> Unit,
    onInitiateOAuth: () -> Unit = {},
    onCheckOAuthStatus: () -> Unit = {}
) {
    val step = session.currentStep
    val fieldValues = remember(session.currentStepIndex) { mutableStateMapOf<String, String>() }
    var manualUrl by remember { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Progress indicator
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Step ${session.currentStepIndex + 1} of ${session.totalSteps}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            LinearProgressIndicator(
                progress = { (session.currentStepIndex + 1).toFloat() / session.totalSteps },
                modifier = Modifier.width(120.dp)
            )
        }

        if (step != null) {
            // Step title and description
            Text(
                text = step.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            step.description?.let { desc ->
                Text(
                    text = desc,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (error != null) {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = error,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            // Log the step type being rendered
            LaunchedEffect(step.stepType, session.currentStepIndex) {
                ai.ciris.mobile.shared.platform.PlatformLogger.i(
                    "WizardStepContent",
                    "=== RENDERING STEP === type='${step.stepType}', index=${session.currentStepIndex}, " +
                    "title='${step.title}', fields=${step.fields.size}, required=${step.required}"
                )
            }

            // Handle different step types
            when (step.stepType) {
                "discovery" -> {
                    // Discovery step - show discovered items and manual entry
                    DiscoveryStepContent(
                        discoveredItems = discoveredItems,
                        discoveryExecuted = discoveryExecuted,
                        isLoading = isLoading,
                        manualUrl = manualUrl,
                        onManualUrlChange = { manualUrl = it },
                        onSelectItem = onSelectDiscoveredItem,
                        onSubmitManualUrl = { onSubmitManualUrl(manualUrl) },
                        onRetryDiscovery = onRetryDiscovery
                    )
                }
                "oauth", "device_auth" -> {
                    // OAuth / device auth step
                    OAuthStepContent(
                        oauthUrl = oauthUrl,
                        awaitingCallback = awaitingOAuthCallback,
                        isLoading = isLoading,
                        onInitiateOAuth = onInitiateOAuth,
                        onCheckOAuthStatus = onCheckOAuthStatus
                    )
                }
                "select" -> {
                    // Select step - render options as checkboxes
                    SelectStepContent(
                        step = step,
                        selectOptions = selectOptions,
                        fieldValues = fieldValues,
                        isLastStep = session.currentStepIndex == session.totalSteps - 1,
                        onSubmit = onSubmit
                    )
                }
                "confirm" -> {
                    // Confirm step - show collected config summary
                    if (session.collectedConfig.isNotEmpty()) {
                        LazyColumn(
                            modifier = Modifier.weight(1f),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(session.collectedConfig.entries.toList()) { (key, value) ->
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp)
                                ) {
                                    Text(
                                        text = key.replace("_", " ")
                                            .replaceFirstChar { it.uppercaseChar() },
                                        style = MaterialTheme.typography.labelMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = if (key.contains("token", ignoreCase = true) ||
                                                   key.contains("secret", ignoreCase = true))
                                            "****" else value.take(200),
                                        style = MaterialTheme.typography.bodyMedium
                                    )
                                }
                            }
                        }
                    } else {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                    Button(
                        onClick = { onSubmit(emptyMap()) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_wizard_confirm") { onSubmit(emptyMap()) },
                        enabled = !isLoading
                    ) {
                        Text("Confirm & Apply")
                    }
                }
                else -> {
                    // Standard input step - show fields
                    InputStepContent(
                        step = step,
                        fieldValues = fieldValues,
                        isLastStep = session.currentStepIndex == session.totalSteps - 1,
                        onSubmit = onSubmit
                    )
                }
            }
        } else {
            // No current step (shouldn't happen normally)
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "No step data available",
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}

@Composable
private fun DiscoveryStepContent(
    discoveredItems: List<DiscoveredItemData>,
    discoveryExecuted: Boolean,
    isLoading: Boolean,
    manualUrl: String,
    onManualUrlChange: (String) -> Unit,
    onSelectItem: (DiscoveredItemData) -> Unit,
    onSubmitManualUrl: () -> Unit,
    onRetryDiscovery: () -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Show loading state during discovery
        if (isLoading && !discoveryExecuted) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    CircularProgressIndicator()
                    Text(
                        text = "Scanning network...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            // Discovered items section
            if (discoveredItems.isNotEmpty()) {
                Text(
                    text = "Found on your network:",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold
                )

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(discoveredItems) { item ->
                        DiscoveredItemCard(
                            item = item,
                            onClick = { onSelectItem(item) }
                        )
                    }
                }
            } else if (discoveryExecuted) {
                // No items found
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = "No devices found on network",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        TextButton(
                            onClick = onRetryDiscovery,
                            enabled = !isLoading
                        ) {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Retry scan")
                        }
                    }
                }
            }

            // Manual URL entry section
            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = "Or enter URL manually:",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold
            )

            OutlinedTextField(
                value = manualUrl,
                onValueChange = onManualUrlChange,
                label = { Text("URL") },
                placeholder = { Text("http://homeassistant.local:8123") },
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("input_manual_url"),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
            )

            Button(
                onClick = onSubmitManualUrl,
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("btn_submit_manual_url") { onSubmitManualUrl() },
                enabled = manualUrl.isNotBlank() && !isLoading
            ) {
                Text("Connect")
            }
        }
    }
}

@Composable
private fun DiscoveredItemCard(
    item: DiscoveredItemData,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("item_discovered_${item.id}") { onClick() },
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Text(
                text = item.label,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = item.value,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            // Show metadata if available (e.g., IP address, version)
            item.metadata.entries.take(2).forEach { (key, value) ->
                Text(
                    text = "$key: $value",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun ConfigField(
    field: ConfigFieldData,
    value: String,
    onValueChange: (String) -> Unit
) {
    val isPassword = field.fieldType == "password" || field.name.contains("secret", ignoreCase = true)

    Column(
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = {
                Row {
                    Text(field.label)
                    if (field.required) {
                        Text(" *", color = MaterialTheme.colorScheme.error)
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_config_${field.name}"),
            singleLine = field.fieldType != "textarea",
            visualTransformation = if (isPassword) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = when (field.fieldType) {
                "number" -> KeyboardOptions(keyboardType = KeyboardType.Number)
                "email" -> KeyboardOptions(keyboardType = KeyboardType.Email)
                "url" -> KeyboardOptions(keyboardType = KeyboardType.Uri)
                else -> KeyboardOptions.Default
            },
            supportingText = field.helpText?.let { { Text(it) } }
        )
    }
}

/**
 * OAuth step content — shows "Sign In" button, then "Waiting for authentication..." while polling.
 */
@Composable
private fun OAuthStepContent(
    oauthUrl: String?,
    awaitingCallback: Boolean,
    isLoading: Boolean,
    onInitiateOAuth: () -> Unit,
    onCheckOAuthStatus: () -> Unit = {}
) {
    // When awaiting callback, periodically re-check status.
    // This handles iOS app suspension (no debugger = coroutines frozen in background).
    if (awaitingCallback) {
        LaunchedEffect(Unit) {
            while (true) {
                kotlinx.coroutines.delay(2000)
                onCheckOAuthStatus()
            }
        }
    }

    // Log state on every recomposition
    LaunchedEffect(oauthUrl, awaitingCallback, isLoading) {
        ai.ciris.mobile.shared.platform.PlatformLogger.i(
            "OAuthStepContent",
            "[RENDER] oauthUrl=${if (oauthUrl != null) "${oauthUrl.take(80)}..." else "null"}, " +
            "awaitingCallback=$awaitingCallback, isLoading=$isLoading"
        )
    }

    // If we have an OAuth URL, open it automatically
    if (oauthUrl != null) {
        LaunchedEffect(oauthUrl) {
            ai.ciris.mobile.shared.platform.PlatformLogger.i(
                "OAuthStepContent",
                "=== OPENING BROWSER ==="
            )
            ai.ciris.mobile.shared.platform.PlatformLogger.i(
                "OAuthStepContent",
                "Full URL: $oauthUrl"
            )
            ai.ciris.mobile.shared.platform.openUrlInBrowser(oauthUrl)
            ai.ciris.mobile.shared.platform.PlatformLogger.i(
                "OAuthStepContent",
                "openUrlInBrowser() returned"
            )
        }
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (awaitingCallback) {
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Waiting for authentication...",
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Complete sign-in in your browser, then return here.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            // Show the URL for debugging
            if (oauthUrl != null) {
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = "If browser didn't open, tap below:",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                TextButton(
                    onClick = {
                        ai.ciris.mobile.shared.platform.PlatformLogger.i(
                            "OAuthStepContent",
                            "Manual browser open tapped: $oauthUrl"
                        )
                        ai.ciris.mobile.shared.platform.openUrlInBrowser(oauthUrl)
                    }
                ) {
                    Text("Open Browser", style = MaterialTheme.typography.labelSmall)
                }
            }
        } else {
            Text(
                text = "Tap below to sign in via your browser.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(16.dp))
            Button(
                onClick = {
                    ai.ciris.mobile.shared.platform.PlatformLogger.i(
                        "OAuthStepContent",
                        "Sign In button tapped — calling onInitiateOAuth()"
                    )
                    onInitiateOAuth()
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("btn_oauth_sign_in") { onInitiateOAuth() },
                enabled = !isLoading
            ) {
                Text("Sign In")
            }
        }
    }
}

/**
 * Select step content — renders fields (typically checkboxes/toggles) and a Next button.
 */
@Composable
private fun SelectStepContent(
    step: ai.ciris.mobile.shared.models.ConfigStepData,
    selectOptions: List<SelectOptionData>,
    fieldValues: MutableMap<String, String>,
    isLastStep: Boolean,
    onSubmit: (Map<String, String>) -> Unit
) {
    // Initialize defaults on first render
    LaunchedEffect(selectOptions) {
        for (option in selectOptions) {
            if (!fieldValues.containsKey(option.id)) {
                fieldValues[option.id] = option.defaultEnabled.toString()
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (selectOptions.isEmpty()) {
            // Options still loading
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(selectOptions) { option ->
                    val checked = (fieldValues[option.id] ?: option.defaultEnabled.toString()).toBooleanStrictOrNull() ?: true
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { fieldValues[option.id] = (!checked).toString() }
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Checkbox(
                            checked = checked,
                            onCheckedChange = { fieldValues[option.id] = it.toString() }
                        )
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = option.label,
                                style = MaterialTheme.typography.bodyLarge
                            )
                            option.description?.let {
                                Text(
                                    text = it,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }
        }

        Button(
            onClick = {
                // Backend expects {"selection": ["id1", "id2", ...]} for select steps
                val selectedIds = fieldValues.filter { it.value == "true" }.keys.toList()
                onSubmit(mapOf("selection" to selectedIds.joinToString(",")))
            },
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable(if (isLastStep) "btn_wizard_complete" else "btn_wizard_next") {
                    val selectedIds = fieldValues.filter { it.value == "true" }.keys.toList()
                    onSubmit(mapOf("selection" to selectedIds.joinToString(",")))
                },
            enabled = selectOptions.isNotEmpty()
        ) {
            Text(if (isLastStep) "Complete" else "Next")
        }
    }
}

/**
 * Input step content — standard text fields with a submit button.
 */
@Composable
private fun InputStepContent(
    step: ai.ciris.mobile.shared.models.ConfigStepData,
    fieldValues: MutableMap<String, String>,
    isLastStep: Boolean,
    onSubmit: (Map<String, String>) -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            items(step.fields) { field ->
                ConfigField(
                    field = field,
                    value = fieldValues[field.name] ?: field.defaultValue ?: "",
                    onValueChange = { fieldValues[field.name] = it }
                )
            }
        }

        Button(
            onClick = { onSubmit(fieldValues.toMap()) },
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable(
                    if (isLastStep) "btn_wizard_complete" else "btn_wizard_next"
                ) { onSubmit(fieldValues.toMap()) },
            enabled = step.fields.filter { it.required }.all {
                (fieldValues[it.name] ?: it.defaultValue)?.isNotBlank() == true
            }
        ) {
            Text(if (isLastStep) "Complete" else "Next")
        }
    }
}
