package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.vector.ImageVector
import ai.ciris.mobile.shared.ui.nav.SubstrateGate
import ai.ciris.mobile.shared.ui.theme.CIRISColors
// CIRISIcons is in the same package; no explicit import needed.

/**
 * Placeholder rendered by federation / manage screens whose data depends on
 * an upstream substrate API that has not landed yet.
 *
 * Doctrinally important: each placeholder names *which substrate produces the
 * data*, links to the gating issue, and lists the FSD-002 prefix family. Users
 * see the federation-surface ownership map; the wait itself teaches the
 * architecture.
 *
 * See `EpistemicNav.SubstrateGate` for the gate metadata and CIRISAgent#800
 * for the umbrella.
 */
@Composable
fun ComingSoonPlaceholder(
    title: String,
    icon: ImageVector,
    description: String,
    gate: SubstrateGate,
    onIssueClick: (String) -> Unit = {},
) {
    var expanded by remember { mutableStateOf(false) }
    val scroll = rememberScrollState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(CIRISColors.BackgroundDark),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 520.dp)
                .padding(24.dp)
                .verticalScroll(scroll),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            // Icon
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(CIRISColors.SignetTeal.copy(alpha = 0.10f))
                    .border(
                        width = 1.dp,
                        color = CIRISColors.SignetTeal.copy(alpha = 0.40f),
                        shape = RoundedCornerShape(16.dp),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = CIRISColors.AccentCyan,
                    modifier = Modifier.size(36.dp),
                )
            }

            // Title
            Text(
                text = title,
                color = CIRISColors.TextPrimary,
                fontSize = 22.sp,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
            )

            // Coming Soon chip
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(CIRISColors.BusTool.copy(alpha = 0.15f))
                    .border(
                        width = 1.dp,
                        color = CIRISColors.BusTool.copy(alpha = 0.50f),
                        shape = RoundedCornerShape(50),
                    )
                    .padding(horizontal = 14.dp, vertical = 6.dp),
            ) {
                Text(
                    text = "COMING SOON",
                    color = CIRISColors.BusTool,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.2.sp,
                )
            }

            // One-sentence description (from FSD-002 §3)
            Text(
                text = description,
                color = CIRISColors.TextSecondary,
                fontSize = 14.sp,
                lineHeight = 22.sp,
                textAlign = TextAlign.Center,
            )

            // Substrate-issue link
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .clickable { onIssueClick(gate.url) }
                    .background(CIRISColors.BackgroundDarker)
                    .border(
                        width = 1.dp,
                        color = CIRISColors.AccentCyan.copy(alpha = 0.30f),
                        shape = RoundedCornerShape(10.dp),
                    )
                    .padding(horizontal = 14.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Tracking: ${gate.shortRef}",
                    color = CIRISColors.AccentCyan,
                    fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace,
                )
                Icon(
                    imageVector = CIRISIcons.arrowForward,
                    contentDescription = "Open issue",
                    tint = CIRISColors.AccentCyan,
                    modifier = Modifier.size(14.dp),
                )
            }

            // "Why it's gated" — expandable showing the FSD-002 prefix family
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(CIRISColors.BackgroundDarker.copy(alpha = 0.7f))
                    .border(
                        width = 1.dp,
                        color = Color.White.copy(alpha = 0.06f),
                        shape = RoundedCornerShape(10.dp),
                    ),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { expanded = !expanded }
                        .padding(horizontal = 14.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "Why it's gated",
                        color = CIRISColors.TextSecondary,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.weight(1f),
                    )
                    Icon(
                        imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
                        contentDescription = null,
                        tint = CIRISColors.TextTertiary,
                        modifier = Modifier.size(18.dp),
                    )
                }
                if (expanded) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 14.dp, end = 14.dp, bottom = 14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        GateMetaRow("Substrate", gate.repo)
                        GateMetaRow("Prefix family", gate.prefixFamily, mono = true)
                        GateMetaRow("Spec section", gate.fsdSection)
                    }
                }
            }
        }
    }
}

@Composable
private fun GateMetaRow(label: String, value: String, mono: Boolean = false) {
    Column {
        Text(
            text = label.uppercase(),
            color = CIRISColors.TextDim,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.0.sp,
        )
        Text(
            text = value,
            color = CIRISColors.TextSecondary,
            fontSize = 12.sp,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
            modifier = Modifier.padding(top = 2.dp),
        )
    }
}
