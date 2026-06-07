package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import androidx.compose.runtime.CompositionLocalProvider
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.NetworkPeersViewModel
import ai.ciris.mobile.shared.viewmodels.PeerTrustFilter
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch

/**
 * Network → Peers sub-screen (T-E-UI Batch A).
 *
 * Lists the local federation peers (canonical + organic). Each row shows the
 * trust glyph + alias + truncated key id. Trust state and canonical chip
 * follow Sideband / Reticulum cribsheet conventions:
 *  - icon glyph = trust signal (NOT just colour)
 *  - canonical peers get a CIRIS chip overlay (NOT removed from list)
 *
 * Filter row: All / Canonical / Trusted / Unknown / Untrusted / Blocked.
 * "Show CIRIS infrastructure" toggle is independent — toggles whether
 * canonical peers are included alongside organic peers.
 *
 * FAB → ModalBottomSheet for adding a peer from a NodeCode (paste / QR).
 * Tapping a row navigates to the parameterised peer-detail route.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkPeersScreen(
    apiClient: CIRISApiClient,
    onNavigateBack: () -> Unit,
    onPeerClick: (String) -> Unit,
    onIssueClick: (String) -> Unit = {},
) {
    val viewModel: NetworkPeersViewModel = viewModel { NetworkPeersViewModel(apiClient) }

    val peers by viewModel.peers.collectAsState()
    val filter by viewModel.filter.collectAsState()
    val showInfra by viewModel.showCirisInfrastructure.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val sheetOpen by viewModel.addPeerSheetOpen.collectAsState()
    val sheetInput by viewModel.addPeerInput.collectAsState()
    val sheetError by viewModel.addPeerError.collectAsState()
    val sheetInFlight by viewModel.addPeerInFlight.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.peers.title")) },
                navigationIcon = {
                    // Suppressed on compact viewports — global 3-state
                    // overlay handles back there.
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onNavigateBack,
                            modifier = Modifier.testableClickable("btn_network_peers_back") { onNavigateBack() },
                        ) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("mobile.common_back"),
                            )
                        }
                    } else {
                        // Reserve the global signet/back overlay's footprint so the
                        // TopAppBar title doesn't slide underneath it on compact.
                        Spacer(Modifier.width(56.dp))
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.refresh() },
                        enabled = !loading,
                        modifier = Modifier.testableClickable("btn_federation_peers_refresh") { viewModel.refresh() },
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("mobile.common_refresh"),
                        )
                    }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { viewModel.openAddPeerSheet() },
                icon = { Icon(Icons.Filled.Add, contentDescription = null) },
                text = { Text(localizedString("network.peers.add_peer_fab")) },
                modifier = Modifier.testableClickable("btn_add_peer") { viewModel.openAddPeerSheet() },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .testable("screen_federation_peers"),
        ) {
            FilterRow(
                filter = filter,
                showInfra = showInfra,
                onFilterChange = viewModel::setFilter,
                onShowInfraChange = viewModel::setShowCirisInfrastructure,
            )

            if (error != null) {
                Box(modifier = Modifier.padding(horizontal = 16.dp)) {
                    ErrorBanner(message = error!!, onDismiss = { viewModel.clearError() })
                }
            }

            if (loading && peers.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (peers.isEmpty()) {
                EmptyState()
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .testable("list_peers"),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(peers, key = { it.keyId }) { peer ->
                        PeerRow(peer = peer, onClick = { onPeerClick(peer.keyId) })
                    }
                    item { Spacer(Modifier.height(80.dp)) } // FAB clearance
                }
            }
        }

        if (sheetOpen) {
            ModalBottomSheet(
                onDismissRequest = { viewModel.closeAddPeerSheet() },
                sheetState = sheetState,
            ) {
                AddPeerSheet(
                    input = sheetInput,
                    error = sheetError,
                    inFlight = sheetInFlight,
                    onInputChange = viewModel::setAddPeerInput,
                    onCancel = { viewModel.closeAddPeerSheet() },
                    onSubmit = { viewModel.submitAddPeer() },
                    onScanQr = {
                        scope.launch {
                            snackbarHostState.showSnackbar(
                                message = "QR scanning coming soon",
                            )
                        }
                    },
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Filter row
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun FilterRow(
    filter: PeerTrustFilter,
    showInfra: Boolean,
    onFilterChange: (PeerTrustFilter) -> Unit,
    onShowInfraChange: (Boolean) -> Unit,
) {
    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterEntry(PeerTrustFilter.ALL, filter, "network.peers.filter_all", onFilterChange)
            FilterEntry(PeerTrustFilter.CANONICAL, filter, "network.peers.filter_canonical", onFilterChange)
            FilterEntry(PeerTrustFilter.TRUSTED, filter, "network.peers.filter_trusted", onFilterChange)
            FilterEntry(PeerTrustFilter.UNKNOWN, filter, "network.peers.filter_unknown", onFilterChange)
            FilterEntry(PeerTrustFilter.UNTRUSTED, filter, "network.peers.filter_untrusted", onFilterChange)
            FilterEntry(PeerTrustFilter.BLOCKED, filter, "network.peers.filter_blocked", onFilterChange)
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(
                checked = showInfra,
                onCheckedChange = onShowInfraChange,
                modifier = Modifier.testable("switch_show_infra"),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = localizedString("network.peers.show_infra"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun FilterEntry(
    target: PeerTrustFilter,
    selected: PeerTrustFilter,
    key: String,
    onSelect: (PeerTrustFilter) -> Unit,
) {
    FilterChip(
        selected = selected == target,
        onClick = { onSelect(target) },
        label = { Text(localizedString(key)) },
        modifier = Modifier.testableClickable("btn_filter_${target.name.lowercase()}") { onSelect(target) },
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// Peer row
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun PeerRow(peer: LocalPeerState, onClick: () -> Unit) {
    val (icon, tint) = trustGlyph(peer.trust)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("peer_row_${peer.keyId}") { onClick() },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
        onClick = onClick,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Leading: trust glyph
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(tint.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = peer.trust.wire,
                    tint = tint,
                    modifier = Modifier.size(22.dp),
                )
            }

            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = peer.aliasOverride ?: (peer.keyId.take(12) + "…"),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    if (peer.canonical) {
                        Spacer(Modifier.width(6.dp))
                        CanonicalChip()
                    }
                }
                Spacer(Modifier.height(2.dp))
                // Truncated key id render: <…last10>
                Text(
                    text = "<…${peer.keyId.takeLast(10)}>",
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            // Trailing: trust pill
            TrustPill(peer.trust)
        }
    }
}

@Composable
private fun CanonicalChip() {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(CIRISColors.SignetTeal.copy(alpha = 0.25f))
            .border(
                width = 1.dp,
                color = CIRISColors.SignetTeal.copy(alpha = 0.5f),
                shape = RoundedCornerShape(4.dp),
            )
            .padding(horizontal = 6.dp, vertical = 2.dp),
    ) {
        Text(
            text = localizedString("network.peers.canonical_chip"),
            style = MaterialTheme.typography.labelSmall,
            color = CIRISColors.SignetTeal,
            fontWeight = FontWeight.Bold,
            fontSize = 9.sp,
            letterSpacing = 0.5.sp,
        )
    }
}

@Composable
private fun TrustPill(trust: PeerTrustState) {
    val (_, color) = trustGlyph(trust)
    val key = when (trust) {
        PeerTrustState.TRUSTED -> "network.peers.trust_trusted"
        PeerTrustState.UNKNOWN -> "network.peers.trust_unknown"
        PeerTrustState.UNTRUSTED -> "network.peers.trust_untrusted"
        PeerTrustState.BLOCKED -> "network.peers.trust_blocked"
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(
            text = localizedString(key),
            style = MaterialTheme.typography.labelSmall,
            color = color,
            fontSize = 10.sp,
        )
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Add Peer bottom sheet
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun AddPeerSheet(
    input: String,
    error: String?,
    inFlight: Boolean,
    onInputChange: (String) -> Unit,
    onCancel: () -> Unit,
    onSubmit: () -> Unit,
    onScanQr: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 16.dp)
            .testable("sheet_add_peer")
            // Also expose dialog_add_peer here so the QA walk-test's
            // `wait_for_element(DIALOG_ADD_PEER)` resolves once the
            // ModalBottomSheet renders. Compose Multiplatform renders the
            // sheet content in a Popup tree on desktop, so the outer
            // ModalBottomSheet modifier doesn't necessarily reach `/tree`.
            .testable("dialog_add_peer"),
    ) {
        Text(
            text = localizedString("network.peers.add_peer_title"),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            // Mirror the dialog_add_peer tag on a Text inside the sheet
            // content so it's reliably discoverable across Compose
            // Multiplatform's popup composition boundary.
            modifier = Modifier.testable("dialog_add_peer"),
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = input,
            onValueChange = onInputChange,
            label = { Text(localizedString("network.peers.add_peer_paste_label")) },
            placeholder = { Text(localizedString("network.peers.add_peer_paste_placeholder")) },
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_add_peer_code"),
            minLines = 3,
            maxLines = 5,
            singleLine = false,
        )

        // Always render the error Text slot so `text_add_peer_error` is
        // discoverable by the QA walk-test post-submit even when the error
        // string hasn't arrived yet on the StateFlow. When there's no error,
        // we render an empty Text (height 0) — same compose-eagerness pattern
        // as T-T2 / T-T3.
        Spacer(Modifier.height(8.dp))
        Text(
            text = error.orEmpty(),
            style = MaterialTheme.typography.bodySmall,
            color = CIRISColors.ErrorRed,
            modifier = Modifier.testable("text_add_peer_error"),
        )

        Spacer(Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedButton(
                onClick = onScanQr,
                modifier = Modifier
                    .weight(1f)
                    .testableClickable("btn_scan_qr") { onScanQr() },
            ) {
                Text(localizedString("network.peers.add_peer_scan_qr"))
            }
            OutlinedButton(
                onClick = onCancel,
                modifier = Modifier
                    .weight(1f)
                    .testableClickable("btn_add_peer_cancel") { onCancel() },
            ) {
                Text(localizedString("network.peers.add_peer_cancel"))
            }
            Button(
                onClick = onSubmit,
                enabled = input.isNotBlank() && !inFlight,
                modifier = Modifier
                    .weight(1f)
                    .testableClickable("btn_add_peer_submit") { onSubmit() },
            ) {
                if (inFlight) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(localizedString("network.peers.add_peer_submit"))
                }
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Empty state
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun EmptyState() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp)
            .testable("empty_peers"),
        contentAlignment = Alignment.Center,
    ) {
        Card(
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface,
            ),
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(
                    imageVector = Icons.Filled.Person,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(36.dp),
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    text = localizedString("network.peers.empty_title"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = localizedString("network.peers.empty_subtitle"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Shared helpers (also used by NetworkPeerDetailScreen)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Return the (icon, tint) pair for a trust state. The icon IS the signal —
 * colour tint only reinforces. Mirrors Sideband convention.
 *
 * `account-check`/`account-question`/`account-cancel`/`account-alert` are
 * not present in the base material-icons set we ship; we substitute close
 * equivalents that read at-a-glance the same way:
 *  - TRUSTED  → Check (+ green) — affirmative
 *  - UNKNOWN  → Person (+ neutral) — placeholder, no judgement yet
 *  - BLOCKED  → Close (+ red) — refuse
 *  - UNTRUSTED → Warning (+ amber) — caution
 */
internal fun trustGlyph(trust: PeerTrustState): Pair<ImageVector, Color> = when (trust) {
    PeerTrustState.TRUSTED -> Icons.Filled.Check to CIRISColors.SuccessGreen
    PeerTrustState.UNKNOWN -> Icons.Filled.Person to CIRISColors.TextSecondary
    PeerTrustState.UNTRUSTED -> Icons.Filled.Warning to CIRISColors.WarningYellow
    PeerTrustState.BLOCKED -> CIRISIcons.close to CIRISColors.ErrorRed
}

