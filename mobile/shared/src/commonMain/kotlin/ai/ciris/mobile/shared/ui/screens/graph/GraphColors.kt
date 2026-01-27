package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.api.models.NodeType
import ai.ciris.api.models.GraphScope
import androidx.compose.ui.graphics.Color

/**
 * Color configuration for graph visualization.
 * Colors match the backend memory_visualization.py exactly.
 */
object GraphColors {
    // Background color (dark navy)
    val Background = Color(0xFF1A1A2E)
    val BackgroundLight = Color(0xFF242438)

    // Node colors by type (matching backend)
    private val nodeColors = mapOf(
        NodeType.AGENT to Color(0xFF3B82F6),      // Blue
        NodeType.USER to Color(0xFF10B981),        // Green
        NodeType.CHANNEL to Color(0xFFF59E0B),     // Amber
        NodeType.CONCEPT to Color(0xFFEC4899),     // Pink
        NodeType.CONFIG to Color(0xFF4B5563),      // Gray
        NodeType.TSDB_DATA to Color(0xFF06B6D4),   // Cyan
        NodeType.TSDB_SUMMARY to Color(0xFF06B6D4), // Cyan
        NodeType.CONVERSATION_SUMMARY to Color(0xFF8B5CF6), // Purple
        NodeType.TRACE_SUMMARY to Color(0xFF8B5CF6), // Purple
        NodeType.AUDIT_SUMMARY to Color(0xFF6B7280), // Gray
        NodeType.TASK_SUMMARY to Color(0xFF8B5CF6), // Purple
        NodeType.AUDIT_ENTRY to Color(0xFF6B7280), // Gray
        NodeType.IDENTITY_SNAPSHOT to Color(0xFF06B6D4), // Cyan
        NodeType.BEHAVIORAL to Color(0xFFF97316),  // Orange
        NodeType.SOCIAL to Color(0xFFF97316),      // Orange
        NodeType.IDENTITY to Color(0xFF06B6D4),    // Cyan
        NodeType.OBSERVATION to Color(0xFFFBBF24), // Yellow
        NodeType.CONSENT to Color(0xFF10B981),     // Green
        NodeType.DECAY to Color(0xFF6B7280),       // Gray
        NodeType.MODERATION to Color(0xFFEF4444),  // Red
        NodeType.SAFETY_SCORE to Color(0xFFEF4444) // Red
    )

    // Scope colors
    private val scopeColors = mapOf(
        GraphScope.LOCAL to Color(0xFF3B82F6),      // Blue
        GraphScope.IDENTITY to Color(0xFF06B6D4),   // Cyan
        GraphScope.ENVIRONMENT to Color(0xFF10B981), // Green
        GraphScope.COMMUNITY to Color(0xFFF59E0B)   // Amber
    )

    // Edge colors and styles by relationship type
    private val edgeStyles = mapOf(
        "CREATED" to (Color(0xFF2563EB) to false),        // Blue, solid
        "TRIGGERED" to (Color(0xFFEF4444) to false),      // Red, solid
        "REFERENCED" to (Color(0xFFF59E0B) to true),      // Amber, dashed
        "SUMMARIZES" to (Color(0xFF8B5CF6) to true),      // Purple, dashed
        "TEMPORAL_NEXT" to (Color(0xFF64748B) to false),  // Slate, solid
        "PARTICIPATED" to (Color(0xFF10B981) to false),   // Green, solid
        "RELATES_TO" to (Color(0xFF64748B) to true),      // Slate, dashed
        "PARENT_OF" to (Color(0xFF3B82F6) to false),      // Blue, solid
        "CHILD_OF" to (Color(0xFF3B82F6) to false)        // Blue, solid
    )

    // Default colors
    val DefaultNodeColor = Color(0xFF6B7280)  // Gray
    val DefaultEdgeColor = Color(0xFF64748B)  // Slate
    val SelectionColor = Color(0xFFFFFFFF)    // White
    val LabelColor = Color(0xFFE2E8F0)        // Light gray
    val LabelColorMuted = Color(0xFF94A3B8)   // Muted gray

    // Node sizes by type (important nodes are larger)
    private val nodeSizes = mapOf(
        NodeType.AGENT to 28f,
        NodeType.USER to 24f,
        NodeType.CHANNEL to 24f,
        NodeType.IDENTITY to 26f,
        NodeType.CONCEPT to 20f,
        NodeType.OBSERVATION to 18f,
        NodeType.CONFIG to 16f,
        NodeType.AUDIT_ENTRY to 14f
    )

    val DefaultNodeRadius = 18f

    /**
     * Get color for a node type.
     */
    fun getNodeColor(type: NodeType): Color {
        return nodeColors[type] ?: DefaultNodeColor
    }

    /**
     * Get color for a scope.
     */
    fun getScopeColor(scope: GraphScope): Color {
        return scopeColors[scope] ?: DefaultNodeColor
    }

    /**
     * Get color and dash style for an edge.
     */
    fun getEdgeStyle(relationship: String): Pair<Color, Boolean> {
        val normalized = relationship.uppercase()
        return edgeStyles[normalized] ?: (DefaultEdgeColor to false)
    }

    /**
     * Get radius for a node type.
     */
    fun getNodeRadius(type: NodeType): Float {
        return nodeSizes[type] ?: DefaultNodeRadius
    }

    /**
     * Get a lighter/darker variant of a color for hover/selection states.
     */
    fun lighten(color: Color, factor: Float = 0.2f): Color {
        return Color(
            red = (color.red + (1 - color.red) * factor).coerceIn(0f, 1f),
            green = (color.green + (1 - color.green) * factor).coerceIn(0f, 1f),
            blue = (color.blue + (1 - color.blue) * factor).coerceIn(0f, 1f),
            alpha = color.alpha
        )
    }

    fun darken(color: Color, factor: Float = 0.2f): Color {
        return Color(
            red = (color.red * (1 - factor)).coerceIn(0f, 1f),
            green = (color.green * (1 - factor)).coerceIn(0f, 1f),
            blue = (color.blue * (1 - factor)).coerceIn(0f, 1f),
            alpha = color.alpha
        )
    }

    /**
     * Get a semi-transparent version of a color.
     */
    fun withAlpha(color: Color, alpha: Float): Color {
        return color.copy(alpha = alpha)
    }
}
