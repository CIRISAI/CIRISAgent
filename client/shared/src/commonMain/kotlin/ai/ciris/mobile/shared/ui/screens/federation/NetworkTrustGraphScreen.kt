package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.viewmodels.federation.NetworkTrustGraphViewModel
import ai.ciris.mobile.shared.viewmodels.federation.PeerWithReachability
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/**
 * Network → Trust Graph sub-screen (T-E-UI Batch D).
 *
 * Radial trust topology rendered on a Compose [Canvas]:
 *  - Self at the exact center, ring of canonical peers near the middle,
 *    organic peers on the outer ring sorted by trust state
 *    (TRUSTED top, UNKNOWN right, UNTRUSTED bottom, BLOCKED left).
 *  - Each peer node is tinted by its trust state.
 *  - Each edge from self → peer is colored by the peer's trust state
 *    and its opacity is the peer's averaged per-medium reachability
 *    ratio (with a sensible default when no measurement exists yet —
 *    we do NOT collapse "unknown" to 0.0 opacity, that would render a
 *    perfectly healthy peer as a black-out).
 *  - Canonical peers get a thicker stroke ring overlay to distinguish
 *    them from organic peers at the same trust level.
 *  - Tapping a node calls [onPeerClick] with the peer's key id; the
 *    parent dispatcher navigates to ``federation/peer/{key_id}``.
 *
 * Force-directed layout was scoped out for v1 — too much complexity
 * for a first pass; the simpler radial layout is honest about the
 * trust dimension we're actually rendering and stays readable on
 * mobile. Pinch/pan support is also deferred — Compose Multiplatform
 * `Modifier.transformable` is available but the gesture mapping to
 * raw Canvas coordinates is brittle enough that we'd rather ship a
 * static-but-correct first cut than a janky interactive one.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkTrustGraphScreen(
    apiClient: CIRISApiClient,
    onPeerClick: (String) -> Unit = {},
    onIssueClick: (String) -> Unit = {},
) {
    val vm = remember { NetworkTrustGraphViewModel(apiClient) }
    val identity by vm.identity.collectAsState()
    val peers by vm.peers.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val selectedPeerId by vm.selectedPeerId.collectAsState()

    LaunchedEffect(vm) { vm.load() }

    val canonicalCount = peers.count { it.peer.canonical }
    val summary = localizedString(
        key = "network.trust_graph.summary",
        params = mapOf(
            "count" to peers.size.toString(),
            "canonical" to canonicalCount.toString(),
        ),
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(localizedString("network.tiles.trust_graph"))
                        if (peers.isNotEmpty()) {
                            Text(
                                text = summary,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                },
                actions = {
                    IconButton(
                        onClick = { vm.refresh() },
                        modifier = Modifier.testableClickable("btn_trust_graph_refresh") { vm.refresh() },
                    ) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("network.trust_graph.refresh"),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .testable("screen_federation_trust_graph"),
        ) {
            // Always compose the Column + TrustGraphCanvas + Legend so that
            // `canvas_trust_graph` (the testable tag inside TrustGraphCanvas)
            // is reachable by the QA walk-test even on a fresh agent with no
            // peers. Loading/empty/error states overlay the same canvas so
            // the test-automation tree stays stable across state transitions
            // — matches the rendering-eagerness pattern T-T2 used on the hub.
            Column(modifier = Modifier.fillMaxSize()) {
                error?.let { msg -> InlineError(msg) }
                TrustGraphCanvas(
                    peers = peers,
                    selectedPeerId = selectedPeerId,
                    onPeerTap = { keyId ->
                        vm.selectPeer(keyId)
                        onPeerClick(keyId)
                    },
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth(),
                )
                TrustGraphLegend()
            }
            // Overlay loading or empty-state hints when there are no peers.
            // These don't suppress the canvas; they sit on top so the testTag
            // tree (canvas_trust_graph, screen_federation_trust_graph) is
            // unconditionally present.
            when {
                peers.isEmpty() && loading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                }
                peers.isEmpty() -> {
                    EmptyOrErrorState(error = error)
                }
                else -> Unit
            }
        }
    }
}

@Composable
private fun EmptyOrErrorState(error: String?) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = localizedString("network.trust_graph.empty"),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (error != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = error,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun InlineError(message: String) {
    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(12.dp),
            color = MaterialTheme.colorScheme.onErrorContainer,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

/**
 * Radial canvas: self at center, canonical ring inside, organic ring outside.
 *
 * Layout math:
 *  - innerRadius = 0.28 * min(w, h) / 2   → canonical ring
 *  - outerRadius = 0.46 * min(w, h) / 2   → organic ring
 *  - Canonical peers are spread uniformly around the inner ring.
 *  - Organic peers are bucketed by trust state and laid out around the
 *    outer ring in fixed angular sectors:
 *      TRUSTED   centered at 270° (top)
 *      UNKNOWN   centered at   0° (right)
 *      UNTRUSTED centered at  90° (bottom)
 *      BLOCKED   centered at 180° (left)
 *    so a quick glance reveals which direction trouble is in.
 */
