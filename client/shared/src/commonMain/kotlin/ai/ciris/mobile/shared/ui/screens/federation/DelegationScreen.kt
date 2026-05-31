package ai.ciris.mobile.shared.ui.screens.federation

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * "Delegation" — delegates_to scope graph. Shows what scopes this agent's
 * keys have delegated to other parties + the inverse: who has delegated
 * scopes to this agent.
 *
 * Gated on CIRISPersist#104 (delegates_to graph traversal API — one of the
 * 4 structural primitives per FSD-002 §2.2.1, persisted in the federation
 * directory per §3.3).
 */
@Composable
fun DelegationScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = localizedString("commons.federation.delegation.title").ifEmpty { NavSurface.Delegation.label },
        icon = NavSurface.Delegation.icon,
        description = localizedString("commons.federation.delegation.description"),
        gate = SubstrateGate.PERSIST_DELEGATES_TO,
        onIssueClick = onIssueClick,
    )
}
