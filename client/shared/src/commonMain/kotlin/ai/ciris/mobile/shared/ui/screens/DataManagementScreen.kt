package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.DataManagementViewModel
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
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
    val isResetting by viewModel.isResetting.collectAsState()
    val resetSuccess by viewModel.resetSuccess.collectAsState()
    val isWipingSigningKey by viewModel.isWipingSigningKey.collectAsState()
    val wipeSigningKeySuccess by viewModel.wipeSigningKeySuccess.collectAsState()
    val isLoadingAdapter by viewModel.isLoadingAdapter.collectAsState()

    var showResetDialog by remember { mutableStateOf(false) }
    var showWipeSigningKeyDialog by remember { mutableStateOf(false) }
    var showDeleteTracesDialog by remember { mutableStateOf(false) }
    var deletionReason by remember { mutableStateOf("") }

    val snackbarHostState = remember { SnackbarHostState() }

    // Load data when screen is first shown
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    // Handle reset success - trigger app restart (signing key preserved)
    LaunchedEffect(resetSuccess) {
        if (resetSuccess) {
            viewModel.clearFactoryResetSuccess()
            onResetSetup()
        }
    }

    // Handle wipe signing key success - trigger app restart (wallet access destroyed)
    LaunchedEffect(wipeSigningKeySuccess) {
        if (wipeSigningKeySuccess) {
            viewModel.clearWipeSigningKeySuccess()
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
                LocalizationHelper.getString("mobile.data_deletion_success")
            } else {
                "${LocalizationHelper.getString("mobile.data_deletion_failed")}: ${result.message}"
            }
            snackbarHostState.showSnackbar(message)
            viewModel.clearDeletionResult()
        }
    }

    // Reset account confirmation dialog (preserves signing key)
    if (showResetDialog) {
        AlertDialog(
            onDismissRequest = { showResetDialog = false },
            title = { Text(localizedString("mobile.data_reset_confirm")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(localizedString("mobile.data_reset_confirm_body"))
                    Text(
                        text = localizedString("mobile.data_reset_wallet_preserved"),
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        showResetDialog = false
                        viewModel.factoryReset()
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.testableClickable("btn_reset_confirm") {
                        showResetDialog = false
                        viewModel.factoryReset()
                    }
                ) {
                    Text(localizedString("mobile.data_reset_account"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showResetDialog = false },
                    modifier = Modifier.testableClickable("btn_reset_cancel") {
                        showResetDialog = false
                    }
                ) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }

    // DANGER: Wipe signing key confirmation dialog (destroys wallet access)
    if (showWipeSigningKeyDialog) {
        AlertDialog(
            onDismissRequest = { showWipeSigningKeyDialog = false },
            title = {
                Text(
                    localizedString("mobile.data_wipe_key_confirm"),
                    color = MaterialTheme.colorScheme.error
                )
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = localizedString("mobile.data_wipe_key_warning"),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error
                    )
                    Text(localizedString("mobile.data_wipe_key_body"))
                    Text(
                        text = localizedString("mobile.data_wipe_key_funds_lost"),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        showWipeSigningKeyDialog = false
                        viewModel.wipeSigningKey()
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.testableClickable("btn_wipe_key_confirm") {
                        showWipeSigningKeyDialog = false
                        viewModel.wipeSigningKey()
                    }
                ) {
                    Text(localizedString("mobile.data_wipe_key_button"))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showWipeSigningKeyDialog = false },
                    modifier = Modifier.testableClickable("btn_wipe_key_cancel") {
                        showWipeSigningKeyDialog = false
                    }
                ) {
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }

    // Delete lens traces confirmation dialog
    if (showDeleteTracesDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteTracesDialog = false },
            title = { Text(localizedString("mobile.data_delete_traces")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        localizedString("mobile.data_delete_traces_body")
                            .replace("{hash}", accordSettings?.agentIdHash ?: localizedString("mobile.common_loading"))
                    )

                    OutlinedTextField(
                        value = deletionReason,
                        onValueChange = { deletionReason = it },
                        label = { Text(localizedString("mobile.data_reason")) },
                        placeholder = { Text(localizedString("mobile.data_reason_placeholder")) },
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
                    Text(localizedString("mobile.data_delete_traces_button"))
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
                    Text(localizedString("mobile.common_cancel"))
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.nav_data_management")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = localizedString("mobile.common_back")
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
                            contentDescription = localizedString("mobile.common_refresh")
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
                    Text(localizedString("mobile.data_loading"))
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
                    text = localizedString("mobile.data_rights_title"),
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.primary
                )

                Text(
                    text = localizedString("mobile.data_rights_desc_full"),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // Privacy & Data Practices summary
                PrivacyInfoCard()

                // Section 1: Delete Opt-In Traces
                Text(
                    text = localizedString("mobile.data_lens_title"),
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

                // Section 2: Reset Account (preserves signing key for wallet access)
                Text(
                    text = localizedString("mobile.data_reset_title"),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                ResetAccountCard(
                    isResetting = isResetting,
                    onResetClick = { showResetDialog = true }
                )

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

                // Section 3: DANGER - Wipe Signing Key (destroys wallet access)
                Text(
                    text = localizedString("mobile.data_wipe_key_title"),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.error
                )

                WipeSigningKeyCard(
                    isWiping = isWipingSigningKey,
                    onWipeClick = { showWipeSigningKeyDialog = true }
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
                text = localizedString("mobile.data_accord_title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            // Info text - always show
            Text(
                text = localizedString("mobile.data_accord_desc_full"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Text(
                text = localizedString("mobile.data_accord_learn"),
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
                    InfoRow(localizedString("mobile.data_agent_hash_label"), settings.agentIdHash)
                    InfoRow(localizedString("mobile.data_events_sent"), settings.eventsSent.toString())
                    if (settings.eventsReceived > 0 || settings.eventsQueued > 0) {
                        InfoRow(localizedString("mobile.data_events_captured"), settings.eventsReceived.toString())
                        if (settings.eventsQueued > 0) {
                            InfoRow(localizedString("mobile.data_events_queued"), settings.eventsQueued.toString())
                        }
                    }
                    settings.traceLevel?.let { level ->
                        InfoRow(localizedString("mobile.data_detail_level"), level)
                    }
                    settings.endpointUrl?.let { url ->
                        InfoRow(localizedString("mobile.data_endpoint"), url.take(40) + if (url.length > 40) "..." else "")
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
                            text = localizedString("mobile.data_trace_collection"),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = if (isConsentActive)
                                localizedString("mobile.data_traces_active")
                            else
                                localizedString("mobile.data_traces_disabled"),
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
                    text = localizedString("mobile.data_delete_lens"),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )

                Text(
                    text = if (traceCount > 0) {
                        localizedString("mobile.data_delete_lens_desc_count")
                            .replace("{count}", traceCount.toString())
                    } else {
                        localizedString("mobile.data_delete_lens_desc_zero")
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
                        if (isDeleting) localizedString("mobile.data_processing")
                        else localizedString("mobile.data_delete_traces_revoke")
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
                    Text(if (isLoadingAdapter) localizedString("mobile.data_enabling") else localizedString("mobile.data_enable_accord"))
                }
            }
        }
    }
}

/**
 * Card for resetting account data while preserving the signing key.
 * This allows wallet access to be retained after reset.
 */
@Composable
private fun ResetAccountCard(
    isResetting: Boolean,
    onResetClick: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.tertiaryContainer
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.data_reset_account"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onTertiaryContainer
            )

            Text(
                text = localizedString("mobile.data_reset_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.8f)
            )

            Text(
                text = localizedString("mobile.data_reset_preserves"),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )

            Button(
                onClick = onResetClick,
                enabled = !isResetting,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.tertiary
                ),
                modifier = Modifier.fillMaxWidth().testableClickable("btn_reset_account") {
                    if (!isResetting) onResetClick()
                }
            ) {
                if (isResetting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = MaterialTheme.colorScheme.onTertiary,
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (isResetting) localizedString("mobile.data_resetting") else localizedString("mobile.data_reset_account"))
            }
        }
    }
}

/**
 * Card for DANGER zone - wiping the agent signing key.
 * WARNING: This destroys wallet access permanently!
 */
@Composable
private fun WipeSigningKeyCard(
    isWiping: Boolean,
    onWipeClick: () -> Unit
) {
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
                text = localizedString("mobile.data_wipe_key_danger"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.error
            )

            Text(
                text = localizedString("mobile.data_wipe_key_desc"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = 0.8f)
            )

            Text(
                text = localizedString("mobile.data_wipe_key_warning_short"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.error
            )

            Text(
                text = localizedString("mobile.data_wipe_key_deletes"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = 0.8f)
            )

            Button(
                onClick = onWipeClick,
                enabled = !isWiping,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                ),
                modifier = Modifier.fillMaxWidth().testableClickable("btn_wipe_signing_key") {
                    if (!isWiping) onWipeClick()
                }
            ) {
                if (isWiping) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = MaterialTheme.colorScheme.onError,
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (isWiping) localizedString("mobile.data_wiping") else localizedString("mobile.data_wipe_key_button"))
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
                text = localizedString("mobile.data_how_title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )

            // LLM zero data retention
            Text(
                text = localizedString("mobile.data_llm_title"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.data_llm_desc_full"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Local data
            Text(
                text = localizedString("mobile.data_local_title"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.data_local_desc_full"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Billing records
            Text(
                text = localizedString("mobile.data_billing_title"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.data_billing_desc_full"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Your rights
            Text(
                text = localizedString("mobile.data_your_rights"),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = localizedString("mobile.data_your_rights_desc_full"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))

            // Contact & links
            Text(
                text = localizedString("mobile.data_contact"),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable {
                    uriHandler.openUri("mailto:privacy@ciris.ai")
                }
            )

            Text(
                text = localizedString("mobile.data_privacy_policy"),
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
