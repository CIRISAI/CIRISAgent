package ai.ciris.mobile.shared.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.models.ActionType

/**
 * Centralized icon mapping for CIRIS.
 * Uses Material Design Icons (vector-based, renders identically on all platforms).
 */
object CIRISIcons {
    // === Action types (H3ERE pipeline) ===
    val speak: ImageVector get() = Icons.AutoMirrored.Filled.Send
    val tool: ImageVector get() = Icons.Default.Build
    val observe: ImageVector get() = Icons.Default.Visibility
    val memorize: ImageVector get() = Icons.Default.Add
    val recall: ImageVector get() = Icons.Default.History
    val forget: ImageVector get() = Icons.Default.Delete
    val reject: ImageVector get() = Icons.Default.Close
    val ponder: ImageVector get() = Icons.Default.Lightbulb
    val defer: ImageVector get() = Icons.Default.Schedule
    val taskComplete: ImageVector get() = Icons.Default.Check

    // === Pipeline stages ===
    val thoughtStart: ImageVector get() = Icons.Default.Psychology
    val snapshot: ImageVector get() = Icons.Default.CameraAlt
    val dma: ImageVector get() = Icons.Default.Analytics
    val idma: ImageVector get() = Icons.Default.Insights
    val actionSelection: ImageVector get() = Icons.Default.Tune
    val tsaspdma: ImageVector get() = Icons.Default.Construction
    val conscience: ImageVector get() = Icons.Default.Shield

    // === Status / severity ===
    val warning: ImageVector get() = Icons.Default.Warning
    val error: ImageVector get() = Icons.Default.Error
    val info: ImageVector get() = Icons.Default.Info
    val success: ImageVector get() = Icons.Default.CheckCircle

    // === UI chrome ===
    val trust: ImageVector get() = Icons.Default.Security
    val log: ImageVector get() = Icons.AutoMirrored.Filled.List
    val pkg: ImageVector get() = Icons.Default.Inventory2
    val instructions: ImageVector get() = Icons.Default.Description
    val identity: ImageVector get() = Icons.Default.Badge
    val safety: ImageVector get() = Icons.Default.HealthAndSafety
    val lightning: ImageVector get() = Icons.Default.FlashOn
    val play: ImageVector get() = Icons.Default.PlayArrow
    val welcome: ImageVector get() = Icons.Default.Hub

    // === Debug log levels ===
    val debugLevel: ImageVector get() = Icons.Default.BugReport
    val infoLevel: ImageVector get() = Icons.Default.Info
    val warnLevel: ImageVector get() = Icons.Default.Warning
    val errorLevel: ImageVector get() = Icons.Default.Error

    // === Agent status ===
    val idle: ImageVector get() = Icons.Default.RadioButtonUnchecked
    val processing: ImageVector get() = Icons.Default.Sync
    val disconnected: ImageVector get() = Icons.Default.CloudOff
}

/** Map ActionType enum to its Material icon. */
fun ActionType.icon(): ImageVector = when (this) {
    ActionType.SPEAK -> CIRISIcons.speak
    ActionType.TOOL -> CIRISIcons.tool
    ActionType.OBSERVE -> CIRISIcons.observe
    ActionType.MEMORIZE -> CIRISIcons.memorize
    ActionType.RECALL -> CIRISIcons.recall
    ActionType.FORGET -> CIRISIcons.forget
    ActionType.REJECT -> CIRISIcons.reject
    ActionType.PONDER -> CIRISIcons.ponder
    ActionType.DEFER -> CIRISIcons.defer
    ActionType.TASK_COMPLETE -> CIRISIcons.taskComplete
}

/**
 * Convenience composable — drop-in replacement for Text(actionType.symbol).
 */
@Composable
fun ActionTypeIcon(
    actionType: ActionType?,
    modifier: Modifier = Modifier,
    size: Dp = 20.dp,
    tint: Color = Color.Unspecified
) {
    Icon(
        imageVector = actionType?.icon() ?: CIRISIcons.thoughtStart,
        contentDescription = actionType?.displayName ?: "Unknown",
        modifier = modifier.then(Modifier.size(size)),
        tint = tint
    )
}
