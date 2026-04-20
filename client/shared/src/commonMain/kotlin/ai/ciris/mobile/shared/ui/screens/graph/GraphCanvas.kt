package ai.ciris.mobile.shared.ui.screens.graph

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import kotlin.math.sqrt

/**
 * Main graph visualization canvas.
 *
 * Features:
 * - Pan and zoom with gestures
 * - Node rendering with colors by type
 * - Edge rendering with curves and dash patterns
 * - Node labels (shown when zoomed in)
 * - Selection highlight
 * - Tap to select nodes
 */
@Composable
fun GraphCanvas(
    state: GraphDisplayState,
    onViewportChange: (GraphViewport) -> Unit,
    onNodeSelected: (String?) -> Unit,
    onNodeDragStart: (String) -> Unit,
    onNodeDrag: (String, Float, Float) -> Unit,
    onNodeDragEnd: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val textMeasurer = rememberTextMeasurer()

    // Track dragging state
    var draggedNodeId by remember { mutableStateOf<String?>(null) }
    var lastPanOffset by remember { mutableStateOf(Offset.Zero) }

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .background(GraphColors.Background)
            .pointerInput(state.nodes, state.viewport) {
                detectTransformGestures { centroid, pan, zoom, _ ->
                    // Check if we're dragging a node
                    if (draggedNodeId != null) {
                        // Drag the node
                        val dx = pan.x / state.viewport.scale
                        val dy = pan.y / state.viewport.scale
                        draggedNodeId?.let { onNodeDrag(it, dx, dy) }
                    } else {
                        // Pan/zoom the viewport
                        val newOffsetX = state.viewport.offsetX + pan.x / state.viewport.scale
                        val newOffsetY = state.viewport.offsetY + pan.y / state.viewport.scale
                        val newScale = (state.viewport.scale * zoom).coerceIn(0.1f, 5f)

                        onViewportChange(
                            state.viewport.copy(
                                offsetX = newOffsetX,
                                offsetY = newOffsetY,
                                scale = newScale
                            )
                        )
                    }
                }
            }
            .pointerInput(state.nodes, state.viewport) {
                detectTapGestures(
                    onPress = { offset ->
                        // Check if pressing on a node
                        val worldX = state.viewport.inverseTransformX(offset.x)
                        val worldY = state.viewport.inverseTransformY(offset.y)

                        val hitNode = findNodeAtPosition(
                            state.nodes,
                            worldX,
                            worldY,
                            touchRadius = 30f / state.viewport.scale
                        )

                        if (hitNode != null) {
                            draggedNodeId = hitNode.id
                            onNodeDragStart(hitNode.id)
                        }

                        // Wait for release
                        tryAwaitRelease()

                        // End drag
                        draggedNodeId?.let { onNodeDragEnd(it) }
                        draggedNodeId = null
                    },
                    onTap = { offset ->
                        // Select/deselect node
                        val worldX = state.viewport.inverseTransformX(offset.x)
                        val worldY = state.viewport.inverseTransformY(offset.y)

                        val hitNode = findNodeAtPosition(
                            state.nodes,
                            worldX,
                            worldY,
                            touchRadius = 30f / state.viewport.scale
                        )

                        onNodeSelected(hitNode?.id)
                    }
                )
            }
    ) {
        val viewport = state.viewport

        // Draw edges first (behind nodes)
        state.edges.forEach { edge ->
            val sourceNode = state.nodeMap[edge.source]
            val targetNode = state.nodeMap[edge.target]

            if (sourceNode != null && targetNode != null) {
                drawEdge(
                    edge = edge,
                    sourceX = viewport.transformX(sourceNode.x),
                    sourceY = viewport.transformY(sourceNode.y),
                    targetX = viewport.transformX(targetNode.x),
                    targetY = viewport.transformY(targetNode.y),
                    scale = viewport.scale,
                    isHighlighted = state.selectedNodeId == edge.source ||
                            state.selectedNodeId == edge.target
                )
            }
        }

        // Draw nodes
        state.nodes.forEach { node ->
            val screenX = viewport.transformX(node.x)
            val screenY = viewport.transformY(node.y)
            val screenRadius = node.radius * viewport.scale

            // Viewport culling - skip nodes outside visible area
            if (screenX + screenRadius < 0 || screenX - screenRadius > size.width ||
                screenY + screenRadius < 0 || screenY - screenRadius > size.height
            ) {
                return@forEach
            }

            val isSelected = state.selectedNodeId == node.id

            drawNode(
                node = node,
                x = screenX,
                y = screenY,
                radius = screenRadius,
                isSelected = isSelected
            )

            // Draw label if zoomed in enough
            if (viewport.scale > 0.5f) {
                drawNodeLabel(
                    textMeasurer = textMeasurer,
                    label = node.label,
                    x = screenX,
                    y = screenY + screenRadius + 12f,
                    scale = viewport.scale,
                    isSelected = isSelected
                )
            }
        }
    }
}

