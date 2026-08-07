package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.selfreader.AdminMessage
import ai.ciris.mobile.shared.models.selfreader.AdminRefusalDto
import ai.ciris.mobile.shared.models.selfreader.QuarantineFoldDto
import ai.ciris.mobile.shared.models.selfreader.ReaderDecision
import ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome
import ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome
import ai.ciris.mobile.shared.models.selfreader.ReaderFoldResponse
import ai.ciris.mobile.shared.models.selfreader.ReaderJudgementDto
import ai.ciris.mobile.shared.models.selfreader.ReaderStanding
import ai.ciris.mobile.shared.models.selfreader.SelfActOutcome
import ai.ciris.mobile.shared.models.selfreader.SelfAxis
import ai.ciris.mobile.shared.models.selfreader.SelfAxisStandingDto
import ai.ciris.mobile.shared.models.selfreader.SelfStanding
import ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * Tier S (self-directed) + tier R (per-reader) — `CIRISServer/src/admin_ops.rs`,
 * the two rungs that act on NOBODY else. Hosted by [NetworkOpsScreen], which is
 * already "this node, locally" — tier S is this node's own standing and tier R
 * is this node's own reader policy, so both belong beside the node's federation
 * identity rather than beside the agent's runtime pipeline.
 *
 * The three things this file is built to render correctly:
 *
 * 1. **Three tier-S axes, three cards, three standings.** `shed`,
 *    `stop-accepting` and `compelled` are never one switch and never one status
 *    line: "this node chose to stop" and "this node was made to stop" are the
 *    same observable with opposite meanings, and a downstream party has no other
 *    signal for the difference.
 * 2. **Three zeroes that never render alike.** Never declared / declared and
 *    lifted / could not be read each get their own colour, their own label AND
 *    their own meaning line — and an unreadable standing is never allowed to
 *    look like a clear one, which is exactly why the server puts it on both
 *    halves of its response.
 * 3. **Declining is normal.** A declined judgement is drawn in the same weight
 *    as an honoured one, in a neutral container — never an error colour, never a
 *    warning icon, never a failure toast.
 */
