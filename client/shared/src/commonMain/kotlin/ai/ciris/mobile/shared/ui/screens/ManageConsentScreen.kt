package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.ConsentObjectsViewModel
import ai.ciris.mobile.shared.viewmodels.DataManagementViewModel
import ai.ciris.mobile.shared.viewmodels.GrantDirectionState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Manage Consent — view + manage the consent objects this device holds.
 *
 * Today the fabric exposes one consent object through a node-driven API: the
 * **bilateral `consent:replication`** peering between two nodes A↔B, driven by
 * [ConsentObjectsViewModel] (`POST /v1/federation/peering` in each direction —
 * ratified iff both grants present). This screen renders the current grant
 * state for the two selected nodes and lets the user (re)run the set-up.
 *
 * **Revoke** is intentionally a disabled/TODO affordance: the node-side
 * federation API exposes `self-key-record` + `peering` but **no peering-revoke
 * (`withdraws`) endpoint yet** — see the upstream flag. The app does no crypto,
 * so it cannot synthesise a withdrawal; it can only drive the node once an
 * endpoint exists.
 *
 * For the **user-data** consent stream (`consent:state` — TEMPORARY / PARTNERED /
 * ANONYMOUS, GDPR), this screen points the user at the existing Consent surface
 * via [onOpenUserConsent] rather than duplicating it.
 *
 * @param onOpenUserConsent navigate to the existing user-data Consent screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManageConsentScreen(
    viewModel: ConsentObjectsViewModel,
    onBack: () -> Unit,
    onOpenUserConsent: () -> Unit = {},
    /**
     * Trace-consent surface. The **same** `consent:community_trust:v1` CEG
     * object the setup wizard writes, viewed post-config — one-tap opt-in/out
     * drives [DataManagementViewModel.updateAccordConsent] (the my-data PUT that
     * re-emits/withdraws the grant AND re-arms the running adapter's seal). Null
     * = caller didn't wire it (card hidden); we never invent a second write path.
     */
    dataViewModel: DataManagementViewModel? = null,
    /**
     * Whether a node-side peering-revoke endpoint exists. False today; when the
     * server ships `withdraws` for consent:replication, flip this and wire the
     * revoke action.
     */
    revokeEndpointAvailable: Boolean = false,
) {
    val state by viewModel.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.manage_consent_title")) },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testable("btn_manage_consent_back"),
                        ) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("mobile.common_back"),
                            )
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = localizedString("mobile.manage_consent_subtitle"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            state.error?.let { msg ->
                MessageBar(msg, isError = true) { viewModel.clearMessages() }
            }
            state.message?.let { msg ->
                MessageBar(msg, isError = false) { viewModel.clearMessages() }
            }

            // ── Send reasoning traces (consent:community_trust) ──────────────
            // An alternative view of the SAME CEG object the wizard writes.
            dataViewModel?.let { SendTracesCard(it) }

            // ── consent:replication peering ──────────────────────────────────
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        localizedString("mobile.manage_consent_replication_title"),
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                    )
                    Text(
                        localizedString("mobile.manage_consent_replication_desc"),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    if (state.nodeA == null || state.nodeB == null) {
                        Text(
                            localizedString("mobile.manage_consent_need_two_nodes"),
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.error,
                        )
                    } else {
                        // Node pair + direction states.
                        DirectionRow(
                            label = "${state.nodeA?.name}  →  ${state.nodeB?.name}",
                            grant = state.aToB,
                        )
                        DirectionRow(
                            label = "${state.nodeB?.name}  →  ${state.nodeA?.name}",
                            grant = state.bToA,
                        )

                        Surface(
                            color = if (state.isRatified) MaterialTheme.colorScheme.tertiaryContainer
                            else MaterialTheme.colorScheme.surface,
                            shape = RoundedCornerShape(4.dp),
                        ) {
                            Text(
                                text = if (state.isRatified)
                                    localizedString("mobile.manage_consent_ratified")
                                else localizedString("mobile.manage_consent_not_ratified"),
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Medium,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            )
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = { viewModel.runBilateralPeering() },
                                enabled = state.canRun,
                                modifier = Modifier.testable("btn_consent_setup_peering"),
                            ) {
                                if (state.isRunning) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(16.dp),
                                        strokeWidth = 2.dp,
                                    )
                                } else {
                                    Text(
                                        if (state.isRatified)
                                            localizedString("mobile.manage_consent_resetup")
                                        else localizedString("mobile.manage_consent_setup"),
                                    )
                                }
                            }

                            // Revoke — disabled until a node-side withdraws endpoint exists.
                            OutlinedButton(
                                onClick = { /* TODO: wire when server ships withdraws */ },
                                enabled = revokeEndpointAvailable && state.isRatified,
                                modifier = Modifier.testable("btn_consent_revoke_peering"),
                            ) {
                                Text(localizedString("mobile.manage_consent_revoke"))
                            }
                        }
                        if (!revokeEndpointAvailable) {
                            Text(
                                localizedString("mobile.manage_consent_revoke_todo"),
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(4.dp))

            // ── user-data consent pointer ────────────────────────────────────
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        localizedString("mobile.manage_consent_userdata_title"),
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                    )
                    Text(
                        localizedString("mobile.manage_consent_userdata_desc"),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(
                        onClick = onOpenUserConsent,
                        modifier = Modifier.testable("btn_open_user_consent"),
                    ) {
                        Icon(CIRISIcons.lock, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(localizedString("mobile.manage_consent_open_userdata"))
                    }
                }
            }
        }
    }
}

