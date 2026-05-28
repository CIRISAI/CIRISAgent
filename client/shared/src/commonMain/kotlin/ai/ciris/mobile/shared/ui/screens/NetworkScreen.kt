package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Network — federation transport substrate operator surface (2.9.4).
 *
 * Edge data is source of truth; UI is display + content-type-aware CRUD.
 * Implementation lands in lockstep with CIRISEdge 1.0/1.1; until then the
 * screen renders mock-data sketches so the FFI surface ask can be
 * shaken out against a real layout.
 *
 * Five tabs:
 *   - Peers (default)  — sortable peer × transport reachability matrix
 *   - Topology         — force-directed graph (Kuiver, gated)
 *   - Transports       — per-interface health + config blob + stats
 *   - Events           — reverse-chrono announce/path/link event stream
 *   - Config           — config-as-code round-trip (spec → runtime → diff)
 *
 * "FFI Coverage" chip on each tab surfaces which pymethods this view depends
 * on; tap to expand the gap list (`NETWORK_FFI_GAPS`).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkScreen(
    snapshot: NetworkSnapshot? = MOCK_NETWORK_SNAPSHOT,
    onAddPeer: () -> Unit = {},
    onAddTransport: () -> Unit = {},
    onRefresh: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    var selectedTab by remember { mutableStateOf(NetworkTab.PEERS) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .testable("screen_network"),
    ) {
        // ── Header strip: local identity + summary chips ──────────────────────
        NetworkHeader(
            snapshot = snapshot,
            onRefresh = onRefresh,
        )

        // ── Tab bar ───────────────────────────────────────────────────────────
        ScrollableTabRow(
            selectedTabIndex = selectedTab.ordinal,
            edgePadding = 0.dp,
            modifier = Modifier.testable("network_tabs"),
        ) {
            NetworkTab.values().forEach { tab ->
                Tab(
                    selected = selectedTab == tab,
                    onClick = { selectedTab = tab },
                    text = { Text(tab.label) },
                    modifier = Modifier.testable("network_tab_${tab.name.lowercase()}"),
                )
            }
        }

        // ── Active tab content ────────────────────────────────────────────────
        Box(modifier = Modifier.fillMaxSize().weight(1f)) {
            when (selectedTab) {
                NetworkTab.PEERS -> PeersTab(
                    snapshot = snapshot,
                    onAddPeer = onAddPeer,
                )
                NetworkTab.TOPOLOGY -> TopologyTab(snapshot = snapshot)
                NetworkTab.TRANSPORTS -> TransportsTab(
                    snapshot = snapshot,
                    onAddTransport = onAddTransport,
                )
                NetworkTab.EVENTS -> EventsTab(snapshot = snapshot)
                NetworkTab.CONFIG -> ConfigTab(snapshot = snapshot)
            }
        }
    }
}

enum class NetworkTab(val label: String) {
    PEERS("Peers"),
    TOPOLOGY("Topology"),
    TRANSPORTS("Transports"),
    EVENTS("Events"),
    CONFIG("Config"),
}

// ═════════════════════════════════════════════════════════════════════════════
// Header — local identity + 6 summary chips
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun NetworkHeader(snapshot: NetworkSnapshot?, onRefresh: () -> Unit) {
    Surface(tonalElevation = 1.dp) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = CIRISIcons.globe,
                    contentDescription = null,
                    tint = CIRISColors.AccentCyan,
                    modifier = Modifier.size(28.dp),
                )
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Federation Network",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    if (snapshot != null) {
                        Text(
                            text = snapshot.localIdentity.displayName
                                ?: "your federation address",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        SelectionContainer {
                            Text(
                                text = snapshot.localIdentity.keyId,
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace,
                                modifier = Modifier
                                    .padding(top = 4.dp)
                                    .testable("local_federation_key_id"),
                            )
                        }
                    } else {
                        Text(
                            text = "Edge runtime not available",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
                IconButton(onClick = onRefresh, modifier = Modifier.testable("btn_network_refresh")) {
                    Icon(
                        imageVector = Icons.Filled.Refresh,
                        contentDescription = "Refresh",
                    )
                }
            }
            if (snapshot != null) {
                Spacer(Modifier.height(12.dp))
                SummaryChips(snapshot.summary)
            }
        }
    }
}

