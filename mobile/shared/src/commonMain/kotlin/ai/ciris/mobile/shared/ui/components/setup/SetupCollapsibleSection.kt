package ai.ciris.mobile.shared.ui.components.setup

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Collapsible card section for setup wizard.
 * Provides consistent styling and expand/collapse behavior.
 *
 * Reusable from both SetupScreen and LLMSettingsScreen.
 */
@Composable
fun SetupCollapsibleSection(
    title: String,
    subtitle: String,
    icon: ImageVector,
    expanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
    headerColor: Color = SetupCardColors.CardBackground,
    iconTint: Color = SetupCardColors.Primary,
    content: @Composable () -> Unit
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = headerColor,
        modifier = modifier.fillMaxWidth()
    ) {
        Column {
            // Header (always visible, clickable to expand)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggle() }
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = iconTint
                    )
                    Column {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                            color = SetupCardColors.TextPrimary
                        )
                        Text(
                            text = subtitle,
                            style = MaterialTheme.typography.bodySmall,
                            color = SetupCardColors.TextSecondary
                        )
                    }
                }
                Icon(
                    imageVector = if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = SetupCardColors.TextSecondary
                )
            }

            // Expandable content
            AnimatedVisibility(
                visible = expanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                Column(
                    modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
                ) {
                    HorizontalDivider(
                        modifier = Modifier.padding(bottom = 12.dp),
                        color = SetupCardColors.GrayBorder
                    )
                    content()
                }
            }
        }
    }
}
