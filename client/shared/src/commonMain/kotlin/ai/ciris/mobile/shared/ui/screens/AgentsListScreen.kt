package ai.ciris.mobile.shared.ui.screens

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Agents" (Client group) — multi-agent peer view. Post substrate-substitution
 * Step 4: every agent runs the full Rust substrate, this list is the client's
 * known c/r/n peers.
 *
 * Gated on the substrate-substitution trajectory closing (Persist → Edge →
 * LensCore → NodeCore). Tracked under CIRISAgent#800 umbrella; concrete
 * shape lands when CIRISNodeCore + CIRISEdge expose c/r/n peer state.
 */
@Composable
fun AgentsListScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = NavSurface.AgentsList.label,
        icon = NavSurface.AgentsList.icon,
        description = "Multi-agent peer list — every agent is a client at minimum; opt-in to relay or node " +
            "mode. Renders the federation's known peer set and each peer's c/r/n role.",
        gate = SubstrateGate.POST_SUBSTRATE_SUBSTITUTION,
        onIssueClick = onIssueClick,
    )
}
