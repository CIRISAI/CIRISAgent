package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.math.sqrt
import kotlin.math.max
import kotlin.math.min
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.PI
import kotlin.random.Random

/**
 * Force-directed graph layout simulation.
 *
 * Implements a simplified D3-style force simulation with:
 * - Repulsion forces between all nodes (Coulomb-like)
 * - Attraction forces along edges (spring-like)
 * - Center gravity pull
 * - Velocity damping
 * - Alpha cooling (simulation stops when stable)
 */
class ForceSimulation(
    private val repulsionStrength: Float = -400f,
    private val linkDistance: Float = 120f,
    private val linkStrength: Float = 0.3f,
    private val centerStrength: Float = 0.05f,
    private val damping: Float = 0.9f,
    private val alphaDecay: Float = 0.0228f,
    private val alphaMin: Float = 0.001f,
    private val alphaTarget: Float = 0f
) {
    var alpha: Float = 1f
        private set

    private var centerX: Float = 0f
    private var centerY: Float = 0f

    /**
     * Initialize node positions randomly around center.
     */
    fun initializePositions(
        nodes: List<GraphNodeDisplay>,
        width: Float,
        height: Float
    ) {
        centerX = width / 2
        centerY = height / 2

        val radius = min(width, height) * 0.3f

        nodes.forEachIndexed { index, node ->
            if (!node.fixed) {
                // Distribute nodes in a circle with some randomness
                val angle = (index.toFloat() / nodes.size) * 2f * PI.toFloat()
                val r = radius * (0.5f + Random.nextFloat() * 0.5f)
                node.x = centerX + r * cos(angle)
                node.y = centerY + r * sin(angle)
                node.vx = 0f
                node.vy = 0f
            }
        }

        alpha = 1f
    }

    /**
     * Run one tick of the simulation.
     * Returns true if simulation is still active (alpha > alphaMin).
     */
    fun tick(
        nodes: List<GraphNodeDisplay>,
        edges: List<GraphEdgeDisplay>,
        nodeMap: Map<String, GraphNodeDisplay>
    ): Boolean {
        if (alpha < alphaMin) return false

        // Apply forces
        applyRepulsionForces(nodes)
        applyLinkForces(edges, nodeMap)
        applyCenterForce(nodes)

        // Update positions
        nodes.forEach { node ->
            if (!node.fixed) {
                // Apply velocity with damping
                node.vx *= damping
                node.vy *= damping

                // Update position
                node.x += node.vx * alpha
                node.y += node.vy * alpha
            }
        }

        // Cool down
        alpha += (alphaTarget - alpha) * alphaDecay
        if (alpha < alphaMin) alpha = 0f

        return alpha > alphaMin
    }

    /**
     * Apply repulsion forces between all pairs of nodes.
     * Uses Barnes-Hut approximation for performance with many nodes.
     */
    private fun applyRepulsionForces(nodes: List<GraphNodeDisplay>) {
        // Simple O(n^2) implementation for now
        // For large graphs, implement quad-tree Barnes-Hut
        for (i in nodes.indices) {
            val nodeA = nodes[i]
            if (nodeA.fixed) continue

            for (j in (i + 1) until nodes.size) {
                val nodeB = nodes[j]

                var dx = nodeB.x - nodeA.x
                var dy = nodeB.y - nodeA.y
                var distSq = dx * dx + dy * dy

                // Minimum distance to avoid extreme forces
                if (distSq < 1f) {
                    dx = (Random.nextFloat() - 0.5f) * 2f
                    dy = (Random.nextFloat() - 0.5f) * 2f
                    distSq = dx * dx + dy * dy
                }

                val dist = sqrt(distSq)
                val force = repulsionStrength / distSq

                val fx = (dx / dist) * force
                val fy = (dy / dist) * force

                nodeA.vx -= fx
                nodeA.vy -= fy

                if (!nodeB.fixed) {
                    nodeB.vx += fx
                    nodeB.vy += fy
                }
            }
        }
    }

    /**
     * Apply spring forces along edges.
     */
    private fun applyLinkForces(
        edges: List<GraphEdgeDisplay>,
        nodeMap: Map<String, GraphNodeDisplay>
    ) {
        edges.forEach { edge ->
            val source = nodeMap[edge.source] ?: return@forEach
            val target = nodeMap[edge.target] ?: return@forEach

            var dx = target.x - source.x
            var dy = target.y - source.y
            var dist = sqrt(dx * dx + dy * dy)

            if (dist < 0.001f) {
                dx = (Random.nextFloat() - 0.5f) * 2f
                dy = (Random.nextFloat() - 0.5f) * 2f
                dist = sqrt(dx * dx + dy * dy)
            }

            // Spring force: F = k * (distance - restLength)
            val targetDist = linkDistance * edge.weight
            val force = (dist - targetDist) * linkStrength

            val fx = (dx / dist) * force
            val fy = (dy / dist) * force

            if (!source.fixed) {
                source.vx += fx
                source.vy += fy
            }
            if (!target.fixed) {
                target.vx -= fx
                target.vy -= fy
            }
        }
    }

    /**
     * Apply gentle pull towards center to prevent nodes from flying off.
     */
    private fun applyCenterForce(nodes: List<GraphNodeDisplay>) {
        nodes.forEach { node ->
            if (!node.fixed) {
                node.vx += (centerX - node.x) * centerStrength
                node.vy += (centerY - node.y) * centerStrength
            }
        }
    }

    /**
     * Restart the simulation with full alpha.
     */
    fun restart() {
        alpha = 1f
    }

    /**
     * Stop the simulation immediately.
     */
    fun stop() {
        alpha = 0f
    }

    /**
     * Check if simulation is active.
     */
    fun isActive(): Boolean = alpha > alphaMin

    /**
     * "Reheat" the simulation - increase alpha when user interacts.
     */
    fun reheat(amount: Float = 0.3f) {
        alpha = max(alpha, min(1f, alpha + amount))
    }

    companion object {
        /**
         * Apply timeline layout (chronological left-to-right).
         */
        fun applyTimelineLayout(
            nodes: List<GraphNodeDisplay>,
            width: Float,
            height: Float
        ) {
            if (nodes.isEmpty()) return

            // Sort by creation time if available, otherwise by ID
            val sorted = nodes.sortedBy { it.originalNode?.updatedAt?.toString() ?: it.id }

            val padding = 60f
            val availableWidth = width - 2 * padding
            val step = if (sorted.size > 1) availableWidth / (sorted.size - 1) else 0f

            sorted.forEachIndexed { index, node ->
                node.x = padding + index * step
                node.y = height / 2 + (Random.nextFloat() - 0.5f) * 100f
                node.vx = 0f
                node.vy = 0f
            }
        }

        /**
         * Apply hierarchy layout (type-based vertical layers).
         */
        fun applyHierarchyLayout(
            nodes: List<GraphNodeDisplay>,
            width: Float,
            height: Float
        ) {
            if (nodes.isEmpty()) return

            // Group by type
            val byType = nodes.groupBy { it.type }
            val typeCount = byType.size
            val padding = 60f
            val layerHeight = (height - 2 * padding) / max(1, typeCount)

            var layerIndex = 0
            byType.forEach { (_, typeNodes) ->
                val y = padding + layerIndex * layerHeight + layerHeight / 2
                val nodeStep = (width - 2 * padding) / max(1, typeNodes.size)

                typeNodes.forEachIndexed { i, node ->
                    node.x = padding + i * nodeStep + nodeStep / 2
                    node.y = y
                    node.vx = 0f
                    node.vy = 0f
                }
                layerIndex++
            }
        }

        /**
         * Apply circular layout.
         */
        fun applyCircularLayout(
            nodes: List<GraphNodeDisplay>,
            width: Float,
            height: Float
        ) {
            if (nodes.isEmpty()) return

            val centerX = width / 2
            val centerY = height / 2
            val radius = min(width, height) * 0.35f

            nodes.forEachIndexed { index, node ->
                val angle = (index.toFloat() / nodes.size) * 2f * PI.toFloat()
                node.x = centerX + radius * cos(angle)
                node.y = centerY + radius * sin(angle)
                node.vx = 0f
                node.vy = 0f
            }
        }
    }
}
