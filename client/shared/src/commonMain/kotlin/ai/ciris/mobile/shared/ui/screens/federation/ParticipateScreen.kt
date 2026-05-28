package ai.ciris.mobile.shared.ui.screens.federation

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Participate" — needs registry. Agents register `need:{domain}:{kind}`
 * attestations the federation can witness and respond to.
 *
 * Gated on the `need:*` primitive (CIRISNodeCore — being added to the
 * primitive list per maintainer decision 2026-05-27, tracked via
 * CIRISNodeCore#12).
 */
@Composable
fun ParticipateScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = NavSurface.Participate.label,
        icon = NavSurface.Participate.icon,
        description = "Federation needs registry — agents register what they need (rubric review, safety witness, " +
            "delegation scope) as need:{domain}:{kind} attestations; other agents see, score, and respond.",
        gate = SubstrateGate.NODECORE_NEEDS,
        onIssueClick = onIssueClick,
    )
}
