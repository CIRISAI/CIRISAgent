package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.components.ComingSoonPlaceholder
import ai.ciris.mobile.shared.ui.nav.NavSurface
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import ai.ciris.mobile.shared.ui.screens.graph.CellVizState
import ai.ciris.mobile.shared.ui.theme.CIRISColors

/**
 * "Health & Reputation" — the agent's CIRIS Capacity Score, surfaced as a
 * proper card in the new Epistemic Commons nav (2.9.4 promotion: moved out
 * of the InteractScreen badge popup).
 *
 * Data source: `InteractViewModel.cellVizState: StateFlow<CellVizState>`,
 * which already polls `/v1/my-data/capacity?scope=both`. The caller (the
 * app shell) hoists that flow and passes the current value here — no new
 * fetch path. See `graph/CellVizState.kt` for the data model and the
 * §5a TODO in CELL_VIZ_REDESIGN for the local-vs-fleet split rationale.
 *
 * **Anti-Goodhart constraint** (FSD-002 §4.7): capacity scores are an
 * **operator-facing render** only. The agent itself never reads its own
 * capacity. This screen surfaces local + fleet to the user; the underlying
 * StateFlow is similarly excluded from the agent's prompt context.
 *
 * Federation-signed capacity attestations (the full `capacity:*` namespace
 * per FSD-002 §3.5.4 — cohort-conformity, manifold-conformity, distributive
 * access, etc.) ship in a later 2.9.X patch when CIRISLensCore#25 closes.
 * The card pins that as a "Federation attestations" sub-section gated by
 * the substrate issue so users see the architecture even though local+fleet
 * gives them the score number today.
 */
@Composable
fun HealthReputationScreen(
    state: CellVizState,
    onIssueClick: (String) -> Unit = {},
) {
    val scroll = rememberScrollState()
    val uriHandler = LocalUriHandler.current

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(CIRISColors.BackgroundDark)
            .testTag("screen_health_reputation"),
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 760.dp)
                .padding(24.dp)
                .verticalScroll(scroll)
                .align(Alignment.TopCenter),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            // Title + category pill
            HealthHeader(state)

            // Composite score hero
            CompositeScoreHero(state)

            // Five-factor breakdown
            Text(
                text = "Five-factor breakdown",
                color = CIRISColors.TextSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.0.sp,
                modifier = Modifier.padding(top = 8.dp),
            )
            FactorRow("C", "Core identity", state.c, "Consistency — no contradictions, identity stable.")
            FactorRow("I_int", "Integrity", state.iInt, "All traces signed and chain-verified.")
            FactorRow("R", "Resilience", state.r, "No drift from baseline behavior.")
            FactorRow("I_inc", "Incompleteness awareness", state.iInc, "Calibrated and defers when unsure.")
            FactorRow("S", "Sustained coherence", state.s, "Ethical faculties passing; σ-maturity climbing with use.")

            // The σ-maturity explainer (lifted from the old popup)
            CapacityMaturityNote(state)

            // Federation-attestations sub-section gated on CIRISLensCore#25
            Spacer(Modifier.height(8.dp))
            FederationAttestationsGate(onIssueClick)

            // Spec link
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .clickable {
                        uriHandler.openUri("https://ciris.ai/ciris-scoring/")
                    }
                    .testable("btn_capacity_full_spec")
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Read the full spec",
                    color = CIRISColors.AccentCyan,
                    fontSize = 13.sp,
                )
            }
        }
    }
}

@Composable
private fun HealthHeader(state: CellVizState) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = NavSurface.HealthReputation.label,
            color = CIRISColors.TextPrimary,
            fontSize = 22.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f),
        )
        CategoryPill(category = if (state.isPreFetch) "pending" else state.category)
    }
}

