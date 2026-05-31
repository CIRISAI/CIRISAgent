package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.AgentMode
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.AgentModeSelector
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.NetworkViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Network — federation transport substrate operator hub (2.9.4).
 *
 * Hub-and-spoke replacement for the prior 5-tab scaffold. The hub itself
 * exposes:
 *   1. Identity card — federation signer_key_id with copy-to-clipboard + QR
 *      placeholder (Edge 1.0 ratchet/rotation lands in a sibling release).
 *   2. Mode selector card — Client / Proxy (default) / Server segmented control
 *      backed by [NetworkViewModel] talking to /v1/system/agent-mode.
 *   3. Live stats strip — 4 inline metrics (placeholders until Edge 1.0).
 *   4. 10 navigation tiles — Identity / Map / Trust Graph / Peers /
 *      Interfaces / Paths / Announces / Queue / Diagnostics / Content.
 *
 * Each tile carries a "Coming Soon" badge until the corresponding sub-screen
 * lands with real Edge data. Surface is intentionally exhaustive so federation
 * capability is *visible* to operators today, not deferred to "Edge 1.0 ships."
 */
@Composable
fun NetworkScreen(
    viewModel: NetworkViewModel,
    onTileClick: (NetworkTile) -> Unit,
    modifier: Modifier = Modifier,
) {
    val status by viewModel.status.collectAsState()
    val mode by viewModel.mode.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val restartPending by viewModel.restartPending.collectAsState()
    val insufficientDisk by viewModel.insufficientDisk.collectAsState()
    val federationAddress by viewModel.federationAddress.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadAgentMode()
        // Seed federation address from the existing mock until Edge 1.0 wires
        // up a real signer_key_id pymethod. The card renders the placeholder
        // until the real value arrives.
        if (federationAddress == null) {
            viewModel.setFederationAddress(MOCK_NETWORK_SNAPSHOT.localIdentity.keyId)
        }
    }

    // Pending-mode confirmation dialog state — apply mode change on confirm.
    var pendingMode: AgentMode? by remember { mutableStateOf(null) }

    pendingMode?.let { target ->
        AlertDialog(
            onDismissRequest = { pendingMode = null },
            modifier = Modifier.testable("dialog_mode_confirm"),
            // Also tag the title Text inside the dialog content with the same
            // dialog_mode_confirm tag. Compose Multiplatform renders AlertDialog
            // content inside a separate Popup/Window on desktop, and the
            // TestAutomationServer's `/tree` walker doesn't reliably traverse
            // outer Modifier tags down into popup composition trees. Mirroring
            // the tag onto a Text element inside the popup content guarantees
            // QA's `wait_for_element(DIALOG_MODE_CONFIRM)` resolves after the
            // mode-button click trigger.
            title = {
                Text(
                    text = localizedString("network.mode_card.confirm_change_title"),
                    modifier = Modifier.testable("dialog_mode_confirm"),
                )
            },
            text = { Text(localizedString("network.mode_card.confirm_change_body")) },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.setMode(target)
                        pendingMode = null
                    },
                    modifier = Modifier.testableClickable("btn_mode_confirm") {
                        viewModel.setMode(target)
                        pendingMode = null
                    },
                ) { Text(localizedString("network.mode_card.confirm_change_button")) }
            },
            dismissButton = {
                TextButton(
                    onClick = { pendingMode = null },
                    modifier = Modifier.testableClickable("btn_mode_cancel") { pendingMode = null },
                ) { Text(localizedString("network.mode_card.cancel_button")) }
            },
        )
    }

    // Bounded hub content (one identity card + mode card + stats strip + ~10
    // tiles) — uses `Column.verticalScroll` instead of `LazyColumn` so every
    // section composes eagerly regardless of viewport width. T-T2 / T-T3
    // wrapped the rows in a single `LazyColumn item { … }` for desktop, but
    // T-Q5 surfaced that the wrapper itself falls below the fold on Android's
    // narrower viewport (1080×2400 with sidebar consuming the left half), so
    // the LazyColumn skips composing the stats strip + tiles grid and 14
    // testTags don't appear in the test-automation tree. A bounded Column +
    // verticalScroll has the same UX (scrollable, padded, spaced) but
    // composes everything eagerly — testTags reach `/tree` on Android and
    // desktop alike.
    Column(
        modifier = modifier
            .fillMaxSize()
            .testable("screen_network_hub")
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenTitle()

        // ── Identity card ────────────────────────────────────────────────────
        IdentityCard(address = federationAddress)

        // ── Mode selector card ───────────────────────────────────────────────
        ModeCard(
            mode = mode,
            status = status,
            loading = loading,
            onModeSelected = { target ->
                if (target != mode) pendingMode = target
            },
        )

        // ── Live stats strip ─────────────────────────────────────────────────
        StatsStrip()

        // ── Inline error banner ──────────────────────────────────────────────
        if (insufficientDisk != null) {
            ErrorBanner(
                message = localizedString(
                    "network.mode_card.insufficient_disk_error",
                    mapOf(
                        "available" to humanGiB(insufficientDisk!!.availableBytes),
                        "required" to humanGiB(insufficientDisk!!.requiredBytes),
                    ),
                ),
                onDismiss = { viewModel.clearInsufficientDisk() },
            )
        }
        if (restartPending) {
            RestartBanner(onDismiss = { viewModel.clearRestartPending() })
        }
        if (error != null) {
            ErrorBanner(message = error!!, onDismiss = { viewModel.clearError() })
        }

        // ── 10 navigation tiles in a 2-column grid ───────────────────────────
        tilesGrid(onTileClick)
    }
}

