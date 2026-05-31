package ai.ciris.mobile.shared.ui.nav

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.CIRISSignet
import ai.ciris.mobile.shared.ui.theme.BrightnessPreference
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
    // Optional brightness state — when both are non-null, the sidebar renders
    // a 3-way segmented control (Light / System / Dark) at the bottom so the
    // user can flip themes without leaving the nav. Both null keeps the old
    // sidebar contract for callers that don't surface theme state.
    brightnessPreference: BrightnessPreference? = null,
    onBrightnessChange: ((BrightnessPreference) -> Unit)? = null,
    // Optional close callback — when non-null, the CIRIS header row at the top
    // of the drawer becomes the close affordance (tap the CIRIS signet to
    // dismiss the drawer). The drawer-open hamburger button on the main
    // content is also the CIRIS signet so the open/close affordances are
    // visually identical and always anchored at the top.
    onCloseRequest: (() -> Unit)? = null,
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

    // Theme-aware surface color. `MaterialTheme.colorScheme.surface` follows
    // the app's brightness preference (Light/Dark/System) so the sidebar
    // visually matches the rest of the chrome instead of being a hardcoded
    // dark slab on a light app.
    val sidebarBackground = MaterialTheme.colorScheme.surface

    Column(
        modifier = modifier
            .fillMaxHeight()
            .width(220.dp)
            .background(sidebarBackground)
            .testTag("epistemic_sidebar"),
    ) {
        // Logo / header — the CIRIS signet at the top doubles as the
        // "close drawer" affordance when `onCloseRequest` is wired. This is
        // the second half of the "CIRIS icon = hamburger, always and
        // everywhere" contract: tapping the CIRIS signet on the main content
        // opens the drawer; tapping the SAME signet in the drawer header
        // closes it. Always anchored at the top so it's easy to re-reach.
        val accentColor = MaterialTheme.colorScheme.primary
        val onSurfaceColor = MaterialTheme.colorScheme.onSurface
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .let { if (onCloseRequest != null) it.testableClickable("btn_nav_drawer_close") { onCloseRequest() } else it }
                .padding(horizontal = 16.dp, vertical = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CIRISSignet(
                modifier = Modifier.size(22.dp).testable("img_ciris_signet_drawer"),
                tintColor = accentColor,
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = "CIRIS",
                color = onSurfaceColor.copy(alpha = 0.85f),
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
            if (appVersion.isNotBlank()) {
                Spacer(Modifier.width(6.dp))
                Text(
                    text = appVersion,
                    color = onSurfaceColor.copy(alpha = 0.5f),
                    fontSize = 9.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }

        // Thin divider — theme-aware so it reads on both light + dark
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(1.dp)
                .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.12f)),
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
                        // Pure expand/collapse. The earlier "useful landing"
                        // jump to the first non-gated surface produced an
                        // expand-and-jump-away surprise (e.g. tapping Manage →
                        // jumped into Health Reputation card instead of showing
                        // the group's options). Let the user expand to see
                        // options, then pick one explicitly.
                        groupExpanded[group.id] = !expanded
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

        // ─── Theme strip at the bottom of the drawer ─────────────────
        // Only renders when callers wire brightnessPreference + the change
        // callback. Three-segment chip row (Light / System / Dark) so the
        // user can toggle theme without leaving the nav. Surfaced here
        // because the drawer is the canonical "global app affordance"
        // surface in 2.9.4+ and theme is a global app affordance.
        if (brightnessPreference != null && onBrightnessChange != null) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(1.dp)
                    .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.10f)),
            )
            BrightnessStrip(
                current = brightnessPreference,
                onChange = onBrightnessChange,
            )
        }
    }
}

