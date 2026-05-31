package ai.ciris.mobile.shared.ui.screens.federation

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "The Commons" — federation contribution cards. Each card is an EpistemicContrib
 * (accord_file / safety_test / behavior_witness / rubric_update / recantation /
 * delegate_scope) with polarity verdict, confidence bar, witness count, and
 * audit-chain lineage.
 *
 * Gated on CIRISEdge#22 (PeerResolver + ContentFetch for evidence_refs[]
 * SHA-256 resolution — per FSD-002 §3.6.7 transport substrate). Once Edge
 * ships the ContentFetch + VerifiedEnvelope subscription surface, the
 * agent can subscribe to the federation feed and render cards in real time.
 */
@Composable
fun CommonsScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("commons.federation.commons.title").ifEmpty { NavSurface.Commons.label },
        icon = NavSurface.Commons.icon,
        description = localizedString("commons.federation.commons.description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
