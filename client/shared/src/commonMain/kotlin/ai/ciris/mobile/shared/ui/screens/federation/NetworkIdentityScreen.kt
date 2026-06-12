package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.models.federation.FederationIdentityResponse
import ai.ciris.mobile.shared.models.federation.NodeCodeShareResponse
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import androidx.compose.runtime.CompositionLocalProvider
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.NetworkIdentityViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * Network → Identity sub-screen (T-E-UI Batch A).
 *
 * Exposes:
 *  - Federation signer key (32-char hex inside `<...>` per Reticulum cribsheet)
 *    with copy-to-clipboard and a QR placeholder.
 *  - Stats row: Edge crate version, total peers, canonical peer count.
 *  - Capabilities chip row.
 *  - "My Node Code" sub-card with copy + QR placeholder + share hint.
 *
 * Source-of-truth APIs: `getFederationIdentity()` and `getMyNodeCode()`.
 * Both endpoints land on Edge 1.0 — the screen renders gracefully while
 * waiting for either round-trip.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkIdentityScreen(
    apiClient: CIRISApiClient,
    onNavigateBack: () -> Unit,
    onIssueClick: (String) -> Unit = {},
) {
    val viewModel: NetworkIdentityViewModel = viewModel { NetworkIdentityViewModel(apiClient) }

    val identity by viewModel.identity.collectAsState()
    val nodeCode by viewModel.nodeCode.collectAsState()
    val federationId by viewModel.federationId.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.identity_card.title")) },
                navigationIcon = {
                    // Suppressed on compact viewports — the global 3-state
                    // overlay button in CIRISApp handles back navigation
                    // there to avoid the prior "back arrow + signet stacked"
                    // bug. Wider viewports (tablet/desktop) keep this arrow.
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onNavigateBack,
                            modifier = Modifier.testableClickable("btn_network_identity_back") { onNavigateBack() },
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
                        modifier = Modifier.testableClickable("btn_federation_identity_refresh") { viewModel.refresh() },
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
            // Bounded content (4 cards) — switched from LazyColumn to
            // Column.verticalScroll for the same reason as T-T4 on the hub:
            // narrow mobile viewports pushed NodeCodeCard below the
            // LazyColumn's compose window, so text_my_node_code and
            // btn_copy_my_node_code never reached /tree and the iOS
            // federation walk-test reported them missing.
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp)
                    .testable("screen_federation_identity"),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                if (error != null) {
                    ErrorBanner(message = error!!, onDismiss = { viewModel.clearError() })
                }
                IdentityHeaderCard(identity = identity)
                StatsRow(identity = identity)
                CapabilitiesCard(identity = identity)
                NodeCodeCard(nodeCode = nodeCode)
                FederationIdCard(federationId = federationId)
            }
            if (loading && identity == null) {
                CircularProgressIndicator(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 16.dp),
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Identity header card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun IdentityHeaderCard(identity: FederationIdentity?) {
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_identity_header"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.identity_card.signer_key_label"),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))

            val keyId = identity?.signerKeyId
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SelectionContainer(modifier = Modifier.weight(1f)) {
                    Text(
                        text = if (keyId.isNullOrBlank()) "—" else "<$keyId>",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 13.sp,
                        modifier = Modifier.testable("text_signer_key_id"),
                    )
                }
                // Always render the copy IconButton — `enabled` gates the
                // actual copy/state change. Wrapping in `if (!keyId.isNullOrBlank())`
                // hid `btn_copy_signer_key` from the QA walk-test during the
                // brief pre-seed window (same composition-timing race as the
                // hub IdentityCard fix in T-T2 / 868ad9226).
                run {
                    val hasKey = !keyId.isNullOrBlank()
                    IconButton(
                        onClick = {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                                scope.launch {
                                    delay(1500)
                                    copied = false
                                }
                            }
                        },
                        enabled = hasKey,
                        modifier = Modifier.testableClickable("btn_copy_signer_key") {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                            }
                        },
                    ) {
                        Icon(
                            imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                            contentDescription = localizedString("network.identity_card.copy_address"),
                            tint = CIRISColors.AccentCyan,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
            if (copied) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = localizedString("network.identity_card.copied"),
                    style = MaterialTheme.typography.labelSmall,
                    color = CIRISColors.SuccessGreen,
                )
            }

            Spacer(Modifier.height(12.dp))

            // QR placeholder
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                QrPlaceholder(modifier = Modifier.testable("img_identity_qr_placeholder"))
                Column {
                    Text(
                        text = localizedString("network.identity_card.qr_placeholder_label"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = localizedString("network.stats_strip.awaiting_edge_1_0"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Stats row (crate / peers total / peers canonical)
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun StatsRow(identity: FederationIdentity?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testable("row_identity_stats"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        StatChip(
            tag = "text_crate_version",
            label = localizedString(
                "network.identity_card.crate_version",
                mapOf("version" to (identity?.crateVersion ?: "—")),
            ),
            modifier = Modifier.weight(1f),
        )
        StatChip(
            tag = "text_peer_count_total",
            label = localizedString("network.identity_card.peers_total") + ": " + (identity?.peerCountTotal?.toString() ?: "—"),
            modifier = Modifier.weight(1f),
        )
        StatChip(
            tag = "text_peer_count_canonical",
            label = localizedString("network.identity_card.peers_canonical") + ": " + (identity?.peerCountCanonical?.toString() ?: "—"),
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun StatChip(tag: String, label: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.testable(tag),
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
        tonalElevation = 2.dp,
    ) {
        Box(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurface,
                fontFamily = FontFamily.Monospace,
                fontSize = 11.sp,
            )
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Capabilities card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun CapabilitiesCard(identity: FederationIdentity?) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_identity_capabilities"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.identity_card.capabilities_title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(8.dp))
            val capabilities = identity?.capabilities.orEmpty()
            if (capabilities.isEmpty()) {
                Text(
                    text = "—",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                FlowRowChips(capabilities)
            }
        }
    }
}

/**
 * Simple wrapping chip row — Compose Multiplatform doesn't expose the
 * experimental FlowRow on every platform, so we hand-wrap into rows.
 */
@Composable
private fun FlowRowChips(items: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // Render chips inline; rely on Row's overflow with wrapped Surface chips.
        // We split into chunks of 3 to keep things tidy on narrow widths.
        items.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { cap ->
                    AssistChip(
                        onClick = {},
                        label = {
                            Text(
                                text = cap,
                                style = MaterialTheme.typography.labelSmall,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 11.sp,
                            )
                        },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = CIRISColors.SignetTeal.copy(alpha = 0.15f),
                            labelColor = CIRISColors.AccentCyan,
                        ),
                        modifier = Modifier.testable("chip_capability_$cap"),
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Node Code card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun NodeCodeCard(nodeCode: NodeCodeShareResponse?) {
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_node_code"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.identity_card.node_code_title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(8.dp))

            val code = nodeCode?.code
            Row(
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                QrPlaceholder(modifier = Modifier.testable("img_node_code_qr_placeholder"))

                Column(modifier = Modifier.weight(1f)) {
                    SelectionContainer {
                        Text(
                            text = code ?: "—",
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 12.sp,
                            modifier = Modifier.testable("text_my_node_code"),
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = localizedString("network.identity_card.node_code_hint"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 16.sp,
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledTonalButton(
                    onClick = {
                        if (code != null) {
                            clipboard.setText(AnnotatedString(code))
                            copied = true
                            scope.launch {
                                delay(1500)
                                copied = false
                            }
                        }
                    },
                    enabled = code != null,
                    modifier = Modifier.testableClickable("btn_copy_my_node_code") {
                        if (code != null) {
                            clipboard.setText(AnnotatedString(code))
                            copied = true
                        }
                    },
                ) {
                    Icon(
                        imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(localizedString("network.identity_card.copy_node_code"))
                }
                if (copied) {
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = localizedString("network.identity_card.copied"),
                        style = MaterialTheme.typography.labelSmall,
                        color = CIRISColors.SuccessGreen,
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Federation ID card (persist LocalIdentityAggregate)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Compact "Federation ID" card rendered right next to the NodeCode
 * connect/share card. Shows persist's `key_id` — THE address production
 * lens / registry servers use to reach this node (CIRISPersist#198,
 * CEG §5.6.8.8.2) — plus a short form of the Ed25519 pubkey and chips
 * for which capability keys are present.
 *
 * Graceful 503: [federationId] is null both while loading and when the
 * backend reports the persist identity is still initializing, so the
 * card renders an "Identity initializing…" state instead of an error.
 */
@Composable
private fun FederationIdCard(federationId: FederationIdentityResponse?) {
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("federation_id_card"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.federation_id.title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = localizedString("network.federation_id.hint"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 16.sp,
            )
            Spacer(Modifier.height(8.dp))

            val aggregate = federationId?.aggregate
            val keyId = aggregate?.keyId
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SelectionContainer(modifier = Modifier.weight(1f)) {
                    Text(
                        text = keyId ?: localizedString("network.federation_id.initializing"),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        color = if (keyId != null) {
                            MaterialTheme.colorScheme.onSurface
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontSize = 13.sp,
                        modifier = Modifier.testable("federation_id_key"),
                    )
                }
                // Always render the copy IconButton — `enabled` gates the
                // actual copy/state change (same composition-timing-race
                // rationale as btn_copy_signer_key above).
                run {
                    val hasKey = !keyId.isNullOrBlank()
                    IconButton(
                        onClick = {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                                scope.launch {
                                    delay(1500)
                                    copied = false
                                }
                            }
                        },
                        enabled = hasKey,
                        modifier = Modifier.testableClickable("federation_id_copy") {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                            }
                        },
                    ) {
                        Icon(
                            imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                            contentDescription = localizedString("network.federation_id.copy_key_id"),
                            tint = CIRISColors.AccentCyan,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
            if (copied) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = localizedString("network.identity_card.copied"),
                    style = MaterialTheme.typography.labelSmall,
                    color = CIRISColors.SuccessGreen,
                )
            }

            if (aggregate != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = localizedString("network.federation_id.pubkey_label") +
                        ": " + pubkeyShortForm(aggregate.ed25519PubkeyB64),
                    style = MaterialTheme.typography.labelMedium,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                // (stable tag, localized label) — present = non-null key material.
                val capabilities = buildList {
                    add("signing" to localizedString("network.federation_id.cap_signing"))
                    if (aggregate.hasPqc) {
                        add("pqc" to localizedString("network.federation_id.cap_pqc"))
                    }
                    if (aggregate.hasReticulum) {
                        add("reticulum" to localizedString("network.federation_id.cap_reticulum"))
                    }
                    if (aggregate.hasContentEncryption) {
                        add("content" to localizedString("network.federation_id.cap_content"))
                    }
                }
                FederationCapabilityChips(capabilities)
            }
        }
    }
}

/**
 * Capability-key chips for the Federation ID card. Mirrors
 * [FlowRowChips] visually but takes (stable tag, localized label)
 * pairs so test tags stay locale-independent.
 */
@Composable
private fun FederationCapabilityChips(items: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (tag, label) ->
                    AssistChip(
                        onClick = {},
                        label = {
                            Text(
                                text = label,
                                style = MaterialTheme.typography.labelSmall,
                                fontSize = 11.sp,
                            )
                        },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = CIRISColors.SignetTeal.copy(alpha = 0.15f),
                            labelColor = CIRISColors.AccentCyan,
                        ),
                        modifier = Modifier.testable("chip_federation_id_$tag"),
                    )
                }
            }
        }
    }
}

/**
 * Short display form of a base64 pubkey: hex of the first 6 decoded
 * bytes (12 hex chars) + ellipsis. No multiplatform SHA-256 is wired
 * into commonMain, so this is a key-prefix short form, not a hash
 * fingerprint; falls back to the b64 head when decoding fails.
 */
@OptIn(ExperimentalEncodingApi::class)
internal fun pubkeyShortForm(pubkeyB64: String): String {
    return try {
        val bytes = Base64.decode(pubkeyB64)
        bytes.take(6).joinToString("") { byte ->
            (byte.toInt() and 0xFF).toString(16).padStart(2, '0')
        } + "…"
    } catch (_: Exception) {
        pubkeyB64.take(12) + "…"
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Shared helpers
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun QrPlaceholder(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .size(64.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surface)
            .border(
                width = 1.dp,
                color = CIRISColors.AccentCyan.copy(alpha = 0.4f),
                shape = RoundedCornerShape(8.dp),
            ),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = CIRISIcons.identity,
            contentDescription = null,
            tint = CIRISColors.AccentCyan,
            modifier = Modifier.size(36.dp),
        )
    }
}

@Composable
internal fun ErrorBanner(message: String, onDismiss: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("banner_federation_error"),
        colors = CardDefaults.cardColors(
            containerColor = CIRISColors.ErrorRed.copy(alpha = 0.15f),
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Filled.Info,
                contentDescription = null,
                tint = CIRISColors.ErrorRed,
                modifier = Modifier.size(18.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = message,
                style = MaterialTheme.typography.bodySmall,
                color = CIRISColors.ErrorRed,
                modifier = Modifier.weight(1f),
            )
            IconButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_dismiss_error") { onDismiss() },
            ) {
                Icon(
                    imageVector = CIRISIcons.close,
                    contentDescription = null,
                    tint = CIRISColors.ErrorRed,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
    }
}
