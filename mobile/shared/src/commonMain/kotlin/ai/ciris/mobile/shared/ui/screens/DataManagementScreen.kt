package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.DataManagementViewModel
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp

/**
 * Data Management screen for DSAR self-service.
 *
 * Provides two main functions:
 * 1. Delete Local Account & Data - Factory reset of all local data
 * 2. Delete Opt-In Traces Sent - Request deletion of CIRISLens traces (GDPR Art. 17)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DataManagementScreen(
    viewModel: DataManagementViewModel,
    onNavigateBack: () -> Unit,
    onResetSetup: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isLoading by viewModel.isLoading.collectAsState()
    val lensIdentifier by viewModel.lensIdentifier.collectAsState()
    val accordSettings by viewModel.accordSettings.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()
    val isDeletingLensTraces by viewModel.isDeletingLensTraces.collectAsState()
    val lensDeletionResult by viewModel.lensDeletionResult.collectAsState()
    val isFactoryResetting by viewModel.isFactoryResetting.collectAsState()
    val factoryResetSuccess by viewModel.factoryResetSuccess.collectAsState()
    val isLoadingAdapter by viewModel.isLoadingAdapter.collectAsState()

    var showFactoryResetDialog by remember { mutableStateOf(false) }
    var showDeleteTracesDialog by remember { mutableStateOf(false) }
    var deletionReason by remember { mutableStateOf("") }

    val snackbarHostState = remember { SnackbarHostState() }

    // Load data when screen is first shown
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    // Handle factory reset success - trigger app restart
    LaunchedEffect(factoryResetSuccess) {
        if (factoryResetSuccess) {
            viewModel.clearFactoryResetSuccess()
            onResetSetup()
        }
    }

    // Show errors in snackbar
    LaunchedEffect(errorMessage) {
        errorMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearError()
        }
    }

    // Show deletion result
    LaunchedEffect(lensDeletionResult) {
        lensDeletionResult?.let { result ->
            val message = if (result.success) {
                "Trace deletion requested successfully"
            } else {
                "Deletion failed: ${result.message}"
            }
            snackbarHostState.showSnackbar(message)
            viewModel.clearDeletionResult()
        }
    }

    // Factory reset confirmation dialog
    if (showFactoryResetDialog) {
        AlertDialog(
            onDismissRequest = { showFactoryResetDialog = false },
            title = { Text("Delete Account & Data?") },
            text = {
                Text(
                    "This will permanently delete all local data:\n\n" +
                    "\u2022 Conversations and chat history\n" +
                    "\u2022 Memory and knowledge graph\n" +
                    "\u2022 Audit logs and signing keys\n" +
                    "\u2022 All configuration\n\n" +
                    "Transaction records (amounts, dates, credit balance) are retained " +
                    "server-side for 10 years as required by EU AI Act and tax compliance " +
                    "(see ciris.ai/privacy). No conversation content is ever stored on our servers.\n\n" +
                    "This cannot be undone."
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
                    Text("Delete Account & Data")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showFactoryResetDialog = false },
                    modifier = Modifier.testableClickable("btn_factory_reset_cancel") {
                        showFactoryResetDialog = false
                    }
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    // Delete lens traces confirmation dialog
    if (showDeleteTracesDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteTracesDialog = false },
            title = { Text("Delete Opt-In Traces?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        "This will request deletion of all traces sent to CIRISLens under your agent ID.\n\n" +
                        "Your agent ID hash: ${accordSettings?.agentIdHash ?: "Loading..."}\n\n" +
                        "This action:\n" +
                        "\u2022 Sends a deletion request to CIRISLens\n" +
                        "\u2022 Revokes your opt-in consent (stops future collection)\n" +
                        "\u2022 Is irreversible\n\n" +
                        "You can re-enable trace collection later if desired."
                    )

                    OutlinedTextField(
                        value = deletionReason,
                        onValueChange = { deletionReason = it },
                        label = { Text("Reason (optional)") },
                        placeholder = { Text("e.g., \"Leaving service\", \"Privacy preference\"") },
                        modifier = Modifier.fillMaxWidth(),
                        maxLines = 2
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        showDeleteTracesDialog = false
                        viewModel.deleteLensTraces(deletionReason.takeIf { it.isNotBlank() })
                        deletionReason = ""
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.testableClickable("btn_delete_traces_confirm") {
                        showDeleteTracesDialog = false
                        viewModel.deleteLensTraces(deletionReason.takeIf { it.isNotBlank() })
                        deletionReason = ""
                    }
                ) {
                    Text("Delete Traces")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showDeleteTracesDialog = false
                        deletionReason = ""
                    },
                    modifier = Modifier.testableClickable("btn_delete_traces_cancel") {
                        showDeleteTracesDialog = false
                        deletionReason = ""
                    }
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Data Management") },
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
                    Text("Loading data management info...")
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
                // Header
                Text(
                    text = "Your Data Rights",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.primary
                )

                Text(
                    text = "CIRIS respects your data rights under GDPR, CCPA, and the EU AI Act. " +
                            "Use these options to manage or delete your data.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // Privacy & Data Practices summary
                PrivacyInfoCard()

                // Section 1: Delete Opt-In Traces
                Text(
                    text = "CIRISLens Trace Data",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                DeleteTracesCard(
                    accordSettings = accordSettings,
                    isDeleting = isDeletingLensTraces,
                    isLoadingAdapter = isLoadingAdapter,
                    onDeleteClick = { showDeleteTracesDialog = true },
                    onConsentChanged = { consent -> viewModel.updateAccordConsent(consent) },
                    onEnableAdapter = { viewModel.enableAccordMetrics() }
                )

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

                // Section 2: Delete Local Account & Data
                Text(
                    text = "Local Device Data",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                DeleteLocalDataCard(
                    isResetting = isFactoryResetting,
                    onDeleteClick = { showFactoryResetDialog = true }
                )
            }
        }
    }
}

/**
 * Card for managing CIRISLens trace collection and deletion.
 * Uses accordSettings as the source of truth (matches adapter state shown in Adapters screen).
 */
