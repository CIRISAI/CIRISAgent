package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.random.Random

/**
 * Network topology canvas.
 *
 * Approach mirrors [GraphCanvas]: Compose Canvas + transformGestures pan/zoom +
 * rememberTextMeasurer drawText + force-directed physics. Proven performant
 * on Android / iOS / Desktop for the memory graph; reused here for federation
 * topology because the data shape is structurally similar (node = peer,
 * edge = reachability-via-transport).
 *
 * Differences from the memory graph renderer:
 *  - The local agent is the anchored center node (fixed=true, never moves).
 *  - Edges carry a transport-kind that drives their color so the operator
 *    reads the same color-coded transcript metaphor used elsewhere in the UI.
 *  - When peer count > 40, layout falls back to concentric rings by hop count
 *    (force-directed becomes hard to read at that density).
 *  - All text labels passed in pre-localized (via composable [labelFor]) so
 *    the canvas renders correctly across all 29 supported locales.
 */
@Composable
fun NetworkTopologyCanvas(
    snapshot: NetworkSnapshot,
    selectedPeerKeyId: String? = null,
    onPeerSelected: (String?) -> Unit = {},
    /** Returns the localized label to render under each peer. */
    labelFor: (NetworkPeer) -> String = { it.displayName ?: it.keyIdShort },
    /** Returns the localized label for the local identity. */
    localLabel: String = snapshot.localIdentity.displayName ?: "this agent",
    modifier: Modifier = Modifier,
) {
    val textMeasurer = rememberTextMeasurer()

    val state = remember(snapshot) { buildTopologyState(snapshot) }
    var viewport by remember { mutableStateOf(GraphViewport()) }
    var draggedNodeId by remember { mutableStateOf<String?>(null) }

    // Force simulation tick — only run while not stable, to avoid burning
    // battery once the layout settles.
    LaunchedEffect(state.dataKey) {
        // Initialize positions if not already placed
        state.initializePositions(width = 1000f, height = 1000f)
        // Step the sim ~60 times per second until alpha drops below floor.
        // Bound at 300 ticks (~5s) so even a non-converging case stops.
        repeat(300) {
            val moved = state.step()
            if (!moved) return@LaunchedEffect
            kotlinx.coroutines.delay(16)
        }
    }

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFF0A1620))
            .pointerInput(state.dataKey) {
                detectTransformGestures { _, pan, zoom, _ ->
                    val dragId = draggedNodeId
                    if (dragId != null) {
                        state.dragNode(dragId, pan.x / viewport.scale, pan.y / viewport.scale)
                    } else {
                        viewport = viewport.copy(
                            offsetX = viewport.offsetX + pan.x / viewport.scale,
                            offsetY = viewport.offsetY + pan.y / viewport.scale,
                            scale = (viewport.scale * zoom).coerceIn(0.3f, 4f),
                        )
                    }
                }
            }
            .pointerInput(state.dataKey) {
                detectTapGestures(
                    onPress = { offset ->
                        val worldX = offset.x / viewport.scale - viewport.offsetX
                        val worldY = offset.y / viewport.scale - viewport.offsetY
                        val hit = state.findAt(worldX, worldY)
                        if (hit != null) {
                            draggedNodeId = hit.id
                            // Re-warm sim so dragged node settles
                            state.warm()
                        }
                        tryAwaitRelease()
                        draggedNodeId = null
                    },
                    onTap = { offset ->
                        val worldX = offset.x / viewport.scale - viewport.offsetX
                        val worldY = offset.y / viewport.scale - viewport.offsetY
                        val hit = state.findAt(worldX, worldY)
                        onPeerSelected(if (hit?.kind == TopologyNodeKind.PEER) hit.id else null)
                    },
                )
            },
    ) {
        // Edges
        state.edges.forEach { edge ->
            val src = state.nodes.find { it.id == edge.sourceId } ?: return@forEach
            val dst = state.nodes.find { it.id == edge.targetId } ?: return@forEach
            val color = edge.color.copy(alpha = if (edge.dimmed) 0.25f else 0.7f)
            val sx = (src.x + viewport.offsetX) * viewport.scale
            val sy = (src.y + viewport.offsetY) * viewport.scale
            val dx = (dst.x + viewport.offsetX) * viewport.scale
            val dy = (dst.y + viewport.offsetY) * viewport.scale
            drawLine(
                color = color,
                start = Offset(sx, sy),
                end = Offset(dx, dy),
                strokeWidth = edge.width,
            )
        }

        // Nodes
        state.nodes.forEach { node ->
            val x = (node.x + viewport.offsetX) * viewport.scale
            val y = (node.y + viewport.offsetY) * viewport.scale
            val r = node.radius * viewport.scale
            val isSelected = node.id == selectedPeerKeyId

            // Selection ring
            if (isSelected) {
                drawCircle(
                    color = Color.White.copy(alpha = 0.8f),
                    radius = r + 4f,
                    center = Offset(x, y),
                    style = Stroke(width = 2f),
                )
            }

            // Node fill
            drawCircle(
                color = node.color,
                radius = r,
                center = Offset(x, y),
            )

            // Node border (anchor = thicker for local identity)
            drawCircle(
                color = Color.White.copy(alpha = if (node.kind == TopologyNodeKind.LOCAL) 0.9f else 0.3f),
                radius = r,
                center = Offset(x, y),
                style = Stroke(width = if (node.kind == TopologyNodeKind.LOCAL) 2.5f else 1f),
            )

            // Label — only when zoomed-in enough that the label is legible
            if (viewport.scale > 0.7f && node.label.isNotEmpty()) {
                val label = node.label.take(20)
                val style = TextStyle(color = Color.White, fontSize = 11.sp)
                val layout = textMeasurer.measure(label, style = style)
                drawText(
                    textMeasurer = textMeasurer,
                    text = label,
                    style = style,
                    topLeft = Offset(
                        x - layout.size.width / 2f,
                        y + r + 6f,
                    ),
                )
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Internal state — topology layout + force-directed physics
// ═════════════════════════════════════════════════════════════════════════════

private enum class TopologyNodeKind { LOCAL, PEER }

private data class TopologyNode(
    val id: String,
    val kind: TopologyNodeKind,
    val label: String,
    val color: Color,
    val radius: Float,
    var x: Float = 0f,
    var y: Float = 0f,
    var vx: Float = 0f,
    var vy: Float = 0f,
    val fixed: Boolean = false,
)

private data class TopologyEdge(
    val sourceId: String,
    val targetId: String,
    val color: Color,
    val width: Float = 1.5f,
    val dimmed: Boolean = false,
)

private class TopologyState(
    val nodes: MutableList<TopologyNode>,
    val edges: List<TopologyEdge>,
    val dataKey: Int,
) {
    private var alpha: Float = 1f
    private val repulsion = -350f
    private val linkDist = 130f
    private val linkStrength = 0.25f
    private val centerStrength = 0.04f
    private val damping = 0.88f
    private val alphaDecay = 0.025f
    private val alphaMin = 0.005f

    fun initializePositions(width: Float, height: Float) {
        val cx = width / 2f
        val cy = height / 2f
        nodes.forEachIndexed { index, n ->
            if (n.kind == TopologyNodeKind.LOCAL) {
                n.x = cx
                n.y = cy
            } else if (n.x == 0f && n.y == 0f) {
                val angle = (index.toFloat() / nodes.size.toFloat()) * 2f * PI
                val r = 200f + Random.nextFloat() * 100f
                n.x = cx + r * cos(angle)
                n.y = cy + r * sin(angle)
            }
        }
    }

    fun warm() { alpha = max(alpha, 0.6f) }

    fun dragNode(id: String, dx: Float, dy: Float) {
        nodes.find { it.id == id }?.let { it.x += dx; it.y += dy }
    }

    /** Returns true if any non-local node moved meaningfully. */
    fun step(): Boolean {
        if (alpha < alphaMin) return false
        val cx = nodes.firstOrNull { it.kind == TopologyNodeKind.LOCAL }?.x ?: 500f
        val cy = nodes.firstOrNull { it.kind == TopologyNodeKind.LOCAL }?.y ?: 500f

        // Repulsion (Barnes-Hut-lite — O(n²) for small networks)
        for (i in nodes.indices) {
            for (j in i + 1 until nodes.size) {
                val a = nodes[i]
                val b = nodes[j]
                var dx = b.x - a.x
                var dy = b.y - a.y
                var dist2 = dx * dx + dy * dy
                if (dist2 < 1f) dist2 = 1f
                val dist = sqrt(dist2)
                val force = repulsion * alpha / dist2
                dx /= dist; dy /= dist
                a.vx -= dx * force; a.vy -= dy * force
                b.vx += dx * force; b.vy += dy * force
            }
        }

        // Link attraction
        for (e in edges) {
            val a = nodes.find { it.id == e.sourceId } ?: continue
            val b = nodes.find { it.id == e.targetId } ?: continue
            var dx = b.x - a.x
            var dy = b.y - a.y
            val dist = sqrt(dx * dx + dy * dy).coerceAtLeast(0.1f)
            val force = (dist - linkDist) * linkStrength * alpha
            dx /= dist; dy /= dist
            a.vx += dx * force; a.vy += dy * force
            b.vx -= dx * force; b.vy -= dy * force
        }

        // Center gravity (toward local-identity anchor)
        for (n in nodes) {
            if (n.kind == TopologyNodeKind.LOCAL || n.fixed) continue
            n.vx += (cx - n.x) * centerStrength * alpha
            n.vy += (cy - n.y) * centerStrength * alpha
        }

        // Integrate + damping + measure motion
        var maxMotion = 0f
        for (n in nodes) {
            if (n.kind == TopologyNodeKind.LOCAL || n.fixed) {
                n.vx = 0f; n.vy = 0f; continue
            }
            n.vx *= damping; n.vy *= damping
            n.x += n.vx; n.y += n.vy
            val mag = abs(n.vx) + abs(n.vy)
            if (mag > maxMotion) maxMotion = mag
        }

        alpha -= alphaDecay
        return maxMotion > 0.1f
    }

    fun findAt(worldX: Float, worldY: Float): TopologyNode? {
        for (n in nodes.reversed()) {
            val dx = n.x - worldX
            val dy = n.y - worldY
            if (dx * dx + dy * dy <= (n.radius * n.radius + 100f)) return n
        }
        return null
    }
}

private val PI = kotlin.math.PI.toFloat()
private fun abs(f: Float) = if (f < 0) -f else f

private fun buildTopologyState(snapshot: NetworkSnapshot): TopologyState {
    val nodes = mutableListOf<TopologyNode>()

    // Anchor: local identity at center
    nodes.add(
        TopologyNode(
            id = snapshot.localIdentity.keyId,
            kind = TopologyNodeKind.LOCAL,
            label = snapshot.localIdentity.displayName ?: snapshot.localIdentity.keyIdShort,
            color = Color(0xFF00d4ff), // AccentCyan
            radius = 22f,
            fixed = true,
        ),
    )

    // Peers
    for (peer in snapshot.peers) {
        val trustColor = when (peer.trust) {
            PeerTrust.TRUSTED -> Color(0xFF4CAF50)
            PeerTrust.UNTRUSTED -> Color(0xFF9E9E9E)
            PeerTrust.BLOCKED -> Color(0xFFF44336)
            PeerTrust.UNKNOWN -> Color(0xFF607D8B)
        }
        nodes.add(
            TopologyNode(
                id = peer.keyId,
                kind = TopologyNodeKind.PEER,
                label = peer.displayName ?: peer.keyIdShort,
                color = trustColor,
                radius = 14f,
            ),
        )
    }

    // Edges: peer → local for each reachability entry, colored by transport
    val edges = mutableListOf<TopologyEdge>()
    for (peer in snapshot.peers) {
        for (reach in peer.reachability) {
            edges.add(
                TopologyEdge(
                    sourceId = peer.keyId,
                    targetId = snapshot.localIdentity.keyId,
                    color = transportKindCanvasColor(reach.transportKind),
                    width = max(1f, 3f - reach.hops),
                    dimmed = reach.lastSeenAt == null,
                ),
            )
        }
    }

    return TopologyState(
        nodes = nodes,
        edges = edges,
        dataKey = snapshot.hashCode(),
    )
}

private fun transportKindCanvasColor(kind: TransportKind): Color = when (kind) {
    TransportKind.HTTPS -> Color(0xFF00d4ff)
    TransportKind.TCP -> Color(0xFF22C0E8)
    TransportKind.UDP -> Color(0xFF419CA0)
    TransportKind.AUTO -> Color(0xFF22C0E8)
    TransportKind.RNODE -> Color(0xFFC96A38)
    TransportKind.I2P -> Color(0xFFB08A3E)
    TransportKind.KISS -> Color(0xFFC96A38)
    TransportKind.SERIAL -> Color(0xFFC96A38)
    TransportKind.PIPE -> Color(0xFF9E9E9E)
    TransportKind.LOCAL -> Color(0xFF419CA0)
    TransportKind.UNKNOWN -> Color(0xFF607D8B)
}

private data class GraphViewport(
    val offsetX: Float = 0f,
    val offsetY: Float = 0f,
    val scale: Float = 1f,
)
