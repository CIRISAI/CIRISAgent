package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.mobile.shared.platform.PlatformLogger
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.max
import kotlin.math.min

private const val TAG = "CylinderLayout"

/**
 * 3D Cylinder Layout for memory graph visualization.
 *
 * Organizes nodes into TEMPORAL RINGS where each ring represents a 6-hour period.
 * The cylinder forms organically over time as more periods accumulate.
 *
 * Structure:
 * - Each ring = one 6-hour time bucket
 * - Rings stack vertically (oldest at bottom, newest at top)
 * - Nodes within a ring are distributed around the circumference
 * - Only rings with nodes are rendered
 *
 * Visual cues:
 * - Nodes "behind" the cylinder appear smaller (perspective)
 * - Nodes "behind" have reduced alpha (atmospheric perspective)
 * - Ring outlines show time period boundaries
 */
class CylinderLayout(
    /** Focal length for perspective projection. Larger = less distortion. */
    private val focalLength: Float = 800f,
    /** How much nodes shrink with depth (0 = none, 1 = full) */
    private val depthScaleFactor: Float = 0.4f,
    /** How much alpha reduces with depth (0 = none, 1 = full) */
    private val depthAlphaFactor: Float = 0.5f,
    /** Hours per ring (default 6 = consolidation period) */
    private val hoursPerRing: Int = 6
) {
    /** Current Y-axis rotation in radians */
    var rotationY: Float = 0f
        private set

    /** Rotation velocity for momentum */
    private var rotationVelocity: Float = 0f

    /** Damping factor for rotation momentum */
    private val rotationDamping: Float = 0.95f

    /** Minimum velocity before stopping */
    private val minVelocity: Float = 0.001f

    /** Time rings with their Y positions (for rendering ring outlines) */
    var timeRings: List<TimeRing> = emptyList()
        private set

    /**
     * Represents a 6-hour time ring on the cylinder.
     * Horizontal layout: each ring is a vertical slice at a specific X position.
     */
    data class TimeRing(
        val periodStart: Long,      // Epoch millis of period start
        val periodEnd: Long,        // Epoch millis of period end
        val label: String,          // Human-readable label (e.g., "Mar 15, 6AM-12PM")
        val xPosition: Float = 0f,  // X position for horizontal layout
        val yPosition: Float,       // Y center position
        val nodeCount: Int          // Number of nodes in this ring
    )

    /**
     * Projected 2D point with depth info.
     */
    data class ProjectedPoint(
        val screenX: Float,
        val screenY: Float,
        val depth: Float,           // Z value for sorting (higher = further)
        val scale: Float,           // Size scale based on depth (0-1)
        val alpha: Float,           // Alpha based on depth (0-1)
        val isBehind: Boolean       // True if behind the cylinder center
    )

    /**
     * Apply temporal ring layout to nodes.
     *
     * Groups nodes by 6-hour periods, creating one ring per period.
     * Only periods with nodes get rings.
     *
     * @param nodes The nodes to position
     * @param width Canvas width
     * @param height Canvas height
     * @param groupByType Ignored for temporal layout
     */
    fun applyLayout(
        nodes: List<GraphNodeDisplay>,
        width: Float,
        height: Float,
        groupByType: Boolean = false
    ) {
        if (nodes.isEmpty()) {
            timeRings = emptyList()
            return
        }

        val centerX = width / 2
        val centerY = height / 2
        val radius = min(width, height) * 0.15f  // Smaller radius for tighter rings
        val cylinderHeight = height * 0.6f

        applyTemporalRingLayout(nodes, centerX, centerY, radius, cylinderHeight)
    }

    /**
     * Group nodes by 6-hour time buckets and arrange as HORIZONTAL rings.
     * Oldest ring on LEFT, newest on RIGHT.
     */
    private fun applyTemporalRingLayout(
        nodes: List<GraphNodeDisplay>,
        centerX: Float,
        centerY: Float,
        radius: Float,
        cylinderHeight: Float
    ) {
        // Parse timestamps and group by 6-hour period
        val periodMs = hoursPerRing * 60 * 60 * 1000L

        val nodesWithTime = nodes.mapNotNull { node ->
            // updatedAt is already kotlinx.datetime.Instant
            val timestamp = node.originalNode?.updatedAt?.toEpochMilliseconds()
            if (timestamp != null) {
                node to timestamp
            } else null
        }

        if (nodesWithTime.isEmpty()) {
            // Fallback: distribute evenly if no timestamps
            applyFallbackLayout(nodes, centerX, centerY, radius, cylinderHeight)
            return
        }

        // Find time range
        val minTime = nodesWithTime.minOf { it.second }
        val maxTime = nodesWithTime.maxOf { it.second }

        // Group nodes by period
        val buckets = mutableMapOf<Long, MutableList<GraphNodeDisplay>>()
        nodesWithTime.forEach { (node, time) ->
            val bucketStart = (time / periodMs) * periodMs
            buckets.getOrPut(bucketStart) { mutableListOf() }.add(node)
        }

        // Only keep non-empty buckets, sorted by time (oldest first)
        val sortedBuckets = buckets.entries
            .filter { it.value.isNotEmpty() }
            .sortedBy { it.key }

        if (sortedBuckets.isEmpty()) {
            timeRings = emptyList()
            return
        }

        // HORIZONTAL layout: oldest on LEFT, newest on RIGHT
        // Scale rings to fill screen width with padding
        val ringCount = sortedBuckets.size
        val screenWidth = centerX * 2
        val edgePadding = 40f     // Padding from screen edges
        val availableWidth = screenWidth - (edgePadding * 2)
        val ringSpacing = availableWidth / max(1, ringCount)
        val xStart = edgePadding + ringSpacing / 2  // Start from left edge

        val rings = mutableListOf<TimeRing>()

        sortedBuckets.forEachIndexed { ringIndex, (periodStart, ringNodes) ->
            val ringX = xStart + ringIndex * ringSpacing  // Move right for newer
            val periodEnd = periodStart + periodMs

            // Distribute nodes around this ring (vertical circle)
            val angleStep = 2f * PI.toFloat() / max(1, ringNodes.size)
            val angleOffset = (ringIndex * 0.3f) // Slight stagger for visual interest

            ringNodes.forEachIndexed { nodeIndex, node ->
                val theta = angleOffset + nodeIndex * angleStep

                node.cylinderTheta = theta
                node.cylinderX = ringX  // Store X position for horizontal layout
                node.cylinderY = centerY  // Base Y is center
                node.cylinderRadius = radius

                node.x = ringX
                node.y = centerY
            }

            // Create ring metadata with X position
            rings.add(TimeRing(
                periodStart = periodStart,
                periodEnd = periodEnd,
                label = formatPeriodLabel(periodStart, periodEnd),
                xPosition = ringX,
                yPosition = centerY,
                nodeCount = ringNodes.size
            ))
        }

        timeRings = rings
    }

    /**
     * Fallback layout when no timestamps available.
     */
    private fun applyFallbackLayout(
        nodes: List<GraphNodeDisplay>,
        centerX: Float,
        centerY: Float,
        radius: Float,
        cylinderHeight: Float
    ) {
        // Single ring with all nodes at center
        val angleStep = 2f * PI.toFloat() / max(1, nodes.size)

        nodes.forEachIndexed { index, node ->
            val theta = index * angleStep

            node.cylinderTheta = theta
            node.cylinderX = centerX
            node.cylinderY = centerY
            node.cylinderRadius = radius

            node.x = centerX
            node.y = centerY
        }

        timeRings = listOf(TimeRing(
            periodStart = 0,
            periodEnd = 0,
            label = "All Nodes",
            xPosition = centerX,
            yPosition = centerY,
            nodeCount = nodes.size
        ))
    }

    /**
     * Format period label for display.
     */
    private fun formatPeriodLabel(startMs: Long, endMs: Long): String {
        return try {
            // Calculate hour from epoch millis
            val startHour = ((startMs / (60 * 60 * 1000)) % 24).toInt()
            val endHour = (startHour + hoursPerRing) % 24

            // Simple format: "HH:00 - HH:00"
            "${startHour.toString().padStart(2, '0')}:00 - ${endHour.toString().padStart(2, '0')}:00"
        } catch (e: Exception) {
            "Period"
        }
    }

    /**
     * Project all nodes from 3D cylinder space to 2D screen space.
     * Call this each frame before rendering.
     *
     * @param nodes The nodes to project
     * @param centerX Screen center X
     * @param centerY Screen center Y
     * @return Nodes sorted by depth (furthest first for correct z-order)
     */
    fun projectNodes(
        nodes: List<GraphNodeDisplay>,
        centerX: Float,
        centerY: Float
    ): List<Pair<GraphNodeDisplay, ProjectedPoint>> {
        return nodes.map { node ->
            val projected = projectNode(node, centerX, centerY)
            node to projected
        }.sortedByDescending { it.second.depth } // Draw furthest first
    }

    /**
     * Project a single node to screen coordinates.
     * HORIZONTAL cylinder: rings are vertical slices, rotation spins around X-axis.
     */
    fun projectNode(
        node: GraphNodeDisplay,
        centerX: Float,
        centerY: Float
    ): ProjectedPoint {
        // Apply rotation to get 3D position
        // For horizontal cylinder, theta rotates in YZ plane (vertical circle)
        val rotatedTheta = node.cylinderTheta + rotationY
        val radius = node.cylinderRadius

        // 3D coordinates for HORIZONTAL cylinder:
        // X = ring position (left to right)
        // Y = vertical position on ring (up/down)
        // Z = depth (towards/away from viewer)
        val y3d = radius * sin(rotatedTheta)  // Vertical displacement
        val z3d = radius * cos(rotatedTheta)  // Depth
        val x3d = node.cylinderX - centerX    // Horizontal ring position

        // Perspective projection
        val perspectiveFactor = focalLength / (focalLength + z3d)
        val screenX = centerX + x3d * perspectiveFactor
        val screenY = centerY + y3d * perspectiveFactor

        // Depth-based visual adjustments
        val normalizedDepth = (radius - z3d) / (2 * radius)

        val scale = 1f - (normalizedDepth * depthScaleFactor)
        val alpha = 1f - (normalizedDepth * depthAlphaFactor)

        return ProjectedPoint(
            screenX = screenX,
            screenY = screenY,
            depth = z3d,
            scale = scale.coerceIn(0.3f, 1f),
            alpha = alpha.coerceIn(0.2f, 1f),
            isBehind = z3d < 0
        )
    }

    /**
     * Rotate the cylinder by delta radians.
     * Call this from drag gesture handler.
     */
    fun rotate(deltaRadians: Float) {
        rotationY += deltaRadians
        rotationVelocity = deltaRadians
    }

    /**
     * Set rotation velocity for momentum after drag ends.
     */
    fun setVelocity(velocity: Float) {
        rotationVelocity = velocity
    }

    /**
     * Tick the momentum physics. Call each frame.
     * @return true if still animating, false if stopped
     */
    fun tickMomentum(): Boolean {
        if (kotlin.math.abs(rotationVelocity) < minVelocity) {
            rotationVelocity = 0f
            return false
        }

        rotationY += rotationVelocity
        rotationVelocity *= rotationDamping

        // Normalize rotation to 0-2PI
        while (rotationY > 2 * PI.toFloat()) rotationY -= 2 * PI.toFloat()
        while (rotationY < 0) rotationY += 2 * PI.toFloat()

        return true
    }

    /**
     * Set rotation directly (e.g., for auto-rotation animation).
     */
    fun setRotation(radians: Float) {
        rotationY = radians
        rotationVelocity = 0f
    }

    /**
     * Reset rotation to initial position.
     */
    fun reset() {
        rotationY = 0f
        rotationVelocity = 0f
    }

    /**
     * Check if momentum animation is active.
     */
    fun isAnimating(): Boolean = kotlin.math.abs(rotationVelocity) >= minVelocity

    companion object {
        /** Auto-rotation speed for idle animation (radians per tick) */
        const val AUTO_ROTATION_SPEED = 0.005f

        /** Slow reveal rotation for initial load */
        const val REVEAL_ROTATION_SPEED = 0.02f
    }
}

// Extension properties for GraphNodeDisplay to store cylinder coordinates
// These are mutable and updated by the layout

var GraphNodeDisplay.cylinderTheta: Float
    get() = extra["cylinderTheta"] as? Float ?: 0f
    set(value) { extra["cylinderTheta"] = value }

var GraphNodeDisplay.cylinderX: Float
    get() = extra["cylinderX"] as? Float ?: 0f
    set(value) { extra["cylinderX"] = value }

var GraphNodeDisplay.cylinderY: Float
    get() = extra["cylinderY"] as? Float ?: 0f
    set(value) { extra["cylinderY"] = value }

var GraphNodeDisplay.cylinderRadius: Float
    get() = extra["cylinderRadius"] as? Float ?: 100f
    set(value) { extra["cylinderRadius"] = value }
