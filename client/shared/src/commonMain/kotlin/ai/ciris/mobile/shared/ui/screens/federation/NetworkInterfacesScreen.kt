package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.viewmodels.federation.NetworkInterfacesViewModel
import ai.ciris.mobile.shared.viewmodels.federation.TransportRow
import ai.ciris.mobile.shared.viewmodels.federation.TransportStatus
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt

/**
 * Network → Interfaces sub-screen.
 *
 * Renders per-transport health in an rnstatus aesthetic — one [ElevatedCard]
 * per transport, monospace metric rows, tiny status dot derived from
 * cumulative throughput + reachability. Auto-refreshes every 10 s; the
 * top-bar refresh button forces an immediate fetch.
 *
 * The aggregation contract is owned by [NetworkInterfacesViewModel]; this
 * Composable is render-only.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkInterfacesScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val vm = remember { NetworkInterfacesViewModel(apiClient) }
    val rows by vm.transportRows.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()

    // 10s polling — disposed when the screen leaves composition.
    DisposableEffect(vm) {
        vm.refreshNow()
        vm.startAutoRefresh(10_000L)
        onDispose { vm.stopAutoRefresh() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.tiles.interfaces")) },
                actions = {
                    IconButton(
                        onClick = { vm.refreshNow() },
                        modifier = Modifier.testableClickable("btn_federation_interfaces_refresh") { vm.refreshNow() },
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("network.interfaces.refresh"),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .testable("screen_federation_interfaces"),
        ) {
            when {
                rows.isEmpty() && loading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                }
                rows.isEmpty() -> {
                    EmptyTransports(error = error)
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        error?.let { msg ->
                            item { TransientError(msg) }
                        }
                        items(rows, key = { it.id }) { row ->
                            TransportCard(row = row, status = vm.statusOf(row))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyTransports(error: String?) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = localizedString("network.interfaces.empty"),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (error != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = error,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun TransientError(message: String) {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(12.dp),
            color = MaterialTheme.colorScheme.onErrorContainer,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun TransportCard(row: TransportRow, status: TransportStatus) {
    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .testable("card_transport_${row.id}"),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header: transport id + status dot
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(status)
                Spacer(Modifier.size(10.dp))
                Text(
                    text = row.id,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = labelForStatus(status),
                    style = MaterialTheme.typography.labelSmall,
                    color = colorForStatus(status),
                )
            }
            Spacer(Modifier.height(10.dp))
            // Monospace metric rows
            MetricRow(
                key = localizedString("network.interfaces.row.status"),
                value = buildString {
                    append(labelForStatus(status))
                    if (row.rssiDbm != null || row.snrDb != null) {
                        append("  ")
                        row.rssiDbm?.let { append("[RSSI ${it.roundToInt()} dBm] ") }
                        row.snrDb?.let { append("[SNR ${formatDouble(it, 1)} dB]") }
                    }
                },
            )
            MetricRow(
                key = localizedString("network.interfaces.row.bytes_in"),
                value = "${formatBytes(row.bytesIn)}↑",
            )
            MetricRow(
                key = localizedString("network.interfaces.row.bytes_out"),
                value = "${formatBytes(row.bytesOut)}↓",
            )
            MetricRow(
                key = localizedString("network.interfaces.row.reach"),
                value = formatReach(row),
            )
        }
    }
}

@Composable
private fun MetricRow(key: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = key.padEnd(10),
            fontFamily = FontFamily.Monospace,
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = ": ",
            fontFamily = FontFamily.Monospace,
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            fontFamily = FontFamily.Monospace,
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun StatusDot(status: TransportStatus) {
    Box(
        modifier = Modifier
            .size(10.dp)
            .clip(CircleShape)
            .background(colorForStatus(status)),
    )
}

@Composable
private fun colorForStatus(status: TransportStatus): Color = when (status) {
    TransportStatus.ACTIVE -> Color(0xFF2E7D32)
    TransportStatus.DEGRADED -> Color(0xFFF9A825)
    TransportStatus.IDLE -> Color(0xFFC62828)
    TransportStatus.UNKNOWN -> MaterialTheme.colorScheme.outline
}

@Composable
private fun labelForStatus(status: TransportStatus): String = when (status) {
    TransportStatus.ACTIVE -> localizedString("network.interfaces.status.active")
    TransportStatus.DEGRADED -> localizedString("network.interfaces.status.degraded")
    TransportStatus.IDLE -> localizedString("network.interfaces.status.idle")
    TransportStatus.UNKNOWN -> localizedString("network.interfaces.status.unknown")
}

@Composable
private fun formatReach(row: TransportRow): String {
    val ratio = row.reachRatio
    val count = row.peerCount
    return if (ratio == null || count == null) {
        localizedString("network.interfaces.not_measured")
    } else {
        val pct = (ratio * 100).roundToInt()
        "$pct% ($count ${localizedString("network.interfaces.peers")})"
    }
}

/** Cross-platform-safe byte formatter (no java.text dependencies). */
internal fun formatBytes(bytes: Long): String {
    if (bytes < 1024) return "$bytes B"
    val kb = bytes.toDouble() / 1024.0
    if (kb < 1024) return "${formatDouble(kb, 2)} KB"
    val mb = kb / 1024.0
    if (mb < 1024) return "${formatDouble(mb, 2)} MB"
    val gb = mb / 1024.0
    return "${formatDouble(gb, 2)} GB"
}

/**
 * Minimal portable double-formatter — Kotlin/Native does not ship
 * java.util.Locale so we hand-roll a fixed-precision string. Preserves
 * sign + truncates rather than rounds for predictability across the
 * Android/iOS/desktop trio.
 */
internal fun formatDouble(value: Double, digits: Int): String {
    val scale = (1..digits).fold(1.0) { acc, _ -> acc * 10.0 }
    val rounded = kotlin.math.round(value * scale) / scale
    val whole = rounded.toLong()
    if (digits == 0) return whole.toString()
    val fracPart = kotlin.math.round(kotlin.math.abs(rounded - whole) * scale).toLong()
    val fracStr = fracPart.toString().padStart(digits, '0')
    return "$whole.$fracStr"
}
