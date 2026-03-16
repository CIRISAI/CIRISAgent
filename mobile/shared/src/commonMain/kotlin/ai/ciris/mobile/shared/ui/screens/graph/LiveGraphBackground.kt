package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

private const val TAG = "LiveGraphBackground"
private const val BIRTH_ANIMATION_DURATION_MS = 2000L  // 2 seconds for new node animation
private const val EVENT_REFRESH_DELAY_MS = 1500L  // Delay after event before refresh (let DB settle)

/**
 * Safe color copy that clamps alpha to valid range [0, 1].
 * Prevents crashes from invalid color values in animations.
 */
private fun Color.safeAlpha(alpha: Float): Color {
    return this.copy(alpha = alpha.coerceIn(0f, 1f))
}
private const val MIN_REFRESH_INTERVAL_MS = 5000L  // Minimum time between refreshes

/**
 * Live animated 3D memory graph background for the Interact screen.
 *
 * Features:
 * - Loads past 24 hours of memory graph data
 * - Renders nodes on a slowly rotating 3D cylinder
 * - Low opacity and subtle blur effect for readability
 * - Dual-axis rotation (X around center, Y tilt)
 * - Minimal performance impact through reduced frame rate
 * - Birth animation for newly appearing nodes (pulse + scale)
 * - Event-driven refresh: SSE events trigger organic graph updates
 *
 * Best practices applied:
 * - 20-40% opacity for background elements
 * - Slow rotation to avoid distraction
 * - Dark overlay gradient for text contrast
 * - Lightweight animations (alpha + scale only)
 * - Debounced refresh to avoid resource contention
 */
private const val SPIN_APART_DURATION_MS = 1500L  // Animation duration

