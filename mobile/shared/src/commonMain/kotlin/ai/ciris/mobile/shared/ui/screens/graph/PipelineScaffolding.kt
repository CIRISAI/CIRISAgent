package ai.ciris.mobile.shared.ui.screens.graph

import androidx.compose.ui.graphics.Color
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * Visualization mode for the live graph background.
 * - OFF: No visualization (plain background)
 * - BACKGROUND: Subtle background visualization (current default)
 * - FOREGROUND: Prominent foreground visualization (higher opacity, more visible)
 */
enum class VisualizationMode {
    OFF,
    BACKGROUND,
    FOREGROUND;

    fun next(): VisualizationMode = when (this) {
        OFF -> BACKGROUND
        BACKGROUND -> FOREGROUND
        FOREGROUND -> OFF
    }

    val label: String get() = when (this) {
        OFF -> "OFF"
        BACKGROUND -> "BG"
        FOREGROUND -> "FG"
    }

    val description: String get() = when (this) {
        OFF -> "Visualization off"
        BACKGROUND -> "Background mode"
        FOREGROUND -> "Foreground mode"
    }
}

/**
 * H3ERE pipeline stage representation for scaffolding visualization.
 *
 * Each stage maps to a reasoning stream SSE event type and is drawn
 * as a horizontal ring around the memory cylinder. Rings glow when
 * their corresponding event fires, then fade over GLOW_DURATION_MS.
 */
data class PipelineStage(
    val eventType: String,
    val label: String,
    val color: Color,
    val activatedAtMs: Long = 0L  // 0 = never activated
) {
    companion object {
        /** How long a ring glows after activation (ms) */
        const val GLOW_DURATION_MS = 3000L

        /** Number of vertical struts around the cylinder */
        const val STRUT_COUNT = 12

        /** All H3ERE pipeline stages in order (top to bottom on cylinder) */
        fun defaultStages(): List<PipelineStage> = listOf(
            PipelineStage("thought_start", "THINK", Color(0xFF60A5FA)),       // Blue
            PipelineStage("snapshot_and_context", "CONTEXT", Color(0xFF34D399)), // Green
            PipelineStage("dma_results", "DMA", Color(0xFFFBBF24)),           // Yellow
            PipelineStage("idma_result", "IDMA", Color(0xFFF97316)),          // Orange
            PipelineStage("aspdma_result", "SELECT", Color(0xFFA78BFA)),      // Purple
            PipelineStage("conscience_result", "ETHICS", Color(0xFF38BDF8)), // Sky
            PipelineStage("action_result", "ACT", Color(0xFF4ADE80))          // Emerald
        )
    }
}

/**
 * Immutable pipeline state passed to LiveGraphBackground for scaffolding rendering.
 */
data class PipelineState(
    val stages: List<PipelineStage> = PipelineStage.defaultStages(),
    val version: Int = 0  // Increments on each update to trigger recomposition
) {
    /**
     * Return a new state with the given event type activated at the current time.
     */
    fun activate(eventType: String, currentTimeMs: Long): PipelineState {
        val updated = stages.map { stage ->
            if (stage.eventType == eventType) {
                stage.copy(activatedAtMs = currentTimeMs)
            } else {
                stage
            }
        }
        return copy(stages = updated, version = version + 1)
    }

    /**
     * Reset all stages (e.g., on new thought round).
     */
    fun reset(): PipelineState {
        return copy(
            stages = PipelineStage.defaultStages(),
            version = version + 1
        )
    }
}

/**
 * Projected scaffolding point on the cylinder surface.
 */
data class ScaffoldPoint(
    val screenX: Float,
    val screenY: Float,
    val alpha: Float,     // Depth-based alpha (back of cylinder is dimmer)
    val isBehind: Boolean // True if on the back half
)

/**
 * Project a point on the scaffolding cylinder to 2D screen coordinates.
 *
 * @param theta Angle around cylinder (radians)
 * @param heightFraction Vertical position 0=top, 1=bottom
 * @param rotationY Current Y rotation (degrees)
 * @param rotationX Current X tilt (degrees)
 * @param centerX Screen center X
 * @param centerY Screen center Y
 * @param cylinderRadius Cylinder radius in pixels
 * @param cylinderHeight Cylinder height in pixels
 */
fun projectScaffoldPoint(
    theta: Float,
    heightFraction: Float,
    rotationY: Float,
    rotationX: Float,
    centerX: Float,
    centerY: Float,
    cylinderRadius: Float,
    cylinderHeight: Float
): ScaffoldPoint {
    // Apply Y rotation
    val rotatedTheta = theta + (rotationY.toDouble() * PI / 180.0).toFloat()

    // 3D position on cylinder surface
    val x3d = cos(rotatedTheta) * cylinderRadius
    val z3d = sin(rotatedTheta) * cylinderRadius
    val y3d = (heightFraction - 0.5f) * cylinderHeight  // Center vertically

    // Apply X tilt
    val rotX = rotationX.toDouble() * PI / 180.0
    val y3dRotated = (y3d * cos(rotX) - z3d * sin(rotX)).toFloat()
    val z3dRotated = (y3d * sin(rotX) + z3d * cos(rotX)).toFloat()

    // Perspective projection
    val perspective = 800f
    val scale = perspective / (perspective + z3dRotated)

    val screenX = centerX + x3d * scale
    val screenY = centerY + y3dRotated * scale

    // Depth-based alpha: front is brighter, back is dimmer
    val normalizedDepth = (z3dRotated + cylinderRadius) / (2 * cylinderRadius)
    val alpha = (0.15f + 0.85f * (1f - normalizedDepth)).coerceIn(0.05f, 1f)

    return ScaffoldPoint(
        screenX = screenX,
        screenY = screenY,
        alpha = alpha,
        isBehind = z3dRotated < 0
    )
}
