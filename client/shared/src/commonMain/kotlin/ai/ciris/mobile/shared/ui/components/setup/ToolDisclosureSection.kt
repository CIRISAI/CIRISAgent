package ai.ciris.mobile.shared.ui.components.setup

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.AdapterToolDisclosure
import ai.ciris.mobile.shared.models.ToolCapabilityFlags
import ai.ciris.mobile.shared.models.ToolDisclosure
import ai.ciris.mobile.shared.models.ToolDisclosureSources
import ai.ciris.mobile.shared.models.summarizeCapabilityFlags
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Tool disclosure for the first-run wizard's optional-features step (#941).
 *
 * **Wide tool access is intended.** Nothing in this file restricts a capability,
 * defaults anything off, or adds a gate. Every adapter keeps whatever default it
 * had. This is disclosure and only disclosure: the operator accepting the
 * enabled-by-default optional features gets told what those choices actually
 * grant the agent -- including the uncomfortable parts, and including the
 * always-on tools that no choice controls and that therefore cannot be declined.
 *
 * Everything rendered here comes from the server's generated
 * `GET /v1/setup/tool-disclosure`, which reads each tool service's own
 * `get_all_tool_info()`. Nothing is transcribed on this side, so the list cannot
 * drift from the implementation the way `ciris_templates/echo.yaml`'s
 * `moderation_tools` did.
 *
 * Shape follows the existing setup idiom (see [SetupCollapsibleSection]):
 * a scannable collapsed summary, detail behind one tap.
 */

/**
 * Expansion key for the always-on group. Not an adapter id -- no adapter
 * controls these tools, which is the whole point of disclosing them separately.
 */
const val ALWAYS_ON_DISCLOSURE_ID = "__always_on__"

/** Localization keys added for this surface. Base bundle is `en.json`. */
private const val KEY_SUMMARY = "mobile.tool_disclosure_summary"
private const val KEY_SUMMARY_ONE = "mobile.tool_disclosure_summary_one"
private const val KEY_PARAMS = "mobile.tool_disclosure_params"
private const val KEY_UNAVAILABLE = "mobile.tool_disclosure_unavailable"
private const val KEY_NOT_LISTED = "mobile.tool_disclosure_not_listed"
private const val KEY_LOADING = "mobile.tool_disclosure_loading"
private const val KEY_ALWAYS_ON_TITLE = "mobile.tool_disclosure_always_on_title"
private const val KEY_ALWAYS_ON_SUBTITLE = "mobile.tool_disclosure_always_on_subtitle"
private const val KEY_ALWAYS_ON_BODY = "mobile.tool_disclosure_always_on_body"
private const val KEY_NO_TOOLS = "mobile.tool_disclosure_no_tools"

/**
 * Collapsed one-line summary plus expandable per-tool detail for a single
 * adapter choice. Rendered directly beneath that adapter's toggle.
 *
 * @param disclosure the server's generated disclosure, or null when the server
 *   listed none for this adapter. Null renders "could not be listed", never an
 *   empty list -- an empty list would read as "grants nothing", which would be
 *   the exact false assurance this feature exists to remove.
 * @param loading true while the disclosure request is still in flight.
 */
@Composable
fun AdapterToolDisclosure(
    adapterId: String,
    disclosure: AdapterToolDisclosure?,
    expanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
    loading: Boolean = false
) {
    Column(modifier = modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, bottom = 10.dp)) {
        when {
            loading && disclosure == null -> DisclosureNote(localizedString(KEY_LOADING))

            disclosure == null -> DisclosureNote(localizedString(KEY_NOT_LISTED))

            else -> {
                ToolDisclosureHeader(
                    testTag = "tool_disclosure_$adapterId",
                    tools = disclosure.tools,
                    unavailable = disclosure.source == ToolDisclosureSources.UNAVAILABLE,
                    expanded = expanded,
                    onToggle = onToggle
                )
                AnimatedVisibility(
                    visible = expanded,
                    enter = expandVertically(),
                    exit = shrinkVertically()
                ) {
                    Column(modifier = Modifier.padding(top = 8.dp)) {
                        if (disclosure.source == ToolDisclosureSources.UNAVAILABLE) {
                            DisclosureNote(disclosure.source_note ?: localizedString(KEY_UNAVAILABLE))
                        }
                        disclosure.tools.forEach { tool ->
                            ToolDisclosureRow(tool)
                        }
                    }
                }
            }
        }
    }
}

/**
 * The always-on group: tools registered regardless of every wizard choice.
 *
 * These appear in no other list in the wizard and cannot be declined, so the
 * section says that plainly rather than omitting them.
 */