@Composable
fun LiveGraphBackground(
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier,
    baseOpacity: Float = 0.85f,  // Near-solid for sharp nodes
    eventTrigger: Int = 0,  // Incremented when SSE events occur (speak, tool, etc.)
    externalRotation: Float = 0f,  // External rotation from swipe gestures (degrees)
    spinEnergy: Float = 0f,  // Accumulated spin energy from multiple flicks
    spinEnergyThreshold: Float = 100f,  // Energy threshold to trigger spin apart
    onSpinApartTriggered: () -> Unit = {}  // Callback when spin apart animation starts
) {
    // Log when composable is first called
    PlatformLogger.i(TAG, ">>> LiveGraphBackground COMPOSING (eventTrigger=$eventTrigger, opacity=$baseOpacity)")

    var canvasSize by remember { mutableStateOf(IntSize.Zero) }
    var nodes by remember { mutableStateOf<List<BackgroundNode>>(emptyList()) }
    var edges by remember { mutableStateOf<List<BackgroundEdge>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }

    // Track known node IDs for detecting new nodes
    var knownNodeIds by remember { mutableStateOf<Set<String>>(emptySet()) }

    // Refresh tracking for debouncing
    var lastRefreshTime by remember { mutableStateOf(0L) }
    var pendingRefresh by remember { mutableStateOf(false) }

    // Spin apart animation state
    var isSpinningApart by remember { mutableStateOf(false) }
    var spinApartProgress by remember { mutableStateOf(0f) }
    var spinApartStartTime by remember { mutableStateOf(0L) }

    // Detect spin apart trigger - requires building up energy over multiple flicks
    LaunchedEffect(spinEnergy) {
        if (spinEnergy >= spinEnergyThreshold && !isSpinningApart) {
            PlatformLogger.i(TAG, ">>> SPIN APART TRIGGERED! energy=$spinEnergy threshold=$spinEnergyThreshold")
            isSpinningApart = true
            spinApartStartTime = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
            onSpinApartTriggered()
        }
    }

    // Spin apart animation loop
    LaunchedEffect(isSpinningApart) {
        if (isSpinningApart) {
            while (isActive && isSpinningApart) {
                delay(16)  // ~60 FPS
                val elapsed = kotlinx.datetime.Clock.System.now().toEpochMilliseconds() - spinApartStartTime
                spinApartProgress = (elapsed.toFloat() / SPIN_APART_DURATION_MS).coerceIn(0f, 1f)

                if (spinApartProgress >= 1f) {
                    // Animation complete - reset
                    isSpinningApart = false
                    spinApartProgress = 0f
                    PlatformLogger.i(TAG, ">>> SPIN APART COMPLETE - reforming")
                }
            }
        }
    }

    // Continuous rotation animation (base automatic rotation)
    val infiniteTransition = rememberInfiniteTransition(label = "rotation")

    // Primary rotation around Y-axis (horizontal spin) - automatic
    val autoRotationY by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 60000, easing = LinearEasing),  // 60 seconds per rotation
            repeatMode = RepeatMode.Restart
        ),
        label = "rotationY"
    )

    // Combined rotation: auto + external (swipe) rotation
    val rotationY = autoRotationY + externalRotation

    // Secondary tilt on X-axis (gentle rocking)
    val rotationX by infiniteTransition.animateFloat(
        initialValue = -10f,
        targetValue = 10f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 15000, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "rotationX"
    )

    // Birth animation pulse for new nodes
    val birthPulse by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1000, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "birthPulse"
    )

    // Event-triggered refresh with debouncing
    LaunchedEffect(eventTrigger) {
        if (eventTrigger > 0) {
            val now = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
            val timeSinceLastRefresh = now - lastRefreshTime

            if (timeSinceLastRefresh < MIN_REFRESH_INTERVAL_MS) {
                // Too soon - mark as pending and wait
                pendingRefresh = true
                delay(MIN_REFRESH_INTERVAL_MS - timeSinceLastRefresh + EVENT_REFRESH_DELAY_MS)
            } else {
                // Wait for DB to settle after event
                delay(EVENT_REFRESH_DELAY_MS)
            }

            pendingRefresh = false
            lastRefreshTime = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
        }
    }

    // Load/refresh data when trigger changes or pending refresh clears
    LaunchedEffect(eventTrigger, pendingRefresh) {
        if (pendingRefresh) return@LaunchedEffect  // Wait for debounce
        val isFirstLoad = knownNodeIds.isEmpty()
        if (isFirstLoad) {
            PlatformLogger.d(TAG, "Loading background graph data...")
        } else {
            PlatformLogger.d(TAG, "Refreshing background graph data...")
        }

        try {
            val graphData = apiClient.getGraphData(
                hours = 24,
                scope = null,  // All scopes
                nodeType = null,
                limit = 200,  // Limited nodes for performance
                includeMetrics = false  // Exclude telemetry
            )

            val currentTime = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
            val newNodeIds = graphData.nodes.map { it.id }.toSet()
            val previousIds = knownNodeIds

            nodes = graphData.nodes.mapIndexed { index, node ->
                // Distribute nodes on cylinder surface
                val theta = (index.toFloat() / graphData.nodes.size) * 2 * PI.toFloat()
                val heightOffset = (index % 5 - 2) * 0.15f  // Vertical spread

                // Check if this is a new node (not in previous data)
                val isNew = !isFirstLoad && node.id !in previousIds
                val birthTime = if (isNew) currentTime else 0L

                if (isNew) {
                    PlatformLogger.d(TAG, "New node detected: ${node.id.take(20)}...")
                }

                BackgroundNode(
                    id = node.id,
                    theta = theta,
                    heightOffset = heightOffset,
                    color = GraphColors.getScopeColor(node.scope),
                    radius = GraphColors.getNodeRadius(node.type) * 1.5f,  // Larger nodes for visibility
                    birthTimeMs = birthTime
                )
            }

            edges = graphData.edges.take(100).mapNotNull { edge ->
                val sourceIndex = graphData.nodes.indexOfFirst { it.id == edge.source }
                val targetIndex = graphData.nodes.indexOfFirst { it.id == edge.target }
                if (sourceIndex >= 0 && targetIndex >= 0) {
                    BackgroundEdge(sourceIndex, targetIndex)
                } else null
            }

            // Update known IDs for next refresh comparison
            knownNodeIds = newNodeIds

            val newCount = if (isFirstLoad) 0 else nodes.count { it.birthTimeMs > 0 }
            PlatformLogger.i(TAG, ">>> DATA LOADED: ${nodes.size} nodes ($newCount new), ${edges.size} edges, setting isLoading=false")
            isLoading = false
        } catch (e: Exception) {
            PlatformLogger.e(TAG, ">>> LOAD FAILED: ${e.message}")
            e.printStackTrace()
            isLoading = false
        }
    }

    // Log render state on every recomposition
    PlatformLogger.d(TAG, ">>> RENDER CHECK: isLoading=$isLoading, nodes=${nodes.size}, canvasSize=${canvasSize.width}x${canvasSize.height}")

    Box(
        modifier = modifier
            .fillMaxSize()
            .onSizeChanged { newSize ->
                PlatformLogger.i(TAG, ">>> CANVAS SIZE CHANGED: ${newSize.width}x${newSize.height}")
                canvasSize = newSize
            }
    ) {
        // Log whether we're rendering or not
        val shouldRender = !isLoading && nodes.isNotEmpty() && canvasSize.width > 0
        PlatformLogger.d(TAG, ">>> SHOULD RENDER: $shouldRender (isLoading=$isLoading, nodes=${nodes.size}, width=${canvasSize.width})")

        if (shouldRender) {
            PlatformLogger.i(TAG, ">>> RENDERING CANVAS with ${nodes.size} nodes")
            Canvas(modifier = Modifier.fillMaxSize()) {
                val centerX = size.width / 2
                val centerY = size.height / 2
                val cylinderRadius = minOf(size.width, size.height) * 0.35f
                val cylinderHeight = size.height * 0.6f

                // Project and draw nodes (with optional spin apart explosion)
                val projectedNodes = nodes.mapIndexed { index, node ->
                    projectNode(
                        node = node,
                        rotationY = rotationY,
                        rotationX = rotationX,
                        centerX = centerX,
                        centerY = centerY,
                        cylinderRadius = cylinderRadius,
                        cylinderHeight = cylinderHeight,
                        spinApartProgress = spinApartProgress,
                        nodeIndex = index,
                        totalNodes = nodes.size
                    )
                }

                // Draw edges first (behind nodes)
                edges.forEach { edge ->
                    if (edge.sourceIndex < projectedNodes.size && edge.targetIndex < projectedNodes.size) {
                        val source = projectedNodes[edge.sourceIndex]
                        val target = projectedNodes[edge.targetIndex]

                        // Only draw if both endpoints are somewhat visible
                        if (source.alpha > 0.1f && target.alpha > 0.1f) {
                            drawBackgroundEdge(
                                source = source,
                                target = target,
                                baseOpacity = baseOpacity
                            )
                        }
                    }
                }

                // Draw nodes sorted by depth (furthest first)
                val currentTimeMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                projectedNodes.sortedByDescending { it.depth }.forEach { projected ->
                    // Calculate birth animation progress (0 = just born, 1 = mature)
                    val birthProgress = if (projected.birthTimeMs > 0) {
                        val age = currentTimeMs - projected.birthTimeMs
                        min(1f, age.toFloat() / BIRTH_ANIMATION_DURATION_MS)
                    } else 1f

                    drawBackgroundNode(
                        projected = projected,
                        baseOpacity = baseOpacity,
                        birthProgress = birthProgress,
                        birthPulse = if (birthProgress < 1f) birthPulse else 0f
                    )
                }
            }
        }

        // Vignette overlay removed for clarity
    }
}

