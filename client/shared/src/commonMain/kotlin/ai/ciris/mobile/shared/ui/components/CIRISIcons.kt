package ai.ciris.mobile.shared.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.theme.CIRISColors
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
 *
 * Uses custom CIRIS icons from the Icon Redesign spec. Each icon family uses
 * a dedicated bus color (comm, llm, memory, tool, wise, runtime) so the
 * UI reads as a color-coded transcript.
 *
 * Icon design principles:
 * - Two-tone chip: surface at 16% alpha, glyph at 100%
 * - 24dp viewBox, 2px strokes, 20px target
 * - Colors from the bus palette (CIRISColors.Bus*)
 */
object CIRISIcons {
    // === Action types (H3ERE pipeline) ===
    // Custom CIRIS icons replacing generic Material icons
    val speak: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSpeak          // COMM bus
    val tool: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTool            // TOOL bus
    val observe: ImageVector get() = CIRISMaterialIcons.Filled.CIRISObserve      // COMM bus
    val memorize: ImageVector get() = CIRISMaterialIcons.Filled.CIRISMemorize    // MEMORY bus
    val recall: ImageVector get() = CIRISMaterialIcons.Filled.CIRISRecall        // MEMORY bus (FIX for red "?")
    val forget: ImageVector get() = CIRISMaterialIcons.Filled.CIRISForget        // MEMORY bus
    val reject: ImageVector get() = CIRISMaterialIcons.Filled.CIRISReject        // RUNTIME bus
    val ponder: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPonder        // WISE bus
    val defer: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDefer          // WISE bus
    val taskComplete: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTaskComplete // TOOL bus

    // === Pipeline stages ===
    // Custom CIRIS icons for H3ERE pipeline visualization
    val thoughtStart: ImageVector get() = CIRISMaterialIcons.Filled.CIRISThoughtStart  // LLM bus
    val snapshot: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSnapshot          // MEMORY bus
    val dma: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDMA                    // LLM bus
    val idma: ImageVector get() = CIRISMaterialIcons.Filled.CIRISIDMA                  // LLM bus
    val actionSelection: ImageVector get() = CIRISMaterialIcons.Filled.CIRISActionSelection // LLM bus
    val tsaspdma: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTSASPDMA          // LLM bus
    val conscience: ImageVector get() = CIRISMaterialIcons.Filled.CIRISConscience      // LLM bus

    // === Status / severity ===
    // Custom CIRIS status icons with semantic colors
    val warning: ImageVector get() = CIRISMaterialIcons.Filled.CIRISWarning
    val error: ImageVector get() = CIRISMaterialIcons.Filled.CIRISError
    val info: ImageVector get() = CIRISMaterialIcons.Filled.CIRISInfo
    val success: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSuccess

    // === UI chrome ===
    val trust: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTrust
    val log: ImageVector get() = CIRISMaterialIcons.Filled.CIRISList
    val pkg: ImageVector get() = CIRISMaterialIcons.Filled.Inventory2
    val instructions: ImageVector get() = CIRISMaterialIcons.Filled.Description
    val identity: ImageVector get() = CIRISMaterialIcons.Filled.CIRISIdentity
    val safety: ImageVector get() = CIRISMaterialIcons.Filled.HealthAndSafety
    val lightning: ImageVector get() = CIRISMaterialIcons.Filled.CIRISLightning
    val play: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPlay
    val welcome: ImageVector get() = CIRISMaterialIcons.Filled.Hub

    // === Debug log levels ===
    val debugLevel: ImageVector get() = CIRISMaterialIcons.Filled.BugReport
    val infoLevel: ImageVector get() = CIRISMaterialIcons.Filled.CIRISInfo
    val warnLevel: ImageVector get() = CIRISMaterialIcons.Filled.CIRISWarning
    val errorLevel: ImageVector get() = CIRISMaterialIcons.Filled.CIRISError