@Composable
fun SelfAndReaderOpsSection(
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().testable("section_self_reader_ops"),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SelfDirectedCard(apiClient)
        ReaderPolicyCard(apiClient)
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  Tier S — self-directed
// ═════════════════════════════════════════════════════════════════════════════

/** One pending tier S act, waiting on the operator's delegation + reason. */
private data class SelfActPrompt(val axis: String, val declaring: Boolean)

@Composable
private fun SelfDirectedCard(apiClient: CIRISApiClient) {
    var outcome by remember { mutableStateOf<SelfStandingOutcome?>(null) }
    var loading by remember { mutableStateOf(true) }
    var prompt by remember { mutableStateOf<SelfActPrompt?>(null) }
    var lastAct by remember { mutableStateOf<SelfActOutcome?>(null) }
    var working by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun reload() {
        loading = true
        outcome = apiClient.getSelfStanding()
        loading = false
    }

    LaunchedEffect(Unit) { reload() }

    SelfROpsCard(testTag = "card_self_directed") {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    uiText("network_ops.self.title", "Self-directed (tier S)"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    uiText("network_ops.self.subtitle", "Acts on this node and nobody else"),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(
                onClick = { scope.launch { reload() } },
                enabled = !loading,
                modifier = Modifier.testableClickable("btn_self_refresh") {
                    scope.launch { reload() }
                },
            ) { Text(uiText("network_ops.self.refresh", "Re-read standings")) }
        }

        Text(
            uiText(
                "network_ops.self.partition_only",
                "The only rung that still works while partitioned — every other rung has to " +
                    "reach someone.",
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            uiText(
                "network_ops.self.records_only",
                "Each act records an attributed declaration and nothing more. No loop on this " +
                    "node reads them, so nothing is throttled, gated or stopped by the act itself.",
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (loading && outcome == null) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth().testable("progress_self_standing"))
        }

        when (val o = outcome) {
            null -> Unit

            // The node itself is gone. Tier S is the rung for exactly this
            // moment — so say the standings are UNKNOWN, never blank them.
            is SelfStandingOutcome.Unreachable -> SelfRBanner(
                tone = SelfRTone.UNKNOWN,
                title = uiText("network_ops.self.unreachable_title", "This node could not be reached"),
                body = uiText(
                    "network_ops.self.unreachable_body",
                    "The three standings are unknown — which is not 'nothing in force'. Tier S " +
                        "acts are local to this node, so they are available again the moment it " +
                        "answers.",
                ),
                detail = o.detail,
                testTag = "banner_self_unreachable",
            )

            is SelfStandingOutcome.Refused -> SelfRBanner(
                tone = SelfRTone.UNKNOWN,
                title = uiText("network_ops.self.refused_title", "The node refused this read"),
                body = uiText(
                    "network_ops.self.refused_body",
                    "The standings are unknown. A refused read is not a clear one.",
                ),
                detail = refusalDetail(o.refusal, o.httpStatus),
                testTag = "banner_self_refused",
            )

            is SelfStandingOutcome.Read -> {
                if (o.partiallyUnreadable) {
                    SelfRBanner(
                        tone = SelfRTone.UNKNOWN,
                        title = uiText(
                            "network_ops.self.unreadable_axes_title",
                            "Some standings could not be read",
                        ),
                        body = uiText(
                            "network_ops.self.unreadable_axes_body",
                            "The node answered, but it could not read the axes marked below. It " +
                                "does not know its own standing there — do not read that as clear.",
                        ),
                        detail = o.response.unreadableAxes
                            ?.entries
                            ?.joinToString("\n") { "${it.key}: ${it.value}" },
                        testTag = "banner_self_unreadable_axes",
                    )
                }
                SelfROpsRow(
                    uiText("network_ops.self.node_key", "This node"),
                    o.response.nodeKeyId.ifBlank { "—" },
                    "row_self_node_key",
                    mono = true,
                )
                Text(
                    uiText(
                        "network_ops.self.axes_never_folded",
                        "Three separate axes, three separate acts. A node that CHOSE to stop and " +
                            "a node that was MADE to stop are the same observable with opposite " +
                            "meanings, so they are never one switch.",
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                o.response.axes().forEach { axis ->
                    SelfAxisCard(
                        axis = axis,
                        onDeclare = { prompt = SelfActPrompt(axis.axis, declaring = true) },
                        onLift = { prompt = SelfActPrompt(axis.axis, declaring = false) },
                    )
                }
                serverMessage(o.response.distinctZeroes)?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testable("text_self_distinct_zeroes"),
                    )
                }
                serverMessage(o.response.partition)?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testable("text_self_partition"),
                    )
                }
            }
        }

        lastAct?.let { SelfActResult(it) }
    }

    prompt?.let { p ->
        SelfActDialog(
            prompt = p,
            working = working,
            onDismiss = { prompt = null },
            onConfirm = { delegationId, reason, compelledBy ->
                working = true
                scope.launch {
                    val result = when (p.axis to p.declaring) {
                        SelfAxis.LOAD_SHED to true -> apiClient.selfShedLoad(delegationId, reason)
                        SelfAxis.LOAD_SHED to false -> apiClient.selfResumeLoad(delegationId, reason)
                        SelfAxis.ACCEPTING to true -> apiClient.selfStopAccepting(delegationId, reason)
                        SelfAxis.ACCEPTING to false -> apiClient.selfResumeAccepting(delegationId, reason)
                        // `compelled_by` rides on the compulsion DECLARATION alone.
                        SelfAxis.LEGAL_COMPULSION to true ->
                            apiClient.selfDeclareCompelled(delegationId, reason, compelledBy)
                        else -> apiClient.selfCompulsionLifted(delegationId, reason)
                    }
                    lastAct = result
                    working = false
                    prompt = null
                    if (result is SelfActOutcome.Recorded) reload()
                }
            },
        )
    }
}

/**
 * One axis. Its own standing, its own history counts, its own two acts —
 * nothing on this card is shared with the other two.
 */
