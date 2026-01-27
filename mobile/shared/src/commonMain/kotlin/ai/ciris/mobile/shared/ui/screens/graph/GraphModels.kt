package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.api.models.GraphNode
import ai.ciris.api.models.GraphEdge
import ai.ciris.api.models.GraphScope
import ai.ciris.api.models.NodeType
import androidx.compose.ui.graphics.Color

/**
 * Display-ready node for graph visualization.
 * Contains position, velocity, and visual properties.
 */
data class GraphNodeDisplay(
    val id: String,
    val type: NodeType,
    val scope: GraphScope,
    val label: String,
    val color: Color,
    val radius: Float = 20f,
    // Position (mutable for physics simulation)
    var x: Float = 0f,
    var y: Float = 0f,
    // Velocity (mutable for physics simulation)
    var vx: Float = 0f,
    var vy: Float = 0f,
    // Fixed position (if user pinned the node)
    var fixed: Boolean = false,
    // Original data for details panel
    val originalNode: GraphNode? = null
) {
    companion object {
        fun fromGraphNode(node: GraphNode): GraphNodeDisplay {
            val label = node.attributes.content?.take(30)
                ?: node.attributes.description?.take(30)
                ?: node.id.take(10)

            return GraphNodeDisplay(
                id = node.id,
                type = node.type,
                scope = node.scope,
                label = label,
                color = GraphColors.getNodeColor(node.type),
                radius = GraphColors.getNodeRadius(node.type),
                originalNode = node
            )
        }
    }
}

/**
 * Display-ready edge for graph visualization.
 */
data class GraphEdgeDisplay(
    val source: String,
    val target: String,
    val relationship: String,
    val scope: GraphScope,
    val color: Color,
    val isDashed: Boolean,
    val weight: Float = 1f
) {
    companion object {
        fun fromGraphEdge(edge: GraphEdge): GraphEdgeDisplay {
            val (color, isDashed) = GraphColors.getEdgeStyle(edge.relationship)
            return GraphEdgeDisplay(
                source = edge.source,
                target = edge.target,
                relationship = edge.relationship,
                scope = edge.scope,
                color = color,
                isDashed = isDashed,
                weight = edge.weight?.toFloat() ?: 1f
            )
        }
    }
}

/**
 * Viewport state for pan/zoom.
 */
data class GraphViewport(
    val offsetX: Float = 0f,
    val offsetY: Float = 0f,
    val scale: Float = 1f
) {
    fun transformX(x: Float): Float = (x + offsetX) * scale
    fun transformY(y: Float): Float = (y + offsetY) * scale
    fun inverseTransformX(screenX: Float): Float = screenX / scale - offsetX
    fun inverseTransformY(screenY: Float): Float = screenY / scale - offsetY
}

/**
 * Layout algorithm options.
 */
enum class GraphLayout(val displayName: String) {
    FORCE("Force-Directed"),
    TIMELINE("Timeline"),
    HIERARCHY("Hierarchy"),
    CIRCULAR("Circular")
}

/**
 * Overall graph display state.
 */
data class GraphDisplayState(
    val nodes: List<GraphNodeDisplay> = emptyList(),
    val edges: List<GraphEdgeDisplay> = emptyList(),
    val viewport: GraphViewport = GraphViewport(),
    val selectedNodeId: String? = null,
    val layout: GraphLayout = GraphLayout.FORCE,
    val isSimulationRunning: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null
) {
    val selectedNode: GraphNodeDisplay?
        get() = selectedNodeId?.let { id -> nodes.find { it.id == id } }

    val nodeMap: Map<String, GraphNodeDisplay> by lazy {
        nodes.associateBy { it.id }
    }
}

/**
 * Filter options for graph data.
 */
data class GraphFilter(
    val scope: GraphScope? = null,
    val nodeTypes: Set<NodeType> = emptySet(),
    val hours: Int = 24,
    val searchQuery: String = ""
)

/**
 * Graph statistics for display.
 */
data class GraphStats(
    val totalNodes: Int = 0,
    val totalEdges: Int = 0,
    val nodesByType: Map<NodeType, Int> = emptyMap(),
    val nodesByScope: Map<GraphScope, Int> = emptyMap()
)