@Composable
private fun TrustGraphCanvas(
    peers: List<PeerWithReachability>,
    selectedPeerId: String?,
    onPeerTap: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val textMeasurer = rememberTextMeasurer()
    val outlineColor = MaterialTheme.colorScheme.outline
    val onSurfaceColor = MaterialTheme.colorScheme.onSurface
    val surfaceColor = MaterialTheme.colorScheme.surface
    val primaryColor = MaterialTheme.colorScheme.primary
    val canonicalStrokeColor = MaterialTheme.colorScheme.tertiary

    val trustedColor = primaryColor
    val unknownColor = outlineColor
    val untrustedColor = Color(0xFFF9A825)
    val blockedColor = Color(0xFFC62828)

    fun colorFor(trust: PeerTrustState): Color = when (trust) {
        PeerTrustState.TRUSTED -> trustedColor
        PeerTrustState.UNKNOWN -> unknownColor
        PeerTrustState.UNTRUSTED -> untrustedColor
        PeerTrustState.BLOCKED -> blockedColor
    }

    // Pre-compute node positions outside the canvas draw so we can hit-test
    // them in the pointerInput modifier.  Recomputed when peers list changes.
    data class NodePosition(
        val keyId: String,
        val center: Offset,
        val radius: Float,
        val color: Color,
        val canonical: Boolean,
        val reach: Float,
        val label: String,
    )

    val positions = remember(peers) { mutableListOf<NodePosition>() }

    Canvas(
        modifier = modifier
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .testable("canvas_trust_graph")
            .pointerInput(peers) {
                detectTapGestures { offset ->
                    val hit = positions.firstOrNull { node ->
                        val dx = offset.x - node.center.x
                        val dy = offset.y - node.center.y
                        dx * dx + dy * dy <= (node.radius + 18f) * (node.radius + 18f)
                    }
                    if (hit != null) onPeerTap(hit.keyId)
                }
            },
    ) {
        positions.clear()

        val w = size.width
        val h = size.height
        val cx = w / 2f
        val cy = h / 2f
        val half = min(w, h) / 2f
        val innerRadius = half * 0.28f
        val outerRadius = half * 0.46f
        val nodeRadius = (half * 0.06f).coerceAtMost(28f)
        val selfRadius = (half * 0.075f).coerceAtMost(34f)

        val canonical = peers.filter { it.peer.canonical }
        val organic = peers.filter { !it.peer.canonical }

        // ── Canonical ring layout ────────────────────────────────────
        if (canonical.isNotEmpty()) {
            val step = (2.0 * PI) / canonical.size
            canonical.forEachIndexed { idx, p ->
                // Offset by -PI/2 so the first canonical peer sits at the top.
                val angle = -PI / 2.0 + step * idx
                val px = cx + (innerRadius * cos(angle)).toFloat()
                val py = cy + (innerRadius * sin(angle)).toFloat()
                positions += NodePosition(
                    keyId = p.peer.keyId,
                    center = Offset(px, py),
                    radius = nodeRadius,
                    color = colorFor(p.peer.trust),
                    canonical = true,
                    reach = p.avgRatio?.toFloat() ?: DEFAULT_REACH,
                    label = labelFor(p),
                )
            }
        }

        // ── Organic ring layout (bucket by trust, distribute in sector) ──
        if (organic.isNotEmpty()) {
            val bucketCenters: Map<PeerTrustState, Double> = mapOf(
                PeerTrustState.TRUSTED to -PI / 2.0,     // top
                PeerTrustState.UNKNOWN to 0.0,           // right
                PeerTrustState.UNTRUSTED to PI / 2.0,    // bottom
                PeerTrustState.BLOCKED to PI,            // left
            )
            // Sector half-width: 70° so adjacent buckets stay distinct but
            // visually flow into each other when populated.
            val sectorHalf = (70.0 * PI / 180.0)
            val grouped = organic.groupBy { it.peer.trust }
            for ((trust, group) in grouped) {
                val center = bucketCenters[trust] ?: 0.0
                val n = group.size
                group.forEachIndexed { i, p ->
                    // Distribute n nodes within the sector arc.  For n==1
                    // we land exactly on the bucket center; otherwise we
                    // spread across [-sectorHalf, +sectorHalf].
                    val t = if (n == 1) 0.0 else (i.toDouble() / (n - 1)) - 0.5
                    val angle = center + t * (2 * sectorHalf)
                    val px = cx + (outerRadius * cos(angle)).toFloat()
                    val py = cy + (outerRadius * sin(angle)).toFloat()
                    positions += NodePosition(
                        keyId = p.peer.keyId,
                        center = Offset(px, py),
                        radius = nodeRadius,
                        color = colorFor(trust),
                        canonical = false,
                        reach = p.avgRatio?.toFloat() ?: DEFAULT_REACH,
                        label = labelFor(p),
                    )
                }
            }
        }

        // ── Draw edges from self to every node ──────────────────────
        for (node in positions) {
            // Reachability ratio drives edge opacity; floor at 0.18 so a
            // peer with bad-but-present reachability is still visible.
            val alpha = (node.reach.coerceIn(0f, 1f) * 0.8f + 0.18f).coerceAtMost(1f)
            drawLine(
                color = node.color.copy(alpha = alpha),
                start = Offset(cx, cy),
                end = node.center,
                strokeWidth = 2f,
            )
        }

        // ── Draw nodes ──────────────────────────────────────────────
        for (node in positions) {
            // Body fill
            drawCircle(
                color = node.color,
                radius = node.radius,
                center = node.center,
            )
            // Canonical stroke overlay
            if (node.canonical) {
                drawCircle(
                    color = canonicalStrokeColor,
                    radius = node.radius + 4f,
                    center = node.center,
                    style = Stroke(width = 3f),
                )
            }
            // Selection highlight
            if (node.keyId == selectedPeerId) {
                drawCircle(
                    color = onSurfaceColor,
                    radius = node.radius + 8f,
                    center = node.center,
                    style = Stroke(width = 2f),
                )
            }

            // Compact label below the node (first 6 chars of key id, or
            // alias if set on the underlying peer).
            val labelLayout = textMeasurer.measure(
                text = node.label,
                style = TextStyle(
                    color = onSurfaceColor,
                    fontSize = 9.sp,
                ),
            )
            drawText(
                textLayoutResult = labelLayout,
                topLeft = Offset(
                    node.center.x - labelLayout.size.width / 2f,
                    node.center.y + node.radius + 4f,
                ),
            )
        }

        // ── Self node at center (drawn LAST so it sits on top of edges) ──
        drawCircle(
            color = surfaceColor,
            radius = selfRadius + 4f,
            center = Offset(cx, cy),
        )
        drawCircle(
            color = primaryColor,
            radius = selfRadius,
            center = Offset(cx, cy),
        )
        drawCircle(
            color = onSurfaceColor,
            radius = selfRadius,
            center = Offset(cx, cy),
            style = Stroke(width = 2f),
        )
    }
}

