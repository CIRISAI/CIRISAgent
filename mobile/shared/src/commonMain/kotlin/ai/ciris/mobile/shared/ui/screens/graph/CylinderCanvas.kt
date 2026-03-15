package ai.ciris.mobile.shared.ui.screens.graph

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.tween
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * 3D Cylinder graph visualization canvas.
 *
 * Features:
 * - Nodes arranged on a rotating 3D cylinder surface
 * - Perspective projection with depth-based sizing and alpha
 * - Horizontal drag to rotate the cylinder
 * - Tap to select nodes
 * - Auto-rotation when idle
 * - Smooth momentum after drag release
 */
private const val TAG = "CylinderCanvas"

@Composable
fun CylinderCanvas(
    state: GraphDisplayState,
    cylinderLayout: CylinderLayout,
    onNodeSelected: (String?) -> Unit,
    onLayoutApplied: () -> Unit,
    modifier: Modifier = Modifier,
    autoRotate: Boolean = true,
    groupByType: Boolean = false
) {
    // Use BoxWithConstraints to get size BEFORE drawing
    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        val canvasWidth = constraints.maxWidth.toFloat()
        val canvasHeight = constraints.maxHeight.toFloat()

        PlatformLogger.d(TAG, "Canvas size: ${canvasWidth}x${canvasHeight}, nodes: ${state.nodes.size}, edges: ${state.edges.size}")

        // Apply layout when we have size and nodes
        LaunchedEffect(state.nodes.size, canvasWidth, canvasHeight) {
            if (state.nodes.isNotEmpty() && canvasWidth > 0 && canvasHeight > 0) {
                val layoutStart = System.currentTimeMillis()
                PlatformLogger.d(TAG, ">>> Layout START: ${state.nodes.size} nodes, ${state.edges.size} edges")

                cylinderLayout.applyLayout(
                    nodes = state.nodes,
                    width = canvasWidth,
                    height = canvasHeight,
                    groupByType = groupByType
                )

                val layoutTime = System.currentTimeMillis() - layoutStart
                PlatformLogger.d(TAG, "<<< Layout DONE in ${layoutTime}ms: ${cylinderLayout.timeRings.size} rings created")
                cylinderLayout.timeRings.forEach { ring ->
                    PlatformLogger.d(TAG, "  Ring: ${ring.label} @ x=${ring.xPosition.toInt()}, ${ring.nodeCount} nodes")
                }
                onLayoutApplied()
            }
        }

        CylinderCanvasContent(
            state = state,
            cylinderLayout = cylinderLayout,
            onNodeSelected = onNodeSelected,
            canvasWidth = canvasWidth,
            canvasHeight = canvasHeight,
            autoRotate = autoRotate
        )
    }
}