/**
 * Lightweight node data for background rendering.
 */
private data class BackgroundNode(
    val id: String,
    val theta: Float,      // Angle on cylinder (radians)
    val heightOffset: Float,  // Vertical position offset (-1 to 1)
    val color: Color,
    val radius: Float,
    val birthTimeMs: Long = 0L  // When this node first appeared (0 = not new)
)

/**
 * Edge reference for background rendering.
 */
private data class BackgroundEdge(
    val sourceIndex: Int,
    val targetIndex: Int
)

/**
 * Projected node position for drawing.
 */
private data class ProjectedNode(
    val x: Float,
    val y: Float,
    val depth: Float,  // For z-ordering
    val scale: Float,  // Perspective scaling
    val alpha: Float,  // Depth-based transparency
    val color: Color,
    val radius: Float,
    val birthTimeMs: Long = 0L  // For birth animation
)

/**
 * Project a 3D cylinder node to 2D screen coordinates.
 * Includes "spin apart" explosion effect when spinApartProgress > 0.
 */
private fun projectNode(
    node: BackgroundNode,
    rotationY: Float,
    rotationX: Float,
    centerX: Float,
    centerY: Float,
    cylinderRadius: Float,
    cylinderHeight: Float,
    spinApartProgress: Float = 0f,
    nodeIndex: Int = 0,
    totalNodes: Int = 1
): ProjectedNode {
    // Apply Y rotation (horizontal spin)
    val rotatedTheta = node.theta + (rotationY.toDouble() * PI / 180.0).toFloat()

    // 3D position on cylinder
    var x3d = cos(rotatedTheta) * cylinderRadius
    var z3d = sin(rotatedTheta) * cylinderRadius
    var y3d = node.heightOffset * cylinderHeight / 2

    // Spin apart explosion effect
    if (spinApartProgress > 0f) {
        // Phase 1 (0-0.5): Explosion - nodes fly outward
        // Phase 2 (0.5-1.0): Reform - nodes return to cylinder
        val explosionPhase = if (spinApartProgress < 0.5f) {
            // Ease out for explosion
            val t = spinApartProgress * 2f
            t * t  // Quadratic ease in
        } else {
            // Ease in for reform
            val t = (1f - spinApartProgress) * 2f
            t * t  // Quadratic ease in (reversed)
        }

        // Each node gets a unique explosion direction based on its index
        val explosionAngle = (nodeIndex.toFloat() / totalNodes) * 2 * PI.toFloat()
        val explosionRadius = cylinderRadius * 3f * explosionPhase  // Fly out 3x the cylinder radius

        // Add explosion offset to position
        x3d += cos(explosionAngle) * explosionRadius
        z3d += sin(explosionAngle) * explosionRadius
        // Vertical scatter
        y3d += sin(explosionAngle * 2.7f) * cylinderHeight * 0.5f * explosionPhase
    }

    // Apply X rotation (tilt)
    val rotX = rotationX.toDouble() * PI / 180.0
    val y3dRotated = (y3d * cos(rotX) - z3d * sin(rotX)).toFloat()
    val z3dRotated = (y3d * sin(rotX) + z3d * cos(rotX)).toFloat()

    // Perspective projection
    val perspective = 800f
    val scale = perspective / (perspective + z3dRotated)

    val screenX = centerX + x3d * scale
    val screenY = centerY + y3dRotated * scale

    // Alpha: fade during explosion, solid during reform
    val alpha = if (spinApartProgress > 0f && spinApartProgress < 0.5f) {
        1f - spinApartProgress  // Fade out during explosion
    } else if (spinApartProgress >= 0.5f) {
        spinApartProgress  // Fade in during reform
    } else {
        1.0f
    }

    return ProjectedNode(
        x = screenX,
        y = screenY,
        depth = z3dRotated,
        scale = scale,
        alpha = alpha,
        color = node.color,
        radius = node.radius,
        birthTimeMs = node.birthTimeMs
    )
}

