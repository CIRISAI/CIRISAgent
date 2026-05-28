package ai.ciris.mobile.shared.ui.screens.federation

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Constitutional" — accord-holder identity + their reserved-prefix
 * attestations. Per FSD-002 §4.1, `accord:*` is the one constitutional
 * asymmetry: only `identity_type=accord_holder` may emit those attestations,
 * and the federation directory authoritatively lists current holders.
 *
 * Gated on CIRISRegistry#23 (accord_holder identity surface + reserved-prefix
 * enforcement query API).
 */
@Composable
fun ConstitutionalScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = NavSurface.Constitutional.label,
        icon = NavSurface.Constitutional.icon,
        description = "Accord-holder identity surface — the one constitutional asymmetry per FSD-002 §4.1. " +
            "Only identity_type=accord_holder keys may emit accord:* attestations; this screen shows current " +
            "holders, their issued accord-prefix emissions, and the reserved-prefix enforcement audit.",
        gate = SubstrateGate.REGISTRY_ACCORD_HOLDER,
        onIssueClick = onIssueClick,
    )
}