@Composable
private fun SelfAxisCard(
    axis: SelfAxisStandingDto,
    onDeclare: () -> Unit,
    onLift: () -> Unit,
) {
    val standing = axis.standingValue
    val tag = axis.axis.ifBlank { "unknown" }
    Surface(
        modifier = Modifier.fillMaxWidth().testable("card_self_axis_$tag"),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                axisTitle(axis.axis),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                axisQuestion(axis.axis),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            SelfStandingChip(standing, "chip_self_standing_$tag")
            Text(
                standingMeaning(standing),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testable("text_self_meaning_$tag"),
            )
            // The server's own sentence for this standing, resolved through the
            // bundle (id first, English source only as a fallback).
            serverMessage(axis.message)?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            axis.since?.let { SelfROpsRow(uiText("network_ops.self.since", "Since"), it, "row_self_since_$tag") }
            axis.reason?.let {
                SelfROpsRow(uiText("network_ops.self.reason_label", "Reason recorded"), it, "row_self_reason_$tag")
            }
            axis.delegationId?.let {
                SelfROpsRow(
                    uiText("network_ops.self.delegation", "Under delegation"),
                    it,
                    "row_self_delegation_$tag",
                    mono = true,
                )
            }
            axis.eventId?.let {
                SelfROpsRow(uiText("network_ops.self.event", "Event"), it, "row_self_event_$tag", mono = true)
            }
            // History, not state: "declared twice and lifted twice" is a
            // different fact from "never declared", and the counts say so even
            // when the current standing is the same shape.
            Text(
                uiText(
                    "network_ops.self.counts",
                    mapOf(
                        "declarations" to axis.counts.declarations.toString(),
                        "lifts" to axis.counts.lifts.toString(),
                    ),
                    "Declared ${axis.counts.declarations}× · lifted ${axis.counts.lifts}×",
                ),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testable("text_self_counts_$tag"),
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onDeclare,
                    modifier = Modifier.testableClickable("btn_self_declare_$tag") { onDeclare() },
                ) { Text(axisDeclareLabel(axis.axis)) }
                OutlinedButton(
                    onClick = onLift,
                    // Only a standing we could READ can rule a lift out. An
                    // unreadable axis leaves both acts available, because we do
                    // not know that nothing was declared.
                    enabled = standing != SelfStanding.NEVER_DECLARED,
                    modifier = Modifier.testableClickable("btn_self_lift_$tag") { onLift() },
                ) { Text(axisLiftLabel(axis.axis)) }
            }
            if (standing == SelfStanding.NEVER_DECLARED) {
                Text(
                    uiText(
                        "network_ops.self.lift_disabled_hint",
                        "Nothing has been declared on this axis, so there is nothing to lift.",
                    ),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * The four standings, four visuals. The three zeroes differ in colour, in label
 * AND in the meaning line beneath — one of those alone is the collapse this
 * rung exists to avoid.
 */
@Composable
private fun SelfStandingChip(standing: SelfStanding, testTag: String) {
    val label: String
    val container: androidx.compose.ui.graphics.Color
    val content: androidx.compose.ui.graphics.Color
    var outlined = false
    when (standing) {
        SelfStanding.IN_FORCE -> {
            label = uiText("network_ops.self.standing.in_force", "In force")
            container = MaterialTheme.colorScheme.primary
            content = MaterialTheme.colorScheme.onPrimary
        }
        SelfStanding.LIFTED -> {
            label = uiText("network_ops.self.standing.lifted", "Declared, then lifted")
            container = MaterialTheme.colorScheme.secondaryContainer
            content = MaterialTheme.colorScheme.onSecondaryContainer
        }
        SelfStanding.NEVER_DECLARED -> {
            label = uiText("network_ops.self.standing.never_declared", "Never declared")
            container = MaterialTheme.colorScheme.surface
            content = MaterialTheme.colorScheme.onSurfaceVariant
            outlined = true
        }
        SelfStanding.UNREADABLE -> {
            label = uiText("network_ops.self.standing.unreadable", "Standing unknown — could not read")
            container = MaterialTheme.colorScheme.errorContainer
            content = MaterialTheme.colorScheme.onErrorContainer
        }
        SelfStanding.UNKNOWN -> {
            label = uiText("network_ops.self.standing.unknown", "Unrecognised standing")
            container = MaterialTheme.colorScheme.errorContainer
            content = MaterialTheme.colorScheme.onErrorContainer
            outlined = true
        }
    }
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = container,
        contentColor = content,
        border = if (outlined) BorderStroke(1.dp, MaterialTheme.colorScheme.outline) else null,
        modifier = Modifier.testable(testTag),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun standingMeaning(standing: SelfStanding): String = when (standing) {
    SelfStanding.IN_FORCE -> uiText(
        "network_ops.self.standing.in_force_meaning",
        "This node declared it and has not lifted it.",
    )
    SelfStanding.LIFTED -> uiText(
        "network_ops.self.standing.lifted_meaning",
        "Not in force now — and not the same fact as never having declared it.",
    )
    SelfStanding.NEVER_DECLARED -> uiText(
        "network_ops.self.standing.never_declared_meaning",
        "No act on this axis was ever recorded here.",
    )
    SelfStanding.UNREADABLE -> uiText(
        "network_ops.self.standing.unreadable_meaning",
        "The record could not be read, so this node does not know its own standing. This is " +
            "NOT 'nothing in force'.",
    )
    SelfStanding.UNKNOWN -> uiText(
        "network_ops.self.standing.unknown_meaning",
        "The node reported a standing this app does not recognise. Treat it as unknown, never " +
            "as clear.",
    )
}

/** What one act produced: the record, and what it does NOT reach. */
@Composable
private fun SelfActResult(outcome: SelfActOutcome) {
    when (outcome) {
        is SelfActOutcome.Recorded -> SelfRBanner(
            tone = SelfRTone.NEUTRAL,
            title = uiText("network_ops.self.recorded_title", "Recorded"),
            body = serverMessage(outcome.response.enforcement)
                ?: uiText(
                    "network_ops.self.records_only",
                    "Each act records an attributed declaration and nothing more.",
                ),
            detail = listOfNotNull(
                outcome.response.eventId?.let { "event: $it" },
                serverMessage(outcome.response.lift),
                serverMessage(outcome.response.reversal?.note),
            ).joinToString("\n").ifBlank { null },
            testTag = "banner_self_act_recorded",
        )
        is SelfActOutcome.Refused -> SelfRBanner(
            tone = SelfRTone.PROBLEM,
            title = uiText("network_ops.self.act_refused_title", "The act was refused"),
            body = uiText(
                "network_ops.self.act_refused_body",
                "Nothing was recorded. The standings above are unchanged.",
            ),
            detail = refusalDetail(outcome.refusal, outcome.httpStatus),
            testTag = "banner_self_act_refused",
        )
        is SelfActOutcome.Unreachable -> SelfRBanner(
            tone = SelfRTone.UNKNOWN,
            title = uiText("network_ops.self.act_unreachable_title", "This node could not be reached"),
            body = uiText(
                "network_ops.self.act_unreachable_body",
                "It is not known whether the act was recorded. Re-read the standings once the " +
                    "node answers.",
            ),
            detail = outcome.detail,
            testTag = "banner_self_act_unreachable",
        )
    }
}

/** delegation + reason, and `compelled_by` on the compulsion declaration ONLY. */
@Composable
private fun SelfActDialog(
    prompt: SelfActPrompt,
    working: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (delegationId: String, reason: String, compelledBy: String?) -> Unit,
) {
    var delegationId by remember(prompt) { mutableStateOf("") }
    var reason by remember(prompt) { mutableStateOf("") }
    var compelledBy by remember(prompt) { mutableStateOf("") }
    val carriesCompelledBy = prompt.axis == SelfAxis.LEGAL_COMPULSION && prompt.declaring

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                if (prompt.declaring) axisDeclareLabel(prompt.axis) else axisLiftLabel(prompt.axis),
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    axisQuestion(prompt.axis),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = delegationId,
                    onValueChange = { delegationId = it },
                    label = {
                        Text(uiText("network_ops.self.dialog.delegation_label", "Owner delegation id"))
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testable("input_self_delegation_id"),
                )
                Text(
                    uiText(
                        "network_ops.self.dialog.delegation_hint",
                        "The owner's own delegates_to id. A self-directed act is the owner's own: " +
                            "a third party's serve grant will not do.",
                    ),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    label = { Text(uiText("network_ops.self.dialog.reason_label", "Reason (required)")) },
                    modifier = Modifier.fillMaxWidth().testable("input_self_reason"),
                )
                Text(
                    uiText(
                        "network_ops.self.dialog.reason_hint",
                        "Recorded verbatim and never interpreted. An act with no recorded reason " +
                            "is indistinguishable from an unauthorised one once the actor is gone.",
                    ),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (carriesCompelledBy) {
                    OutlinedTextField(
                        value = compelledBy,
                        onValueChange = { compelledBy = it },
                        label = {
                            Text(
                                uiText(
                                    "network_ops.self.dialog.compelled_by_label",
                                    "Compelled by (optional)",
                                ),
                            )
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_self_compelled_by"),
                    )
                    Text(
                        uiText(
                            "network_ops.self.dialog.compelled_by_hint",
                            "Only the compulsion carries this. Leave it blank if you cannot say — " +
                                "'compelled, cannot say by whom' is a real answer, and a gagged " +
                                "operator can still leave the trace.",
                        ),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(delegationId.trim(), reason.trim(), compelledBy) },
                enabled = !working && delegationId.isNotBlank() && reason.isNotBlank(),
                modifier = Modifier.testableClickable("btn_self_confirm") {
                    onConfirm(delegationId.trim(), reason.trim(), compelledBy)
                },
            ) {
                Text(
                    if (working) {
                        uiText("network_ops.self.dialog.working", "Recording…")
                    } else {
                        uiText("network_ops.self.dialog.confirm", "Record")
                    },
                )
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_self_cancel") { onDismiss() },
            ) { Text(uiText("network_ops.self.dialog.cancel", "Cancel")) }
        },
    )
}

// ═════════════════════════════════════════════════════════════════════════════
//  Tier R — per-reader
// ═════════════════════════════════════════════════════════════════════════════

private data class ReaderPrompt(val judgementId: String, val declining: Boolean)

@Composable
private fun ReaderPolicyCard(apiClient: CIRISApiClient) {
    var subject by remember { mutableStateOf("") }
    var outcome by remember { mutableStateOf<ReaderFoldOutcome?>(null) }
    var loading by remember { mutableStateOf(false) }
    var prompt by remember { mutableStateOf<ReaderPrompt?>(null) }
    var lastDecision by remember { mutableStateOf<ReaderDecisionOutcome?>(null) }
    var working by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun reload(subjectKeyId: String) {
        if (subjectKeyId.isBlank()) return
        loading = true
        outcome = apiClient.readerFold(subjectKeyId)
        loading = false
    }

    SelfROpsCard(testTag = "card_reader_policy") {
        Text(
            uiText("network_ops.reader.title", "What this reader honours (tier R)"),
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            uiText(
                "network_ops.reader.subtitle",
                "Other parties' judgements, and what THIS node's reader policy makes of them",
            ),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            uiText(
                "network_ops.reader.advisory",
                "An issued judgement is advisory to each reader. Declining one is a first-class " +
                    "outcome, not an error: two readers with different policies reaching " +
                    "different, both-valid states from the same judgement is the design working.",
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        OutlinedTextField(
            value = subject,
            onValueChange = { subject = it },
            label = { Text(uiText("network_ops.reader.subject_label", "Subject key id")) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testable("input_reader_subject"),
        )
        Button(
            onClick = { scope.launch { reload(subject.trim()) } },
            enabled = !loading && subject.isNotBlank(),
            modifier = Modifier.testableClickable("btn_reader_fold") {
                scope.launch { reload(subject.trim()) }
            },
        ) {
            Text(
                if (loading) {
                    uiText("network_ops.reader.reading", "Reading…")
                } else {
                    uiText("network_ops.reader.read", "Read this reader's fold")
                },
            )
        }

        when (val o = outcome) {
            null -> Unit

            is ReaderFoldOutcome.Unreachable -> SelfRBanner(
                tone = SelfRTone.UNKNOWN,
                title = uiText("network_ops.reader.unreachable_title", "This node could not be reached"),
                body = uiText(
                    "network_ops.reader.unreachable_body",
                    "Tier R reads what this node holds, so nothing can be said about the subject " +
                        "until it answers. Unlike tier S, this rung needs the node.",
                ),
                detail = o.detail,
                testTag = "banner_reader_unreachable",
            )

            is ReaderFoldOutcome.Refused -> SelfRBanner(
                tone = SelfRTone.UNKNOWN,
                title = uiText("network_ops.reader.refused_title", "The node refused this read"),
                body = uiText(
                    "network_ops.reader.refused_body",
                    "Nothing can be concluded about what this reader honours.",
                ),
                detail = refusalDetail(o.refusal, o.httpStatus),
                testTag = "banner_reader_refused",
            )

            // The 503 half. NOT "no judgements" and NOT "nothing withheld".
            is ReaderFoldOutcome.Unreadable -> SelfRBanner(
                tone = SelfRTone.UNKNOWN,
                title = uiText(
                    "network_ops.reader.standing.unreadable",
                    "This reader could not read its own state",
                ),
                body = serverMessage(o.response.message)
                    ?: uiText(
                        "network_ops.reader.standing.unreadable_meaning",
                        "NOT 'no judgements' and NOT 'nothing withheld' — an unreadable policy " +
                            "shown as an empty one silently drops every restriction it carried.",
                    ),
                detail = o.response.error,
                testTag = "banner_reader_unreadable",
            )

            is ReaderFoldOutcome.Read -> ReaderFoldBody(
                response = o.response,
                onHonour = { prompt = ReaderPrompt(it, declining = false) },
                onDecline = { prompt = ReaderPrompt(it, declining = true) },
            )
        }

        lastDecision?.let { ReaderDecisionResult(it) }
    }

    prompt?.let { p ->
        ReaderDecisionDialog(
            prompt = p,
            working = working,
            onDismiss = { prompt = null },
            onConfirm = { delegationId, reason ->
                working = true
                scope.launch {
                    val result = if (p.declining) {
                        apiClient.readerDecline(p.judgementId, delegationId, reason)
                    } else {
                        apiClient.readerHonour(p.judgementId, delegationId, reason)
                    }
                    lastDecision = result
                    working = false
                    prompt = null
                    if (result is ReaderDecisionOutcome.Recorded) reload(subject.trim())
                }
            },
        )
    }
}

@Composable
private fun ReaderFoldBody(
    response: ReaderFoldResponse,
    onHonour: (String) -> Unit,
    onDecline: (String) -> Unit,
) {
    val standing = response.standingValue
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        val standingLabel = when (standing) {
            ReaderStanding.DECIDED -> uiText("network_ops.reader.standing.decided", "Judgements classified")
            ReaderStanding.NO_JUDGEMENTS_HELD ->
                uiText("network_ops.reader.standing.none_held", "No judgements held here")
            ReaderStanding.UNREADABLE ->
                uiText("network_ops.reader.standing.unreadable", "This reader could not read its own state")
            ReaderStanding.UNKNOWN ->
                uiText("network_ops.reader.standing.unknown", "Unrecognised standing")
        }
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = if (standing.isKnown) {
                MaterialTheme.colorScheme.surfaceVariant
            } else {
                MaterialTheme.colorScheme.errorContainer
            },
            contentColor = if (standing.isKnown) {
                MaterialTheme.colorScheme.onSurfaceVariant
            } else {
                MaterialTheme.colorScheme.onErrorContainer
            },
            modifier = Modifier.testable("chip_reader_standing"),
        ) {
            Text(
                standingLabel,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            )
        }
        serverMessage(response.message)?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        SelfROpsRow(
            uiText("network_ops.reader.held", "Judgements held"),
            response.counts.judgementsHeld.toString(),
            "row_reader_held",
        )
        SelfROpsRow(
            uiText("network_ops.reader.subscription", "Subscribed roots"),
            response.subscription.count.toString(),
            "row_reader_subscription",
        )

        response.judgements.forEach { j ->
            ReaderJudgementRow(judgement = j, onHonour = onHonour, onDecline = onDecline)
        }

        ReaderFoldComparison(response)
    }
}

/**
 * One judgement, and what this reader does about it.
 *
 * Honour and decline are drawn as **peers**: same button weight, same row
 * treatment, no error colour and no warning icon on the decline. Rendering a
 * decline as a failure would invert the meaning of the whole rung.
 */
@Composable
private fun ReaderJudgementRow(
    judgement: ReaderJudgementDto,
    onHonour: (String) -> Unit,
    onDecline: (String) -> Unit,
) {
    val decision = judgement.decisionValue
    val id = judgement.judgementId
    Surface(
        modifier = Modifier.fillMaxWidth().testable("row_reader_judgement_${id.take(16)}"),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ReaderDecisionChip(decision, "chip_reader_decision_${id.take(16)}")
            serverMessage(judgement.message)?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            SelfROpsRow(uiText("network_ops.reader.judgement", "Judgement"), id, "row_reader_id", mono = true)
            SelfROpsRow(
                uiText("network_ops.reader.signer", "Signed by"),
                judgement.signerKeyId,
                "row_reader_signer",
                mono = true,
            )
            judgement.dimension?.let {
                SelfROpsRow(uiText("network_ops.reader.dimension", "Dimension"), it, "row_reader_dimension")
            }
            judgement.assertedAt?.let {
                SelfROpsRow(uiText("network_ops.reader.asserted", "Asserted"), it, "row_reader_asserted")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(
                    onClick = { onHonour(id) },
                    modifier = Modifier.testableClickable("btn_reader_honour_${id.take(16)}") { onHonour(id) },
                ) { Text(uiText("network_ops.reader.honour", "Honour")) }
                // Same shape, same weight, ordinary colours: a decline is a
                // decision this rung is FOR.
                FilledTonalButton(
                    onClick = { onDecline(id) },
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = MaterialTheme.colorScheme.tertiaryContainer,
                        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
                    ),
                    modifier = Modifier.testableClickable("btn_reader_decline_${id.take(16)}") { onDecline(id) },
                ) { Text(uiText("network_ops.reader.decline", "Decline")) }
            }
        }
    }
}

/** Four decisions, four neutral-to-positive treatments. None is an error. */
@Composable
private fun ReaderDecisionChip(decision: ReaderDecision, testTag: String) {
    val label: String
    val container: androidx.compose.ui.graphics.Color
    val content: androidx.compose.ui.graphics.Color
    var outlined = false
    when (decision) {
        ReaderDecision.HONOURED_EXPLICIT -> {
            label = uiText("network_ops.reader.decision.honoured_explicit", "Honoured — this reader adopted it")
            container = MaterialTheme.colorScheme.primaryContainer
            content = MaterialTheme.colorScheme.onPrimaryContainer
        }
        ReaderDecision.HONOURED_BY_SUBSCRIPTION -> {
            label = uiText("network_ops.reader.decision.honoured_by_subscription", "Honoured by subscription")
            container = MaterialTheme.colorScheme.secondaryContainer
            content = MaterialTheme.colorScheme.onSecondaryContainer
        }
        ReaderDecision.DECLINED -> {
            label = uiText("network_ops.reader.decision.declined", "Declined by this reader")
            container = MaterialTheme.colorScheme.tertiaryContainer
            content = MaterialTheme.colorScheme.onTertiaryContainer
        }
        ReaderDecision.UNDECIDED_UNSUBSCRIBED -> {
            label = uiText("network_ops.reader.decision.undecided_unsubscribed", "No decision yet")
            container = MaterialTheme.colorScheme.surface
            content = MaterialTheme.colorScheme.onSurfaceVariant
            outlined = true
        }
        ReaderDecision.UNKNOWN -> {
            label = uiText("network_ops.reader.decision.unknown", "Unrecognised decision")
            container = MaterialTheme.colorScheme.surface
            content = MaterialTheme.colorScheme.onSurfaceVariant
            outlined = true
        }
    }
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = container,
        contentColor = content,
        border = if (outlined) BorderStroke(1.dp, MaterialTheme.colorScheme.outline) else null,
        modifier = Modifier.testable(testTag),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

/** reader_fold vs node_fold — a divergence is information, not a fault. */
@Composable
private fun ReaderFoldComparison(response: ReaderFoldResponse) {
    val reader = response.readerFold
    val node = response.nodeFold
    if (reader == null && node == null) return
    Surface(
        modifier = Modifier.fillMaxWidth().testable("card_reader_fold_comparison"),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            SelfROpsRow(
                uiText("network_ops.reader.fold.reader", "This reader's fold"),
                foldState(reader),
                "row_reader_fold_reader",
            )
            SelfROpsRow(
                uiText("network_ops.reader.fold.node", "This node's serve paths"),
                foldState(node),
                "row_reader_fold_node",
            )
            Text(
                if (response.diverges) {
                    uiText(
                        "network_ops.reader.fold.diverges",
                        "These differ — which is the reader deciding. The decline is recorded and " +
                            "reported; it does not yet stop this node withholding.",
                    )
                } else {
                    uiText("network_ops.reader.fold.agrees", "These agree.")
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            serverMessage(response.advisory)?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

private fun foldState(fold: QuarantineFoldDto?): String = fold?.state?.takeIf { it.isNotBlank() } ?: "—"

/** A recorded decision — honour or decline, one shape, one tone. */
@Composable
private fun ReaderDecisionResult(outcome: ReaderDecisionOutcome) {
    when (outcome) {
        is ReaderDecisionOutcome.Recorded -> SelfRBanner(
            tone = SelfRTone.NEUTRAL,
            title = uiText("network_ops.reader.decision_recorded", "Decision recorded"),
            body = serverMessage(outcome.response.message)
                ?: uiText("network_ops.reader.advisory", "An issued judgement is advisory to each reader."),
            detail = outcome.response.eventId?.let { "event: $it" },
            testTag = "banner_reader_decision_recorded",
        )
        is ReaderDecisionOutcome.Refused -> SelfRBanner(
            tone = SelfRTone.PROBLEM,
            title = uiText("network_ops.reader.decision_refused", "The decision was refused"),
            body = uiText(
                "network_ops.reader.decision_refused_body",
                "Nothing was recorded, and this reader's policy is unchanged.",
            ),
            detail = refusalDetail(outcome.refusal, outcome.httpStatus),
            testTag = "banner_reader_decision_refused",
        )
        is ReaderDecisionOutcome.Unreachable -> SelfRBanner(
            tone = SelfRTone.UNKNOWN,
            title = uiText("network_ops.reader.unreachable_title", "This node could not be reached"),
            body = uiText(
                "network_ops.reader.decision_unreachable_body",
                "It is not known whether the decision was recorded. Read the fold again once the " +
                    "node answers.",
            ),
            detail = outcome.detail,
            testTag = "banner_reader_decision_unreachable",
        )
    }
}

@Composable
private fun ReaderDecisionDialog(
    prompt: ReaderPrompt,
    working: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (delegationId: String, reason: String) -> Unit,
) {
    var delegationId by remember(prompt) { mutableStateOf("") }
    var reason by remember(prompt) { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                if (prompt.declining) {
                    uiText("network_ops.reader.dialog.decline_title", "Decline this judgement")
                } else {
                    uiText("network_ops.reader.dialog.honour_title", "Honour this judgement")
                },
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    if (prompt.declining) {
                        uiText(
                            "network_ops.reader.dialog.decline_note",
                            "A normal outcome. Nothing about the judgement is deleted or " +
                                "contested: this records that THIS reader does not adopt it.",
                        )
                    } else {
                        uiText(
                            "network_ops.reader.dialog.honour_note",
                            "This reader adopts the judgement deliberately. The signer need not " +
                                "be subscribed.",
                        )
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    prompt.judgementId,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace,
                )
                OutlinedTextField(
                    value = delegationId,
                    onValueChange = { delegationId = it },
                    label = {
                        Text(uiText("network_ops.self.dialog.delegation_label", "Owner delegation id"))
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testable("input_reader_delegation_id"),
                )
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    label = { Text(uiText("network_ops.self.dialog.reason_label", "Reason (required)")) },
                    modifier = Modifier.fillMaxWidth().testable("input_reader_reason"),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(delegationId.trim(), reason.trim()) },
                enabled = !working && delegationId.isNotBlank() && reason.isNotBlank(),
                modifier = Modifier.testableClickable("btn_reader_confirm") {
                    onConfirm(delegationId.trim(), reason.trim())
                },
            ) {
                Text(
                    if (working) {
                        uiText("network_ops.self.dialog.working", "Recording…")
                    } else {
                        uiText("network_ops.self.dialog.confirm", "Record")
                    },
                )
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_reader_cancel") { onDismiss() },
            ) { Text(uiText("network_ops.self.dialog.cancel", "Cancel")) }
        },
    )
}

// ═════════════════════════════════════════════════════════════════════════════
//  Shared pieces
// ═════════════════════════════════════════════════════════════════════════════

/** Three tones — and NONE of them is the decline. */
private enum class SelfRTone {
    /** Something happened and it is fine (a record was written). */
    NEUTRAL,

    /** We do not know: unreachable, refused, unreadable. Never a clear state. */
    UNKNOWN,

    /** A real failure of the act the operator asked for. */
    PROBLEM,
}

@Composable
private fun SelfRBanner(
    tone: SelfRTone,
    title: String,
    body: String,
    detail: String?,
    testTag: String,
) {
    val container = when (tone) {
        SelfRTone.NEUTRAL -> MaterialTheme.colorScheme.surfaceVariant
        SelfRTone.UNKNOWN -> MaterialTheme.colorScheme.errorContainer
        SelfRTone.PROBLEM -> MaterialTheme.colorScheme.errorContainer
    }
    val content = when (tone) {
        SelfRTone.NEUTRAL -> MaterialTheme.colorScheme.onSurfaceVariant
        SelfRTone.UNKNOWN -> MaterialTheme.colorScheme.onErrorContainer
        SelfRTone.PROBLEM -> MaterialTheme.colorScheme.onErrorContainer
    }
    Surface(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        shape = RoundedCornerShape(12.dp),
        color = container,
        contentColor = content,
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Text(body, style = MaterialTheme.typography.bodySmall)
            detail?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace)
            }
        }
    }
}

@Composable
private fun SelfROpsCard(testTag: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content,
        )
    }
}

@Composable
private fun SelfROpsRow(label: String, value: String, testTag: String, mono: Boolean = false) {
    Column(modifier = Modifier.fillMaxWidth().testable(testTag)) {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
        )
    }
}

