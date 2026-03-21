package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.getScopeColor
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
    externalTilt: Float = 0f,  // External vertical tilt from gestures (degrees)
    spinEnergy: Float = 0f,  // Accumulated spin energy from multiple flicks
    spinEnergyThreshold: Float = 100f,  // Energy threshold to trigger spin apart
    onSpinApartTriggered: () -> Unit = {},  // Callback when spin apart animation starts
    pipelineState: PipelineState = PipelineState(),  // H3ERE pipeline scaffolding state
    isForegroundMode: Boolean = false,  // Thicker rings and more visible scaffolding
    ringColor: Color = Color(0xFFE54D2E),  // Default: tomato9 tertiary color
    colorTheme: ColorTheme = ColorTheme.DEFAULT  // Theme for graph node colors
) {
    // Composable entry - no logging here (recomposes every frame)

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

    // Secondary tilt on X-axis (gentle rocking) + external tilt from gestures
    val autoTiltX by infiniteTransition.animateFloat(
        initialValue = -10f,
        targetValue = 10f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 15000, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "rotationX"
    )
    // Combined tilt: auto + external (gesture) tilt
    val rotationX = autoTiltX + externalTilt

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
                    scope = node.scope,  // Store scope for dynamic theme-based coloring
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
        // shouldRender check - no per-frame logging

        if (shouldRender) {
            // Canvas render - no per-frame logging
            Canvas(modifier = Modifier.fillMaxSize()) {
                val centerX = size.width / 2
                val centerY = size.height / 2
                val cylinderRadius = minOf(size.width, size.height) * 0.35f
                val cylinderHeight = size.height * 0.6f
                val currentTimeMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()

                // Draw H3ERE pipeline scaffolding (behind everything)
                drawPipelineScaffolding(
                    pipelineState = pipelineState,
                    rotationY = rotationY,
                    rotationX = rotationX,
                    centerX = centerX,
                    centerY = centerY,
                    cylinderRadius = cylinderRadius * 1.15f,  // Slightly larger than node cylinder
                    cylinderHeight = cylinderHeight,
                    currentTimeMs = currentTimeMs,
                    baseOpacity = baseOpacity,
                    isForegroundMode = isForegroundMode,
                    ringColor = ringColor  // Use theme's tertiary color
                )

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
                projectedNodes.sortedByDescending { it.depth }.forEach { projected ->
                    // Calculate birth animation progress (0 = just born, 1 = mature)
                    val birthProgress = if (projected.birthTimeMs > 0) {
                        val age = currentTimeMs - projected.birthTimeMs
                        min(1f, age.toFloat() / BIRTH_ANIMATION_DURATION_MS)
                    } else 1f

                    drawBackgroundNode(
                        projected = projected,
                        baseOpacity = baseOpacity,
                        colorTheme = colorTheme,
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
 * Stores scope instead of color to support dynamic theme changes.
 */
private data class BackgroundNode(
    val id: String,
    val theta: Float,      // Angle on cylinder (radians)
    val heightOffset: Float,  // Vertical position offset (-1 to 1)
    val scope: ai.ciris.api.models.GraphScope,  // Store scope for dynamic color lookup
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
    val scope: ai.ciris.api.models.GraphScope,  // Store scope for dynamic color lookup
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
        scope = node.scope,  // Pass scope for dynamic color lookup
        radius = node.radius,
        birthTimeMs = node.birthTimeMs
    )
}

/**
 * Draw a background node with depth-based effects and optional birth animation.
 *
 * Birth animation: New nodes scale up from 0 with a pulsing glow effect,
 * then settle into normal background rendering.
 *
 * @param colorTheme The current color theme for dynamic node coloring
 */
private fun DrawScope.drawBackgroundNode(
    projected: ProjectedNode,
    baseOpacity: Float,
    colorTheme: ColorTheme,
    birthProgress: Float = 1f,  // 0 = just born, 1 = fully mature
    birthPulse: Float = 0f      // 0-1 pulse cycle for glow effect
) {
    // Compute color at render time based on current theme
    val nodeColor = colorTheme.getScopeColor(projected.scope)
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
            color = nodeColor.safeAlpha(ringAlpha * 0.6f),
            radius = scaledRadius * 1.8f,
            center = Offset(projected.x, projected.y)
        )
    }

    // Main node - solid
    drawCircle(
        color = nodeColor.safeAlpha(effectiveAlpha),
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

// =============================================================================
// H3ERE Pipeline Scaffolding Drawing
// =============================================================================

/**
 * Draw H3ERE pipeline scaffolding around the memory cylinder.
 *
 * The scaffolding consists of:
 * 1. Vertical struts running along the cylinder surface
 * 2. Horizontal rings at each pipeline stage height
 * 3. Glow effects on rings when their stage is active
 *
 * Stages are distributed evenly along the cylinder height, with
 * padding at top and bottom. The scaffolding radius is slightly
 * larger than the node cylinder so it wraps around the data.
 *
 * Performance optimizations:
 * - Draw segments individually for proper depth alpha (fixes front/back rendering)
 * - Batch similar alpha ranges when possible
 * - Skip segments below visibility threshold
 */
private fun DrawScope.drawPipelineScaffolding(
    pipelineState: PipelineState,
    rotationY: Float,
    rotationX: Float,
    centerX: Float,
    centerY: Float,
    cylinderRadius: Float,
    cylinderHeight: Float,
    currentTimeMs: Long,
    baseOpacity: Float,
    isForegroundMode: Boolean = false,
    ringColor: Color = Color(0xFFE54D2E)  // Theme tertiary color
) {
    val stages = pipelineState.stages
    if (stages.isEmpty()) return

    // Rings MUCH closer together - tight cluster in the middle
    // Use 30% of cylinder height, centered (35% padding each end)
    val verticalPadding = 0.30f
    val verticalSpan = 1f - 2 * verticalPadding  // 0.40 of total height

    // NO STRUTS - just clean rings around the graph

    // Draw horizontal rings for each pipeline stage
    // REVERSED: Bottom-to-top flow to match graph (new nodes at top)
    // Index 0 (THINK) at bottom, index 6 (ACT) at top
    stages.forEachIndexed { index, stage ->
        // Distribute stages in the middle band - REVERSED direction
        // (1 - verticalPadding) is bottom, verticalPadding is top
        val heightFraction = (1f - verticalPadding) -
            (index.toFloat() / (stages.size - 1).coerceAtLeast(1)) * verticalSpan

        // EGG SHAPE: radius varies with height
        // Maximum at center (0.5), pinched at ends (0.0 and 1.0)
        // Use sine curve for smooth egg profile
        val eggFactor = sin(heightFraction * PI.toFloat())  // 0 at ends, 1 at middle
        val minRadiusFactor = 0.6f  // How pinched the ends are (0.6 = 60% of max)
        val radiusFactor = minRadiusFactor + (1f - minRadiusFactor) * eggFactor
        val ringRadius = cylinderRadius * radiusFactor

        // Calculate glow intensity (1.0 when just activated, fading to 0)
        val glowIntensity = if (stage.activatedAtMs > 0) {
            val elapsed = currentTimeMs - stage.activatedAtMs
            if (elapsed < PipelineStage.GLOW_DURATION_MS) {
                1f - (elapsed.toFloat() / PipelineStage.GLOW_DURATION_MS)
            } else 0f
        } else 0f

        drawScaffoldRing(
            stage = stage,
            heightFraction = heightFraction,
            glowIntensity = glowIntensity,
            rotationY = rotationY,
            rotationX = rotationX,
            centerX = centerX,
            centerY = centerY,
            cylinderRadius = ringRadius,  // Egg-shaped varying radius
            cylinderHeight = cylinderHeight,
            baseOpacity = baseOpacity,
            isForegroundMode = isForegroundMode,
            ringColor = ringColor  // Use theme color
        )
    }
}

/**
 * Draw vertical struts connecting the top and bottom of the scaffolding.
 * These give the scaffolding its cage-like structure.
 */
private fun DrawScope.drawScaffoldStruts(
    strutCount: Int,
    rotationY: Float,
    rotationX: Float,
    centerX: Float,
    centerY: Float,
    cylinderRadius: Float,
    cylinderHeight: Float,
    verticalPadding: Float,
    baseOpacity: Float,
    isForegroundMode: Boolean = false
) {
    val topFraction = verticalPadding
    val bottomFraction = 1f - verticalPadding

    // Foreground mode: thicker, more visible struts
    // Background mode: still visible but subtle
    val strutWidth = if (isForegroundMode) 2.5f else 1.2f  // BG: 1.2px
    val strutAlphaMultiplier = if (isForegroundMode) 0.4f else 0.25f  // BG: 0.25 alpha

    for (i in 0 until strutCount) {
        val theta = (i.toFloat() / strutCount) * 2 * PI.toFloat()

        val top = projectScaffoldPoint(
            theta, topFraction, rotationY, rotationX,
            centerX, centerY, cylinderRadius, cylinderHeight
        )
        val bottom = projectScaffoldPoint(
            theta, bottomFraction, rotationY, rotationX,
            centerX, centerY, cylinderRadius, cylinderHeight
        )

        // Only draw struts on the visible side (or dimmed on back)
        val avgAlpha = (top.alpha + bottom.alpha) / 2 * baseOpacity * strutAlphaMultiplier

        if (avgAlpha > 0.01f) {
            drawLine(
                color = Color.White.safeAlpha(avgAlpha),
                start = Offset(top.screenX, top.screenY),
                end = Offset(bottom.screenX, bottom.screenY),
                strokeWidth = strutWidth
            )
        }
    }
}

/**
 * Draw a single horizontal pipeline ring at the given height.
 * When glowIntensity > 0, the ring lights up in the stage's color.
 *
 * FIX: Draw segments individually with per-segment alpha to properly
 * show depth (back-side dimmer than front-side). Using a single path
 * with constant alpha breaks the front/back depth cue.
 */
private fun DrawScope.drawScaffoldRing(
    stage: PipelineStage,
    heightFraction: Float,
    glowIntensity: Float,
    rotationY: Float,
    rotationX: Float,
    centerX: Float,
    centerY: Float,
    cylinderRadius: Float,
    cylinderHeight: Float,
    baseOpacity: Float,
    isForegroundMode: Boolean = false,
    ringColor: Color = Color(0xFFE54D2E)  // Theme tertiary color
) {
    // Sample points around the ring circumference
    val segments = 48  // Smooth ring

    // Foreground mode: much thicker, more visible rings
    // Background mode: still visible but more subtle
    val thicknessMultiplier = if (isForegroundMode) 3.5f else 2f  // Thicker rings
    val alphaBoost = if (isForegroundMode) 0.35f else 0.2f  // Brighter

    // Determine ring color and intensity
    // Use theme's tertiary color for inactive, stage color when active
    val isActive = glowIntensity > 0f
    val effectiveRingColor = if (isActive) stage.color else ringColor
    val baseRingAlpha = if (isActive) {
        0.5f + glowIntensity * 0.5f + alphaBoost  // Active: very bright
    } else {
        0.4f + alphaBoost  // Inactive: clearly visible (was 0.22)
    }
    val ringWidth = (if (isActive) {
        3f + glowIntensity * 3f  // Active: 3 to 6px
    } else {
        2.5f  // Inactive: nice thick baseline
    }) * thicknessMultiplier

    // Draw ring as individual line segments with per-segment depth alpha
    // This fixes the depth rendering issue where back-side segments
    // were drawn at the same opacity as front-side segments
    for (i in 0 until segments) {
        val theta1 = (i.toFloat() / segments) * 2 * PI.toFloat()
        val theta2 = ((i + 1).toFloat() / segments) * 2 * PI.toFloat()

        val p1 = projectScaffoldPoint(
            theta1, heightFraction, rotationY, rotationX,
            centerX, centerY, cylinderRadius, cylinderHeight
        )
        val p2 = projectScaffoldPoint(
            theta2, heightFraction, rotationY, rotationX,
            centerX, centerY, cylinderRadius, cylinderHeight
        )

        // Per-segment alpha based on depth (front brighter, back dimmer)
        val segAlpha = ((p1.alpha + p2.alpha) / 2 * baseOpacity * baseRingAlpha).coerceIn(0f, 1f)

        if (segAlpha > 0.01f) {
            drawLine(
                color = effectiveRingColor.safeAlpha(segAlpha),
                start = Offset(p1.screenX, p1.screenY),
                end = Offset(p2.screenX, p2.screenY),
                strokeWidth = ringWidth,
                cap = StrokeCap.Round
            )
        }
    }

    // Draw outer glow for active rings (larger, more transparent)
    // Also use per-segment alpha for proper depth
    if (isActive && glowIntensity > 0.1f) {
        val glowWidth = (ringWidth + 6f) * thicknessMultiplier

        for (i in 0 until segments) {
            val theta1 = (i.toFloat() / segments) * 2 * PI.toFloat()
            val theta2 = ((i + 1).toFloat() / segments) * 2 * PI.toFloat()

            val p1 = projectScaffoldPoint(
                theta1, heightFraction, rotationY, rotationX,
                centerX, centerY, cylinderRadius, cylinderHeight
            )
            val p2 = projectScaffoldPoint(
                theta2, heightFraction, rotationY, rotationX,
                centerX, centerY, cylinderRadius, cylinderHeight
            )

            val segAlpha = ((p1.alpha + p2.alpha) / 2 * baseOpacity * glowIntensity * 0.3f)
                .coerceIn(0f, 1f)

            if (segAlpha > 0.02f) {
                drawLine(
                    color = stage.color.safeAlpha(segAlpha),
                    start = Offset(p1.screenX, p1.screenY),
                    end = Offset(p2.screenX, p2.screenY),
                    strokeWidth = glowWidth,
                    cap = StrokeCap.Round
                )
            }
        }
    }

    // Draw label ON the cylinder surface, ABOVE the ring (in the space between rings)
    // Label rotates WITH the cylinder like a decal
    val labelAlpha = if (isActive) {
        0.95f + glowIntensity * 0.05f  // Active: very bright
    } else {
        0.75f  // Inactive: clearly visible
    }
    val labelScale = if (isActive) {
        1f + glowIntensity * 0.3f  // Grow when active
    } else {
        1f
    }
    val labelColor = if (isActive) stage.color else ringColor

    // Position label ABOVE the ring on cylinder surface (smaller heightFraction = higher)
    val labelHeightOffset = 0.04f  // Space above ring
    val labelHeightFraction = (heightFraction - labelHeightOffset).coerceIn(0.02f, 0.98f)

    // Project label ON the cylinder surface at front-facing position (theta = 0)
    // Uses same radius as ring so it appears on the cylinder surface
    val labelPoint = projectScaffoldPoint(
        0f, labelHeightFraction, rotationY, rotationX,
        centerX, centerY, cylinderRadius * 1.05f, cylinderHeight  // Slightly outside ring
    )

    // Always draw label - visible through the cylinder
    // Use minimum alpha so back-side labels are dimmer but still readable
    val minLabelAlpha = 0.4f  // Minimum visibility even on back side
    val textAlpha = ((labelPoint.alpha * 0.6f + minLabelAlpha) * baseOpacity * labelAlpha).coerceIn(0f, 1f)
    val charSize = (24f + (if (isForegroundMode) 12f else 0f)) * labelScale  // 3x larger
    val strokeWidth = (3f + (if (isForegroundMode) 2f else 0f)) * labelScale

    // Draw label using line-based block letters
    drawBlockText(
        text = stage.label,
        x = labelPoint.screenX,
        y = labelPoint.screenY,
        charSize = charSize,
        color = labelColor.safeAlpha(textAlpha),
        strokeWidth = strokeWidth
    )
}

// =============================================================================
// Line-Based Block Text Rendering (Platform Agnostic)
// =============================================================================

/**
 * Draw text using simple line segments - works on all platforms.
 * Each character is rendered as a set of line strokes.
 */
private fun DrawScope.drawBlockText(
    text: String,
    x: Float,
    y: Float,
    charSize: Float,
    color: Color,
    strokeWidth: Float
) {
    val charWidth = charSize * 0.8f
    val spacing = charSize * 0.3f
    val totalWidth = text.length * (charWidth + spacing) - spacing
    var currentX = x - totalWidth / 2  // Center the text

    for (char in text.uppercase()) {
        drawBlockChar(char, currentX, y, charSize, charWidth, color, strokeWidth)
        currentX += charWidth + spacing
    }
}

/**
 * Draw a single character using line segments.
 * Simple block-letter font optimized for clarity at small sizes.
 */
private fun DrawScope.drawBlockChar(
    char: Char,
    x: Float,
    y: Float,
    h: Float,  // Height
    w: Float,  // Width
    color: Color,
    sw: Float  // Stroke width
) {
    val t = y - h / 2  // Top
    val b = y + h / 2  // Bottom
    val m = y          // Middle
    val l = x          // Left
    val r = x + w      // Right
    val c = x + w / 2  // Center

    // Helper to draw a line
    fun line(x1: Float, y1: Float, x2: Float, y2: Float) {
        drawLine(color, Offset(x1, y1), Offset(x2, y2), sw, StrokeCap.Round)
    }

    when (char) {
        'A' -> { line(l, b, c, t); line(c, t, r, b); line(l + w*0.2f, m, r - w*0.2f, m) }
        'C' -> { line(r, t, l, t); line(l, t, l, b); line(l, b, r, b) }
        'D' -> { line(l, t, l, b); line(l, t, c, t); line(c, t, r, m); line(r, m, c, b); line(c, b, l, b) }
        'E' -> { line(r, t, l, t); line(l, t, l, b); line(l, b, r, b); line(l, m, c, m) }
        'H' -> { line(l, t, l, b); line(r, t, r, b); line(l, m, r, m) }
        'I' -> { line(l, t, r, t); line(c, t, c, b); line(l, b, r, b) }
        'K' -> { line(l, t, l, b); line(r, t, l, m); line(l, m, r, b) }
        'L' -> { line(l, t, l, b); line(l, b, r, b) }
        'M' -> { line(l, b, l, t); line(l, t, c, m); line(c, m, r, t); line(r, t, r, b) }
        'N' -> { line(l, b, l, t); line(l, t, r, b); line(r, b, r, t) }
        'O' -> { line(l, t, r, t); line(r, t, r, b); line(r, b, l, b); line(l, b, l, t) }
        'S' -> { line(r, t, l, t); line(l, t, l, m); line(l, m, r, m); line(r, m, r, b); line(r, b, l, b) }
        'T' -> { line(l, t, r, t); line(c, t, c, b) }
        'X' -> { line(l, t, r, b); line(r, t, l, b) }
        // Numbers and special chars as needed
        else -> { /* Skip unknown chars */ }
    }
}