@Composable
fun AlwaysOnToolDisclosure(
    groups: List<AdapterToolDisclosure>,
    expanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    if (groups.isEmpty()) return
    val allTools = groups.flatMap { it.tools }

    SetupCollapsibleSection(
        title = localizedString(KEY_ALWAYS_ON_TITLE),
        subtitle = localizedString(
            KEY_ALWAYS_ON_SUBTITLE,
            mapOf("count" to allTools.size.toString())
        ),
        icon = CIRISIcons.lock,
        expanded = expanded,
        onToggle = onToggle,
        modifier = modifier.testable("tool_disclosure_always_on"),
        iconTint = SetupCardColors.TextSecondary
    ) {
        Column {
            Text(
                text = localizedString(KEY_ALWAYS_ON_BODY),
                color = SetupCardColors.TextSecondary,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                modifier = Modifier.padding(bottom = 10.dp)
            )
            groups.forEach { group ->
                if (groups.size > 1) {
                    Text(
                        text = group.adapter_name,
                        color = SetupCardColors.TextPrimary,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 4.dp, bottom = 4.dp)
                    )
                }
                group.tools.forEach { tool -> ToolDisclosureRow(tool) }
            }
        }
    }
}

// ========== Internals ==========

@Composable
private fun ToolDisclosureHeader(
    testTag: String,
    tools: List<ToolDisclosure>,
    unavailable: Boolean,
    expanded: Boolean,
    onToggle: () -> Unit
) {
    val count = tools.size
    val summary = when {
        unavailable && count == 0 -> localizedString(KEY_UNAVAILABLE)
        count == 0 -> localizedString(KEY_NO_TOOLS)
        count == 1 -> localizedString(KEY_SUMMARY_ONE)
        else -> localizedString(KEY_SUMMARY, mapOf("count" to count.toString()))
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable(testTag) { onToggle() },
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = if (expanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
            contentDescription = null,
            tint = SetupCardColors.TextSecondary,
            modifier = Modifier.size(16.dp)
        )
        Spacer(modifier = Modifier.width(6.dp))
        Text(
            text = summary,
            color = SetupCardColors.TextSecondary,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium
        )
    }

    // The collapsed state leads with the least-expected consequences, so the
    // uncomfortable ones are readable without expanding anything. Ordering comes
    // from summarizeCapabilityFlags, not from adapter order.
    val notable = summarizeCapabilityFlags(tools)
    if (notable.isNotEmpty() && !expanded) {
        Column(modifier = Modifier.fillMaxWidth().padding(start = 22.dp, top = 3.dp)) {
            notable.take(2).forEach { flag ->
                Text(
                    text = localizedString(ToolCapabilityFlags.localizationKey(flag)),
                    color = SetupCardColors.TextTertiary,
                    fontSize = 11.sp,
                    lineHeight = 15.sp
                )
            }
        }
    }
}

@Composable
private fun ToolDisclosureRow(tool: ToolDisclosure) {
    Column(modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp)) {
        Text(
            text = tool.name,
            color = SetupCardColors.TextPrimary,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.Monospace
        )
        if (tool.description.isNotBlank()) {
            Text(
                text = tool.description,
                color = SetupCardColors.TextSecondary,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                modifier = Modifier.padding(top = 1.dp)
            )
        }
        // Plain-language consequences, derived server-side from the tool's
        // declared parameter shape.
        tool.capability_flags.forEach { flag ->
            Row(modifier = Modifier.padding(top = 3.dp)) {
                Text(
                    text = "•",
                    color = SetupCardColors.TextTertiary,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(end = 6.dp)
                )
                Text(
                    text = localizedString(ToolCapabilityFlags.localizationKey(flag)),
                    color = SetupCardColors.TextPrimary,
                    fontSize = 12.sp,
                    lineHeight = 17.sp
                )
            }
        }
        if (tool.model_authored_parameters.isNotEmpty()) {
            Text(
                text = localizedString(
                    KEY_PARAMS,
                    mapOf("params" to tool.model_authored_parameters.joinToString(", "))
                ),
                color = SetupCardColors.TextTertiary,
                fontSize = 11.sp,
                lineHeight = 16.sp,
                modifier = Modifier.padding(top = 3.dp)
            )
        }
        HorizontalDivider(
            modifier = Modifier.padding(top = 8.dp),
            color = SetupCardColors.GrayBorder
        )
    }
}

@Composable
private fun DisclosureNote(text: String) {
    Text(
        text = text,
        color = SetupCardColors.TextSecondary,
        fontSize = 12.sp,
        lineHeight = 17.sp,
        modifier = Modifier.fillMaxWidth()
    )
}