/**
 * Resolve a server `{id, text}` pair: the id THROUGH the bundle first (all 200
 * ids ship in 29 languages), the English `text` only when the bundle has no
 * entry — which the manager signals by handing back the key itself.
 */
@Composable
private fun serverMessage(message: AdminMessage?): String? {
    if (message == null) return null
    if (message.id.isBlank()) return message.text.takeIf { it.isNotBlank() }
    val resolved = localizedString(message.id)
    val usable = resolved.isNotBlank() && resolved != message.id
    return if (usable) resolved else message.text.takeIf { it.isNotBlank() }
}

/** A UI string, with the English source as the load-time / missing-key fallback. */
@Composable
private fun uiText(key: String, fallback: String): String {
    val resolved = localizedString(key)
    return if (resolved.isBlank() || resolved == key) fallback else resolved
}

@Composable
private fun uiText(key: String, params: Map<String, String>, fallback: String): String {
    val resolved = localizedString(key, params)
    return if (resolved.isBlank() || resolved == key) fallback else resolved
}

@Composable
private fun refusalDetail(refusal: AdminRefusalDto, httpStatus: Int): String {
    val token = refusal.refusal ?: "refused"
    val text = serverMessage(refusal.message)
    return listOfNotNull("HTTP $httpStatus · $token", text).joinToString("\n")
}