    // === Agent status ===
    val idle: ImageVector get() = CIRISMaterialIcons.Filled.CIRISIdle
    val processing: ImageVector get() = CIRISMaterialIcons.Filled.CIRISProcessing
    val disconnected: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDisconnected

    // === Emoji replacement icons ===
    // Complete set from Icon Redesign spec - replaces all Unicode emoji
    val check: ImageVector get() = CIRISMaterialIcons.Filled.CIRISCheck           // replaces ✓
    val xmark: ImageVector get() = CIRISMaterialIcons.Filled.CIRISXMark           // replaces ✗ ✖
    val circle: ImageVector get() = CIRISMaterialIcons.Filled.CIRISCircle         // replaces ○
    val question: ImageVector get() = CIRISMaterialIcons.Filled.CIRISQuestion     // replaces ?
    val keySecure: ImageVector get() = CIRISMaterialIcons.Filled.CIRISKeySecure   // replaces 🔐
    val globe: ImageVector get() = CIRISMaterialIcons.Filled.CIRISGlobe           // replaces 🌍
    val refresh: ImageVector get() = CIRISMaterialIcons.Filled.CIRISRefresh       // replaces 🔄
    val wallet: ImageVector get() = CIRISMaterialIcons.Filled.CIRISWallet         // replaces 💰
    val gas: ImageVector get() = CIRISMaterialIcons.Filled.CIRISGas               // replaces ⛽
    val telemetry: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTelemetry   // replaces 📊
    val requirements: ImageVector get() = CIRISMaterialIcons.Filled.CIRISRequirements  // replaces ■
    val instruct: ImageVector get() = CIRISMaterialIcons.Filled.CIRISInstructions // replaces ≡
    val shield: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSafety         // replaces ◆
    val diamond: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDiamond       // replaces ❖ (no dot)
    val identityDiamond: ImageVector get() = CIRISMaterialIcons.Filled.CIRISIdentity  // replaces ❖ (with center dot)

    // === Domain concept icons ===
    val memory: ImageVector get() = CIRISMaterialIcons.Filled.CIRISMemory         // Memory chip
    val skill: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSkill           // SkillStudio
    val model: ImageVector get() = CIRISMaterialIcons.Filled.CIRISModel           // LLM model
    val audit: ImageVector get() = CIRISMaterialIcons.Filled.CIRISAudit           // Audit log
    val adapter: ImageVector get() = CIRISMaterialIcons.Filled.CIRISAdapter       // Adapter plug
    val key: ImageVector get() = CIRISMaterialIcons.Filled.CIRISKey               // Simple key
    val thought: ImageVector get() = CIRISMaterialIcons.Filled.CIRISThought       // Chat bubble
    val task: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTask             // Task clipboard
    val handler: ImageVector get() = CIRISMaterialIcons.Filled.CIRISHandler       // Action handler
    val graph: ImageVector get() = CIRISMaterialIcons.Filled.CIRISGraph           // Memory graph
    val agent: ImageVector get() = CIRISMaterialIcons.Filled.CIRISAgent           // Wise Authority
    val bus: ImageVector get() = CIRISMaterialIcons.Filled.CIRISBus               // Message bus
    val stage: ImageVector get() = CIRISMaterialIcons.Filled.CIRISStage           // Pipeline stage

    // === Action chrome icons ===
    val upload: ImageVector get() = CIRISMaterialIcons.Filled.CIRISUpload         // Upload
    val download: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDownload     // Download
    val search: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSearch         // Search
    val filter: ImageVector get() = CIRISMaterialIcons.Filled.CIRISFilter         // Filter
    val tools: ImageVector get() = CIRISMaterialIcons.Filled.CIRISTools           // Tools (replaces ⚒)