@Composable
private fun CategoryPill(category: String) {
    val (bg, fg, label) = when (category) {
        "high_capacity", "healthy" -> Triple(CIRISColors.StatusOk.copy(alpha = 0.15f), CIRISColors.StatusOk, category.uppercase().replace("_", " "))
        "moderate" -> Triple(CIRISColors.StatusWarn.copy(alpha = 0.15f), CIRISColors.StatusWarn, "MODERATE")
        "high_fragility" -> Triple(CIRISColors.StatusErr.copy(alpha = 0.15f), CIRISColors.StatusErr, "HIGH FRAGILITY")
        "pending" -> Triple(CIRISColors.TextDim.copy(alpha = 0.15f), CIRISColors.TextDim, "WARMING UP")
        else -> Triple(CIRISColors.TextDim.copy(alpha = 0.15f), CIRISColors.TextDim, category.uppercase())
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(bg)
            .border(1.dp, fg.copy(alpha = 0.40f), RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 4.dp)
            .testTag("capacity_category_pill"),
    ) {
        Text(text = label, color = fg, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.0.sp)
    }
}

@Composable
private fun CompositeScoreHero(state: CellVizState) {
    val local = state.localScore
    val fleet = state.compositeScore
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(CIRISColors.BackgroundDarker)
            .border(1.dp, CIRISColors.SignetTeal.copy(alpha = 0.30f), RoundedCornerShape(12.dp))
            .padding(20.dp)
            .testTag("capacity_composite_hero"),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = "Composite (𝒞_CIRIS = C · I_int · R · I_inc · S)",
                color = CIRISColors.TextTertiary,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            Row(verticalAlignment = Alignment.Bottom) {
                Text(
                    text = if (state.isPreFetch) "…" else fmt(fleet),
                    color = CIRISColors.AccentCyan,
                    fontSize = 44.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.testTag("capacity_composite_value"),
                )
                Spacer(Modifier.width(12.dp))
                local?.let {
                    Column {
                        Text(
                            text = "local",
                            color = CIRISColors.TextDim,
                            fontSize = 9.sp,
                            letterSpacing = 1.0.sp,
                        )
                        Text(
                            text = fmt(it),
                            color = CIRISColors.SignetTeal,
                            fontSize = 22.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.testTag("capacity_local_value"),
                        )
                    }
                }
            }
            Text(
                text = if (local != null) {
                    "Local reflects this device's CCA approximation (service health, LLM health, sustainability). Fleet is the template-aggregate across every install of the same agent template — your context."
                } else {
                    "Fleet score across every install of the same agent template. Local score climbs as the device accumulates operational evidence."
                },
                color = CIRISColors.TextSecondary,
                fontSize = 12.sp,
                lineHeight = 18.sp,
            )
            // Fragility — only show when measurably elevated
            if (!state.isPreFetch && state.fragilityIndex > 1.2f) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "Fragility index: ${fmt2(state.fragilityIndex)}",
                    color = CIRISColors.StatusWarn,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
    }
}

