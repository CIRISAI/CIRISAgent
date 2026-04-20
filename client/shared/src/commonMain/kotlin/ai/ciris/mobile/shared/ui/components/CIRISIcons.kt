package ai.ciris.mobile.shared.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import ai.ciris.mobile.shared.ui.icons.*
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
    val observe: ImageVector get() = CIRISMaterialIcons.Filled.Visibility
    val memorize: ImageVector get() = Icons.Default.Add
    val recall: ImageVector get() = CIRISMaterialIcons.Filled.History
    val forget: ImageVector get() = Icons.Default.Delete
    val reject: ImageVector get() = Icons.Default.Close
    val ponder: ImageVector get() = CIRISMaterialIcons.Filled.Lightbulb
    val defer: ImageVector get() = CIRISMaterialIcons.Filled.Schedule
    val taskComplete: ImageVector get() = Icons.Default.Check

    // === Pipeline stages ===
    val thoughtStart: ImageVector get() = CIRISMaterialIcons.Filled.Psychology
    val snapshot: ImageVector get() = CIRISMaterialIcons.Filled.CameraAlt
    val dma: ImageVector get() = CIRISMaterialIcons.Filled.Analytics
    val idma: ImageVector get() = CIRISMaterialIcons.Filled.Insights
    val actionSelection: ImageVector get() = CIRISMaterialIcons.Filled.Tune
    val tsaspdma: ImageVector get() = CIRISMaterialIcons.Filled.Construction
    val conscience: ImageVector get() = CIRISMaterialIcons.Filled.Shield

    // === Status / severity ===
    val warning: ImageVector get() = Icons.Default.Warning
    val error: ImageVector get() = CIRISMaterialIcons.Filled.Error
    val info: ImageVector get() = Icons.Default.Info
    val success: ImageVector get() = Icons.Default.CheckCircle

    // === UI chrome ===
    val trust: ImageVector get() = CIRISMaterialIcons.Filled.Security
    val log: ImageVector get() = Icons.AutoMirrored.Filled.List
    val pkg: ImageVector get() = CIRISMaterialIcons.Filled.Inventory2
    val instructions: ImageVector get() = CIRISMaterialIcons.Filled.Description
    val identity: ImageVector get() = CIRISMaterialIcons.Filled.Badge
    val safety: ImageVector get() = CIRISMaterialIcons.Filled.HealthAndSafety
    val lightning: ImageVector get() = CIRISMaterialIcons.Filled.FlashOn
    val play: ImageVector get() = Icons.Default.PlayArrow
    val welcome: ImageVector get() = CIRISMaterialIcons.Filled.Hub

    // === Debug log levels ===
    val debugLevel: ImageVector get() = CIRISMaterialIcons.Filled.BugReport
    val infoLevel: ImageVector get() = Icons.Default.Info
    val warnLevel: ImageVector get() = Icons.Default.Warning
    val errorLevel: ImageVector get() = CIRISMaterialIcons.Filled.Error

    // === Agent status ===
    val idle: ImageVector get() = CIRISMaterialIcons.Filled.RadioButtonUnchecked
    val processing: ImageVector get() = CIRISMaterialIcons.Filled.Sync
    val disconnected: ImageVector get() = CIRISMaterialIcons.Filled.CloudOff
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