    // === UI control icons ===
    val add: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPlus              // Add/Plus
    val plus: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPlus             // Alias for add
    val minus: ImageVector get() = CIRISMaterialIcons.Filled.CIRISMinus           // Minus/Remove
    val star: ImageVector get() = CIRISMaterialIcons.Filled.CIRISStar             // Rating star
    val location: ImageVector get() = CIRISMaterialIcons.Filled.CIRISLocation     // Map pin
    val clear: ImageVector get() = CIRISMaterialIcons.Filled.CIRISClear           // Clear/Cancel
    val close: ImageVector get() = CIRISMaterialIcons.Filled.CIRISXMark           // Alias for xmark
    val pause: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPause           // Pause button
    val stop: ImageVector get() = CIRISMaterialIcons.Filled.CIRISStop             // Stop button
    val checkCircle: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSuccess   // Green checkmark circle
    val exit: ImageVector get() = CIRISMaterialIcons.Filled.CIRISExit             // Exit/logout
    val moreVert: ImageVector get() = CIRISMaterialIcons.Filled.CIRISMoreVert     // Vertical menu dots

    // === Navigation icons ===
    val arrowBack: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowBack   // Back navigation
    val arrowForward: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowForward // Forward navigation
    val arrowUp: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowUp       // Expand/collapse up
    val arrowDown: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowDown   // Dropdown chevron
    val arrowRight: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowRight // Right chevron
    val arrowLeft: ImageVector get() = CIRISMaterialIcons.Filled.CIRISArrowLeft   // Left chevron

    // === Action icons ===
    val delete: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDelete         // Delete/Trash
    val edit: ImageVector get() = CIRISMaterialIcons.Filled.CIRISEdit             // Edit/Pencil
    val send: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSend             // Send message

    // === UI chrome icons ===
    val settings: ImageVector get() = CIRISMaterialIcons.Filled.CIRISSettings     // Settings gear
    val person: ImageVector get() = CIRISMaterialIcons.Filled.CIRISPerson         // User profile
    val build: ImageVector get() = CIRISMaterialIcons.Filled.CIRISBuild           // Build/Wrench
    val home: ImageVector get() = CIRISMaterialIcons.Filled.CIRISHome             // Home
    val lock: ImageVector get() = CIRISMaterialIcons.Filled.CIRISLock             // Lock/Security
    val dateRange: ImageVector get() = CIRISMaterialIcons.Filled.CIRISDateRange   // Calendar/Date
}

