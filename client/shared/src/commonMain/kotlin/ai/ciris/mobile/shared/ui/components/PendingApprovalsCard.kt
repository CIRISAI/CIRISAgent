package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.approvals.ApprovalKind
import ai.ciris.mobile.shared.approvals.BudgetApprovalSeam
import ai.ciris.mobile.shared.approvals.BudgetCapability
import ai.ciris.mobile.shared.approvals.OverGrantMagnitude
import ai.ciris.mobile.shared.approvals.PendingApproval
import ai.ciris.mobile.shared.approvals.TicketBudgetState
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * "The agent is blocked waiting on you."
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * The card an operator must not be able to miss. A fail-closed authorization
 * model that denies an action and then says nothing is indistinguishable, from
 * where the operator sits, from the agent being broken. This card is the
 * difference: it names the block, counts it, and puts the decision one tap away.
 *
 * Renders nothing when there is nothing pending — an always-visible "0 pending"
 * card trains people to ignore the space it occupies.
 */
@Composable
fun PendingApprovalsCard(
    approvals: List<PendingApproval>,
    onApprovalClick: (PendingApproval) -> Unit,
    modifier: Modifier = Modifier,
    maxVisible: Int = 3,
) {
    if (approvals.isEmpty()) return

    val budgetCount = approvals.count { it.needsBudgetDecision }
    val accent = if (approvals.any { it.isHighPriority } || budgetCount > 0) {
        SemanticColors.Default.warning
    } else {
        SemanticColors.Default.info
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_pending_approvals"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = CIRISIcons.defer,
                    contentDescription = null,
                    tint = accent,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = localizedString("approval_blocked_on_you"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f),
                )
                CountPill(count = approvals.size, color = accent, tag = "pill_approval_count")
            }

            Spacer(Modifier.height(4.dp))

            Text(
                text = if (budgetCount > 0) {
                    localizedString("approval_summary_with_budget", "count", budgetCount.toString())
                } else {
                    localizedString("approval_summary")
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(12.dp))

            approvals.take(maxVisible).forEach { approval ->
                ApprovalRow(approval = approval, onClick = { onApprovalClick(approval) })
                Spacer(Modifier.height(8.dp))
            }

            if (approvals.size > maxVisible) {
                Text(
                    text = localizedString(
                        "approval_and_more",
                        "count",
                        (approvals.size - maxVisible).toString(),
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ApprovalRow(
    approval: PendingApproval,
    onClick: () -> Unit,
) {
    val shortId = approval.id.take(8)
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("item_approval_$shortId") { onClick() },
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = approval.title,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                // The chip shows what is at stake. For an un-granted request
                // that is the amount asked for; once a budget exists it is what
                // is actually left, never the granted ceiling — after a spend
                // those differ, and the larger of the two is the wrong one.
                val chip = when {
                    approval.grantedBudget != null -> approval.grantedBudget.let { g ->
                        BudgetApprovalSeam.remainingAmount(g.grantedAmount, approval.budgetSpend?.totalSpent)
                            ?.let { it to g.grantedCurrency }
                    }
                    approval.requestedBudget != null ->
                        approval.requestedBudget.requestedAmount to approval.requestedBudget.requestedCurrency
                    else -> null
                }
                chip?.let { (amount, currency) ->
                    Spacer(Modifier.width(8.dp))
                    BudgetChip(
                        amount = amount,
                        currency = currency,
                        tag = "chip_budget_$shortId",
                    )
                }
            }
            if (approval.detail.isNotBlank() && approval.detail != approval.title) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = approval.detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = when (approval.kind) {
                    ApprovalKind.DEFERRAL -> localizedString("approval_kind_deferral")
                    ApprovalKind.TICKET_PROPOSAL -> localizedString("approval_kind_proposal")
                },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun BudgetChip(amount: String, currency: String, tag: String) {
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = SemanticColors.Default.warning.copy(alpha = 0.18f),
        modifier = Modifier.testable(tag),
    ) {
        Text(
            text = "$amount $currency",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = SemanticColors.Default.warning,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
        )
    }
}

/**
 * A small count pill. Also used by the nav to badge the approval surface, so
 * the count an operator sees in the drawer and the count on the card are drawn
 * by the same code.
 */
@Composable
fun CountPill(count: Int, color: androidx.compose.ui.graphics.Color, tag: String) {
    if (count <= 0) return
    Box(
        modifier = Modifier
            .background(color, RoundedCornerShape(10.dp))
            .testable(tag)
            .padding(horizontal = 7.dp, vertical = 1.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = if (count > 99) "99+" else count.toString(),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.surface,
        )
    }
}

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * Proposal approval — including budget issuance.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * When the proposal carries a requested budget, the human's approval here IS
 * the issuance event: it grants a budget envelope nested inside the
 * deployment's trust envelope. Three properties are enforced in the UI, not
 * merely trusted to the server:
 *
 *  1. **Approve at or below the request, never above.** The amount field is
 *     pre-filled with the request and re-validated on every keystroke. The
 *     server enforces this too; doing it here makes the constraint visible at
 *     the point of decision instead of arriving as a rejected round-trip.
 *  2. **Every envelope expires.** There is no "forever" option.
 *  3. **Approving money and starting work are separate decisions.** Granting a
 *     budget leaves the ticket blocked; a distinct action promotes it. One
 *     combined button exists for the common case, clearly labelled as doing
 *     both.
 *
 * When the proposal asks for no money the entire money section is omitted and
 * the dialog is a plain start-work / refuse / not-now decision.
 *
 * When the server does not expose issuance ([BudgetCapability.UNAVAILABLE]) the
 * dialog says so plainly rather than offering a button that cannot work — a
 * silent failure here reads to the operator exactly like the agent being stuck,
 * which is the confusion this whole surface exists to prevent.
 */
@Composable
fun ProposalApprovalDialog(
    approval: PendingApproval,
    capability: BudgetCapability,
    isSubmitting: Boolean,
    /**
     * Freshly-read budget state for this ticket, when available. Preferred over
     * the copy carried on [approval] (which came from the list fetch) because
     * it is the only source of trust headroom and is current as of dialog open.
     * Null is normal — the dialog then renders from list data alone.
     */
    budgetState: TicketBudgetState?,
    onDismiss: () -> Unit,
    onApprove: (
        amount: String?,
        expiryHours: Int,
        reason: String,
        promote: Boolean,
        overGrantConfirmed: Boolean,
    ) -> Unit,
    onReject: (reason: String) -> Unit,
    onDefer: (reason: String) -> Unit,
) {
    val requested = approval.requestedBudget
    // Prefer the freshly-read state; fall back to what the list already carried.
    val headroom = budgetState?.headroom
    val granted = budgetState?.granted ?: approval.grantedBudget
    val spent = budgetState?.spent ?: approval.budgetSpend

    var amount by remember(approval.id) { mutableStateOf(requested?.requestedAmount.orEmpty()) }
    var expiryText by remember(approval.id) {
        mutableStateOf(BudgetApprovalSeam.DEFAULT_EXPIRY_HOURS.toString())
    }
    var reason by remember(approval.id) { mutableStateOf("") }
    // Reset whenever the amount changes: a confirmation given for one figure
    // must never carry over to a different one.
    var overGrantConfirmed by remember(approval.id, amount) { mutableStateOf(false) }

    val expiryHours = expiryText.toIntOrNull() ?: -1
    val validation = requested?.let {
        BudgetApprovalSeam.validateGrant(
            requested = it,
            amount = amount,
            expiresInHours = expiryHours,
            purpose = it.purpose.ifBlank { approval.title },
            headroom = headroom,
            overGrantConfirmed = overGrantConfirmed,
        )
    }
    val unavailable = requested != null && capability == BudgetCapability.UNAVAILABLE
    // The over-grant prompt is shown whenever the amount exceeds the request,
    // whether or not it has been confirmed — so the ratio stays on screen after
    // the box is ticked rather than vanishing at the moment of decision.
    val overGrant = requested?.let { BudgetApprovalSeam.describeOverGrant(it, amount) }
    val canApprove = (validation?.ok ?: true) && !isSubmitting && !unavailable

    AlertDialog(
        onDismissRequest = { if (!isSubmitting) onDismiss() },
        modifier = Modifier.testable("dialog_budget_approval"),
        title = {
            Text(
                if (requested != null) localizedString("approval_budget_title")
                else localizedString("approval_proposal_title")
            )
        },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                // ─── What the agent asked for ───────────────────────────────
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(12.dp)) {
                        if (requested != null) {
                            Text(
                                text = localizedString("approval_budget_requested"),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "${requested.requestedAmount} ${requested.requestedCurrency}",
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Bold,
                                color = SemanticColors.Default.warning,
                                modifier = Modifier.testable("txt_budget_requested_amount"),
                            )
                            if (requested.purpose.isNotBlank()) {
                                Spacer(Modifier.height(6.dp))
                                LabelledLine(localizedString("approval_budget_purpose"), requested.purpose)
                            }
                            requested.justification?.takeIf { it.isNotBlank() }?.let {
                                Spacer(Modifier.height(4.dp))
                                LabelledLine(localizedString("approval_budget_justification"), it)
                            }
                        }
                        approval.proposal?.goalDescription?.takeIf { it.isNotBlank() }?.let {
                            Spacer(Modifier.height(4.dp))
                            LabelledLine(localizedString("approval_budget_intent"), it)
                        }
                        // Headroom renders only when the server actually reports
                        // it — this is the same number the spend gate applies,
                        // not a client re-derivation, so it cannot disagree with
                        // what is enforced when the money moves.
                        headroom?.takeIf { requested != null }?.let { room ->
                            Spacer(Modifier.height(4.dp))
                            Column(modifier = Modifier.testable("row_budget_headroom")) {
                                LabelledLine(
                                    localizedString("approval_budget_headroom"),
                                    "${room.amount} ${room.currency}",
                                )
                                // Say WHICH bound is binding. "You have 40 left"
                                // is far less actionable than "40 left today,
                                // against a 100 per-transaction ceiling".
                                if (room.maxTransaction.isNotBlank() && room.dailyRemaining.isNotBlank()) {
                                    Text(
                                        text = localizedString(
                                            "approval_budget_headroom_detail",
                                            mapOf(
                                                "max" to room.maxTransaction,
                                                "daily" to room.dailyRemaining,
                                            ),
                                        ),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }
                    }
                }

                // ─── An already-issued budget, and what is left of it ───────
                //
                // granted_amount ALONE OVERSTATES AVAILABILITY after any spend.
                // A re-grant raises the ceiling; the spend ledger survives it.
                // Grant 25 → spend 25 → re-grant 40 leaves 15 spendable, not 40.
                // So `remaining` is the prominent figure and `granted` is
                // demoted to context.
                granted?.let { g ->
                    val remaining = BudgetApprovalSeam.remainingAmount(
                        g.grantedAmount,
                        spent?.totalSpent,
                    )
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier.fillMaxWidth().testable("row_budget_issued"),
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Text(
                                text = localizedString("approval_budget_remaining"),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = remaining?.let { "$it ${g.grantedCurrency}" }
                                    ?: localizedString("approval_budget_remaining_unknown"),
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Bold,
                                color = SemanticColors.Default.info,
                                modifier = Modifier.testable("txt_budget_remaining"),
                            )
                            Spacer(Modifier.height(6.dp))
                            LabelledLine(
                                localizedString("approval_budget_granted"),
                                "${g.grantedAmount} ${g.grantedCurrency}",
                            )
                            spent?.let {
                                Spacer(Modifier.height(4.dp))
                                LabelledLine(
                                    localizedString("approval_budget_spent"),
                                    "${it.totalSpent} ${it.currency}",
                                )
                            }
                            g.expiresAt?.takeIf { it.isNotBlank() }?.let {
                                Spacer(Modifier.height(4.dp))
                                LabelledLine(localizedString("approval_budget_expires_at"), it)
                            }
                            // The server's own derived marking, carried inside
                            // the signed payload. Shown from the grant's
                            // snapshot rather than the ticket's current request,
                            // because the grant is the record.
                            if (g.exceedsRequest) {
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    text = g.requestedAmountAtGrant?.let {
                                        localizedString(
                                            "approval_budget_exceeded_request",
                                            mapOf("requested" to "$it ${g.grantedCurrency}"),
                                        )
                                    } ?: localizedString("approval_budget_exceeded_request_unknown"),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = SemanticColors.Default.warning,
                                    modifier = Modifier.testable("txt_budget_exceeded_request"),
                                )
                            }
                            if (!g.signed) {
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    text = localizedString("approval_budget_unsigned"),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = SemanticColors.Default.warning,
                                    modifier = Modifier.testable("txt_budget_unsigned"),
                                )
                            }
                            if (requested != null) {
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    text = localizedString("approval_budget_regrant_note"),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }

                if (unavailable) {
                    Text(
                        text = localizedString("approval_budget_unsupported"),
                        style = MaterialTheme.typography.bodySmall,
                        color = SemanticColors.Default.error,
                        modifier = Modifier.testable("txt_budget_unsupported"),
                    )
                }

                if (requested != null) {
                    HorizontalDivider()

                    // ─── What the human is issuing ──────────────────────────
                    Text(
                        text = localizedString("approval_budget_you_approve"),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                    )

                    OutlinedTextField(
                        value = amount,
                        onValueChange = { amount = it },
                        label = {
                            Text("${localizedString("approval_budget_amount")} (${requested.requestedCurrency})")
                        },
                        singleLine = true,
                        isError = validation?.ok == false && amount.isNotBlank(),
                        enabled = !isSubmitting && !unavailable,
                        modifier = Modifier.fillMaxWidth().testable("input_budget_amount"),
                    )

                    OutlinedTextField(
                        value = expiryText,
                        onValueChange = { expiryText = it },
                        label = { Text(localizedString("approval_budget_expiry_hours")) },
                        singleLine = true,
                        enabled = !isSubmitting && !unavailable,
                        modifier = Modifier.fillMaxWidth().testable("input_budget_expiry"),
                    )

                    validation?.takeIf { !it.ok }?.message?.let { msg ->
                        Text(
                            text = msg,
                            style = MaterialTheme.typography.bodySmall,
                            color = SemanticColors.Default.error,
                            modifier = Modifier.testable("txt_budget_validation_error"),
                        )
                    }

                    // ─── Over-grant confirmation ───────────────────────────
                    //
                    // Granting above the request is allowed — the agent may have
                    // asked for too little. It is never allowed *silently*. The
                    // prompt names the ratio rather than asking "are you sure?",
                    // because the hazard is a mis-typed extra zero and only a
                    // ratio makes that legible: 250 next to 25 is easy to scroll
                    // past, "10×" is not.
                    //
                    // ⚠️ RTL BIDI CONSTRAINT on approval_over_grant_ratio and
                    // approval_over_grant_percent — read before editing those
                    // strings in ar / fa / ur.
                    //
                    // Both templates interpolate TWO adjacent numeric runs:
                    // {ratio} ("10×", "20%") and {requested} ("25.00"). In an
                    // RTL paragraph, if the only thing between those two
                    // placeholders is neutral (space, punctuation, an ASCII
                    // hyphen, a bare currency symbol), UAX#9 resolves the
                    // neutrals into the surrounding numeric context and merges
                    // both numbers into ONE left-to-right run. The two figures
                    // then render in swapped visual order — the operator reads
                    // "25.00" where the ratio should be and vice versa, on the
                    // money dialog, in RTL locales only, with no error and no
                    // test failure.
                    //
                    // The invariant: **keep at least one script-bearing word
                    // between {ratio} and {requested}** (in either order). A
                    // strong-directional character breaks the neutral span and
                    // forces two separately-placed runs.
                    //
                    // It holds today only as an accident of phrasing — ar uses
                    // ' عن ' / ' ما طلبه الوكيل البالغ ', fa ' بیشتر از ' /
                    // ' مبلغ ', ur ' سے ' / ' کا '. A translator "tightening"
                    // any of those to a bare dash or comma reintroduces the bug.
                    // Recorded in FSD/HITL_APPROVAL_SURFACE.md; not currently
                    // checked by the localization lint.
                    overGrant?.let { over ->
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = SemanticColors.Default.warning.copy(alpha = 0.12f),
                            modifier = Modifier.fillMaxWidth().testable("row_over_grant"),
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .testableClickable("chk_over_grant_confirm") {
                                        overGrantConfirmed = !overGrantConfirmed
                                    }
                                    .padding(10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Checkbox(
                                    checked = overGrantConfirmed,
                                    onCheckedChange = { overGrantConfirmed = it },
                                    enabled = !isSubmitting && !unavailable,
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    text = when (over.magnitude) {
                                        OverGrantMagnitude.SLIGHT -> localizedString(
                                            "approval_over_grant_slight",
                                            mapOf(
                                                "amount" to "${over.amount} ${over.currency}",
                                                "requested" to over.requestedAmount,
                                            ),
                                        )
                                        // PERCENT and MULTIPLE need DIFFERENT sentences, not one
                                        // template. `display` is "20%" for PERCENT (a percentage
                                        // ABOVE the request) but "10×" for MULTIPLE (a multiple OF
                                        // it). Feeding both into "{ratio} the {requested}" renders
                                        // "20% the 25", which is ungrammatical and reads as 20% OF
                                        // the request — understating the over-grant on a money
                                        // dialog, in the direction that matters least safely.
                                        OverGrantMagnitude.PERCENT -> localizedString(
                                            "approval_over_grant_percent",
                                            mapOf(
                                                "amount" to "${over.amount} ${over.currency}",
                                                "ratio" to over.display,
                                                "requested" to over.requestedAmount,
                                            ),
                                        )
                                        else -> localizedString(
                                            "approval_over_grant_ratio",
                                            mapOf(
                                                "amount" to "${over.amount} ${over.currency}",
                                                "ratio" to over.display,
                                                "requested" to over.requestedAmount,
                                            ),
                                        )
                                    },
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Medium,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.weight(1f).testable("txt_over_grant_ratio"),
                                )
                            }
                        }
                    }
                }

                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    label = { Text(localizedString("approval_reason")) },
                    minLines = 2,
                    maxLines = 4,
                    enabled = !isSubmitting,
                    modifier = Modifier.fillMaxWidth().testable("input_budget_reason"),
                )

                HorizontalDivider()

                // ─── Actions. Money and work are deliberately separate. ─────
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (requested != null) {
                        Button(
                            onClick = { if (canApprove) onApprove(amount, expiryHours, reason, false, overGrantConfirmed) },
                            enabled = canApprove,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SemanticColors.Default.success,
                            ),
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("btn_budget_approve") {
                                    if (canApprove) onApprove(amount, expiryHours, reason, false, overGrantConfirmed)
                                },
                        ) {
                            Text(localizedString("approval_budget_approve"))
                        }
                    }

                    val startLabel = if (requested != null) {
                        localizedString("approval_budget_approve_and_start")
                    } else {
                        localizedString("approval_start_work")
                    }
                    OutlinedButton(
                        onClick = { if (canApprove) onApprove(amount.takeIf { requested != null }, expiryHours, reason, true, overGrantConfirmed) },
                        enabled = canApprove,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_budget_approve_start") {
                                if (canApprove) {
                                    onApprove(amount.takeIf { requested != null }, expiryHours, reason, true, overGrantConfirmed)
                                }
                            },
                    ) {
                        Text(startLabel)
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { if (!isSubmitting) onReject(reason) },
                            enabled = !isSubmitting,
                            modifier = Modifier
                                .weight(1f)
                                .testableClickable("btn_budget_reject") {
                                    if (!isSubmitting) onReject(reason)
                                },
                        ) {
                            Text(localizedString("wa_reject"))
                        }
                        OutlinedButton(
                            onClick = { if (!isSubmitting) onDefer(reason) },
                            enabled = !isSubmitting,
                            modifier = Modifier
                                .weight(1f)
                                .testableClickable("btn_budget_defer") {
                                    if (!isSubmitting) onDefer(reason)
                                },
                        ) {
                            Text(localizedString("approval_not_now"))
                        }
                    }
                }

                if (isSubmitting) {
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSubmitting,
                modifier = Modifier.testableClickable("btn_budget_cancel") { onDismiss() },
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        },
    )
}

/**
 * A structured label/value row. `internal` rather than `private` so the
 * tool-approval card on the deferral screen (CIRISAgent#942) renders its rows
 * with the same code as the budget approval, instead of a second look-alike.
 */
@Composable
internal fun LabelledLine(label: String, value: String) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text = value, style = MaterialTheme.typography.bodySmall)
    }
}