@Composable
private fun CylinderCanvasContent(
    state: GraphDisplayState,
    cylinderLayout: CylinderLayout,
    onNodeSelected: (String?) -> Unit,
    canvasWidth: Float,
    canvasHeight: Float,
    autoRotate: Boolean
) {
    val textMeasurer = rememberTextMeasurer()

    // Interaction state
    var lastInteractionTime by remember { mutableStateOf(0L) }
    val autoRotationDelay = 3000L // Start auto-rotate after 3s of inactivity

    // Rotation state (UP/DOWN controls this)
    var rotation by remember { mutableStateOf(0f) }
    var rotationVelocity by remember { mutableStateOf(0f) }

    // Time scroll state (LEFT/RIGHT controls this)
    var timeOffset by remember { mutableStateOf(0f) }
    var timeVelocity by remember { mutableStateOf(0f) }

    var isDragging by remember { mutableStateOf(false) }
    var frameCount by remember { mutableStateOf(0) }

    // Current time period indicator
    val currentPeriodIndex by remember(timeOffset, cylinderLayout.timeRings.size) {
        mutableStateOf(
            if (cylinderLayout.timeRings.isEmpty()) 0
            else ((timeOffset / 80f).toInt()).coerceIn(0, cylinderLayout.timeRings.size - 1)
        )
    }

    // Animation loop for rotation and time scroll momentum
    LaunchedEffect(Unit) {
        while (isActive) {
            delay(16) // ~60 FPS
            frameCount++ // Force recomposition

            if (!isDragging) {
                // Apply rotation momentum (vertical drag)
                if (abs(rotationVelocity) > 0.0001f) {
                    rotation += rotationVelocity
                    rotationVelocity *= 0.95f // Damping
                } else {
                    rotationVelocity = 0f

                    // Auto-rotate if enabled and idle
                    if (autoRotate) {
                        val now = System.currentTimeMillis()
                        if (now - lastInteractionTime > autoRotationDelay) {
                            rotation += CylinderLayout.AUTO_ROTATION_SPEED
                        }
                    }
                }

                // Apply time scroll momentum (horizontal drag)
                if (abs(timeVelocity) > 0.1f) {
                    timeOffset += timeVelocity
                    timeVelocity *= 0.92f // Damping
                } else {
                    timeVelocity = 0f
                }

                // Normalize rotation
                while (rotation > 2 * PI.toFloat()) rotation -= 2 * PI.toFloat()
                while (rotation < 0) rotation += 2 * PI.toFloat()

                // Update layout rotation
                cylinderLayout.setRotation(rotation)
            }
        }
    }

    // Use frameCount to force recomposition on animation tick
    @Suppress("UNUSED_VARIABLE")
    val forceRecompose = frameCount

    Canvas(
        modifier = Modifier
            .fillMaxSize()
            .background(GraphColors.Background)
            .pointerInput(state.nodes) {
                detectDragGestures(
                    onDragStart = {
                        isDragging = true
                        rotationVelocity = 0f
                        timeVelocity = 0f
                    },
                    onDragEnd = {
                        isDragging = false
                        lastInteractionTime = System.currentTimeMillis()
                    },
                    onDragCancel = {
                        isDragging = false
                        lastInteractionTime = System.currentTimeMillis()
                    },
                    onDrag = { change, dragAmount ->
                        change.consume()
                        // HORIZONTAL drag = scroll through time (left/right)
                        val timeSensitivity = 1.0f
                        timeOffset += dragAmount.x * timeSensitivity
                        timeVelocity = dragAmount.x * timeSensitivity

                        // VERTICAL drag = rotate cylinder (up/down)
                        val rotationSensitivity = 0.01f
                        val deltaRotation = -dragAmount.y * rotationSensitivity
                        rotation += deltaRotation
                        rotationVelocity = deltaRotation
                        cylinderLayout.setRotation(rotation)
                    }
                )
            }
            .pointerInput(state.nodes) {
                detectTapGestures { offset ->
                    lastInteractionTime = System.currentTimeMillis()

                    // Find node at tap position
                    val hitNode = findNodeAtPosition3D(
                        nodes = state.nodes,
                        cylinderLayout = cylinderLayout,
                        centerX = canvasWidth / 2f,
                        centerY = canvasHeight / 2f,
                        tapX = offset.x,
                        tapY = offset.y,
                        touchRadius = 40f
                    )

                    onNodeSelected(hitNode?.id)
                }
            }
    ) {
        val centerX = canvasWidth / 2
        val centerY = canvasHeight / 2

        // Apply time offset to shift view (scroll through time)
        val scrolledCenterX = centerX + timeOffset

        // Draw time ring outlines FIRST (behind everything)
        drawTimeRings(
            rings = cylinderLayout.timeRings,
            cylinderLayout = cylinderLayout,
            centerX = scrolledCenterX,
            centerY = centerY,
            textMeasurer = textMeasurer,
            highlightIndex = currentPeriodIndex
        )

        // Project nodes to 2D with depth sorting (with time offset applied)
        val projectedNodes = cylinderLayout.projectNodes(state.nodes, scrolledCenterX, centerY)

        // Draw edges (sorted by average depth)
        drawCylinderEdges(
            edges = state.edges,
            projectedNodes = projectedNodes,
            nodeMap = state.nodeMap,
            cylinderLayout = cylinderLayout,
            centerX = scrolledCenterX,
            centerY = centerY,
            selectedNodeId = state.selectedNodeId
        )

        // Draw nodes (already sorted by depth - furthest first)
        projectedNodes.forEach { (node, projected) ->
            val isSelected = state.selectedNodeId == node.id

            drawCylinderNode(
                node = node,
                projected = projected,
                isSelected = isSelected
            )

            // Draw labels for front-facing nodes
            if (!projected.isBehind && projected.scale > 0.6f) {
                drawCylinderLabel(
                    textMeasurer = textMeasurer,
                    label = node.label,
                    x = projected.screenX,
                    y = projected.screenY + node.radius * projected.scale + 12f,
                    scale = projected.scale,
                    alpha = projected.alpha,
                    isSelected = isSelected
                )
            }
        }
    }
}

/**
 * Draw time ring slices for HORIZONTAL cylinder layout.
 * All slices are parallel vertical ellipses - same orientation throughout.
 */