/**
 * Draw a single edge as a curved line.
 */
private fun DrawScope.drawEdge(
    edge: GraphEdgeDisplay,
    sourceX: Float,
    sourceY: Float,
    targetX: Float,
    targetY: Float,
    scale: Float,
    isHighlighted: Boolean
) {
    val color = if (isHighlighted) {
        GraphColors.lighten(edge.color, 0.3f)
    } else {
        edge.color.copy(alpha = 0.6f)
    }

    val strokeWidth = if (isHighlighted) 3f * scale else 2f * scale

    val pathEffect = if (edge.isDashed) {
        PathEffect.dashPathEffect(floatArrayOf(10f * scale, 5f * scale), 0f)
    } else {
        null
    }

    // Calculate control point for quadratic bezier curve
    val dx = targetX - sourceX
    val dy = targetY - sourceY
    val dist = sqrt(dx * dx + dy * dy)

    // Add slight curve
    val curvature = 0.1f
    val midX = (sourceX + targetX) / 2
    val midY = (sourceY + targetY) / 2
    val perpX = -dy / dist * curvature * dist
    val perpY = dx / dist * curvature * dist
    val controlX = midX + perpX
    val controlY = midY + perpY

    val path = Path().apply {
        moveTo(sourceX, sourceY)
        quadraticBezierTo(controlX, controlY, targetX, targetY)
    }

    drawPath(
        path = path,
        color = color,
        style = Stroke(
            width = strokeWidth,
            cap = StrokeCap.Round,
            pathEffect = pathEffect
        )
    )
}

/**
 * Draw a single node.
 */
private fun DrawScope.drawNode(
    node: GraphNodeDisplay,
    x: Float,
    y: Float,
    radius: Float,
    isSelected: Boolean
) {
    // Selection ring
    if (isSelected) {
        drawCircle(
            color = GraphColors.SelectionColor,
            radius = radius + 4f,
            center = Offset(x, y),
            style = Stroke(width = 3f)
        )
    }

    // Node border
    drawCircle(
        color = GraphColors.darken(node.color, 0.3f),
        radius = radius,
        center = Offset(x, y)
    )

    // Node fill
    drawCircle(
        color = if (isSelected) GraphColors.lighten(node.color, 0.2f) else node.color,
        radius = radius - 2f,
        center = Offset(x, y)
    )
}

/**
 * Draw node label.
 */
private fun DrawScope.drawNodeLabel(
    textMeasurer: androidx.compose.ui.text.TextMeasurer,
    label: String,
    x: Float,
    y: Float,
    scale: Float,
    isSelected: Boolean
) {
    val displayLabel = if (label.length > 20) label.take(17) + "..." else label
    val fontSize = (10f * scale).coerceIn(8f, 14f)

    val textLayoutResult = textMeasurer.measure(
        text = displayLabel,
        style = TextStyle(
            color = if (isSelected) GraphColors.LabelColor else GraphColors.LabelColorMuted,
            fontSize = fontSize.sp
        )
    )

    drawText(
        textLayoutResult = textLayoutResult,
        topLeft = Offset(
            x - textLayoutResult.size.width / 2,
            y
        )
    )
}

/**
 * Find node at given world coordinates with hit radius.
 */
private fun findNodeAtPosition(
    nodes: List<GraphNodeDisplay>,
    x: Float,
    y: Float,
    touchRadius: Float
): GraphNodeDisplay? {
    // Search in reverse order (top-most nodes first)
    return nodes.lastOrNull { node ->
        val dx = node.x - x
        val dy = node.y - y
        val dist = sqrt(dx * dx + dy * dy)
        dist <= node.radius + touchRadius
    }
}
