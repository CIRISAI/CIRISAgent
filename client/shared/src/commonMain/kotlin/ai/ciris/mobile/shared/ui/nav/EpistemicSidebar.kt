package ai.ciris.mobile.shared.ui.nav

import androidx.compose.foundation.background
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.theme.CIRISColors

/**
 * The Epistemic Commons Framework sidebar — load-bearing nav chrome for 2.9.4.
 *
 * Renders 4 collapsible groups (Agent / Manage / Federation / Client) from
 * [EPISTEMIC_NAV_GROUPS]. Each group expands to show its top-level surfaces;
 * each surface with children expands inline to show sub-surfaces. The active
 * surface is highlighted in `CIRISColors.AccentCyan`.
 *
 * Test tags follow the pattern:
 *   nav_group_{group.id}              — group expand/collapse toggle
 *   nav_epistemic_{slug}              — surface row (clickable via test server)
 *   nav_substrate_gate_{surface.id}   — Coming Soon chip when surface is gated
 *
 * Slugs are the surface id with hyphens normalized to underscores so the QA
 * walk-test can use stable Python-identifier-style names (e.g.
 * "trust-topology" → "nav_epistemic_trust_topology"). The Network surface
 * specifically exposes `nav_epistemic_network` — that's the entry point the
 * federation walk-test uses to reach the Network hub.
 *
 * Existing QA scripts that drove the old top-bar dropdown menu (`menu_*`
 * testTags) will need updating to the new `nav_epistemic_*` testTags. This is
 * expected scope for the 2.9.4 rewire — the old chrome is fully replaced.
 */
private fun navTag(surfaceId: String): String =
    "nav_epistemic_${surfaceId.replace('-', '_')}"