@Composable
private fun DeleteTracesCard(
    accordSettings: ai.ciris.mobile.shared.api.AccordSettingsData?,
    isDeleting: Boolean,
    isLoadingAdapter: Boolean,
    onDeleteClick: () -> Unit,
    onConsentChanged: (Boolean) -> Unit,
    onEnableAdapter: () -> Unit
) {
    val uriHandler = LocalUriHandler.current
    // accordSettings is the source of truth for consent (matches adapter state)
    val isConsentActive = accordSettings?.consentGiven == true
    // Adapter is loaded if we have accord settings
    val adapterLoaded = accordSettings != null

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isConsentActive)
                MaterialTheme.colorScheme.primaryContainer
            else
                MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "CIRISAccord Trace Collection",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            // Info text - always show
            Text(
                text = "CIRISAccord is an opt-in research partnership. When enabled, anonymized " +
                        "interaction traces help improve AI safety research. Traces are stored " +
                        "under a hashed agent ID, not your name or email.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Text(
                text = "Learn more: ciris.ai/ciris-scoring",
                style = MaterialTheme.typography.bodySmall.copy(
                    textDecoration = TextDecoration.Underline
                ),
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable {
                    uriHandler.openUri("https://ciris.ai/ciris-scoring")
                }
            )

            // Adapter-specific controls - only show when adapter is loaded
            accordSettings?.let { settings ->
                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                // Status info
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    InfoRow("Agent ID Hash", settings.agentIdHash)
                    InfoRow("Events Sent to Lens", settings.eventsSent.toString())
                    if (settings.eventsReceived > 0 || settings.eventsQueued > 0) {
                        InfoRow("Events Captured", settings.eventsReceived.toString())
                        if (settings.eventsQueued > 0) {
                            InfoRow("Events Queued", settings.eventsQueued.toString())
                        }
                    }
                    settings.traceLevel?.let { level ->
                        InfoRow("Detail Level", level)
                    }
                    settings.endpointUrl?.let { url ->
                        InfoRow("Endpoint", url.take(40) + if (url.length > 40) "..." else "")
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                // Consent toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Trace Collection",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = if (isConsentActive)
                                "Anonymized traces are being sent to CIRISLens"
                            else
                                "Trace collection is disabled",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = isConsentActive,
                        onCheckedChange = { onConsentChanged(it) },
                        modifier = Modifier.testableClickable("switch_consent") {
                            onConsentChanged(!isConsentActive)
                        }
                    )
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                // Delete/Revoke section - always show deletion request option
                val traceCount = settings.eventsSent

                Text(
                    text = "Request Data Deletion from CIRISLens",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )

                Text(
                    text = if (traceCount > 0) {
                        "Request deletion of all $traceCount traces sent to CIRISLens and revoke consent. " +
                            "This is irreversible."
                    } else {
                        "Send a deletion request to CIRISLens for any traces associated with your agent ID " +
                            "and revoke consent. This ensures no data is retained."
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Button(
                    onClick = onDeleteClick,
                    enabled = !isDeleting,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_delete_traces") {
                        if (!isDeleting) onDeleteClick()
                    }
                ) {
                    if (isDeleting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = MaterialTheme.colorScheme.onError,
                            strokeWidth = 2.dp
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(
                        if (isDeleting) "Processing..."
                        else "Delete Traces & Revoke Consent"
                    )
                }
            }

            // Adapter not loaded - show enable button
            if (!adapterLoaded) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                Button(
                    onClick = onEnableAdapter,
                    enabled = !isLoadingAdapter,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    ),
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_enable_accord") {
                        if (!isLoadingAdapter) onEnableAdapter()
                    }
                ) {
                    if (isLoadingAdapter) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                            strokeWidth = 2.dp
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(if (isLoadingAdapter) "Enabling..." else "Enable CIRISAccord")
                }
            }
        }
    }
}

