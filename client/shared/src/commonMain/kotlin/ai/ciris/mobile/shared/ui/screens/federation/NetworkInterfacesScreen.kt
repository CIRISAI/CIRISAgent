package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Interfaces sub-screen. Per-transport health + config blob + stats
 * (rnstatus-style: TCP / UDP / Auto / RNode / HTTPS / Local). CRUD over the
 * `reticulum.conf`-equivalent.
 */
@Composable
fun NetworkInterfacesScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.interfaces"),
        icon = CIRISIcons.adapter,
        description = localizedString("network.sub_screens.interfaces_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
