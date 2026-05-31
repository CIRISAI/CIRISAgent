package ai.ciris.mobile.shared.ui.screens.federation

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Trust Topology" — graph view of federation trust nodes + edges. Nodes are
 * federation peers; edges are direct / delegated / adversarial trust grants
 * with weights derived from the federation directory.
 *
 * Gated on CIRISEdge#22 + CIRISPersist#104 (PeerResolver reachability +
 * federation_directory query API — per FSD-002 §3.4 + §3.3). Edges colored
 * by transport reachability ratio; nodes sized by aggregate trust weight.
 */
@Composable
fun TrustTopologyScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("commons.federation.trust_topology.title").ifEmpty { NavSurface.TrustTopology.label },
        icon = NavSurface.TrustTopology.icon,
        description = localizedString("commons.federation.trust_topology.description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
