package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Announces sub-screen. Live + retrospective announce stream — who
 * announced, which interface heard it, hop count, signature validation result.
 */
@Composable
fun NetworkAnnouncesScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.announces"),
        icon = CIRISIcons.bus,
        description = localizedString("network.sub_screens.announces_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
