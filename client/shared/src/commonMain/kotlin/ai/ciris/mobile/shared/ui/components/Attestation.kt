package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **The CEG-native Trust Root primitives.**
 *
 * The HUMANITY_ACCORD protocol has ONE noun — a `scores` attestation — and a
 * handful of composer verbs. So the UI is ONE card ([AttestationCard]) + ONE menu
 * ([AttestationHamburger]). Every list in the Trust Root (the family, the holder
 * roster, canonical servers, pending invocations, the withdrawn/superseded history)
 * renders as `items.forEach { AttestationCard(it, …) }` — collapsing the eight
 * hand-rolled sections the old AccordScreen re-derived.
 *
 * This is a PURE client re-composition: no server change. Each op the hamburger
 * offers maps back to an existing `AccordViewModel` method (Cosign→`concur`,
 * Supersede→`selectCanonicalForReplace`+`addCanonicalServer`, Withdraw→
 * `withdrawCanonical`, the mint sheet→`admitNode`/`addCanonicalServer`).
 */

/** The kind of CEG object a card renders. Drives [attestationStyle] + the badge. */
enum class AttKind {
    AccordFamily,
    Holder,
    Node,
    Canonical,
    /** A canonical co-scrub still accumulating cosignatures (CIRISServer#174). */
    Coscrub,
    Invocation,
    Message,
    Withdrawal,
}

/** The standing of an attestation at a glance. */
enum class AttStatus {
    Active,
    Pending,
    Entrenched,
    Withdrawn,
    Superseded,
    Recanted,
}

/**
 * The uniform op vocabulary — the 1 (Cosign) + 4 composers + the 3 read affordances.
 * The SHAPE never changes; `(kind, status, viewer)` only decides which are enabled.
 */
enum class AttOp {
    ViewDetails,
    History,
    Evidence,
    Copy,
    Cosign,
    Delegate,
    Supersede,
    Withdraw,
    Recant,
}

/** What the viewer is allowed to do, best-effort (the node re-checks + 401/403s). */
data class ViewerAuthority(
    /** The local node carries an accord-holder key (roster non-empty ≈ can attempt). */
    val isHolder: Boolean = false,
)

/**
 * A UI view of any CEG object. The screen maps each server DTO (family, holder,
 * canonical, invocation, withdrawal) into this shape; nothing here is a server type.
 */
data class Attestation(
    /** The subject / object id shown mono in the header + used in test tags. */
    val id: String,
    val kind: AttKind,
    val status: AttStatus,
    /** Short kind badge label, already localized (e.g. "CANONICAL", "CONSTITUTIONAL"). */
    val badge: String,
    /**
     * The style discriminator — for an [AttKind.Invocation] this is the invocation
     * kind (CONSTITUTIONAL / DRILL / NOTIFY) that drives the CC 4.2.1 coloring;
     * null for other kinds (styled by [kind] alone).
     */
    val styleKey: String? = null,
    /** The one metadata line that varies (e.g. "identity_type:node,canonical"). */
    val dimension: String? = null,
    /** "attested by …" — the signer / scrubber key_id, or null. */
    val attesterKeyId: String? = null,
    /** RFC-3339 instant or null. */
    val timestamp: String? = null,
    /** m — signers so far (for a threshold object), or null. */
    val signed: Int? = null,
    /** n — the threshold (for a threshold object), or null → 1-of-1. */
    val threshold: Int? = null,
    /** For [AttStatus.Superseded] the successor id, for context. */
    val supersededBy: String? = null,
    /** Count of attached evidence refs (enables the Evidence menu item). */
    val evidenceCount: Int = 0,
    /** True → replicated here from another holder's device (mesh gossip). */
    val arrivedViaGossip: Boolean = false,
)

/** Resolved per-kind colors (the generalization of the old `invocationStyle`). */
data class AttStyle(
    val container: Color,
    val onContainer: Color,
    val border: Color,
    /** CONSTITUTIONAL emergency treatment → heavier border. */
    val emergency: Boolean,
)

/**
 * The MANDATED per-kind visual treatment (CC 4.2.1), generalized from the old
 * `invocationStyle`. CONSTITUTIONAL keeps its emergency red; canonical a primary
 * chip; dead records (withdrawn / superseded / recanted) a muted tone.
 */
