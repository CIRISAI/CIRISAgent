package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Diagnostics sub-screen. Recent errors, signature failures, policy
 * blocks, transport churn, with drill-down per event. Operator forensics view
 * for the Edge runtime.
 */
@Composable
fun NetworkDiagnosticsScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.diagnostics"),
        icon = CIRISIcons.telemetry,
        description = localizedString("network.sub_screens.diagnostics_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
