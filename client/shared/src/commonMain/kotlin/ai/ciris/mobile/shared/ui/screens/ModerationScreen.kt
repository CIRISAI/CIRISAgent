package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.safety.ModerationDuty
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.SafetyViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
 * **Moderation card** — moderation as a delegable DUTY, not a role (CC §4.5.x).
 *
 * Three things, all driving the local node's `/v1/safety/` routes:
 *  1. **File a report** — pick the duty + allegation type + target + note, then
 *     `POST /v1/safety/moderation`. The node admits IFF the signer holds the
 *     duty or sits on a live delegated chain (the §11.10 gate); a non-holder
 *     gets a 403 surfaced here ("the duty is held or delegated, never assumed").
 *  2. **Named moderator** — `GET /v1/safety/named-moderator/{community}` shows
 *     the CC 4.5.4 existence verdict: operate / auto-promote / quiesce. The
 *     invariant FAILS SECURE — better no group than an unmoderated one.
 *  3. **Delegable duty** — an explainer that you can moderate as yourself OR
 *     delegate the `moderate` duty to your agent / a trusted party (the
 *     delegation flow lives on the Family → Delegation surface).
 *
 * The app holds NO keys: every action is a plain localhost call; the node signs.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModerationScreen(
    viewModel: SafetyViewModel,
    onBack: () -> Unit,
    /** Navigate to the delegation flow (Family → Delegation), if present. */
    onOpenDelegation: (() -> Unit)? = null,
) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(Unit) { viewModel.probeIdentityAndStatus() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.moderation_title")) },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(onClick = onBack, modifier = Modifier.testable("btn_moderation_back")) {
                            Icon(CIRISIcons.arrowBack, contentDescription = localizedString("mobile.back"))
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
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = localizedString("mobile.moderation_intro"),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 14.sp,
            )

            // ── Community scope (shared by report + named-moderator) ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.handler, localizedString("mobile.moderation_community_section"))
                    OutlinedTextField(
                        value = state.communityKeyId,
                        onValueChange = viewModel::setCommunityKeyId,
                        label = { Text(localizedString("mobile.moderation_community_label")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_moderation_community"),
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(
                        onClick = { viewModel.loadNamedModerator() },
                        modifier = Modifier.testable("btn_load_named_moderator"),
                    ) {
                        if (state.namedModeratorLoading) {
                            CircularProgressIndicator(Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                        }
                        Text(localizedString("mobile.moderation_check_moderator"))
                    }

                    // Existence-invariant verdict.
                    state.namedModeratorVerdict?.let { v ->
                        Spacer(Modifier.height(10.dp))
                        val (label, detail) = when (v.verdict) {
                            "operate" -> localizedString("mobile.moderation_verdict_operate") to
                                localizedString("mobile.moderation_verdict_operate_detail")
                            "auto_promote" -> localizedString("mobile.moderation_verdict_autopromote") to
                                localizedString("mobile.moderation_verdict_autopromote_detail",
                                    "candidate", v.candidateKeyId ?: "?")
                            "quiesce" -> localizedString("mobile.moderation_verdict_quiesce") to
                                localizedString("mobile.moderation_verdict_quiesce_detail")
                            else -> v.verdict to ""
                        }
                        Text(label, fontWeight = FontWeight.Bold, fontSize = 15.sp,
                            color = MaterialTheme.colorScheme.onSurface)
                        if (detail.isNotEmpty()) {
                            Text(detail, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (state.namedModeratorFailsSecure) {
                            Text(localizedString("mobile.moderation_fails_secure"),
                                fontSize = 12.sp, color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }

            // ── File a report ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.warning, localizedString("mobile.moderation_report_section"))

                    Text(localizedString("mobile.moderation_duty_label"),
                        fontSize = 12.sp, fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 4.dp))
                    val duties = listOf(
                        ModerationDuty.MODERATE to localizedString("mobile.moderation_duty_moderate"),
                        ModerationDuty.TAKEDOWN to localizedString("mobile.moderation_duty_takedown"),
                        ModerationDuty.REVIEW to localizedString("mobile.moderation_duty_review"),
                    )
                    duties.forEach { (duty, label) ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(
                                selected = state.selectedDuty == duty,
                                onClick = { viewModel.setDuty(duty) },
                                modifier = Modifier.testable("duty_${duty.name.lowercase()}"),
                            )
                            Text(label, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
                        }
                    }

                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = state.allegationType,
                        onValueChange = viewModel::setAllegationType,
                        label = { Text(localizedString("mobile.moderation_allegation_label")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_allegation_type"),
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = state.targetKeyIdsRaw,
                        onValueChange = viewModel::setTargetKeyIdsRaw,
                        label = { Text(localizedString("mobile.moderation_targets_label")) },
                        modifier = Modifier.fillMaxWidth().testable("input_moderation_targets"),
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = state.reportNote,
                        onValueChange = viewModel::setReportNote,
                        label = { Text(localizedString("mobile.moderation_note_label")) },
                        modifier = Modifier.fillMaxWidth().testable("input_moderation_note"),
                    )
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = { viewModel.fileModeration() },
                        enabled = !state.filing,
                        modifier = Modifier.testable("btn_file_moderation"),
                    ) {
                        if (state.filing) {
                            CircularProgressIndicator(Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                        }
                        Text(localizedString("mobile.moderation_file_button"))
                    }
                    state.lastModerationAttestationId?.let {
                        Text(localizedString("mobile.moderation_filed_id", "id", it),
                            fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 6.dp))
                    }
                }
            }

            // ── Delegable duty explainer ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.send, localizedString("mobile.moderation_delegate_section"))
                    Text(localizedString("mobile.moderation_delegate_body"),
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (onOpenDelegation != null) {
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = onOpenDelegation,
                            modifier = Modifier.testable("btn_open_delegation"),
                        ) { Text(localizedString("mobile.moderation_open_delegation")) }
                    }
                }
            }

            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
            }
            state.message?.let {
                Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 13.sp)
            }
        }
    }
}

@Composable
internal fun SectionHeader(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.padding(bottom = 10.dp),
    ) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.width(20.dp).height(20.dp))
        Spacer(Modifier.width(8.dp))
        Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onSurface)
    }
}