/**
 * Navigation tile identity — used by [NetworkScreen] callers to route to the
 * matching sub-screen via the existing `screenToSurface` bridge.
 */
enum class NetworkTile(val route: String) {
    IDENTITY("federation/identity"),
    MAP("federation/map"),
    TRUST_GRAPH("federation/trust_graph"),
    PEERS("federation/peers"),
    INTERFACES("federation/interfaces"),
    PATHS("federation/paths"),
    ANNOUNCES("federation/announces"),
    QUEUE("federation/queue"),
    DIAGNOSTICS("federation/diagnostics"),
    CONTENT("federation/content"),
}

// ═══════════════════════════════════════════════════════════════════════════
// Header
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun ScreenTitle() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            imageVector = CIRISIcons.globe,
            contentDescription = null,
            tint = CIRISColors.AccentCyan,
            modifier = Modifier.size(28.dp),
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text = localizedString("network.title"),
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Identity card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun IdentityCard(address: String?) {
    val clipboardManager = LocalClipboardManager.current
    // Always compose AddressRow so its `testable("text_network_identity_key")`
    // + `testableClickable("btn_network_identity_copy")` modifiers fire
    // `onGloballyPositioned` on first paint. Falling back to the mock keyId
    // avoids a transient race where the QA walk-test snapshots the hub
    // before the LaunchedEffect-seeded address propagates through the
    // StateFlow. Edge 1.0 wires the real signer_key_id.
    val rendered: String = address?.takeIf { it.isNotBlank() }
        ?: MOCK_NETWORK_SNAPSHOT.localIdentity.keyId
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_network_identity"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.identity_card.title"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(12.dp))
            AddressRow(address = rendered, clipboard = clipboardManager)
            Spacer(Modifier.height(12.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // QR placeholder
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(MaterialTheme.colorScheme.surface)
                        .border(
                            width = 1.dp,
                            color = CIRISColors.AccentCyan.copy(alpha = 0.4f),
                            shape = RoundedCornerShape(8.dp),
                        )
                        .testable("img_network_qr_placeholder"),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = CIRISIcons.identity,
                        contentDescription = null,
                        tint = CIRISColors.AccentCyan,
                        modifier = Modifier.size(32.dp),
                    )
                }
                Column {
                    Text(
                        text = localizedString("network.identity_card.qr_label"),
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

@Composable
private fun AddressRow(
    address: String,
    clipboard: androidx.compose.ui.platform.ClipboardManager,
) {
    // Reticulum cribsheet: render full 32-char hex inside <...>, truncate to
    // <…last10> when tight. We render full + provide copy; truncation happens
    // in narrow column constraints downstream.
    val rendered = "<$address>"
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SelectionContainer(modifier = Modifier.weight(1f)) {
            Text(
                text = rendered,
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 12.sp,
                modifier = Modifier.testable("text_network_identity_key"),
            )
        }
        IconButton(
            onClick = { clipboard.setText(AnnotatedString(address)) },
            modifier = Modifier.testableClickable("btn_network_identity_copy") {
                clipboard.setText(AnnotatedString(address))
            },
        ) {
            Icon(
                imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                contentDescription = localizedString("network.identity_card.copy_address"),
                tint = CIRISColors.AccentCyan,
                modifier = Modifier.size(18.dp),
            )
        }
    }
}

@Composable
private fun SelectionContainer(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    androidx.compose.foundation.text.selection.SelectionContainer(modifier = modifier) {
        content()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Mode selector card
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun ModeCard(
    mode: AgentMode,
    status: ai.ciris.mobile.shared.models.AgentModeStatus?,
    loading: Boolean,
    onModeSelected: (AgentMode) -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_network_mode"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.mode_card.title"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = localizedString("network.mode_card.subtitle"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            AgentModeSelector(
                mode = mode,
                serverEligible = status?.serverEligible ?: false,
                availableDiskBytes = status?.availableDiskBytes ?: 0L,
                requiredDiskBytes = status?.serverMinimumDiskBytes ?: SERVER_DEFAULT_MIN,
                loading = loading,
                onModeChange = onModeSelected,
            )
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Live stats strip (placeholders until Edge 1.0)
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun StatsStrip() {
    val cells = listOf(
        "text_stat_peers" to localizedString("network.stats_strip.peers"),
        "text_stat_transports" to localizedString("network.stats_strip.transports"),
        "text_stat_queue" to localizedString("network.stats_strip.queue"),
        "text_stat_errors" to localizedString("network.stats_strip.errors"),
    )
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 12.dp),
        ) {
            cells.forEachIndexed { idx, (tag, label) ->
                StatCell(tag = tag, label = label, modifier = Modifier.weight(1f))
                if (idx != cells.lastIndex) StatDivider()
            }
        }
    }
}

@Composable
private fun StatCell(tag: String, label: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.padding(horizontal = 8.dp).testable(tag),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "—",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        )
        Spacer(Modifier.height(2.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 10.sp,
        )
        Text(
            text = localizedString("network.stats_strip.awaiting_edge_1_0"),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            fontSize = 9.sp,
        )
    }
}

@Composable
private fun StatDivider() {
    Box(
        modifier = Modifier
            .width(1.dp)
            .height(48.dp)
            .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f)),
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// Inline banners — restart-required, errors, insufficient-disk
// ═══════════════════════════════════════════════════════════════════════════

@Composable
private fun ErrorBanner(message: String, onDismiss: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onDismiss() }
            .testable("banner_error"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onErrorContainer,
        )
    }
}