/** Map ActionType enum to its CIRIS icon. */
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
 * Map ActionType to its bus color for automatic tinting.
 *
 * Bus colors (from Icon Redesign spec):
 * - COMM (#419CA0 SignetTeal): Speak, Observe
 * - MEMORY (#7A6FD6 Cool violet): Memorize, Recall, Forget
 * - TOOL (#C96A38 Burnt rust): Tool, Task Complete
 * - WISE (#B08A3E Vintage brass): Ponder, Defer
 * - RUNTIME (#E14B7F Magenta-rose): Reject
 */
fun ActionType.busColor(): Color = when (this) {
    ActionType.SPEAK -> CIRISColors.BusComm
    ActionType.OBSERVE -> CIRISColors.BusComm
    ActionType.MEMORIZE -> CIRISColors.BusMemory
    ActionType.RECALL -> CIRISColors.BusMemory
    ActionType.FORGET -> CIRISColors.BusMemory
    ActionType.TOOL -> CIRISColors.BusTool
    ActionType.TASK_COMPLETE -> CIRISColors.BusTool
    ActionType.PONDER -> CIRISColors.BusWise
    ActionType.DEFER -> CIRISColors.BusWise
    ActionType.REJECT -> CIRISColors.BusRuntime
}

/**
 * Convenience composable — drop-in replacement for Text(actionType.symbol).
 *
 * Icons are automatically tinted with their bus color by default.
 * Pass a specific tint to override, or Color.Unspecified to use theme default.
 *
 * @param actionType The action type to display
 * @param modifier Modifier to apply
 * @param size Icon size (default 20dp as per design spec)
 * @param tint Color tint (defaults to bus color for the action type)
 * @param useBusColor Whether to auto-tint with bus color (default true)
 */
@Composable
fun ActionTypeIcon(
    actionType: ActionType?,
    modifier: Modifier = Modifier,
    size: Dp = 20.dp,
    tint: Color = Color.Unspecified,
    useBusColor: Boolean = true
) {
    val effectiveTint = when {
        tint != Color.Unspecified -> tint
        useBusColor && actionType != null -> actionType.busColor()
        else -> Color.Unspecified
    }

    Icon(
        imageVector = actionType?.icon() ?: CIRISIcons.thoughtStart,
        contentDescription = actionType?.displayName ?: "Unknown",
        modifier = modifier.then(Modifier.size(size)),
        tint = effectiveTint
    )
}

/**
 * Map emoji/symbol strings to CIRIS icons for WASM/Skia rendering.
 * SSE events and backend use Unicode symbols; these need conversion to ImageVectors
 * because WASM/Skia doesn't include emoji font support (renders as "tofu" boxes).
 */
fun emojiToIcon(emoji: String): ImageVector? = when (emoji) {
    // Event type symbols
    "\u2753" -> CIRISIcons.thoughtStart       // ❓ thought_start / recall
    "\u25B6" -> CIRISIcons.speak              // ▶ snapshot_and_context / speak
    "\u2248" -> CIRISIcons.dma                // ≈ dma_results
    "\u2139" -> CIRISIcons.idma               // ℹ idma_result
    "\u26A0" -> CIRISIcons.warning            // ⚠ aspdma_result / action_result / default
    "\u2692" -> CIRISIcons.tool               // ⚒ tsaspdma_result / tool
    "\u25CE" -> CIRISIcons.conscience         // ◎ conscience_result
    // Action symbols
    "\u25CB" -> CIRISIcons.observe            // ○ observe
    "\u2716" -> CIRISIcons.reject             // ✖ reject
    "\u22EF" -> CIRISIcons.ponder             // ⋯ ponder
    "\u275A\u275A" -> CIRISIcons.defer        // ❚❚ defer
    "\u2795" -> CIRISIcons.memorize           // ➕ memorize
    "\u2796" -> CIRISIcons.forget             // ➖ forget
    "\u2714" -> CIRISIcons.taskComplete       // ✔ task_complete
    // Common fallbacks
    "\u2705" -> CIRISIcons.check              // ✅ check
    "\u274C" -> CIRISIcons.xmark              // ❌ x-mark
    // Skill dialog symbols
    "\u2756" -> CIRISIcons.identityDiamond    // ❖ identity
    "\u25A0" -> CIRISIcons.requirements       // ■ requirements
    "\u2261" -> CIRISIcons.instruct           // ≡ instructions
    "\u25C6" -> CIRISIcons.shield             // ◆ safety
    else -> null
}

/**
 * Get icon with default fallback for unrecognized emojis.
 */
fun emojiToIconOrDefault(emoji: String): ImageVector =
    emojiToIcon(emoji) ?: CIRISIcons.circle

/**
 * Get bus color for an emoji symbol.
 * Used for tinting icons in the bubble overlay.
 */
fun emojiBusColor(emoji: String): Color = when (emoji) {
    // LLM bus (purple-ish)
    "\u2753", "\u2248", "\u2139", "\u26A0", "\u25CE" -> CIRISColors.BusLLM
    // COMM bus (teal)
    "\u25B6", "\u25CB" -> CIRISColors.BusComm
    // TOOL bus (orange)
    "\u2692", "\u2714" -> CIRISColors.BusTool
    // MEMORY bus (violet)
    "\u2795", "\u2796" -> CIRISColors.BusMemory
    // WISE bus (brass)
    "\u22EF", "\u275A\u275A" -> CIRISColors.BusWise
    // RUNTIME bus (magenta)
    "\u2716" -> CIRISColors.BusRuntime
    else -> Color.Unspecified
}