@Composable
fun attestationStyle(kind: AttKind, styleKey: String?, status: AttStatus): AttStyle {
    val cs = MaterialTheme.colorScheme
    if (status == AttStatus.Withdrawn || status == AttStatus.Superseded ||
        status == AttStatus.Recanted
    ) {
        return AttStyle(cs.surfaceVariant, cs.onSurfaceVariant, cs.outlineVariant, false)
    }
    return when (kind) {
        AttKind.Invocation -> when (styleKey?.uppercase()) {
            "CONSTITUTIONAL" -> AttStyle(cs.errorContainer, cs.onErrorContainer, cs.error, true)
            "DRILL" -> AttStyle(cs.surfaceVariant, cs.onSurfaceVariant, cs.outlineVariant, false)
            else -> AttStyle(cs.secondaryContainer, cs.onSecondaryContainer, cs.secondary, false)
        }
        AttKind.AccordFamily -> AttStyle(cs.primaryContainer, cs.onPrimaryContainer, cs.primary, false)
        AttKind.Canonical -> AttStyle(cs.surfaceVariant, cs.onSurfaceVariant, cs.primary, false)
        AttKind.Coscrub -> AttStyle(cs.secondaryContainer, cs.onSecondaryContainer, cs.primary, false)
        AttKind.Message -> AttStyle(cs.secondaryContainer, cs.onSecondaryContainer, cs.secondary, false)
        else -> AttStyle(cs.surfaceVariant, cs.onSurfaceVariant, cs.outlineVariant, false)
    }
}

/** Which hamburger ops light up for a given `(kind, status, viewer)`. */
private fun AttOp.enabledFor(att: Attestation, viewer: ViewerAuthority): Boolean = when (this) {
    AttOp.ViewDetails, AttOp.History -> true
    AttOp.Evidence -> att.evidenceCount > 0
    // Copy the co-scrub partial JSON to the clipboard so a holder can hand it to the
    // next holder without touching the filesystem. Only co-scrubs carry a partial.
    AttOp.Copy -> att.kind == AttKind.Coscrub
    // Cosign advances a pending m-of-n — only while pending (server 403s a non-holder).
    // Both an invocation (halt/drill/notify) and a canonical co-scrub accumulate scrubs.
    AttOp.Cosign -> att.status == AttStatus.Pending &&
        (att.kind == AttKind.Invocation || att.kind == AttKind.Coscrub)
    // Supersede == "replace / update" a live canonical record (a 1-of-N re-mint).
    AttOp.Supersede -> att.kind == AttKind.Canonical && att.status == AttStatus.Active
    // Withdraw a live canonical record (2-of-3 destructive).
    AttOp.Withdraw -> att.kind == AttKind.Canonical && att.status == AttStatus.Active
    // Delegate / Recant have no in-app endpoint yet (holder revoke / recant are
    // absent server-side) — surfaced in the uniform menu but never enabled.
    AttOp.Delegate, AttOp.Recant -> false
}

private fun AttOp.labelKey(): String = when (this) {
    AttOp.ViewDetails -> "mobile.accord_op_view_details"
    AttOp.History -> "mobile.accord_op_history"
    AttOp.Evidence -> "mobile.accord_op_evidence"
    AttOp.Copy -> "mobile.accord_op_copy"
    AttOp.Cosign -> "mobile.accord_op_cosign"
    AttOp.Delegate -> "mobile.accord_op_delegate"
    AttOp.Supersede -> "mobile.accord_op_supersede"
    AttOp.Withdraw -> "mobile.accord_op_withdraw"
    AttOp.Recant -> "mobile.accord_op_recant"
}

private fun AttOp.verb(): String = when (this) {
    AttOp.ViewDetails -> "view"
    AttOp.History -> "history"
    AttOp.Evidence -> "evidence"
    AttOp.Copy -> "copy"
    AttOp.Cosign -> "cosign"
    AttOp.Delegate -> "delegate"
    AttOp.Supersede -> "supersede"
    AttOp.Withdraw -> "withdraw"
    AttOp.Recant -> "recant"
}

private fun AttOp.destructive(): Boolean = this == AttOp.Withdraw || this == AttOp.Recant

/**
 * The uniform op menu (the 1 + 4, gated). Same items in the same order for every
 * card; items are shown-but-disabled by `(kind, status, viewer)` so the shape is
 * learnable once. Destructive ops carry the error tone.
 */