/**
 * Draw a background node with depth-based effects and optional birth animation.
 *
 * Birth animation: New nodes scale up from 0 with a pulsing glow effect,
 * then settle into normal background rendering.
 */
private fun DrawScope.drawBackgroundNode(
    projected: ProjectedNode,
    baseOpacity: Float,
    birthProgress: Float = 1f,  // 0 = just born, 1 = fully mature
    birthPulse: Float = 0f      // 0-1 pulse cycle for glow effect
) {
    // Apply birth animation: scale up from 0, extra glow while new
    val birthScale = if (birthProgress < 1f) {
        // Ease-out curve for smooth scale-up
        1f - (1f - birthProgress) * (1f - birthProgress)
    } else 1f

    val effectiveAlpha = projected.alpha * baseOpacity * birthScale
    val scaledRadius = projected.radius * projected.scale * birthScale

    if (scaledRadius < 0.5f) return  // Skip nearly invisible nodes

    // Pulsing outer ring for new nodes (very noticeable)
    if (birthProgress < 1f) {
        val pulseScale = 1f + birthPulse * 0.5f  // Pulse between 1x and 1.5x
        val ringAlpha = (1f - birthProgress) * 0.8f  // Fade out as node matures

        // Bright pulsing ring - use safeAlpha to prevent crash
        drawCircle(
            color = Color.White.safeAlpha(ringAlpha * pulseScale),
            radius = scaledRadius * 2.5f * pulseScale,
            center = Offset(projected.x, projected.y),
            style = Stroke(width = 3f)
        )

        // Inner glow
        drawCircle(
            color = projected.color.safeAlpha(ringAlpha * 0.6f),
            radius = scaledRadius * 1.8f,
            center = Offset(projected.x, projected.y)
        )
    }

    // Main node - solid
    drawCircle(
        color = projected.color.safeAlpha(effectiveAlpha),
        radius = scaledRadius,
        center = Offset(projected.x, projected.y)
    )

    // Bright center highlight for new nodes
    if (birthProgress < 1f) {
        drawCircle(
            color = Color.White.safeAlpha((1f - birthProgress) * 0.9f),
            radius = scaledRadius * 0.4f,
            center = Offset(projected.x, projected.y)
        )
    }
}

/**
 * Draw a background edge with subtle styling.
 */
private fun DrawScope.drawBackgroundEdge(
    source: ProjectedNode,
    target: ProjectedNode,
    baseOpacity: Float
) {
    val avgAlpha = (source.alpha + target.alpha) / 2 * baseOpacity * 0.5f

    val dx = target.x - source.x
    val dy = target.y - source.y
    val dist = sqrt(dx * dx + dy * dy)

    if (dist < 5f) return

    // Slight curve for visual interest
    val midX = (source.x + target.x) / 2
    val midY = (source.y + target.y) / 2
    val perpX = -dy / dist * dist * 0.05f
    val perpY = dx / dist * dist * 0.05f

    val path = Path().apply {
        moveTo(source.x, source.y)
        quadraticBezierTo(midX + perpX, midY + perpY, target.x, target.y)
    }

    drawPath(
        path = path,
        color = Color.White.safeAlpha(avgAlpha),
        style = Stroke(
            width = 1f,
            cap = StrokeCap.Round,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 4f), 0f)
        )
    )
}