/** Compact node label — alias override wins if present, else short key id. */
private fun labelFor(peer: PeerWithReachability): String {
    val alias = peer.peer.aliasOverride
    if (!alias.isNullOrBlank()) return alias.take(10)
    return peer.peer.keyId.take(6)
}

@Composable
private fun TrustGraphLegend() {
    val primary = MaterialTheme.colorScheme.primary
    val outline = MaterialTheme.colorScheme.outline
    val amber = Color(0xFFF9A825)
    val red = Color(0xFFC62828)

    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = localizedString("network.trust_graph.legend.title"),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                LegendDot(primary, localizedString("network.trust_graph.legend.trusted"))
                LegendDot(outline, localizedString("network.trust_graph.legend.unknown"))
                LegendDot(amber, localizedString("network.trust_graph.legend.untrusted"))
                LegendDot(red, localizedString("network.trust_graph.legend.blocked"))
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = localizedString("network.trust_graph.legend.canonical_hint"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = localizedString("network.trust_graph.legend.edge_hint"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun LegendDot(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(color),
        )
        Spacer(Modifier.size(6.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

/**
 * Fallback edge-opacity factor for peers that have never had a measured
 * reachability sample.  Picked above 0 (so they're visibly drawn) and
 * below 1 (so they don't outshine measured-healthy peers).
 */
private const val DEFAULT_REACH: Float = 0.45f