@Composable
private fun FactorRow(short: String, name: String, value: Float, description: String) {
    val clamped = value.coerceIn(0f, 1f)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(CIRISColors.BackgroundDarker.copy(alpha = 0.7f))
            .border(1.dp, Color.White.copy(alpha = 0.06f), RoundedCornerShape(10.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .testTag("capacity_factor_$short"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Code label
        Box(
            modifier = Modifier
                .width(58.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(CIRISColors.SignetTeal.copy(alpha = 0.15f))
                .padding(vertical = 6.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = short,
                color = CIRISColors.SignetTeal,
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
            )
        }
        Spacer(Modifier.width(14.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(name, color = CIRISColors.TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Text(description, color = CIRISColors.TextDim, fontSize = 11.sp, lineHeight = 16.sp)
            Spacer(Modifier.height(6.dp))
            LinearProgressIndicator(
                progress = clamped,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .clip(RoundedCornerShape(50)),
                color = CIRISColors.AccentCyan,
                trackColor = Color.White.copy(alpha = 0.06f),
            )
        }
        Spacer(Modifier.width(12.dp))
        Text(
            text = fmt(clamped),
            color = CIRISColors.TextPrimary,
            fontSize = 13.sp,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
private fun CapacityMaturityNote(state: CellVizState) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(CIRISColors.SignetTeal.copy(alpha = 0.06f))
            .border(1.dp, CIRISColors.SignetTeal.copy(alpha = 0.25f), RoundedCornerShape(10.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = "Why a fresh install isn't 1.00",
            color = CIRISColors.SignetTeal,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = "The sustained-coherence factor (S) needs operational evidence: roughly 30 successful interactions over a 30-day rolling window for a fully computed local score. Until then it floors at 0.30 — by design, so a brand-new agent doesn't claim coherence it hasn't earned. Keep using the agent and the number climbs honestly.",
            color = CIRISColors.TextSecondary,
            fontSize = 12.sp,
            lineHeight = 18.sp,
        )
        state.localScore?.let { local ->
            Text(
                text = "Right now your local score is ${fmt(local)}.",
                color = CIRISColors.TextTertiary,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}

@Composable
private fun FederationAttestationsGate(onIssueClick: (String) -> Unit) {
    val gate = SubstrateGate.LENSCORE_CAPACITY
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(CIRISColors.BackgroundDarker.copy(alpha = 0.5f))
            .border(1.dp, Color.White.copy(alpha = 0.06f), RoundedCornerShape(10.dp))
            .padding(14.dp)
            .testTag("federation_capacity_gate"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = "Federation attestations",
                color = CIRISColors.TextSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(CIRISColors.BusTool.copy(alpha = 0.15f))
                    .border(1.dp, CIRISColors.BusTool.copy(alpha = 0.40f), RoundedCornerShape(50))
                    .clickable { onIssueClick(gate.url) }
                    .padding(horizontal = 8.dp, vertical = 3.dp),
            ) {
                Text(
                    text = "COMING SOON",
                    color = CIRISColors.BusTool,
                    fontSize = 8.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.0.sp,
                )
            }
        }
        Text(
            text = "Per-cohort manifold conformity, correlated-action axes, and distributive-access readings ship when ${gate.shortRef} closes. Today's card shows local + fleet only.",
            color = CIRISColors.TextDim,
            fontSize = 11.sp,
            lineHeight = 16.sp,
        )
    }
}

// Integer-math formatter — String.format is JVM-only in commonMain.
private fun fmt(v: Float): String {
    val hundredths = (v.coerceIn(0f, 1f) * 100f + 0.5f).toInt()
    val whole = hundredths / 100
    val frac = hundredths % 100
    val fracStr = if (frac < 10) "0$frac" else "$frac"
    return "$whole.$fracStr"
}

// Same formatter for unbounded values like fragility (capped at 9.99 for display).
private fun fmt2(v: Float): String {
    val capped = v.coerceIn(0f, 9.99f)
    val hundredths = (capped * 100f + 0.5f).toInt()
    val whole = hundredths / 100
    val frac = hundredths % 100
    val fracStr = if (frac < 10) "0$frac" else "$frac"
    return "$whole.$fracStr"
}

/**
 * Deprecated overload — kept as the no-arg path for callers wired up before
 * the state-hoisted version landed. Renders a Coming Soon placeholder; new
 * callers should use the [state]-taking overload above.
 *
 * Once the CIRISApp.kt rewire wires every callsite through the state-hoisted
 * shape, delete this overload.
 */
@Deprecated(
    message = "Use the overload that takes CellVizState — the score now ships as a real card.",
    replaceWith = ReplaceWith("HealthReputationScreen(state, onIssueClick)"),
)
@Composable
fun HealthReputationScreen(onIssueClick: (String) -> Unit = {}) {
    ComingSoonPlaceholder(
        title = NavSurface.HealthReputation.label,
        icon = NavSurface.HealthReputation.icon,
        description = "Per-agent reputation surface. The state-hoisted overload of this composable ships now; this no-arg fallback renders the substrate-gate placeholder.",
        gate = SubstrateGate.LENSCORE_CAPACITY,
        onIssueClick = onIssueClick,
    )
}