private fun DrawScope.drawTimeRings(
    rings: List<CylinderLayout.TimeRing>,
    cylinderLayout: CylinderLayout,
    centerX: Float,
    centerY: Float,
    textMeasurer: androidx.compose.ui.text.TextMeasurer,
    highlightIndex: Int = -1
) {
    val ringColor = Color(0xFF4A5568)  // Subtle gray
    val ringFillColor = Color(0xFF2D3748)  // Darker fill
    val labelColor = Color(0xFF718096)
    val highlightColor = Color(0xFF63B3ED)  // Blue highlight for current period

    // Make slices very acute (narrow) so more rings fit
    val sliceHeight = 140f  // Vertical height
    val sliceWidth = 8f     // Very narrow - acute ellipse

    rings.forEachIndexed { index, ring ->
        // Apply centerX offset (includes time scroll)
        val ringX = ring.xPosition + (centerX - size.width / 2)
        val isHighlighted = index == highlightIndex

        val currentRingColor = if (isHighlighted) highlightColor else ringColor
        val currentFillColor = if (isHighlighted) highlightColor else ringFillColor

        // All slices same size and orientation (parallel)
        // Semi-transparent fill
        drawOval(
            color = currentFillColor.copy(alpha = if (isHighlighted) 0.3f else 0.15f),
            topLeft = Offset(ringX - sliceWidth / 2, centerY - sliceHeight / 2),
            size = Size(sliceWidth, sliceHeight)
        )

        // Solid outline
        drawOval(
            color = currentRingColor.copy(alpha = if (isHighlighted) 0.9f else 0.6f),
            topLeft = Offset(ringX - sliceWidth / 2, centerY - sliceHeight / 2),
            size = Size(sliceWidth, sliceHeight),
            style = Stroke(width = if (isHighlighted) 2.5f else 1.5f)
        )

        // Draw connecting lines between slices (cylinder surface)
        if (index < rings.size - 1) {
            val nextRing = rings[index + 1]
            val nextRingX = nextRing.xPosition + (centerX - size.width / 2)
            // Top line
            drawLine(
                color = ringColor.copy(alpha = 0.25f),
                start = Offset(ringX, centerY - sliceHeight / 2),
                end = Offset(nextRingX, centerY - sliceHeight / 2),
                strokeWidth = 1f
            )
            // Bottom line
            drawLine(
                color = ringColor.copy(alpha = 0.25f),
                start = Offset(ringX, centerY + sliceHeight / 2),
                end = Offset(nextRingX, centerY + sliceHeight / 2),
                strokeWidth = 1f
            )
        }

        // Draw time label below
        val textLayoutResult = textMeasurer.measure(
            text = ring.label,
            style = TextStyle(
                color = if (isHighlighted) highlightColor else labelColor,
                fontSize = if (isHighlighted) 9.sp else 8.sp
            )
        )

        drawText(
            textLayoutResult = textLayoutResult,
            topLeft = Offset(
                ringX - textLayoutResult.size.width / 2,
                centerY + sliceHeight / 2 + 6f
            )
        )

        // Draw node count above
        val countText = textMeasurer.measure(
            text = "(${ring.nodeCount})",
            style = TextStyle(
                color = if (isHighlighted) highlightColor else labelColor.copy(alpha = 0.8f),
                fontSize = 7.sp
            )
        )
        drawText(
            textLayoutResult = countText,
            topLeft = Offset(
                ringX - countText.size.width / 2,
                centerY - sliceHeight / 2 - countText.size.height - 2f
            )
        )
    }
}

/**
 * Draw edges for cylinder layout.
 */
private fun DrawScope.drawCylinderEdges(
    edges: List<GraphEdgeDisplay>,
    projectedNodes: List<Pair<GraphNodeDisplay, CylinderLayout.ProjectedPoint>>,
    nodeMap: Map<String, GraphNodeDisplay>,
    cylinderLayout: CylinderLayout,
    centerX: Float,
    centerY: Float,
    selectedNodeId: String?
) {
    // Create a map of projections for quick lookup
    val projectionMap = projectedNodes.associate { it.first.id to it.second }

    // Sort edges by average depth (draw furthest first)
    val sortedEdges = edges.mapNotNull { edge ->
        val sourceProj = projectionMap[edge.source]
        val targetProj = projectionMap[edge.target]
        if (sourceProj != null && targetProj != null) {
            Triple(edge, sourceProj, targetProj)
        } else null
    }.sortedByDescending { (_, s, t) -> (s.depth + t.depth) / 2 }

    sortedEdges.forEach { (edge, sourceProj, targetProj) ->
        val isHighlighted = selectedNodeId == edge.source || selectedNodeId == edge.target

        // Average alpha based on both endpoints
        val edgeAlpha = ((sourceProj.alpha + targetProj.alpha) / 2) * if (isHighlighted) 1f else 0.5f

        drawCylinderEdge(
            edge = edge,
            sourceX = sourceProj.screenX,
            sourceY = sourceProj.screenY,
            targetX = targetProj.screenX,
            targetY = targetProj.screenY,
            alpha = edgeAlpha,
            isHighlighted = isHighlighted
        )
    }
}

