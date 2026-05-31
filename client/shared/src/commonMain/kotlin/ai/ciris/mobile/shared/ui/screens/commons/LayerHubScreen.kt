package ai.ciris.mobile.shared.ui.screens.commons

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.CohortScope
import ai.ciris.mobile.shared.ui.nav.SubstrateGate

/**
 * Generic layer hub for the 5 UX-facing cohort scopes. Renders three
 * sections that repeat at every scale (Recursive Golden Rule fractal —
 * the same shape applies at Self, Family, Local Community, Global
 * Communities, Global Commons):
 *
 * - **Identities** — list of identities visible at this scope, with
 *   friendly names where available, key_id otherwise.
 * - **Trust** — for each identity, are we trusting them, and if so how
 *   (via a trust policy or direct trust).
 * - **Policies** — trust policies that govern automatic trust at this
 *   scope.
 *
 * Phase A (this commit): three section stubs each pinned to the
 * substrate gate that needs to ship before per-layer data can flow
 * (Edge's PeerResolver for per-scope identity queries). The Global
 * Commons scope routes through this generic hub for now; Phase B will
 * fold the existing NetworkScreen federation surface into the Global
 * Commons hub directly.
 *
 * CEG 0.6 mapping at the wire level: each scope corresponds to one or
 * more `cohort_scope` values from CEG §02 grammar:137 (`self / family /
 * community / affiliations / species / planet / federation`). The 7 →
 * 5 fold is documented on [CohortScope].
 */
@Composable
fun LayerHubScreen(
    scope: CohortScope,
    onIssueClick: (String) -> Unit = {},
) {
    val gate = scopeGate(scope)
    val scrollState = rememberScrollState()
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .testable("layer_hub_${scope.id}"),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            LayerHeader(scope = scope, icon = scopeIcon(scope))

            LayerSection(
                testTag = "layer_section_identities_${scope.id}",
                icon = CIRISIcons.person,
                titleKey = "commons.layer.section.identities",
                descriptionKey = identitiesDescriptionKey(scope),
                gate = gate,
                onIssueClick = onIssueClick,
            )

            LayerSection(
                testTag = "layer_section_trust_${scope.id}",
                icon = CIRISIcons.shield,
                titleKey = "commons.layer.section.trust",
                descriptionKey = trustDescriptionKey(scope),
                gate = gate,
                onIssueClick = onIssueClick,
            )

            LayerSection(
                testTag = "layer_section_policies_${scope.id}",
                icon = CIRISIcons.lock,
                titleKey = "commons.layer.section.policies",
                descriptionKey = policiesDescriptionKey(scope),
                gate = gate,
                onIssueClick = onIssueClick,
            )
        }
    }
}

@Composable
private fun LayerHeader(scope: CohortScope, icon: ImageVector) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Box(
            modifier = Modifier
                .size(56.dp)
                .background(
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                    shape = CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp),
            )
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = localizedString(scopeTitleKey(scope)),
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = localizedString(scopeSubtitleKey(scope)),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
            )
        }
    }
}

@Composable
private fun LayerSection(
    testTag: String,
    icon: ImageVector,
    titleKey: String,
    descriptionKey: String,
    gate: SubstrateGate,
    onIssueClick: (String) -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .testable(testTag),
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp),
                )
                Text(
                    text = localizedString(titleKey),
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(modifier = Modifier.weight(1f))
                ComingSoonBadge()
            }
            Text(
                text = localizedString(descriptionKey),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f),
            )
            GateRow(gate = gate, onIssueClick = onIssueClick)
        }
    }
}

@Composable
private fun ComingSoonBadge() {
    Surface(
        color = MaterialTheme.colorScheme.tertiary.copy(alpha = 0.18f),
        shape = RoundedCornerShape(4.dp),
    ) {
        Text(
            text = localizedString("commons.layer.badge.coming_soon"),
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.tertiary,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

@Composable
private fun GateRow(gate: SubstrateGate, onIssueClick: (String) -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("layer_gate_${gate.name.lowercase()}") {
                onIssueClick(gate.url)
            },
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f),
        shape = RoundedCornerShape(8.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = "🔗",
                fontSize = 11.sp,
            )
            Text(
                text = gate.shortRef,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = "·",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = gate.fsdSection,
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// ─── Per-scope metadata ──────────────────────────────────────────────────────

private fun scopeIcon(scope: CohortScope): ImageVector = when (scope) {
    CohortScope.AGENT -> CIRISIcons.person
    CohortScope.FAMILY -> CIRISIcons.home
    CohortScope.LOCAL_COMMUNITY -> CIRISIcons.location
    CohortScope.GLOBAL_COMMUNITIES -> CIRISIcons.shield
    CohortScope.GLOBAL_COMMONS -> CIRISIcons.globe
}

private fun scopeGate(scope: CohortScope): SubstrateGate = when (scope) {
    // Per-cohort identity / trust queries land with Edge's PeerResolver
    // surface (CIRISEdge#22). The Global Commons surface already has the
    // federation transport substrate in place — the gate is the per-scope
    // cohort-aware view, not the substrate itself.
    CohortScope.AGENT,
    CohortScope.FAMILY,
    CohortScope.LOCAL_COMMUNITY,
    CohortScope.GLOBAL_COMMUNITIES,
    CohortScope.GLOBAL_COMMONS -> SubstrateGate.EDGE_PEERRESOLVER
}

private fun scopeTitleKey(scope: CohortScope): String = "commons.layer.${scope.id.replace('-', '_')}.title"

private fun scopeSubtitleKey(scope: CohortScope): String = "commons.layer.${scope.id.replace('-', '_')}.subtitle"

private fun identitiesDescriptionKey(scope: CohortScope): String =
    "commons.layer.${scope.id.replace('-', '_')}.identities_description"

private fun trustDescriptionKey(scope: CohortScope): String =
    "commons.layer.${scope.id.replace('-', '_')}.trust_description"

private fun policiesDescriptionKey(scope: CohortScope): String =
    "commons.layer.${scope.id.replace('-', '_')}.policies_description"