@Composable
fun AttestationHamburger(
    att: Attestation,
    viewer: ViewerAuthority,
    expanded: Boolean,
    onDismiss: () -> Unit,
    onOp: (AttOp) -> Unit,
) {
    DropdownMenu(expanded = expanded, onDismissRequest = onDismiss) {
        AttOp.values().forEach { op ->
            val enabled = op.enabledFor(att, viewer)
            val tint = if (op.destructive()) MaterialTheme.colorScheme.error else Color.Unspecified
            DropdownMenuItem(
                enabled = enabled,
                text = {
                    Text(
                        localizedString(op.labelKey()),
                        color = if (enabled && op.destructive()) tint else Color.Unspecified,
                    )
                },
                onClick = { onDismiss(); onOp(op) },
                modifier = Modifier.testableClickable("mi_op_${op.verb()}_${att.id}") {
                    onDismiss(); onOp(op)
                },
            )
        }
    }
}

/**
 * The one card for any CEG object. Header = kind badge · mono subject · trust badge ·
 * `⋮`. Then the single varying metadata line, the uniform "attested by / when", and
 * one optional kind-specific [inlineSlot] (canonical IP, invocation binding note).
 * Tapping the body opens details ([AttOp.ViewDetails]); the `⋮` is the only action
 * affordance.
 */
@Composable
fun AttestationCard(
    att: Attestation,
    viewer: ViewerAuthority,
    onOp: (AttOp) -> Unit,
    modifier: Modifier = Modifier,
    inlineSlot: (@Composable ColumnScope.() -> Unit)? = null,
) {
    val style = attestationStyle(att.kind, att.styleKey, att.status)
    var menu by remember { mutableStateOf(false) }
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = style.container,
        border = BorderStroke(if (style.emergency) 2.dp else 1.dp, style.border),
        modifier = modifier
            .fillMaxWidth()
            .padding(bottom = 8.dp)
            .testableClickable("card_${att.kind.name.lowercase()}_${att.id}") { onOp(AttOp.ViewDetails) },
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            // Header row: kind badge · subject · trust badge · ⋮
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindBadge(att.badge, style)
                Spacer(Modifier.width(8.dp))
                Text(
                    att.id,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace,
                    color = style.onContainer,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(6.dp))
                TrustBadge(att, style)
                Box {
                    IconButton(
                        onClick = { menu = true },
                        modifier = Modifier.size(28.dp).testable("card_menu_${att.id}"),
                    ) {
                        Icon(
                            CIRISIcons.moreVert,
                            contentDescription = "Actions",
                            modifier = Modifier.size(18.dp),
                            tint = style.onContainer,
                        )
                    }
                    AttestationHamburger(
                        att = att,
                        viewer = viewer,
                        expanded = menu,
                        onDismiss = { menu = false },
                        onOp = onOp,
                    )
                }
            }
            // The one metadata line that varies.
            att.dimension?.takeIf { it.isNotBlank() }?.let { dim ->
                Spacer(Modifier.height(6.dp))
                Text(
                    dim,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = style.onContainer,
                )
            }
            // Uniform "attested by … · when · (gossip)".
            val provenance = buildProvenance(att)
            if (provenance.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(provenance, fontSize = 11.sp, color = style.onContainer)
            }
            // One optional kind-specific slot.
            inlineSlot?.let {
                Spacer(Modifier.height(6.dp))
                it()
            }
        }
    }
}

@Composable
private fun buildProvenance(att: Attestation): String {
    val parts = mutableListOf<String>()
    att.attesterKeyId?.takeIf { it.isNotBlank() }?.let {
        parts += localizedString("mobile.accord_attested_by", "who", it)
    }
    att.timestamp?.takeIf { it.isNotBlank() }?.let { parts += it }
    if (att.arrivedViaGossip) parts += localizedString("mobile.accord_gossip")
    return parts.joinToString("  ·  ")
}

@Composable
private fun KindBadge(label: String, style: AttStyle) {
    Surface(shape = RoundedCornerShape(6.dp), color = style.border) {
        Text(
            label,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            color = style.container,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
        )
    }
}

/**
 * The object's standing at a glance: `entrenched` for the family, a strikethrough
 * `withdrawn` / `superseded` for dead records, a `m of n ▓░` progress pill for a
 * pending threshold, and `1-of-1 ✓` / `m of n ✓` for a settled attestation.
 */