@Composable
private fun axisTitle(axis: String): String = when (axis) {
    SelfAxis.LOAD_SHED -> uiText("network_ops.self.axis.load_shed.title", "Shed load")
    SelfAxis.ACCEPTING -> uiText("network_ops.self.axis.accepting.title", "Stop accepting")
    SelfAxis.LEGAL_COMPULSION -> uiText("network_ops.self.axis.legal_compulsion.title", "Legal compulsion")
    else -> axis
}

@Composable
private fun axisQuestion(axis: String): String = when (axis) {
    SelfAxis.LOAD_SHED -> uiText(
        "network_ops.self.axis.load_shed.question",
        "Is this node carrying less on purpose?",
    )
    SelfAxis.ACCEPTING -> uiText(
        "network_ops.self.axis.accepting.question",
        "Did this node CHOOSE to take on nothing new?",
    )
    SelfAxis.LEGAL_COMPULSION -> uiText(
        "network_ops.self.axis.legal_compulsion.question",
        "Is force being applied to this node from outside the mesh? Not a choice, and never " +
            "recorded as one.",
    )
    else -> ""
}

@Composable
private fun axisDeclareLabel(axis: String): String = when (axis) {
    SelfAxis.LOAD_SHED -> uiText("network_ops.self.axis.load_shed.declare", "Shed load")
    SelfAxis.ACCEPTING -> uiText("network_ops.self.axis.accepting.declare", "Stop accepting")
    SelfAxis.LEGAL_COMPULSION -> uiText(
        "network_ops.self.axis.legal_compulsion.declare",
        "Declare compulsion",
    )
    else -> axis
}

@Composable
private fun axisLiftLabel(axis: String): String = when (axis) {
    SelfAxis.LOAD_SHED -> uiText("network_ops.self.axis.load_shed.lift", "Carry a full load again")
    SelfAxis.ACCEPTING -> uiText("network_ops.self.axis.accepting.lift", "Accept again")
    SelfAxis.LEGAL_COMPULSION -> uiText("network_ops.self.axis.legal_compulsion.lift", "Compulsion ended")
    else -> axis
}
