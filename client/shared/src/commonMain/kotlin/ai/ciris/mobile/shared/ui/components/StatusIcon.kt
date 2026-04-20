package ai.ciris.mobile.shared.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * Status icons using Material Icons instead of Unicode emoji.
 * This ensures consistent rendering across all platforms including WASM/Skia
 * where emoji may appear as tofu boxes.
 */
enum class StatusIconType(val icon: ImageVector, val contentDescription: String) {
    Check(Icons.Default.Check, "Success"),
    Close(Icons.Default.Close, "Error"),
    Warning(Icons.Default.Warning, "Warning"),
    Star(Icons.Default.Star, "Featured")
}

/**
 * Renders a status icon with consistent cross-platform appearance.
 * Use this instead of Text() with emoji characters.
 */
@Composable
fun StatusIcon(
    type: StatusIconType,
    modifier: Modifier = Modifier,
    tint: Color = Color.Unspecified
) {
    Icon(
        imageVector = type.icon,
        contentDescription = type.contentDescription,
        modifier = modifier,
        tint = tint
    )
}

/**
 * Convenience composables for common status icons.
 */
@Composable
fun CheckIcon(modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    StatusIcon(StatusIconType.Check, modifier, tint)
}

@Composable
fun CloseIcon(modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    StatusIcon(StatusIconType.Close, modifier, tint)
}

@Composable
fun WarningIcon(modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    StatusIcon(StatusIconType.Warning, modifier, tint)
}

@Composable
fun StarIcon(modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    StatusIcon(StatusIconType.Star, modifier, tint)
}
