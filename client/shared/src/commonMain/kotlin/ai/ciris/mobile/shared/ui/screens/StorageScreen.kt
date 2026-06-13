package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.MemoryStatsApiData
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.AgentModeStatus
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Storage — CIRISPersist operator view (Manage group, 2.9.6).
 *
 * Surfaces the persist substrate's local facts: the graph store (total nodes,
 * by type/scope, recent activity) and the on-disk storage location. Read-only;
 * the agent surfaces what persist produces, it does not mutate it here.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StorageScreen(
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier,
) {
    var stats by remember { mutableStateOf<MemoryStatsApiData?>(null) }
    var mode by remember { mutableStateOf<AgentModeStatus?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        loading = true
        try {
            stats = apiClient.getMemoryStats()
        } catch (e: Exception) {
            error = e.message ?: "failed to load graph stats"
            PlatformLogger.d("StorageScreen", "getMemoryStats failed: ${e.message}")
        }
        try {
            mode = apiClient.getAgentMode()
        } catch (e: Exception) {
            PlatformLogger.d("StorageScreen", "getAgentMode failed: ${e.message}")
        }
        loading = false
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(title = { Text(localizedString("nav.surface.storage").ifEmpty { "Storage" }) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
                .testable("screen_storage"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "CIRISPersist · graph store",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            if (loading && stats == null) {
                CircularProgressIndicator(modifier = Modifier.padding(8.dp))
            }

            error?.let {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Text(it, modifier = Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer)
                }
            }

            stats?.let { s ->
                StorageCard(title = "Graph store", testTag = "card_storage_graph") {
                    StatRow("Total nodes", s.totalNodes.toString(), "row_storage_total_nodes")
                    StatRow("New (24h)", s.recentNodes24h.toString(), "row_storage_recent_nodes")
                    s.oldestNodeDate?.let { StatRow("Oldest", it, "row_storage_oldest") }
                    s.newestNodeDate?.let { StatRow("Newest", it, "row_storage_newest") }
                }

                if (s.nodesByType.isNotEmpty()) {
                    StorageCard(title = "Nodes by type", testTag = "card_storage_by_type") {
                        s.nodesByType.entries.sortedByDescending { it.value }.forEach { (k, v) ->
                            StatRow(k, v.toString(), "row_storage_type_$k")
                        }
                    }
                }

                if (s.nodesByScope.isNotEmpty()) {
                    StorageCard(title = "Nodes by scope", testTag = "card_storage_by_scope") {
                        s.nodesByScope.entries.sortedByDescending { it.value }.forEach { (k, v) ->
                            StatRow(k, v.toString(), "row_storage_scope_$k")
                        }
                    }
                }
            }

            mode?.let { m ->
                StorageCard(title = "On disk", testTag = "card_storage_disk") {
                    StatRow("Data directory", m.dataDir, "row_storage_data_dir", mono = true)
                    StatRow("Available", formatBytes(m.availableDiskBytes), "row_storage_available")
                }
            }
        }
    }
}

@Composable
private fun StorageCard(title: String, testTag: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun StatRow(label: String, value: String, testTag: String, mono: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
        )
    }
}

internal fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "—"
    val gb = bytes.toDouble() / (1024 * 1024 * 1024)
    if (gb >= 1.0) return "${(gb * 10).toLong() / 10.0} GB"
    val mb = bytes.toDouble() / (1024 * 1024)
    return "${(mb * 10).toLong() / 10.0} MB"
}
