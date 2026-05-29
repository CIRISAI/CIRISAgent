package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Content sub-screen. Federation content store browser — what's
 * cached locally, what's federated, hash-addressed retrieval, content-type
 * filters.
 */
@Composable
fun NetworkContentScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.content"),
        icon = CIRISIcons.pkg,
        description = localizedString("network.sub_screens.content_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