@Composable
private fun TrustBadge(att: Attestation, style: AttStyle) {
    when (att.status) {
        AttStatus.Entrenched -> BadgeChip(
            localizedString("mobile.accord_badge_entrenched"),
            MaterialTheme.colorScheme.primaryContainer,
            MaterialTheme.colorScheme.onPrimaryContainer,
        )
        AttStatus.Withdrawn -> StrikeBadge(localizedString("mobile.accord_badge_withdrawn"))
        AttStatus.Superseded -> StrikeBadge(localizedString("mobile.accord_badge_superseded"))
        AttStatus.Recanted -> StrikeBadge(localizedString("mobile.accord_badge_recanted"))
        AttStatus.Pending -> QuorumPill(att.signed ?: 0, att.threshold ?: 0, met = false, style)
        AttStatus.Active -> {
            val n = att.threshold ?: 1
            if (n <= 1) {
                MetBadge(localizedString("mobile.accord_trust_1of1"), style)
            } else {
                QuorumPill(att.signed ?: n, n, met = true, style)
            }
        }
    }
}

@Composable
private fun BadgeChip(text: String, bg: Color, fg: Color) {
    Surface(shape = RoundedCornerShape(8.dp), color = bg, modifier = Modifier.padding(end = 2.dp)) {
        Text(
            text,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            color = fg,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun StrikeBadge(text: String) {
    Text(
        text,
        fontSize = 11.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textDecoration = TextDecoration.LineThrough,
        modifier = Modifier.padding(end = 4.dp),
    )
}

@Composable
private fun MetBadge(text: String, style: AttStyle) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(end = 2.dp)) {
        Text(text, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = style.onContainer)
        Spacer(Modifier.width(3.dp))
        Icon(
            CIRISIcons.check,
            contentDescription = null,
            modifier = Modifier.size(14.dp),
            tint = style.onContainer,
        )
    }
}

/** `m of n` count + a tiny filled/empty progress bar (the standard threshold pill). */
@Composable
private fun QuorumPill(signed: Int, threshold: Int, met: Boolean, style: AttStyle) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(end = 2.dp)) {
        Text(
            localizedString("mobile.accord_quorum_short")
                .replace("{signed}", signed.toString())
                // 0 = the node could not resolve the family's M. Show "?" — an
                // invented threshold would misstate how many holders are needed.
                .replace("{threshold}", if (threshold > 0) threshold.toString() else "?"),
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            color = style.onContainer,
        )
        Spacer(Modifier.width(4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            repeat(threshold.coerceAtLeast(1)) { i ->
                val filled = i < signed
                Box(
                    modifier = Modifier
                        .size(width = 8.dp, height = 8.dp)
                ) {
                    Surface(
                        shape = RoundedCornerShape(2.dp),
                        color = if (filled) style.border else style.onContainer.copy(alpha = 0.2f),
                        modifier = Modifier.fillMaxWidth().height(8.dp),
                    ) {}
                }
            }
        }
        if (met) {
            Spacer(Modifier.width(3.dp))
            Icon(
                CIRISIcons.check,
                contentDescription = null,
                modifier = Modifier.size(14.dp),
                tint = style.onContainer,
            )
        }
    }
}

/** One entry the `[+ New]` menu offers — a mint or governance op. */
data class NewAttestationAction(
    val id: String,
    val labelKey: String,
    val enabled: Boolean = true,
    val destructive: Boolean = false,
    val onSelect: () -> Unit,
)

/** The single `[+ New]` affordance (§3.3 / §3.5) that replaces the separate forms. */
@Composable
fun NewAttestationMenu(
    expanded: Boolean,
    onDismiss: () -> Unit,
    actions: List<NewAttestationAction>,
) {
    DropdownMenu(expanded = expanded, onDismissRequest = onDismiss) {
        actions.forEach { action ->
            val tint = when {
                !action.enabled -> Color.Unspecified
                action.destructive -> MaterialTheme.colorScheme.error
                else -> Color.Unspecified
            }
            DropdownMenuItem(
                enabled = action.enabled,
                text = { Text(localizedString(action.labelKey), color = tint) },
                onClick = { onDismiss(); action.onSelect() },
                modifier = Modifier.testableClickable("mi_new_${action.id}") {
                    onDismiss(); action.onSelect()
                },
            )
        }
    }
}
