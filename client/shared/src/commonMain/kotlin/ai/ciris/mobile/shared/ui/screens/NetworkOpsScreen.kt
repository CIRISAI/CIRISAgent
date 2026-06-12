package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.FederationIdCard
import ai.ciris.mobile.shared.viewmodels.NetworkViewModel
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
 * Network — CIRISEdge operator view (Manage group, 2.9.6).
 *
 * THIS node's local edge facts: the federation signer_key_id, the current agent
 * mode, and the disk budget that gates SERVER mode. Read-only here — the full
 * federation experience (mode switching, peers, trust graph, transport tiles)
 * lives in the Commons → Global Commons hub, reached via the button below. This
 * is the operator-infra slice; the Commons hub is the social/federation view.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkOpsScreen(
    viewModel: NetworkViewModel,
    onOpenFederationHub: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val status by viewModel.status.collectAsState()
    val mode by viewModel.mode.collectAsState()
    val federationAddress by viewModel.federationAddress.collectAsState()
    val federationId by viewModel.federationId.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadAgentMode()
        viewModel.loadFederationIdentity()
    }

    // In-content title (hub pattern): the app shell draws a floating logo at
    // the top-left, which clips a Scaffold TopAppBar title ("Network" → "ork").
    // Surface paints the theme background the removed Scaffold used to supply.
    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
            .testable("screen_network_ops"),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Spacer(Modifier.height(36.dp))
        Text(
            text = localizedString("nav.surface.network_ops").ifEmpty { "Network" },
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = "CIRISEdge · this node",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        OpsCard(title = "Federation identity", testTag = "card_netops_identity") {
            OpsRow(
                "Signer key",
                federationAddress?.takeIf { it.isNotBlank() } ?: "—",
                "row_netops_signer_key",
                mono = true,
            )
        }

        FederationIdCard(federationId = federationId)

        OpsCard(title = "Agent mode", testTag = "card_netops_mode") {
            OpsRow("Current", mode.wire.uppercase(), "row_netops_mode")
            status?.let {
                OpsRow("SERVER-eligible", if (it.serverEligible) "yes" else "no", "row_netops_server_eligible")
            }
        }

        status?.let { s ->
            OpsCard(title = "Disk budget", testTag = "card_netops_disk") {
                OpsRow("Available", formatBytes(s.availableDiskBytes), "row_netops_disk_available")
                OpsRow("SERVER minimum", formatBytes(s.serverMinimumDiskBytes), "row_netops_disk_minimum")
                OpsPathRow("Data directory", s.dataDir, "row_netops_data_dir")
            }
        }

        Button(
            onClick = onOpenFederationHub,
            modifier = Modifier.fillMaxWidth().testableClickable("btn_netops_open_hub") { onOpenFederationHub() },
        ) {
            Text(localizedString("network_ops.open_federation_hub").ifEmpty { "Open federation hub →" })
        }
    }
    }
}

@Composable
private fun OpsCard(title: String, testTag: String, content: @Composable ColumnScope.() -> Unit) {
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

/** Long mono values (paths) — label on its own line, value wrapping below.
 *  A SpaceBetween row collides label and value when the value is wider than
 *  the remaining space (seen with the Android data dir path). */
@Composable
private fun OpsPathRow(label: String, value: String, testTag: String) {
    Column(modifier = Modifier.fillMaxWidth().testable(testTag)) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun OpsRow(label: String, value: String, testTag: String, mono: Boolean = false) {
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
