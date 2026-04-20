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
        // Toggle is a 2-state BG <-> FG cycle in practice. Previously
        // FG -> OFF, which users experienced as "the viz closed" on
        // what they thought was a back-to-BG tap. OFF is still reachable
        // via settings; it just isn't part of the casual toggle loop.
        OFF -> BACKGROUND
        BACKGROUND -> FOREGROUND
        FOREGROUND -> BACKGROUND
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
 *
 * The glowBoost multiplier allows certain events (like TSASPDMA) to
 * re-activate a ring with extra brightness (e.g., 1.5x normal glow).
 *
 * Labels are localized via labelKey -> resolved label text.
 * Vector font character sets are loaded per-language to render labels.
 */
data class PipelineStage(
    val eventType: String,
    val labelKey: String,         // Localization key (e.g., "pipeline_label_think")
    val label: String,            // Resolved label text for rendering
    val color: Color,
    val activatedAtMs: Long = 0L,  // 0 = never activated
    val glowBoost: Float = 1.0f    // Multiplier for glow intensity (1.0 = normal, 1.5 = boosted)
) {
    companion object {
        /** How long a ring glows after activation (ms) */
        const val GLOW_DURATION_MS = 3000L

        /** Number of vertical struts around the cylinder */
        const val STRUT_COUNT = 12

        /** Glow boost for TSASPDMA re-activation of ASPDMA ring */
        const val TSASPDMA_BOOST = 1.6f

        /** Stage definitions with localization keys and colors */
        val STAGE_DEFINITIONS = listOf(
            Triple("thought_start", "pipeline_label_think", Color(0xFF60A5FA)),       // Blue
            Triple("snapshot_and_context", "pipeline_label_context", Color(0xFF34D399)), // Green
            Triple("dma_results", "pipeline_label_dma", Color(0xFFFBBF24)),           // Yellow
            Triple("idma_result", "pipeline_label_idma", Color(0xFFF97316)),          // Orange
            Triple("aspdma_result", "pipeline_label_select", Color(0xFFA78BFA)),      // Purple
            Triple("conscience_result", "pipeline_label_ethics", Color(0xFF38BDF8)), // Sky
            Triple("action_result", "pipeline_label_act", Color(0xFF4ADE80))          // Emerald
        )

        /** Default stages with English labels (fallback) */
        fun defaultStages(): List<PipelineStage> = STAGE_DEFINITIONS.map { (eventType, labelKey, color) ->
            PipelineStage(eventType, labelKey, defaultLabel(labelKey), color)
        }

        /** Create stages with localized labels */
        fun localizedStages(labelResolver: (String) -> String): List<PipelineStage> =
            STAGE_DEFINITIONS.map { (eventType, labelKey, color) ->
                PipelineStage(eventType, labelKey, labelResolver(labelKey), color)
            }

        /** English fallback labels */
        private fun defaultLabel(key: String): String = when (key) {
            "pipeline_label_think" -> "THINK"
            "pipeline_label_context" -> "CONTEXT"
            "pipeline_label_dma" -> "DMA"
            "pipeline_label_idma" -> "IDMA"
            "pipeline_label_select" -> "SELECT"
            "pipeline_label_ethics" -> "ETHICS"
            "pipeline_label_act" -> "ACT"
            else -> key
        }
    }
}

/**
 * Immutable pipeline state passed to LiveGraphBackground for scaffolding rendering.
 */
data class PipelineState(
    val stages: List<PipelineStage> = PipelineStage.defaultStages(),
    val version: Int = 0,  // Increments on each update to trigger recomposition
    val labelResolver: ((String) -> String)? = null  // Optional label resolver for localization
) {
    /**
     * Return a new state with the given event type activated at the current time.
     * @param boost Optional glow intensity multiplier (default 1.0)
     */
    fun activate(eventType: String, currentTimeMs: Long, boost: Float = 1.0f): PipelineState {
        val updated = stages.map { stage ->
            if (stage.eventType == eventType) {
                stage.copy(activatedAtMs = currentTimeMs, glowBoost = boost)
            } else {
                stage
            }
        }
        return copy(stages = updated, version = version + 1)
    }

    /**
     * Activate ASPDMA with TSASPDMA boost (re-lights SELECT ring brighter).
     * Called when tsaspdma_result event is received.
     */
    fun activateWithTsaspdmaBoost(currentTimeMs: Long): PipelineState {
        return activate("aspdma_result", currentTimeMs, PipelineStage.TSASPDMA_BOOST)
    }

    /**
     * Reset all stages (e.g., on new thought round).
     * Preserves localization by using stored labelResolver.
     */
    fun reset(): PipelineState {
        val newStages = if (labelResolver != null) {
            PipelineStage.localizedStages(labelResolver)
        } else {
            PipelineStage.defaultStages()
        }
        return copy(stages = newStages, version = version + 1)
    }

    /**
     * Update labels with new localization resolver.
     * Call this when language changes.
     */
    fun withLocalizedLabels(resolver: (String) -> String): PipelineState {
        val localizedStages = stages.map { stage ->
            stage.copy(label = resolver(stage.labelKey))
        }
        return copy(stages = localizedStages, labelResolver = resolver, version = version + 1)
    }

    companion object {
        /** Create a localized pipeline state */
        fun localized(labelResolver: (String) -> String): PipelineState {
            return PipelineState(
                stages = PipelineStage.localizedStages(labelResolver),
                labelResolver = labelResolver
            )
        }
    }
}

/**
 * Current glow intensity for a pipeline stage in `[0, glowBoost]`, given
 * the wall-clock time `nowMs`. Zero when never activated or after the
 * glow window has expired. Decays via `1 - smoothstep(t)` so the ring
 * pulses sharply on activation then fades naturally.
 *
 * Pure: no Compose dependency, no state, only reads the data class.
 * The cell viz uses this to brighten the nucleus shell corresponding
 * to each stage — shell i glows when stage i fires.
 */
fun PipelineStage.glowIntensity(nowMs: Long): Float {
    if (activatedAtMs <= 0L) return 0f
    val elapsed = (nowMs - activatedAtMs).toFloat()
    if (elapsed < 0f || elapsed >= PipelineStage.GLOW_DURATION_MS) return 0f
    val t = elapsed / PipelineStage.GLOW_DURATION_MS.toFloat()
    // smoothstep(t) is 0 at t=0 and 1 at t=1, so (1 - smoothstep(t))
    // decays from 1 → 0 naturally. Multiply by glowBoost so TSASPDMA
    // re-activations peak 1.6× brighter.
    return (1f - smoothstep(t)) * glowBoost
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