/**
 * Draw a single edge in cylinder view.
 */
private fun DrawScope.drawCylinderEdge(
    edge: GraphEdgeDisplay,
    sourceX: Float,
    sourceY: Float,
    targetX: Float,
    targetY: Float,
    alpha: Float,
    isHighlighted: Boolean
) {
    val color = if (isHighlighted) {
        GraphColors.lighten(edge.color, 0.3f).copy(alpha = alpha)
    } else {
        edge.color.copy(alpha = alpha * 0.6f)
    }

    val strokeWidth = if (isHighlighted) 2.5f else 1.5f

    val pathEffect = if (edge.isDashed) {
        PathEffect.dashPathEffect(floatArrayOf(8f, 4f), 0f)
    } else {
        null
    }

    // Curved edge
    val dx = targetX - sourceX
    val dy = targetY - sourceY
    val dist = sqrt(dx * dx + dy * dy)

    if (dist < 1f) return

    val curvature = 0.08f
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
 * Draw a node with depth-based scaling and alpha.
 */
private fun DrawScope.drawCylinderNode(
    node: GraphNodeDisplay,
    projected: CylinderLayout.ProjectedPoint,
    isSelected: Boolean
) {
    val scaledRadius = node.radius * projected.scale
    val nodeColor = node.color.copy(alpha = projected.alpha)

    // Selection ring (only for front-facing nodes)
    if (isSelected && !projected.isBehind) {
        drawCircle(
            color = GraphColors.SelectionColor.copy(alpha = projected.alpha),
            radius = scaledRadius + 4f,
            center = Offset(projected.screenX, projected.screenY),
            style = Stroke(width = 3f)
        )
    }

    // Outer ring (border)
    val borderColor = if (projected.isBehind) {
        GraphColors.darken(node.color, 0.5f).copy(alpha = projected.alpha * 0.6f)
    } else {
        GraphColors.darken(node.color, 0.3f).copy(alpha = projected.alpha)
    }

    drawCircle(
        color = borderColor,
        radius = scaledRadius,
        center = Offset(projected.screenX, projected.screenY)
    )

    // Inner fill
    val fillColor = if (isSelected && !projected.isBehind) {
        GraphColors.lighten(node.color, 0.2f).copy(alpha = projected.alpha)
    } else {
        nodeColor
    }

    drawCircle(
        color = fillColor,
        radius = scaledRadius - 2f,
        center = Offset(projected.screenX, projected.screenY)
    )
}

/**
 * Draw node label with depth-based alpha.
 */
private fun DrawScope.drawCylinderLabel(
    textMeasurer: androidx.compose.ui.text.TextMeasurer,
    label: String,
    x: Float,
    y: Float,
    scale: Float,
    alpha: Float,
    isSelected: Boolean
) {
    val displayLabel = if (label.length > 15) label.take(12) + "..." else label
    val fontSize = (10f * scale).coerceIn(8f, 12f)

    val textColor = if (isSelected) {
        GraphColors.LabelColor.copy(alpha = alpha)
    } else {
        GraphColors.LabelColorMuted.copy(alpha = alpha * 0.8f)
    }

    val textLayoutResult = textMeasurer.measure(
        text = displayLabel,
        style = TextStyle(
            color = textColor,
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
 * Find node at tap position in 3D projected space.
 */
private fun findNodeAtPosition3D(
    nodes: List<GraphNodeDisplay>,
    cylinderLayout: CylinderLayout,
    centerX: Float,
    centerY: Float,
    tapX: Float,
    tapY: Float,
    touchRadius: Float
): GraphNodeDisplay? {
    // Project all nodes and find hit, preferring front-facing nodes
    val candidates = nodes.mapNotNull { node ->
        val projected = cylinderLayout.projectNode(node, centerX, centerY)
        val scaledRadius = node.radius * projected.scale + touchRadius

        val dx = projected.screenX - tapX
        val dy = projected.screenY - tapY
        val dist = sqrt(dx * dx + dy * dy)

        if (dist <= scaledRadius) {
            Triple(node, projected, dist)
        } else null
    }

    // Prefer front-facing nodes, then closest
    return candidates
        .sortedWith(compareBy({ it.second.isBehind }, { it.third }))
        .firstOrNull()?.first
}