/**
 * Card for deleting all local data (factory reset).
 */
@Composable
private fun DeleteLocalDataCard(
    isResetting: Boolean,
    onDeleteClick: () -> Unit
) {
    val uriHandler = LocalUriHandler.current

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
                text = "Delete Account & Data",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onErrorContainer
            )

            Text(
                text = "Permanently deletes all local data including:\n\n" +
                        "\u2022 Conversations and chat history\n" +
                        "\u2022 Memory and knowledge graph\n" +
                        "\u2022 Audit logs and signing keys\n" +
                        "\u2022 All configuration\n\n" +
                        "All agent data \u2014 conversations, memory graphs, and configuration \u2014 " +
                        "is stored exclusively on this device and is completely removed by this action.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = 0.8f)
            )

            Text(
                text = "Transaction records (amounts, dates, account email) are retained " +
                        "server-side for 10 years as required by EU AI Act and tax " +
                        "compliance. No conversation content is ever stored on our servers. " +
                        "To request deletion of billing records, contact privacy@ciris.ai.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = 0.8f)
            )

            Button(
                onClick = onDeleteClick,
                enabled = !isResetting,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                ),
                modifier = Modifier.fillMaxWidth().testableClickable("btn_factory_reset") {
                    if (!isResetting) onDeleteClick()
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
                Text(if (isResetting) "Deleting..." else "Delete Account & Data")
            }
        }
    }
}

/**
 * Card summarizing privacy practices, data retention, user rights, and contact info.
 * Ensures compliance with GDPR Arts. 13-14, CCPA, and EU AI Act transparency requirements.
 */
@Composable
private fun PrivacyInfoCard() {
    val uriHandler = LocalUriHandler.current

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
                text = "How CIRIS Handles Your Data",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            // LLM zero data retention
            Text(
                text = "LLM Services",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = "All LLM providers (Groq, OpenRouter, Together AI) are configured " +
                        "for zero data retention. Your conversations are processed and " +
                        "immediately discarded \u2014 never stored on remote servers or used " +
                        "to train AI models. If you use your own API key (BYOK), the same " +
                        "zero-retention policy applies via our provider configuration.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Local data
            Text(
                text = "Local Device Data",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = "All conversations, memory graphs, audit logs, and configuration " +
                        "are stored exclusively on this device. CIRIS servers never receive " +
                        "or store your conversation content. Audit trails are retained " +
                        "indefinitely on-device with a cryptographic hash chain for integrity. " +
                        "You can delete all local data at any time using the option below.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Billing records
            Text(
                text = "Billing & Transaction Records",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = "Transaction records (amounts, dates, account email) are processed " +
                        "via Stripe and retained for 10 years as required by EU AI Act and " +
                        "tax compliance. These records never contain conversation content. " +
                        "To request deletion of billing records, contact privacy@ciris.ai.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Your rights
            Text(
                text = "Your Rights",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = "Under GDPR and CCPA, you have the right to:\n" +
                        "\u2022 Access \u2014 request a copy of your data\n" +
                        "\u2022 Erasure \u2014 request deletion (90-day decay protocol)\n" +
                        "\u2022 Rectification \u2014 correct inaccurate data\n" +
                        "\u2022 Portability \u2014 export in JSON/CSV format\n" +
                        "\u2022 Restriction \u2014 limit how your data is processed\n" +
                        "\u2022 Object \u2014 opt out of specific processing\n\n" +
                        "DSAR requests are responded to within 30 days.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Contact & links
            Text(
                text = "Contact: privacy@ciris.ai",
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable {
                    uriHandler.openUri("mailto:privacy@ciris.ai")
                }
            )

            Text(
                text = "Full Privacy Policy: ciris.ai/privacy",
                style = MaterialTheme.typography.bodySmall.copy(
                    textDecoration = TextDecoration.Underline
                ),
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable {
                    uriHandler.openUri("https://ciris.ai/privacy")
                }
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
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium
        )
    }
}
