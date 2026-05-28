package ai.ciris.mobile.shared.ui.screens

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Health & Reputation" — operator-facing per-agent reputation card surfacing
 * the Capacity Score composite (𝒞_CIRIS = C · I_int · R · I_inc · S) plus
 * Credits, Expertise, and Partner-role badges.
 *
 * Gated on CIRISLensCore#25 (capacity:* attestations — per FSD-002 §3.5.4).
 *
 * **Anti-Goodhart constraint** (FSD-002 §4.7): capacity scores about this
 * agent are NEVER fed back into the agent's own context. This screen renders
 * scores emitted *by other federation members* about this agent; the agent
 * itself does not see them. The implementation MUST honor this when the gate
 * lifts in a future 2.9.X patch.
 */
@Composable
fun HealthReputationScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = NavSurface.HealthReputation.label,
        icon = NavSurface.HealthReputation.icon,
        description = "Per-agent reputation surface: Capacity Score composite (C · I_int · R · I_inc · S) " +
            "plus Credits, Expertise tier, and partner-role badges. Federation-emitted scores about this agent — " +
            "anti-Goodhart safe (the agent itself never reads its own capacity).",
        gate = SubstrateGate.LENSCORE_CAPACITY,
        onIssueClick = onIssueClick,
    )
}
