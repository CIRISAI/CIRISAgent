package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.icons.CIRISMaterialIcons
import ai.ciris.mobile.shared.ui.icons.Language
import ai.ciris.mobile.shared.viewmodels.federation.NetworkMapViewModel
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.min

/**
 * Network → Map sub-screen (T-E-UI Batch D).
 *
 * Deliberately NOT a fake geographic map. Per the Reticulum cribsheet
 * finding (corroborated by surveying every Sideband / NomadNet / RNS
 * dashboard in the wild), no app in the ecosystem ships a geo view —
 * because no Reticulum transport surfaces geo telemetry. CIRIS doesn't
 * have a geo pipeline yet either, so fabricating locations would be a
 * lie to the operator.
 *
 * What we DO show:
 *  - Hero panel naming the surface honestly ("Geographic view") with a
 *    Material `Language` (globe) icon.
 *  - Explanation card: what this will become, what you can see today.
 *  - Three concentric rings (canonical / trusted / other) drawn on a
 *    Compose [Canvas] with counts.  This is the abstract substitute
 *    for a topology map until the telemetry pipeline lands.
 *  - "What this will show later" card with bullets describing the real
 *    map: peer locations, transport-link overlay (TCP / LoRa / I2P /
 *    AX.25), real-time announces by region.
 *
 * When the geo pipeline ships we replace the canvas in-place; the
 * surface name and information architecture stays.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkMapScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val vm = remember { NetworkMapViewModel(apiClient) }
    val canonical by vm.canonicalCount.collectAsState()
    val trusted by vm.trustedCount.collectAsState()
    val other by vm.otherCount.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()

    LaunchedEffect(vm) { vm.load() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.tiles.map")) },
                actions = {
                    IconButton(onClick = { vm.refresh() }) {
                        Icon(
                            imageVector = CIRISIcons.refresh,
                            contentDescription = localizedString("network.map.refresh"),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Hero()
            ExplanationCard()
            if (loading && canonical == 0 && trusted == 0 && other == 0) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(220.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            } else {
                ConcentricCountsCard(
                    canonical = canonical,
                    trusted = trusted,
                    other = other,
                )
            }
            FutureFeaturesCard()
            if (error != null) {
                ErrorBanner(error!!)
            }
        }
    }
}

@Composable
private fun Hero() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(72.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = CIRISMaterialIcons.Filled.Language,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onPrimaryContainer,
                modifier = Modifier.size(40.dp),
            )
        }
        Spacer(Modifier.size(16.dp))
        Column(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = localizedString("network.map.hero.title"),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = localizedString("network.map.hero.subtitle"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ExplanationCard() {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.map.explanation.title"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = localizedString("network.map.explanation.body"),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Three concentric rings (canonical / trusted / other) with counts.
 *
 * Honest about being abstract — labelled "What we have today" so the
 * operator doesn't read it as a map.  Compose [Canvas] draw — three
 * concentric circles with a centered count label per ring.
 */
@Composable
private fun ConcentricCountsCard(canonical: Int, trusted: Int, other: Int) {
    val textMeasurer = rememberTextMeasurer()
    val canonicalColor = MaterialTheme.colorScheme.primary
    val trustedColor = MaterialTheme.colorScheme.tertiary
    val outlineColor = MaterialTheme.colorScheme.outline
    val onSurfaceColor = MaterialTheme.colorScheme.onSurface

    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.map.today.title"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(12.dp))
            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp),
            ) {
                val w = size.width
                val h = size.height
                val cx = w / 2f
                val cy = h / 2f
                val half = min(w, h) / 2f
                val outerR = half * 0.92f
                val midR = half * 0.62f
                val innerR = half * 0.32f

                // Outer ring (other peers)
                drawCircle(
                    color = outlineColor.copy(alpha = 0.25f),
                    radius = outerR,
                    center = Offset(cx, cy),
                )
                drawCircle(
                    color = outlineColor,
                    radius = outerR,
                    center = Offset(cx, cy),
                    style = Stroke(width = 2f),
                )
                // Middle ring (trusted)
                drawCircle(
                    color = trustedColor.copy(alpha = 0.18f),
                    radius = midR,
                    center = Offset(cx, cy),
                )
                drawCircle(
                    color = trustedColor,
                    radius = midR,
                    center = Offset(cx, cy),
                    style = Stroke(width = 2f),
                )
                // Inner disc (canonical)
                drawCircle(
                    color = canonicalColor.copy(alpha = 0.35f),
                    radius = innerR,
                    center = Offset(cx, cy),
                )
                drawCircle(
                    color = canonicalColor,
                    radius = innerR,
                    center = Offset(cx, cy),
                    style = Stroke(width = 2f),
                )

                // Centered count for canonical
                drawCenteredCount(
                    textMeasurer = textMeasurer,
                    countLabel = canonical.toString(),
                    center = Offset(cx, cy),
                    textColor = onSurfaceColor,
                    sizeSp = 22f,
                )

                // Trusted count: top-right of inner ring
                val trustedLabelPos = Offset(cx + midR * 0.65f, cy - midR * 0.55f)
                drawCenteredCount(
                    textMeasurer = textMeasurer,
                    countLabel = trusted.toString(),
                    center = trustedLabelPos,
                    textColor = onSurfaceColor,
                    sizeSp = 14f,
                )

                // Other count: top-right of outer ring
                val otherLabelPos = Offset(cx + outerR * 0.7f, cy - outerR * 0.55f)
                drawCenteredCount(
                    textMeasurer = textMeasurer,
                    countLabel = other.toString(),
                    center = otherLabelPos,
                    textColor = onSurfaceColor,
                    sizeSp = 14f,
                )
            }
            Spacer(Modifier.height(8.dp))
            // Legend rows beneath the canvas
            LegendRow(
                color = canonicalColor,
                label = localizedString("network.map.today.canonical"),
                count = canonical,
            )
            LegendRow(
                color = trustedColor,
                label = localizedString("network.map.today.trusted"),
                count = trusted,
            )
            LegendRow(
                color = outlineColor,
                label = localizedString("network.map.today.other"),
                count = other,
            )
        }
    }
}

@Composable
private fun LegendRow(color: Color, label: String, count: Int) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(color),
        )
        Spacer(Modifier.size(8.dp))
        Text(
            text = label,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(
            text = count.toString(),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun FutureFeaturesCard() {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.map.future.title"),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            BulletRow(localizedString("network.map.future.bullet_locations"))
            BulletRow(localizedString("network.map.future.bullet_transport"))
            BulletRow(localizedString("network.map.future.bullet_announces"))
        }
    }
}

@Composable
private fun BulletRow(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = "•",
            modifier = Modifier.padding(end = 8.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ErrorBanner(message: String) {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
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

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawCenteredCount(
    textMeasurer: androidx.compose.ui.text.TextMeasurer,
    countLabel: String,
    center: Offset,
    textColor: Color,
    sizeSp: Float,
) {
    val layout = textMeasurer.measure(
        text = countLabel,
        style = TextStyle(
            color = textColor,
            fontSize = sizeSp.sp,
            fontWeight = FontWeight.SemiBold,
        ),
    )
    drawText(
        textLayoutResult = layout,
        topLeft = Offset(
            center.x - layout.size.width / 2f,
            center.y - layout.size.height / 2f,
        ),
    )
}
