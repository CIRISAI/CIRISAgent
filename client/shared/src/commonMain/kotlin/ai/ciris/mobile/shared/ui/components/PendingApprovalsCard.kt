package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.approvals.ApprovalKind
import ai.ciris.mobile.shared.approvals.BudgetApprovalSeam
import ai.ciris.mobile.shared.approvals.BudgetCapability
import ai.ciris.mobile.shared.approvals.PendingApproval
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
                if (approval.needsBudgetDecision) {
                    Spacer(Modifier.width(8.dp))
                    BudgetChip(
                        amount = approval.requestedBudget!!.requestedAmount,
                        currency = approval.requestedBudget.requestedCurrency,
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
    /** Trust-envelope headroom, when the server reports it. Null today. */
    headroom: String?,
    onDismiss: () -> Unit,
    onApprove: (amount: String?, expiryHours: Int, reason: String, promote: Boolean) -> Unit,
    onReject: (reason: String) -> Unit,
    onDefer: (reason: String) -> Unit,
) {
    val requested = approval.requestedBudget

    var amount by remember(approval.id) { mutableStateOf(requested?.requestedAmount.orEmpty()) }
    var expiryText by remember(approval.id) {
        mutableStateOf(BudgetApprovalSeam.DEFAULT_EXPIRY_HOURS.toString())
    }
    var reason by remember(approval.id) { mutableStateOf("") }

    val expiryHours = expiryText.toIntOrNull() ?: -1
    val validation = requested?.let {
        BudgetApprovalSeam.validateGrant(
            requested = it,
            amount = amount,
            expiresInHours = expiryHours,
            purpose = it.purpose.ifBlank { approval.title },
            headroom = headroom,
        )
    }
    val unavailable = requested != null && capability == BudgetCapability.UNAVAILABLE
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
                        // it. Showing a number that disagrees with the gate would
                        // be worse than showing none.
                        headroom?.takeIf { requested != null }?.let {
                            Spacer(Modifier.height(4.dp))
                            LabelledLine(
                                localizedString("approval_budget_headroom"),
                                "$it ${requested?.requestedCurrency.orEmpty()}",
                            )
                        }
                        approval.budgetSpend?.let {
                            Spacer(Modifier.height(4.dp))
                            LabelledLine(
                                localizedString("approval_budget_spent"),
                                "${it.totalSpent} ${it.currency}",
                            )
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
                            onClick = { if (canApprove) onApprove(amount, expiryHours, reason, false) },
                            enabled = canApprove,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SemanticColors.Default.success,
                            ),
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("btn_budget_approve") {
                                    if (canApprove) onApprove(amount, expiryHours, reason, false)
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
                        onClick = { if (canApprove) onApprove(amount.takeIf { requested != null }, expiryHours, reason, true) },
                        enabled = canApprove,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_budget_approve_start") {
                                if (canApprove) {
                                    onApprove(amount.takeIf { requested != null }, expiryHours, reason, true)
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

@Composable
private fun LabelledLine(label: String, value: String) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text = value, style = MaterialTheme.typography.bodySmall)
    }
}