@Composable
private fun RestartBanner(onDismiss: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onDismiss() }
            .testable("banner_restart_pending"),
        colors = CardDefaults.cardColors(
            containerColor = CIRISColors.AccentCyan.copy(alpha = 0.15f),
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = localizedString("network.mode_card.confirm_change_title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = localizedString("network.mode_card.confirm_change_body"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Navigation tiles — 2-column grid (LazyColumn rows of 2)
// ═══════════════════════════════════════════════════════════════════════════

private data class TileSpec(
    val tile: NetworkTile,
    val labelKey: String,
    val icon: ImageVector,
)

private val TILE_ROW_1 = listOf(
    TileSpec(NetworkTile.IDENTITY, "network.tiles.identity", CIRISIcons.identity),
    TileSpec(NetworkTile.MAP, "network.tiles.map", CIRISIcons.snapshot),
)
private val TILE_ROW_2 = listOf(
    TileSpec(NetworkTile.TRUST_GRAPH, "network.tiles.trust_graph", CIRISIcons.welcome),
    TileSpec(NetworkTile.PEERS, "network.tiles.peers", CIRISIcons.person),
)
private val TILE_ROW_3 = listOf(
    TileSpec(NetworkTile.INTERFACES, "network.tiles.interfaces", CIRISIcons.adapter),
    TileSpec(NetworkTile.PATHS, "network.tiles.paths", CIRISIcons.send),
)
private val TILE_ROW_4 = listOf(
    TileSpec(NetworkTile.ANNOUNCES, "network.tiles.announces", CIRISIcons.bus),
    TileSpec(NetworkTile.QUEUE, "network.tiles.queue", CIRISIcons.pkg),
)
private val TILE_ROW_5 = listOf(
    TileSpec(NetworkTile.DIAGNOSTICS, "network.tiles.diagnostics", CIRISIcons.telemetry),
    TileSpec(NetworkTile.CONTENT, "network.tiles.content", CIRISIcons.pkg),
)

@Composable
private fun tilesGrid(onTileClick: (NetworkTile) -> Unit) {
    val rows = listOf(TILE_ROW_1, TILE_ROW_2, TILE_ROW_3, TILE_ROW_4, TILE_ROW_5)
    // Post-T-T4: hub is a Column + verticalScroll (was LazyColumn), so the
    // tiles grid is a bare Composable rather than a LazyListScope extension.
    // Every row + tile composes eagerly regardless of viewport width — see
    // the call-site comment in `NetworkScreen` for the T-Q5 Android viewport
    // diagnostic that motivated the LazyColumn → Column conversion.
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        for (row in rows) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                for (spec in row) {
                    NavTile(
                        spec = spec,
                        onClick = { onTileClick(spec.tile) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun NavTile(
    spec: TileSpec,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier
            .height(120.dp)
            .clickable { onClick() }
            .testableClickable("tile_federation_${spec.tile.name.lowercase()}") { onClick() },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(CIRISColors.AccentCyan.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = spec.icon,
                    contentDescription = null,
                    tint = CIRISColors.AccentCyan,
                    modifier = Modifier.size(24.dp),
                )
            }
            Column {
                Text(
                    text = localizedString(spec.labelKey),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(Modifier.height(4.dp))
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(CIRISColors.BusTool.copy(alpha = 0.15f))
                        .padding(horizontal = 8.dp, vertical = 2.dp),
                ) {
                    Text(
                        text = localizedString("network.tiles.coming_soon_badge"),
                        style = MaterialTheme.typography.labelSmall,
                        color = CIRISColors.BusTool,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

private const val SERVER_DEFAULT_MIN: Long = 256L * 1024 * 1024 * 1024

private fun humanGiB(bytes: Long): String {
    if (bytes <= 0) return "0 GB"
    val gib = bytes / (1024.0 * 1024.0 * 1024.0)
    return when {
        gib >= 100 -> "${gib.toInt()} GB"
        gib >= 10 -> "${(gib * 10).toInt() / 10.0} GB"
        else -> "${(gib * 100).toInt() / 100.0} GB"
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock data — kept here for the identity card seed value until Edge 1.0 wires
// in real PyEdge.signer_key_id() FFI. The NetworkSnapshot mock used by the
// prior tabbed scaffold lives in `models/NetworkSnapshot.kt`.
// ═══════════════════════════════════════════════════════════════════════════

internal val MOCK_NETWORK_SNAPSHOT = ai.ciris.mobile.shared.models.NetworkSnapshot(
    localIdentity = ai.ciris.mobile.shared.models.LocalIdentity(
        keyId = "fed1ce5b9a3c4e8d2017a4b5c6d7e8f901234567890abcdef1234567890abcdef",
        keyIdShort = "fed1ce5b…cdef",
        displayName = null,
        edgeVersion = "0.9.1",
        hardwareBacked = false,
    ),
    transports = emptyList(),
    peers = emptyList(),
    paths = emptyList(),
    links = emptyList(),
    blackholeList = emptyList(),
    recentEvents = emptyList(),
    summary = ai.ciris.mobile.shared.models.NetworkSummary(
        transportCount = 0,
        transportsUp = 0,
        peerCount = 0,
        peersReachableNow = 0,
        trustedPeerCount = 0,
        activeLinkCount = 0,
        pathCount = 0,
        blackholeCount = 0,
        recentEventCount = 0,
    ),
    generatedAt = "2026-05-28T16:43:05Z",
)