/**
 * "Send reasoning traces" opt-in — the post-config, tappable view of the same
 * `consent:community_trust:v1` grant the setup wizard writes. Reads live state
 * from [DataManagementViewModel.accordSettings] (the my-data GET) and toggles
 * via [DataManagementViewModel.updateAccordConsent] (the my-data PUT — the ONE
 * write path; it re-emits/withdraws the CEG grant and re-arms the seal).
 */
@Composable
private fun SendTracesCard(dataViewModel: DataManagementViewModel) {
    val accord by dataViewModel.accordSettings.collectAsState()
    val communityPeer by dataViewModel.communityPeer.collectAsState()

    // Populate accordSettings + community peer on entry (best-effort; the VM
    // guards its own concurrency and degrades to a "federation pending" view).
    LaunchedEffect(Unit) { dataViewModel.refresh() }

    val armed = accord?.consentGiven == true
    Surface(
        color = if (armed) MaterialTheme.colorScheme.primaryContainer
        else MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.weight(1f)) {
                    Text(
                        localizedString("mobile.announce_decision_trace_title"),
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                    )
                    Text(
                        localizedString("mobile.manage_consent_traces_desc"),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.width(8.dp))
                Switch(
                    checked = armed,
                    onCheckedChange = { dataViewModel.updateAccordConsent(it) },
                    modifier = Modifier.testable("toggle_send_traces"),
                )
            }

            // Status chip — armed vs. paused (reuses the Data & Privacy vocab).
            Surface(
                color = if (armed) MaterialTheme.colorScheme.tertiaryContainer
                else MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(4.dp),
            ) {
                Text(
                    text = if (armed) localizedString("mobile.data_community_consent_active")
                    else localizedString("mobile.data_community_consent_paused"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                )
            }

            // Target (directed counterparty) — the canonical CIRIS community.
            Text(
                text = "${localizedString("mobile.data_community_label")}: " +
                    (communityPeer?.aliasOverride
                        ?: localizedString("mobile.data_community_canonical")),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // Detail level + events sent (only once accord settings resolve).
            accord?.let { a ->
                Text(
                    text = "${localizedString("mobile.data_detail_level")}: ${a.traceLevel ?: "-"}  ·  " +
                        "${localizedString("mobile.data_events_sent")}: ${a.eventsSent}",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } ?: Text(
                localizedString("mobile.data_community_pending"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DirectionRow(label: String, grant: GrantDirectionState) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(label, fontSize = 12.sp, modifier = Modifier.weight(1f))
        val (text, color) = when (grant) {
            GrantDirectionState.GRANTED ->
                localizedString("mobile.manage_consent_granted") to MaterialTheme.colorScheme.primary
            GrantDirectionState.IN_PROGRESS ->
                localizedString("mobile.manage_consent_in_progress") to MaterialTheme.colorScheme.onSurfaceVariant
            GrantDirectionState.FAILED ->
                localizedString("mobile.manage_consent_failed") to MaterialTheme.colorScheme.error
            GrantDirectionState.IDLE ->
                localizedString("mobile.manage_consent_idle") to MaterialTheme.colorScheme.onSurfaceVariant
        }
        Text(text, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = color)
    }
}

@Composable
private fun MessageBar(msg: String, isError: Boolean, onDismiss: () -> Unit) {
    Surface(
        color = if (isError) MaterialTheme.colorScheme.errorContainer
        else MaterialTheme.colorScheme.tertiaryContainer,
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(modifier = Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = msg,
                fontSize = 12.sp,
                color = if (isError) MaterialTheme.colorScheme.onErrorContainer
                else MaterialTheme.colorScheme.onTertiaryContainer,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onDismiss) { Text(localizedString("mobile.common_close")) }
        }
    }
}
