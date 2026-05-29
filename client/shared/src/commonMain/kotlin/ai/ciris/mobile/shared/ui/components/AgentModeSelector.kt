package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.AgentMode
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Reusable segmented control for selecting the global [AgentMode].
 *
 * Used by NetworkScreen (hub) and SettingsScreen (mirror surface) so changing
 * the mode produces the same dialog flow regardless of where the user lands.
 *
 * Server eligibility is enforced as a soft gate: the button is rendered
 * disabled with a "requires >=256 GiB" hint when `!serverEligible`. We never
 * hide the option — operators should see the capability exists even if their
 * current device can't host it (per Reticulum cribsheet: "all 3 always").
 */
@Composable
fun AgentModeSelector(
    mode: AgentMode,
    serverEligible: Boolean,
    availableDiskBytes: Long,
    requiredDiskBytes: Long,
    onModeChange: (AgentMode) -> Unit,
    modifier: Modifier = Modifier,
    loading: Boolean = false,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                .border(
                    width = 1.dp,
                    color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f),
                    shape = RoundedCornerShape(10.dp),
                )
                .testable("agent_mode_selector"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ModeButton(
                target = AgentMode.CLIENT,
                current = mode,
                enabled = !loading,
                label = localizedString("network.mode_card.client_label"),
                description = localizedString("network.mode_card.client_description"),
                onClick = { onModeChange(AgentMode.CLIENT) },
                modifier = Modifier.weight(1f),
                testTag = "btn_mode_client",
            )
            VerticalDivider()
            ModeButton(
                target = AgentMode.PROXY,
                current = mode,
                enabled = !loading,
                label = localizedString("network.mode_card.proxy_label"),
                description = localizedString("network.mode_card.proxy_description"),
                defaultMarker = localizedString("network.mode_card.proxy_default_marker"),
                onClick = { onModeChange(AgentMode.PROXY) },
                modifier = Modifier.weight(1f),
                testTag = "btn_mode_proxy",
            )
            VerticalDivider()
            ModeButton(
                target = AgentMode.SERVER,
                current = mode,
                enabled = !loading && serverEligible,
                label = localizedString("network.mode_card.server_label"),
                description = localizedString("network.mode_card.server_description"),
                disabledHint = if (!serverEligible) {
                    localizedString(
                        "network.mode_card.server_disk_gate",
                        mapOf(
                            "available" to humanGiB(availableDiskBytes),
                            "required" to humanGiB(requiredDiskBytes.takeIf { it > 0 } ?: SERVER_DEFAULT_MIN),
                        ),
                    )
                } else null,
                onClick = { onModeChange(AgentMode.SERVER) },
                modifier = Modifier.weight(1f),
                testTag = "btn_mode_server",
            )
        }
        if (!serverEligible) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = localizedString(
                    "network.mode_card.server_disk_gate",
                    mapOf(
                        "available" to humanGiB(availableDiskBytes),
                        "required" to humanGiB(requiredDiskBytes.takeIf { it > 0 } ?: SERVER_DEFAULT_MIN),
                    ),
                ),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
            )
        }
    }
}

@Composable
private fun ModeButton(
    target: AgentMode,
    current: AgentMode,
    enabled: Boolean,
    label: String,
    description: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    testTag: String,
    defaultMarker: String? = null,
    disabledHint: String? = null,
) {
    val isSelected = target == current
    val containerColor = when {
        !enabled -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
        isSelected -> CIRISColors.AccentCyan.copy(alpha = 0.18f)
        else -> Color.Transparent
    }
    val labelColor = when {
        !enabled -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
        isSelected -> CIRISColors.AccentCyan
        else -> MaterialTheme.colorScheme.onSurface
    }
    Column(
        modifier = modifier
            .background(containerColor)
            .clickable(enabled = enabled) { onClick() }
            .padding(horizontal = 12.dp, vertical = 12.dp)
            .testable(testTag),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = label,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.SemiBold,
                color = labelColor,
                textAlign = TextAlign.Center,
            )
            if (defaultMarker != null) {
                Spacer(Modifier.width(4.dp))
                Text(
                    text = defaultMarker,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
            }
        }
        Spacer(Modifier.height(2.dp))
        Text(
            text = description,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            fontSize = 11.sp,
        )
        if (disabledHint != null) {
            Spacer(Modifier.height(2.dp))
            Text(
                text = disabledHint,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error.copy(alpha = 0.8f),
                textAlign = TextAlign.Center,
                fontSize = 10.sp,
                modifier = Modifier.alpha(0.85f),
            )
        }
    }
}

@Composable
private fun VerticalDivider() {
    Box(
        modifier = Modifier
            .width(1.dp)
            .height(56.dp)
            .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f)),
    )
}

/** SERVER mode requires >=256 GiB free disk; mirror backend constant. */
private const val SERVER_DEFAULT_MIN: Long = 256L * 1024 * 1024 * 1024

/** Format bytes as integer GiB for compact UI display ("256 GB"). */
private fun humanGiB(bytes: Long): String {
    if (bytes <= 0) return "0 GB"
    val gib = bytes / (1024.0 * 1024.0 * 1024.0)
    return when {
        gib >= 100 -> "${gib.toInt()} GB"
        gib >= 10 -> "${(gib * 10).toInt() / 10.0} GB"
        else -> "${(gib * 100).toInt() / 100.0} GB"
    }
}
