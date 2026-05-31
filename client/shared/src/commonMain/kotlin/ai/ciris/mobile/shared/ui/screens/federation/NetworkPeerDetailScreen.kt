package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.EdgePeerReachability
import ai.ciris.mobile.shared.models.federation.EdgeReachabilityEntry
import ai.ciris.mobile.shared.models.federation.FederationPeerSASResponse
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.PeerAppearance
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.NetworkPeerDetailViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.datetime.Clock

/**
 * Network → Peer Detail sub-screen (T-E-UI Batch A).
 *
 * Sections:
 *  - Header: trust glyph + alias + full 32-char hex key id with copy
 *  - Trust state segmented control (BLOCKED guarded by confirm dialog)
 *  - Reachability per medium (ratio bar + last-ok-relative timestamp)
 *  - SAS verification modal (5 words + 6 digits + cribsheet instructions)
 *  - Appearance editor (collapsible — icon + fg/bg hex picker)
 *  - Notes (read-only render today)
 *
 * Backend endpoints: getFederationPeer, getFederationPeerSAS,
 * setFederationPeerTrust, setFederationPeerAppearance.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkPeerDetailScreen(
    apiClient: CIRISApiClient,
    keyId: String,
    onNavigateBack: () -> Unit,
) {
    val viewModel: NetworkPeerDetailViewModel = viewModel(key = "peer_detail_$keyId") {
        NetworkPeerDetailViewModel(apiClient, keyId)
    }

    val detail by viewModel.detail.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val pendingTrust by viewModel.pendingTrust.collectAsState()
    val sasModalOpen by viewModel.sasModalOpen.collectAsState()
    val sas by viewModel.sas.collectAsState()
    val sasLoading by viewModel.sasLoading.collectAsState()
    val appearanceExpanded by viewModel.appearanceExpanded.collectAsState()
    val appearanceDraft by viewModel.appearanceDraft.collectAsState()
    val appearanceSaving by viewModel.appearanceSaving.collectAsState()
    val trustChangeInFlight by viewModel.trustChangeInFlight.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    pendingTrust?.let { target ->
        AlertDialog(
            onDismissRequest = { viewModel.cancelPendingTrust() },
            title = { Text(localizedString("network.peer_detail.confirm_block_title")) },
            text = { Text(localizedString("network.peer_detail.confirm_block_body")) },
            confirmButton = {
                TextButton(
                    onClick = { viewModel.confirmPendingTrust() },
                    modifier = Modifier.testableClickable("btn_confirm_block") { viewModel.confirmPendingTrust() },
                ) {
                    Text(
                        text = localizedString("network.peer_detail.confirm_block_button"),
                        color = CIRISColors.ErrorRed,
                    )
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { viewModel.cancelPendingTrust() },
                    modifier = Modifier.testableClickable("btn_cancel_block") { viewModel.cancelPendingTrust() },
                ) {
                    Text(localizedString("network.peer_detail.cancel_button"))
                }
            },
        )
    }

    if (sasModalOpen) {
        SASModal(
            sas = sas,
            loading = sasLoading,
            onClose = { viewModel.hideSAS() },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.peer_detail.title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_peer_detail_back") { onNavigateBack() },
                    ) {
                        Icon(
                            imageVector = CIRISIcons.arrowBack,
                            contentDescription = localizedString("mobile.common_back"),
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.refresh() },
                        enabled = !loading,
                        modifier = Modifier.testableClickable("btn_federation_peer_detail_refresh") { viewModel.refresh() },
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("mobile.common_refresh"),
                        )
                    }
                },
            )
        },
    ) { paddingValues ->
        Box(modifier = Modifier.padding(paddingValues).fillMaxSize()) {
            val current = detail
            if (current == null && loading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (current == null) {
                Box(modifier = Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                    Text(
                        text = localizedString("network.peer_detail.not_found"),
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .testable("screen_federation_peer_detail"),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    if (error != null) {
                        item { ErrorBanner(message = error!!, onDismiss = { viewModel.clearError() }) }
                    }
                    item { PeerHeader(peer = current.peer) }
                    item {
                        TrustStateSection(
                            currentTrust = current.peer.trust,
                            inFlight = trustChangeInFlight,
                            onTrustChange = { viewModel.requestTrust(it) },
                        )
                    }
                    item { ReachabilitySection(reachability = current.reachability) }
                    item { SASSection(onShowSAS = { viewModel.showSAS() }) }
                    item {
                        AppearanceSection(
                            expanded = appearanceExpanded,
                            draft = appearanceDraft,
                            saving = appearanceSaving,
                            onToggle = { viewModel.toggleAppearanceExpanded() },
                            onAppearanceChange = { viewModel.setAppearance(it) },
                            onSave = { viewModel.saveAppearance() },
                        )
                    }
                    item { NotesSection(notes = current.peer.notes) }
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Header
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun PeerHeader(peer: LocalPeerState) {
    val clipboard = LocalClipboardManager.current
    val (icon, tint) = trustGlyph(peer.trust)

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_peer_header"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(tint.copy(alpha = 0.15f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = icon,
                        contentDescription = peer.trust.wire,
                        tint = tint,
                        modifier = Modifier.size(26.dp),
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = peer.aliasOverride ?: (peer.keyId.take(12) + "…"),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    if (peer.canonical) {
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = localizedString("network.peers.canonical_chip"),
                            style = MaterialTheme.typography.labelSmall,
                            color = CIRISColors.SignetTeal,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                SelectionContainer(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "<${peer.keyId}>",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.testable("text_peer_detail_key_id"),
                    )
                }
                IconButton(
                    onClick = { clipboard.setText(AnnotatedString(peer.keyId)) },
                    modifier = Modifier.testableClickable("btn_copy_peer_key") {
                        clipboard.setText(AnnotatedString(peer.keyId))
                    },
                ) {
                    Icon(
                        imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                        contentDescription = localizedString("network.peer_detail.copy_key_id"),
                        tint = CIRISColors.AccentCyan,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Trust state section
// ═══════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TrustStateSection(
    currentTrust: PeerTrustState,
    inFlight: Boolean,
    onTrustChange: (PeerTrustState) -> Unit,
) {
    SectionCard(titleKey = "network.peer_detail.trust_state_title") {
        val options = listOf(
            PeerTrustState.TRUSTED,
            PeerTrustState.UNKNOWN,
            PeerTrustState.UNTRUSTED,
            PeerTrustState.BLOCKED,
        )
        SingleChoiceSegmentedButtonRow(
            modifier = Modifier
                .fillMaxWidth()
                .testable("seg_trust_state"),
        ) {
            options.forEachIndexed { index, state ->
                SegmentedButton(
                    selected = state == currentTrust,
                    onClick = { if (!inFlight) onTrustChange(state) },
                    shape = SegmentedButtonDefaults.itemShape(index = index, count = options.size),
                    modifier = Modifier.testableClickable("btn_trust_${state.wire}") {
                        if (!inFlight) onTrustChange(state)
                    },
                ) {
                    Text(
                        text = state.wire.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
        if (inFlight) {
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Reachability section
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun ReachabilitySection(reachability: EdgePeerReachability?) {
    SectionCard(titleKey = "network.peer_detail.reachability_title") {
        val byMedium = reachability?.byMedium.orEmpty()
        if (byMedium.isEmpty()) {
            Text(
                text = localizedString("network.peer_detail.reachability_empty"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                byMedium.forEach { (medium, entry) ->
                    ReachabilityRow(medium = medium, entry = entry)
                }
            }
        }
    }
}

@Composable
private fun ReachabilityRow(medium: String, entry: EdgeReachabilityEntry) {
    val ratio = entry.ratio.coerceIn(0.0, 1.0)
    val pct = (ratio * 100).toInt()

    Column(modifier = Modifier.testable("text_reachability_$medium")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = medium,
                style = MaterialTheme.typography.labelMedium,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.weight(1f),
            )
            Text(
                text = "$pct%",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = ratioColor(ratio),
            )
        }
        Spacer(Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { ratio.toFloat() },
            modifier = Modifier.fillMaxWidth(),
            color = ratioColor(ratio),
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            text = formatLastOk(entry.lastOkTs),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 10.sp,
        )
    }
}

private fun ratioColor(ratio: Double): Color = when {
    ratio >= 0.8 -> CIRISColors.SuccessGreen
    ratio >= 0.4 -> CIRISColors.WarningYellow
    else -> CIRISColors.ErrorRed
}

@Composable
private fun formatLastOk(lastOkTs: Long): String {
    if (lastOkTs <= 0L) return localizedString("network.peer_detail.last_ok_never")
    val nowMs = Clock.System.now().toEpochMilliseconds()
    val deltaMs = nowMs - lastOkTs
    if (deltaMs < 60_000L) return localizedString("network.peer_detail.last_ok_just_now")
    val minutes = deltaMs / 60_000L
    if (minutes < 60L) {
        return localizedString("network.peer_detail.last_ok_min_ago", mapOf("n" to minutes.toString()))
    }
    val hours = minutes / 60L
    if (hours < 24L) {
        return localizedString("network.peer_detail.last_ok_hours_ago", mapOf("n" to hours.toString()))
    }
    val days = hours / 24L
    return localizedString("network.peer_detail.last_ok_days_ago", mapOf("n" to days.toString()))
}

// ═══════════════════════════════════════════════════════════════════════════
// SAS section + modal
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun SASSection(onShowSAS: () -> Unit) {
    SectionCard(titleKey = "network.peer_detail.sas_title") {
        FilledTonalButton(
            onClick = onShowSAS,
            modifier = Modifier.testableClickable("btn_show_sas") { onShowSAS() },
        ) {
            Text(localizedString("network.peer_detail.sas_show_button"))
        }
    }
}

@Composable
private fun SASModal(
    sas: FederationPeerSASResponse?,
    loading: Boolean,
    onClose: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(localizedString("network.peer_detail.sas_modal_title")) },
        text = {
            Column(modifier = Modifier.testable("dialog_sas")) {
                if (loading || sas == null) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 16.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                } else {
                    Text(
                        text = localizedString("network.peer_detail.sas_words_label"),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    SelectionContainer {
                        Text(
                            text = sas.words.joinToString(" "),
                            style = MaterialTheme.typography.titleLarge,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold,
                            color = CIRISColors.AccentCyan,
                            modifier = Modifier.testable("text_sas_words"),
                        )
                    }
                    Spacer(Modifier.height(12.dp))
                    Text(
                        text = localizedString("network.peer_detail.sas_digits_label"),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    SelectionContainer {
                        Text(
                            text = sas.digits,
                            style = MaterialTheme.typography.headlineSmall,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold,
                            color = CIRISColors.AccentCyan,
                            modifier = Modifier.testable("text_sas_digits"),
                        )
                    }
                    Spacer(Modifier.height(16.dp))
                    Text(
                        text = localizedString("network.peer_detail.sas_instructions"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = onClose,
                modifier = Modifier.testableClickable("btn_close_sas") { onClose() },
            ) {
                Text(localizedString("network.peer_detail.sas_close"))
            }
        },
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// Appearance section
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun AppearanceSection(
    expanded: Boolean,
    draft: PeerAppearance,
    saving: Boolean,
    onToggle: () -> Unit,
    onAppearanceChange: (PeerAppearance) -> Unit,
    onSave: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_appearance"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("btn_appearance_expand") { onToggle() },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = localizedString("network.peer_detail.appearance_title"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                Icon(
                    imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(18.dp),
                )
            }

            if (expanded) {
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = draft.icon ?: "",
                    onValueChange = { onAppearanceChange(draft.copy(icon = it.ifBlank { null })) },
                    label = { Text(localizedString("network.peer_detail.appearance_icon_label")) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_appearance_icon"),
                    singleLine = true,
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = draft.fgColor ?: "",
                    onValueChange = { onAppearanceChange(draft.copy(fgColor = it.ifBlank { null })) },
                    label = { Text(localizedString("network.peer_detail.appearance_fg_label")) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_appearance_fg"),
                    singleLine = true,
                    placeholder = { Text("#00d4ff") },
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = draft.bgColor ?: "",
                    onValueChange = { onAppearanceChange(draft.copy(bgColor = it.ifBlank { null })) },
                    label = { Text(localizedString("network.peer_detail.appearance_bg_label")) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_appearance_bg"),
                    singleLine = true,
                    placeholder = { Text("#1a1a2e") },
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = onSave,
                    enabled = !saving,
                    modifier = Modifier.testableClickable("btn_save_appearance") { onSave() },
                ) {
                    if (saving) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text(localizedString("network.peer_detail.appearance_save"))
                    }
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Notes section
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun NotesSection(notes: String?) {
    SectionCard(titleKey = "network.peer_detail.notes_title") {
        if (notes.isNullOrBlank()) {
            Text(
                text = localizedString("network.peer_detail.notes_empty"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            SelectionContainer {
                Text(
                    text = notes,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Shared section card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun SectionCard(titleKey: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_section_${titleKey.substringAfterLast('.')}"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString(titleKey),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(8.dp))
            content()
        }
    }
}
