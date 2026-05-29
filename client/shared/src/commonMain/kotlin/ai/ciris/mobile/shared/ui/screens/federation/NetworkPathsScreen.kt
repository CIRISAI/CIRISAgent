package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Paths sub-screen. RNS path table — every destination Edge knows
 * how to reach, via which transport, hop count, expiry. A path is a routing
 * decision; distinct from a peer.
 */
@Composable
fun NetworkPathsScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.paths"),
        icon = CIRISIcons.send,
        description = localizedString("network.sub_screens.paths_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
