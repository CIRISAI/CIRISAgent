package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **First-class "Join the federation?" decision card** — the pivotal onboarding
 * choice, reused across BOTH the first-run wizard (FEDERATION_IDENTITY_SETUP) and
 * the catch-up "Add Federation ID" flow.
 *
 * The confirmed model (see CIRISServer `/v1/federation/announce`): announcing is
 * UPSTREAM of everything the community touches. A node can only send reasoning
 * traces to the trusted canonical server group and receive/join communities once
 * its owner identity is federation-visible (announced). Un-announced = self-scoped
 * = traces stay local-tier and never federate. So the trace opt-in is literally
 * *unlocked by* announcing, and this card presents that coupling directly:
 *
 *  - a prominent, deliberate announce switch (default OFF — privacy-first), with
 *    distinct copy for OFF (private, recommended) vs ON (join the community), then
 *  - the trace opt-in, GATED on announce: shown/enabled only when announce is ON;
 *    when OFF, a one-line "announce to enable" note in its place.
 *
 * Stateless by design — takes plain booleans + callbacks so it does not couple to
 * any specific ViewModel (SetupViewModel in first-run, NodeSwitcherViewModel in
 * catch-up). The app performs NO crypto; the local node owns the announce.
 *
 * NOTE: this is the richer replacement for the low-key `AnnounceOwnershipCard`
 * toggle in SetupScreen; that composable is kept intact for signature stability.
 */
/**
 * Localized string with a hardcoded fallback for keys not yet in the manifest.
 * [localizedString] returns the KEY itself when a key is absent (not ""), so a
 * plain `.ifEmpty {}` wouldn't fall back — we treat "blank OR equals the key" as
 * missing and render [fallback]. Lets new UI ship before en.json is updated.
 */
@Composable
private fun l10nOr(key: String, fallback: String): String {
    val v = localizedString(key)
    return if (v.isBlank() || v == key) fallback else v
}

@Composable
fun AnnounceDecisionCard(
    announce: Boolean,
    onAnnounceChange: (Boolean) -> Unit,
    traceOptIn: Boolean,
    onTraceOptInChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    announceTestTag: String = "toggle_announce_ownership",
    traceTestTag: String = "toggle_trace_opt_in",
) {
    val scheme = MaterialTheme.colorScheme
    // Emphasise the ON choice: primaryContainer when opting in, the calmer
    // surfaceVariant when staying private (the recommended default).
    val containerColor = if (announce) scheme.primaryContainer else scheme.surfaceVariant
    val onContainer = if (announce) scheme.onPrimaryContainer else scheme.onSurfaceVariant

    Surface(
        shape = RoundedCornerShape(14.dp),
        color = containerColor,
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            // ── Header ──────────────────────────────────────────────────────
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(text = "🌐", fontSize = 22.sp, modifier = Modifier.padding(end = 10.dp))
                Text(
                    text = l10nOr("mobile.announce_decision_title", "Join the federation?"),
                    color = onContainer,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                )
            }

            Spacer(Modifier.height(10.dp))

            // ── Tradeoff copy (distinct for ON vs OFF) ──────────────────────
            Text(
                text = if (announce) {
                    l10nOr(
                        "mobile.announce_decision_body_on",
                        "ON: your node becomes federation-visible. This is what lets you send " +
                            "reasoning traces to the trusted canonical server group and join " +
                            "communities as they come online. You can turn this off later.",
                    )
                } else {
                    l10nOr(
                        "mobile.announce_decision_body_off",
                        "OFF (recommended): fully private. Your node stays self-scoped — " +
                            "everything works locally and syncs across your own devices, but the " +
                            "community can't see or reach it. Turn this on to send traces and join " +
                            "communities.",
                    )
                },
                color = onContainer,
                fontSize = 13.sp,
                lineHeight = 19.sp,
            )

            Spacer(Modifier.height(14.dp))

            // ── The pivotal announce switch ─────────────────────────────────
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = l10nOr(
                        "mobile.announce_decision_toggle_label",
                        "Make my node federation-visible",
                    ),
                    color = onContainer,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(12.dp))
                Switch(
                    checked = announce,
                    onCheckedChange = { onAnnounceChange(it) },
                    modifier = Modifier.testableClickable(announceTestTag) {
                        onAnnounceChange(!announce)
                    },
                )
            }

            Spacer(Modifier.height(12.dp))
            HorizontalDivider(color = onContainer.copy(alpha = 0.15f))
            Spacer(Modifier.height(12.dp))

            // ── Trace opt-in — GATED on announce ────────────────────────────
            Text(
                text = l10nOr("mobile.announce_decision_trace_title", "Send reasoning traces"),
                color = onContainer,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(6.dp))

            AnimatedVisibility(visible = announce) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testableClickable(traceTestTag) { onTraceOptInChange(!traceOptIn) },
                ) {
                    Checkbox(
                        checked = traceOptIn,
                        onCheckedChange = { onTraceOptInChange(it) },
                        colors = CheckboxDefaults.colors(checkedColor = scheme.primary),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = l10nOr(
                            "mobile.announce_decision_trace_desc",
                            "Share reasoning-quality scores and decision patterns (no message " +
                                "content) with the trusted canonical server group.",
                        ),
                        color = onContainer,
                        fontSize = 13.sp,
                        lineHeight = 18.sp,
                    )
                }
            }

            AnimatedVisibility(visible = !announce) {
                Text(
                    text = l10nOr(
                        "mobile.announce_decision_trace_locked",
                        "Turn on announcing above to enable sending reasoning traces and joining " +
                            "communities.",
                    ),
                    color = onContainer.copy(alpha = 0.6f),
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                )
            }
        }
    }
}
