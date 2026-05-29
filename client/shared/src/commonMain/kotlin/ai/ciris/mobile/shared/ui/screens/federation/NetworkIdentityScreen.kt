package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import androidx.compose.runtime.Composable

/**
 * Network → Identity sub-screen. Exhaustive view of the federation Ed25519
 * identity: signer_key_id, hardware-custody attestation chain, ratchet state,
 * planned rotation history. Hub renders a summary card; this view explodes
 * the detail.
 *
 * Lands in lockstep with Edge 1.0 — until then, ComingSoon pinned to the
 * PeerResolver substrate issue (CIRISEdge#22).
 */
@Composable
fun NetworkIdentityScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("network.tiles.identity"),
        icon = CIRISIcons.identity,
        description = localizedString("network.sub_screens.identity_description"),
        gate = SubstrateGate.EDGE_PEERRESOLVER,
        onIssueClick = onIssueClick,
    )
}
