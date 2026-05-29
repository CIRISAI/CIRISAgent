package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Trust Graph sub-screen. Operator-facing view of the federation
 * trust topology: direct grants, delegated authority, adversarial flags.
 *
 * Distinct from the top-level Federation → Trust Topology surface — this
 * one is scoped to *transport*-trust, not constitutional trust.
 */
@Composable
fun NetworkTrustGraphScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.trust_graph"),
        icon = CIRISIcons.welcome,
        description = localizedString("network.sub_screens.trust_graph_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