@Composable
private fun SummaryChips(summary: NetworkSummary) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SummaryChip("Transports", "${summary.transportsUp}/${summary.transportCount}")
        SummaryChip("Peers", "${summary.peersReachableNow}/${summary.peerCount}")
        SummaryChip("Trusted", "${summary.trustedPeerCount}")
        SummaryChip("Links", "${summary.activeLinkCount}")
        SummaryChip("Paths", "${summary.pathCount}")
        if (summary.blackholeCount > 0) {
            SummaryChip(
                "Blocked",
                "${summary.blackholeCount}",
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun SummaryChip(label: String, value: String, color: Color? = null) {
    val tint = color ?: MaterialTheme.colorScheme.onSurfaceVariant
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(value, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = tint)
            Spacer(Modifier.width(6.dp))
            Text(label, style = MaterialTheme.typography.labelSmall, color = tint)
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Peers tab — sortable table with per-transport reachability chips
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun PeersTab(snapshot: NetworkSnapshot?, onAddPeer: () -> Unit) {
    Box(modifier = Modifier.fillMaxSize()) {
        if (snapshot == null || snapshot.peers.isEmpty()) {
            EmptyState(
                title = if (snapshot == null) "Edge runtime degraded" else "No peers yet",
                body = if (snapshot == null) {
                    "Federation cohabitation is awaiting CIRISEdge#22 fix. " +
                        "Once Edge initializes cleanly, the peer list will populate as " +
                        "announces arrive over each configured transport."
                } else {
                    "Tap “Add peer” to seed one manually, or wait for announces to " +
                        "arrive on a configured transport."
                },
            )
        } else {
            LazyColumn(
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                items(snapshot.peers, key = { it.keyId }) { peer ->
                    PeerRow(peer = peer)
                    Divider()
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onAddPeer,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp)
                .testable("btn_add_peer"),
            icon = {
                Icon(Icons.Filled.Add, contentDescription = null)
            },
            text = { Text("Add peer") },
        )
    }
}

@Composable
private fun PeerRow(peer: NetworkPeer) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { /* TODO: open peer detail */ }
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testable("peer_row_${peer.keyId.take(12)}"),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TrustDot(trust = peer.trust)
            Spacer(Modifier.width(8.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = peer.displayName ?: peer.keyIdShort,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                if (peer.displayName != null) {
                    Text(
                        text = peer.keyIdShort,
                        style = MaterialTheme.typography.labelSmall,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            DiscoveryBadge(peer.discoveredVia)
        }
        if (peer.reachability.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                peer.reachability.forEach { ReachabilityChip(it) }
            }
        }
    }
}

@Composable
private fun TrustDot(trust: PeerTrust) {
    val color = when (trust) {
        PeerTrust.TRUSTED -> Color(0xFF4CAF50)
        PeerTrust.UNTRUSTED -> MaterialTheme.colorScheme.onSurfaceVariant
        PeerTrust.BLOCKED -> MaterialTheme.colorScheme.error
        PeerTrust.UNKNOWN -> Color.Gray
    }
    Box(
        modifier = Modifier
            .size(10.dp)
            .clip(CircleShape)
            .background(color),
    )
}

@Composable
private fun DiscoveryBadge(via: PeerDiscoverySource) {
    val (label, color) = when (via) {
        PeerDiscoverySource.ANNOUNCE -> "announce" to CIRISColors.AccentCyan
        PeerDiscoverySource.MANUAL -> "manual" to MaterialTheme.colorScheme.tertiary
        PeerDiscoverySource.REGISTRY -> "registry" to MaterialTheme.colorScheme.secondary
        PeerDiscoverySource.COHABITATION -> "cohab" to CIRISColors.BusComm
        PeerDiscoverySource.UNKNOWN -> "?" to Color.Gray
    }
    Text(
        text = label,
        style = MaterialTheme.typography.labelSmall,
        color = color,
        modifier = Modifier
            .background(color.copy(alpha = 0.15f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

@Composable
private fun ReachabilityChip(r: PeerReachability) {
    Surface(
        shape = RoundedCornerShape(6.dp),
        color = transportKindColor(r.transportKind).copy(alpha = 0.15f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = transportKindLabel(r.transportKind),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                color = transportKindColor(r.transportKind),
            )
            Spacer(Modifier.width(4.dp))
            Text(
                text = "${r.hops}h",
                style = MaterialTheme.typography.labelSmall,
                color = transportKindColor(r.transportKind),
            )
            r.snrDb?.let {
                Spacer(Modifier.width(4.dp))
                Text(
                    text = "${it.toInt()}dB",
                    style = MaterialTheme.typography.labelSmall,
                    color = transportKindColor(r.transportKind),
                )
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Topology tab — interactive force-directed canvas (same approach as the
// memory graph + neural visualization; proven performant on Android/iOS/wasm
// and stable as the agent core converts to Rust because the FFI contract is
// data, not implementation).
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun TopologyTab(snapshot: NetworkSnapshot?) {
    if (snapshot == null) {
        EmptyState(
            title = "Edge runtime degraded",
            body = "Topology view will populate when the federation runtime " +
                "initializes cleanly (CIRISEdge#22 cohabitation fix).",
        )
        return
    }
    var selectedPeer by remember { mutableStateOf<String?>(null) }
    Box(modifier = Modifier.fillMaxSize()) {
        NetworkTopologyCanvas(
            snapshot = snapshot,
            selectedPeerKeyId = selectedPeer,
            onPeerSelected = { selectedPeer = it },
        )
        // Selection detail overlay — bottom sheet style without the sheet
        selectedPeer?.let { peerId ->
            val peer = snapshot.peers.find { it.keyId == peerId }
            if (peer != null) {
                Surface(
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.95f),
                    tonalElevation = 4.dp,
                    shape = RoundedCornerShape(topStart = 12.dp, topEnd = 12.dp),
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(8.dp),
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = peer.displayName ?: peer.keyIdShort,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = peer.keyId,
                            style = MaterialTheme.typography.labelSmall,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (peer.reachability.isNotEmpty()) {
                            Spacer(Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                peer.reachability.forEach { ReachabilityChip(it) }
                            }
                        }
                    }
                }
            }
        }
        // Caption strip — counts and a hint
        Surface(
            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f),
            shape = RoundedCornerShape(6.dp),
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(8.dp),
        ) {
            Text(
                text = "${snapshot.peers.size} peers · ${snapshot.summary.transportCount} transports · drag to rearrange",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            )
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Transports tab — per-interface card with stats + config blob
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun TransportsTab(snapshot: NetworkSnapshot?, onAddTransport: () -> Unit) {
    Box(modifier = Modifier.fillMaxSize()) {
        if (snapshot == null || snapshot.transports.isEmpty()) {
            EmptyState(
                title = "No transports configured",
                body = "Add a transport (LoRa via RNode, AutoInterface on local LAN, " +
                    "TCP gateway, HTTPS federation) to start exchanging announces.",
            )
        } else {
            LazyColumn(contentPadding = PaddingValues(8.dp)) {
                items(snapshot.transports, key = { it.id }) { transport ->
                    TransportCard(transport = transport)
                    Spacer(Modifier.height(8.dp))
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onAddTransport,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp)
                .testable("btn_add_transport"),
            icon = {
                Icon(Icons.Filled.Add, contentDescription = null)
            },
            text = { Text("Add transport") },
        )
    }
}

@Composable
private fun TransportCard(transport: NetworkTransport) {
    var expanded by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp)
            .clickable { expanded = !expanded }
            .testable("transport_card_${transport.id}"),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(transportStatusColor(transport.status)),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = transport.name,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = transportKindLabel(transport.kind),
                    style = MaterialTheme.typography.labelSmall,
                    color = transportKindColor(transport.kind),
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .background(
                            transportKindColor(transport.kind).copy(alpha = 0.15f),
                            RoundedCornerShape(4.dp),
                        )
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                )
            }
            Spacer(Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth()) {
                StatCol("Peers", "${transport.peerCount}", modifier = Modifier.weight(1f))
                StatCol("In", humanBytes(transport.stats.bytesIn), modifier = Modifier.weight(1f))
                StatCol("Out", humanBytes(transport.stats.bytesOut), modifier = Modifier.weight(1f))
                StatCol("Err", "${transport.stats.errors}", modifier = Modifier.weight(1f))
            }
            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(top = 12.dp)) {
                    Text(
                        text = "Config",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.height(4.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(4.dp),
                    ) {
                        Text(
                            text = transport.configBlob,
                            style = MaterialTheme.typography.bodySmall.copy(fontSize = 12.sp),
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.padding(8.dp),
                        )
                    }
                    transport.stats.lastAnnounceAt?.let {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = "Last announce: $it",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatCol(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Events tab — reverse-chrono announce/path/link event stream
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun EventsTab(snapshot: NetworkSnapshot?) {
    if (snapshot == null || snapshot.recentEvents.isEmpty()) {
        EmptyState(
            title = "No recent events",
            body = "Announces, path discoveries, link establishments, and policy " +
                "blocks will stream here as they happen.",
        )
        return
    }
    LazyColumn(contentPadding = PaddingValues(8.dp)) {
        items(snapshot.recentEvents) { event ->
            EventRow(event)
            Divider()
        }
    }
}

@Composable
private fun EventRow(event: NetworkEvent) {
    val color = when (event.severity) {
        EventSeverity.INFO -> MaterialTheme.colorScheme.onSurface
        EventSeverity.WARNING -> Color(0xFFE5A100)
        EventSeverity.ERROR -> MaterialTheme.colorScheme.error
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = event.at.takeLast(8).take(5),
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(48.dp),
        )
        Text(
            text = eventKindLabel(event.kind),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = color,
            modifier = Modifier.width(120.dp),
        )
        Text(
            text = event.message,
            style = MaterialTheme.typography.bodySmall,
            color = color,
            modifier = Modifier.weight(1f),
        )
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Config tab — config-as-code spec/runtime/diff (deferred to Edge 1.0)
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun ConfigTab(snapshot: NetworkSnapshot?) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("reticulum.conf-equivalent", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Edge will own the canonical config blob. UI accepts INI/YAML " +
                "import-export and shows spec → runtime → diff (Kubernetes-style).",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(16.dp))
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(4.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = if (snapshot != null && snapshot.transports.isNotEmpty()) {
                    snapshot.transports.joinToString("\n\n") {
                        "# ${it.name} (${transportKindLabel(it.kind)})\n${it.configBlob}"
                    }
                } else {
                    "# Awaiting edge.config_read() pymethod (CIRISEdge#25)\n" +
                        "# Once Edge exposes the canonical config surface, this view " +
                        "shows the spec, the runtime, and the diff."
                },
                style = MaterialTheme.typography.bodySmall.copy(fontSize = 12.sp),
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(12.dp),
            )
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Shared helpers
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun EmptyState(title: String, body: String) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text(
            text = body,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SelectionContainer(content: @Composable () -> Unit) {
    androidx.compose.foundation.text.selection.SelectionContainer { content() }
}

private fun transportKindLabel(kind: TransportKind): String = when (kind) {
    TransportKind.HTTPS -> "HTTPS"
    TransportKind.TCP -> "TCP"
    TransportKind.UDP -> "UDP"
    TransportKind.AUTO -> "Auto"
    TransportKind.RNODE -> "LoRa"
    TransportKind.I2P -> "I2P"
    TransportKind.KISS -> "KISS"
    TransportKind.SERIAL -> "Serial"
    TransportKind.PIPE -> "Pipe"
    TransportKind.LOCAL -> "Local"
    TransportKind.UNKNOWN -> "?"
}

private fun transportKindColor(kind: TransportKind): Color = when (kind) {
    TransportKind.HTTPS -> CIRISColors.AccentCyan
    TransportKind.TCP -> CIRISColors.BusLLM
    TransportKind.UDP -> CIRISColors.BusComm
    TransportKind.AUTO -> CIRISColors.BusLLM
    TransportKind.RNODE -> CIRISColors.BusTool       // burnt rust — long-range
    TransportKind.I2P -> CIRISColors.BusWise          // vintage brass — privacy
    TransportKind.KISS -> CIRISColors.BusTool
    TransportKind.SERIAL -> CIRISColors.BusTool
    TransportKind.PIPE -> Color.Gray
    TransportKind.LOCAL -> CIRISColors.BusComm
    TransportKind.UNKNOWN -> Color.Gray
}

private fun transportStatusColor(status: TransportStatus): Color = when (status) {
    TransportStatus.UP -> Color(0xFF4CAF50)
    TransportStatus.DOWN -> Color(0xFFF44336)
    TransportStatus.DEGRADED -> Color(0xFFE5A100)
    TransportStatus.STARTING -> CIRISColors.AccentCyan
    TransportStatus.DISABLED -> Color.Gray
}

private fun eventKindLabel(kind: NetworkEventKind): String = when (kind) {
    NetworkEventKind.ANNOUNCE_RECEIVED -> "announce"
    NetworkEventKind.ANNOUNCE_SENT -> "announce↑"
    NetworkEventKind.PATH_DISCOVERED -> "path+"
    NetworkEventKind.PATH_LOST -> "path−"
    NetworkEventKind.LINK_ESTABLISHED -> "link+"
    NetworkEventKind.LINK_DROPPED -> "link−"
    NetworkEventKind.TRANSPORT_UP -> "transport↑"
    NetworkEventKind.TRANSPORT_DOWN -> "transport↓"
    NetworkEventKind.KEY_ROTATED -> "key rot"
    NetworkEventKind.SIGNATURE_FAILURE -> "sig FAIL"
    NetworkEventKind.POLICY_BLOCK -> "blocked"
    NetworkEventKind.UNKNOWN -> "?"
}

private fun humanBytes(b: Long): String = when {
    b < 1024 -> "${b}B"
    b < 1024 * 1024 -> "${b / 1024}K"
    b < 1024 * 1024 * 1024 -> "${b / (1024 * 1024)}M"
    else -> "${b / (1024L * 1024 * 1024)}G"
}

// ═════════════════════════════════════════════════════════════════════════════
// Mock data — used until Edge 1.0 wires in real PyEdge FFI
// ═════════════════════════════════════════════════════════════════════════════

val MOCK_NETWORK_SNAPSHOT = NetworkSnapshot(
    localIdentity = LocalIdentity(
        keyId = "fed1ce5b9a3c4e8d2017a4b5c6d7e8f901234567890abcdef1234567890abcdef",
        keyIdShort = "fed1ce5b…cdef",
        displayName = null,
        edgeVersion = "0.9.1",
        hardwareBacked = false,
    ),
    transports = listOf(
        NetworkTransport(
            id = "t-https",
            name = "HTTPS federation",
            kind = TransportKind.HTTPS,
            status = TransportStatus.UP,
            configBlob = """name: "https-federation"
endpoint: "https://registry.ciris.ai"
mutual_auth: true""",
            stats = TransportStats(
                bytesIn = 1024 * 384,
                bytesOut = 1024 * 211,
                packetsIn = 412,
                packetsOut = 287,
                errors = 0,
                lastAnnounceAt = "2026-05-28T16:42:11Z",
            ),
            peerCount = 3,
        ),
        NetworkTransport(
            id = "t-auto",
            name = "AutoInterface (LAN)",
            kind = TransportKind.AUTO,
            status = TransportStatus.UP,
            configBlob = """name: "auto-lan"
group_id: "ciris-mesh"
discovery_scope: "site"""",
            stats = TransportStats(
                bytesIn = 1024 * 22,
                bytesOut = 1024 * 18,
                packetsIn = 89,
                packetsOut = 76,
                errors = 0,
                lastAnnounceAt = "2026-05-28T16:43:01Z",
            ),
            peerCount = 1,
        ),
        NetworkTransport(
            id = "t-local",
            name = "Local cohabitation",
            kind = TransportKind.LOCAL,
            status = TransportStatus.DEGRADED,
            configBlob = """name: "local-ffi"
note: "Awaiting CIRISEdge#22 cohabitation fix"""",
            stats = TransportStats(
                bytesIn = 0,
                bytesOut = 0,
                packetsIn = 0,
                packetsOut = 0,
                errors = 1,
                lastAnnounceAt = null,
            ),
            peerCount = 0,
        ),
    ),
    peers = listOf(
        NetworkPeer(
            keyId = "ab12cd34ef56789012abcdef1234567890abcdef1234567890abcdef12345678",
            keyIdShort = "ab12cd34…5678",
            displayName = "echo-speculative-4fc6ru",
            trust = PeerTrust.TRUSTED,
            reachability = listOf(
                PeerReachability(
                    transportId = "t-https",
                    transportKind = TransportKind.HTTPS,
                    hops = 1,
                    lastSeenAt = "2026-05-28T16:43:00Z",
                ),
            ),
            discoveredVia = PeerDiscoverySource.REGISTRY,
            firstSeenAt = "2026-05-15T08:00:00Z",
            lastSeenAt = "2026-05-28T16:43:00Z",
        ),
        NetworkPeer(
            keyId = "cd34ef5678901234abcdef0987654321abcdef0987654321abcdef0987654321",
            keyIdShort = "cd34ef56…4321",
            displayName = null,
            trust = PeerTrust.UNKNOWN,
            reachability = listOf(
                PeerReachability(
                    transportId = "t-auto",
                    transportKind = TransportKind.AUTO,
                    hops = 0,
                    lastSeenAt = "2026-05-28T16:42:55Z",
                ),
            ),
            discoveredVia = PeerDiscoverySource.ANNOUNCE,
            firstSeenAt = "2026-05-28T15:30:00Z",
            lastSeenAt = "2026-05-28T16:42:55Z",
            notes = null,
        ),
    ),
    paths = listOf(
        NetworkPath(
            destinationHash = "ab12cd34ef567890",
            peerKeyId = "ab12cd34ef56789012abcdef1234567890abcdef1234567890abcdef12345678",
            hops = 1,
            viaTransportId = "t-https",
            viaTransportKind = TransportKind.HTTPS,
            nextHop = "registry-edge",
            lastSeenAt = "2026-05-28T16:43:00Z",
            expiresAt = "2026-06-04T16:43:00Z",
        ),
    ),
    links = emptyList(),
    blackholeList = emptyList(),
    recentEvents = listOf(
        NetworkEvent(
            at = "2026-05-28T16:43:01Z",
            kind = NetworkEventKind.ANNOUNCE_RECEIVED,
            message = "Heard from cd34ef56…4321 on t-auto (0 hops)",
            peerKeyId = "cd34ef5678901234abcdef0987654321abcdef0987654321abcdef0987654321",
            transportId = "t-auto",
        ),
        NetworkEvent(
            at = "2026-05-28T16:42:11Z",
            kind = NetworkEventKind.PATH_DISCOVERED,
            message = "Path to echo-speculative-4fc6ru via t-https",
            peerKeyId = "ab12cd34ef56789012abcdef1234567890abcdef1234567890abcdef12345678",
            transportId = "t-https",
        ),
        NetworkEvent(
            at = "2026-05-28T15:30:00Z",
            kind = NetworkEventKind.TRANSPORT_DOWN,
            message = "Local cohabitation degraded (CIRISEdge#22)",
            transportId = "t-local",
            severity = EventSeverity.WARNING,
        ),
    ),
    summary = NetworkSummary(
        transportCount = 3,
        transportsUp = 2,
        peerCount = 2,
        peersReachableNow = 2,
        trustedPeerCount = 1,
        activeLinkCount = 0,
        pathCount = 1,
        blackholeCount = 0,
        recentEventCount = 3,
    ),
    generatedAt = "2026-05-28T16:43:05Z",
)