@Composable
private fun BrightnessStrip(
    current: BrightnessPreference,
    onChange: (BrightnessPreference) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 10.dp)
            .testTag("sidebar_brightness_strip"),
    ) {
        Text(
            text = localizedString("settings.brightness"),
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(start = 4.dp, bottom = 6.dp),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                .padding(2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BrightnessSegment(
                label = localizedString("settings.brightness_light"),
                target = BrightnessPreference.LIGHT,
                current = current,
                onChange = onChange,
                tag = "btn_brightness_light",
                modifier = Modifier.weight(1f),
            )
            BrightnessSegment(
                label = localizedString("settings.brightness_system"),
                target = BrightnessPreference.SYSTEM,
                current = current,
                onChange = onChange,
                tag = "btn_brightness_system",
                modifier = Modifier.weight(1f),
            )
            BrightnessSegment(
                label = localizedString("settings.brightness_dark"),
                target = BrightnessPreference.DARK,
                current = current,
                onChange = onChange,
                tag = "btn_brightness_dark",
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun BrightnessSegment(
    label: String,
    target: BrightnessPreference,
    current: BrightnessPreference,
    onChange: (BrightnessPreference) -> Unit,
    tag: String,
    modifier: Modifier = Modifier,
) {
    val selected = current == target
    val bg = if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.15f) else Color.Transparent
    val fg = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(bg)
            .testableClickable(tag) { onChange(target) }
            .padding(vertical = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = label,
            color = fg,
            fontSize = 11.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
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
    val primaryColor = MaterialTheme.colorScheme.primary
    val onSurfaceColor = MaterialTheme.colorScheme.onSurface
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
                isActive -> accent ?: primaryColor
                else -> onSurfaceColor.copy(alpha = 0.5f)
            },
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = group.label.uppercase(),
            color = when {
                isActive -> onSurfaceColor.copy(alpha = 0.85f)
                else -> onSurfaceColor.copy(alpha = 0.55f)
            },
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.4.sp,
            modifier = Modifier.weight(1f),
        )
        Icon(
            imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
            contentDescription = null,
            tint = onSurfaceColor.copy(alpha = 0.5f),
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

    val primaryColor = MaterialTheme.colorScheme.primary
    val onSurfaceColor = MaterialTheme.colorScheme.onSurface
    val rowBg = if (isActive) primaryColor.copy(alpha = 0.10f) else Color.Transparent
    val labelColor = when {
        isActive -> primaryColor
        isAncestorOfActive -> onSurfaceColor.copy(alpha = 0.75f)
        else -> onSurfaceColor.copy(alpha = 0.6f)
    }
    val iconColor = when {
        isActive -> primaryColor
        else -> onSurfaceColor.copy(alpha = 0.5f)
    }

    // Split-tap row: left zone (icon + label) navigates; right zone
    // (chevron) only toggles inline expansion without navigating or closing
    // the drawer. When the surface has no children, the whole row navigates
    // (no chevron is rendered).
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(4.dp))
            .background(rowBg)
            .padding(end = if (hasChildren) 0.dp else 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            modifier = Modifier
                .weight(1f)
                .testableClickable(navTag(surface.id)) { onSurfaceSelected(surface) }
                .padding(
                    start = (8 + 12 * indent).dp,
                    end = if (hasChildren) 4.dp else 0.dp,
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
                // Phase-wrap (2.9.4): resolve labelKey via localizer when set;
                // fall back to the hardcoded English label if the locale lacks
                // an entry. NavSurfaces without a labelKey (most non-Commons
                // surfaces) stay on raw label until they're touched.
                text = surface.labelKey
                    ?.let { localizedString(it) }
                    ?.takeIf { it.isNotEmpty() && it != surface.labelKey }
                    ?: surface.label,
                color = labelColor,
                fontSize = 11.sp,
                fontWeight = if (isActive) FontWeight.Medium else FontWeight.Normal,
                modifier = Modifier.weight(1f),
            )
            // Coming Soon chip — pinned to substrate issue (lives inside
            // the nav zone so the chip's tap doesn't trigger expand)
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
        }
        // Chevron zone — separate testableClickable so tapping the chevron
        // ONLY toggles inline expansion (no navigation, no drawer close).
        // This is the user-requested split: left side = jump to the card,
        // right side = expand the category in place.
        if (hasChildren) {
            Box(
                modifier = Modifier
                    .testableClickable("nav_expand_${surface.id}") {
                        expandedMap[surface.id] = !isExpanded
                    }
                    .padding(start = 4.dp, end = 10.dp, top = 7.dp, bottom = 7.dp),
            ) {
                Icon(
                    imageVector = if (isExpanded) CIRISIcons.arrowUp else CIRISIcons.arrowRight,
                    contentDescription = null,
                    tint = onSurfaceColor.copy(alpha = 0.5f),
                    modifier = Modifier.size(12.dp),
                )
            }
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
