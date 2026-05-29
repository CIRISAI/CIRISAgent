package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Map sub-screen. Force-directed canvas of the local federation
 * neighborhood — peers as nodes, transports as colored edges, hop distance as
 * radial distance. The old `NetworkTopologyCanvas` belongs here.
 */
@Composable
fun NetworkMapScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.map"),
        icon = CIRISIcons.snapshot,
        description = localizedString("network.sub_screens.map_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