@Composable
fun EpistemicSidebar(
    activeSurface: NavSurface?,
    onSurfaceSelected: (NavSurface) -> Unit,
    onIssueClick: (String) -> Unit = {},
    appVersion: String = "",
    modifier: Modifier = Modifier,
) {
    val scroll = rememberScrollState()

    // Active group is the group containing the active surface (transitively).
    val activeGroup = activeSurface?.let { surface ->
        EPISTEMIC_NAV_GROUPS.firstOrNull { group ->
            group.surfaces.any { surface in it.descendantsAndSelf() }
        }
    }

    // Per-group expansion state — initialize with the active group expanded.
    val groupExpanded = remember(activeGroup) {
        mutableStateMapOf<String, Boolean>().apply {
            EPISTEMIC_NAV_GROUPS.forEach { put(it.id, it == activeGroup) }
        }
    }

    // Per-parent-surface expansion state — initialize with the active surface's
    // ancestor expanded.
    val surfaceExpanded = remember(activeSurface) {
        mutableStateMapOf<String, Boolean>().apply {
            if (activeSurface != null) {
                EPISTEMIC_NAV_GROUPS.forEach { group ->
                    group.surfaces.forEach { surface ->
                        if (activeSurface in surface.children.flatMap { it.descendantsAndSelf() }) {
                            put(surface.id, true)
                        }
                    }
                }
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxHeight()
            .width(220.dp)
            .background(CIRISColors.BackgroundDarker)
            .testTag("epistemic_sidebar"),
    ) {
        // Logo / header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(26.dp)
                    .clip(RoundedCornerShape(6.dp))
                    .background(CIRISColors.AccentCyan.copy(alpha = 0.10f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = CIRISIcons.keySecure,
                    contentDescription = null,
                    tint = CIRISColors.AccentCyan,
                    modifier = Modifier.size(14.dp),
                )
            }
            Spacer(Modifier.width(8.dp))
            Text(
                text = "CIRIS",
                color = CIRISColors.TextPrimary.copy(alpha = 0.85f),
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
            if (appVersion.isNotBlank()) {
                Spacer(Modifier.width(6.dp))
                Text(
                    text = appVersion,
                    color = CIRISColors.TextDim,
                    fontSize = 9.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }

        // Thin divider
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(1.dp)
                .background(Color.White.copy(alpha = 0.06f)),
        )

        // Nav body — scrollable
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .verticalScroll(scroll)
                .padding(vertical = 4.dp),
        ) {
            EPISTEMIC_NAV_GROUPS.forEach { group ->
                val expanded = groupExpanded[group.id] ?: false
                val isActiveGroup = group == activeGroup
                NavGroupHeader(
                    group = group,
                    expanded = expanded,
                    isActive = isActiveGroup,
                    onToggle = {
                        groupExpanded[group.id] = !expanded
                        // If toggling a non-active group ON, jump to its first non-gated surface
                        // so the user has a useful landing.
                        if (!expanded && !isActiveGroup) {
                            val firstUngated = group.surfaces.firstOrNull { it.gate == null }
                            (firstUngated ?: group.surfaces.first()).let(onSurfaceSelected)
                        }
                    },
                )
                if (expanded) {
                    group.surfaces.forEach { surface ->
                        NavSurfaceRow(
                            surface = surface,
                            indent = 1,
                            activeSurface = activeSurface,
                            expandedMap = surfaceExpanded,
                            onSurfaceSelected = onSurfaceSelected,
                            onIssueClick = onIssueClick,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun NavGroupHeader(
    group: NavGroup,
    expanded: Boolean,
    isActive: Boolean,
    onToggle: () -> Unit,
) {
    val accent = group.accentHex?.let { parseHex(it) }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("nav_group_${group.id}") { onToggle() }
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = group.icon,
            contentDescription = null,
            tint = when {
                isActive -> accent ?: CIRISColors.AccentCyan
                else -> CIRISColors.TextDim
            },
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = group.label.uppercase(),
            color = when {
                isActive -> CIRISColors.TextPrimary.copy(alpha = 0.75f)
                else -> CIRISColors.TextTertiary
            },
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.4.sp,
            modifier = Modifier.weight(1f),
        )
        Icon(
            imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
            contentDescription = null,
            tint = CIRISColors.TextDim,
            modifier = Modifier.size(12.dp),
        )
    }
}

/**
 * Single surface row + recursive child expansion. Indent shifts each level
 * deeper by 12dp; max depth in our taxonomy is 3 (group → surface → sub).
 */
@Composable
private fun NavSurfaceRow(
    surface: NavSurface,
    indent: Int,
    activeSurface: NavSurface?,
    expandedMap: MutableMap<String, Boolean>,
    onSurfaceSelected: (NavSurface) -> Unit,
    onIssueClick: (String) -> Unit,
) {
    val isActive = surface == activeSurface
    val isAncestorOfActive = activeSurface != null &&
        activeSurface in surface.children.flatMap { it.descendantsAndSelf() }
    val isExpanded = expandedMap[surface.id] ?: false
    val hasChildren = surface.children.isNotEmpty()

    val rowBg = if (isActive) CIRISColors.AccentCyan.copy(alpha = 0.08f) else Color.Transparent
    val labelColor = when {
        isActive -> CIRISColors.AccentCyan
        isAncestorOfActive -> CIRISColors.TextPrimary.copy(alpha = 0.6f)
        else -> CIRISColors.TextTertiary
    }
    val iconColor = when {
        isActive -> CIRISColors.AccentCyan
        else -> CIRISColors.TextDim
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(4.dp))
            .background(rowBg)
            .testableClickable(navTag(surface.id)) {
                onSurfaceSelected(surface)
                if (hasChildren) expandedMap[surface.id] = !isExpanded
            }
            .padding(
                start = (8 + 12 * indent).dp,
                end = 10.dp,
                top = 7.dp,
                bottom = 7.dp,
            ),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = surface.icon,
            contentDescription = null,
            tint = iconColor,
            modifier = Modifier.size(12.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = surface.label,
            color = labelColor,
            fontSize = 11.sp,
            fontWeight = if (isActive) FontWeight.Medium else FontWeight.Normal,
            modifier = Modifier.weight(1f),
        )
        // Coming Soon chip — pinned to substrate issue
        if (surface.gate != null) {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(4.dp))
                    .background(CIRISColors.BusTool.copy(alpha = 0.15f))
                    .clickable { onIssueClick(surface.gate.url) }
                    .testTag("nav_substrate_gate_${surface.id}")
                    .padding(horizontal = 4.dp, vertical = 1.dp),
            ) {
                Text(
                    text = "SOON",
                    color = CIRISColors.BusTool,
                    fontSize = 7.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.8.sp,
                )
            }
        }
        if (hasChildren) {
            Spacer(Modifier.width(4.dp))
            Icon(
                imageVector = if (isExpanded) CIRISIcons.arrowUp else CIRISIcons.arrowRight,
                contentDescription = null,
                tint = CIRISColors.TextDim,
                modifier = Modifier.size(10.dp),
            )
        }
    }
    if (hasChildren && isExpanded) {
        surface.children.forEach { child ->
            NavSurfaceRow(
                surface = child,
                indent = indent + 1,
                activeSurface = activeSurface,
                expandedMap = expandedMap,
                onSurfaceSelected = onSurfaceSelected,
                onIssueClick = onIssueClick,
            )
        }
    }
}

/**
 * Parse a `#RRGGBB` hex string into a Compose [Color]. Limited tolerance —
 * caller is expected to pass well-formed hex from [NavGroup.accentHex].
 */
private fun parseHex(hex: String): Color? = runCatching {
    val cleaned = hex.removePrefix("#")
    val r = cleaned.substring(0, 2).toInt(16)
    val g = cleaned.substring(2, 4).toInt(16)
    val b = cleaned.substring(4, 6).toInt(16)
    Color(r, g, b)
}.getOrNull()
