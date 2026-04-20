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
    val originalNode: GraphNode? = null,
    // Extra storage for layout-specific data (e.g., cylinder coordinates)
    val extra: MutableMap<String, Any> = mutableMapOf()
) {
    companion object {
        fun fromGraphNode(node: GraphNode, colorByScope: Boolean = true): GraphNodeDisplay {
            val label = node.attributes.content?.take(30)
                ?: node.attributes.description?.take(30)
                ?: node.id.take(10)

            // Use scope-based coloring for multi-scope cylinder view
            val color = if (colorByScope) {
                GraphColors.getScopeColor(node.scope)
            } else {
                GraphColors.getNodeColor(node.type)
            }

            return GraphNodeDisplay(
                id = node.id,
                type = node.type,
                scope = node.scope,
                label = label,
                color = color,
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
    CIRCULAR("Circular"),
    CYLINDER("3D Cylinder")
}

/**
 * Overall graph display state.
 */
data class GraphDisplayState(
    val nodes: List<GraphNodeDisplay> = emptyList(),
    val edges: List<GraphEdgeDisplay> = emptyList(),
    val viewport: GraphViewport = GraphViewport(),
    val selectedNodeId: String? = null,
    val layout: GraphLayout = GraphLayout.CYLINDER,
    val isSimulationRunning: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null,
    val dataVersion: Int = 0  // Increments each time data is loaded to trigger re-layout
) {
    val selectedNode: GraphNodeDisplay?
        get() = selectedNodeId?.let { id -> nodes.find { it.id == id } }

    val nodeMap: Map<String, GraphNodeDisplay> by lazy {
        nodes.associateBy { it.id }
    }
}

/**
 * Filter options for graph data.
 * Note: scope is non-nullable because cross-scope edges are not supported,
 * so we always display one scope at a time.
 */
data class GraphFilter(
    val scope: GraphScope = GraphScope.LOCAL,
    val nodeTypes: Set<NodeType> = emptySet(),
    val hours: Int = 168,  // 1 week default
    val searchQuery: String = "",
    val includeTelemetry: Boolean = false  // Exclude tsdb_data by default for performance
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
