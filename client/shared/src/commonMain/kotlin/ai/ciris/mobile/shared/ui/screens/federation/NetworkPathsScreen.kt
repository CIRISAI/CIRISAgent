package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.federation.NetworkPathsViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Network → Paths sub-screen. Renders the SSE ``path_events`` stream
 * as a chronological event list. Edge 1.0 does not expose a static
 * path table; the bottom banner makes that explicit so operators don't
 * mistake an empty list for "no paths exist".
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkPathsScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val viewModel: NetworkPathsViewModel = viewModel {
        NetworkPathsViewModel(apiClient)
    }

    val events by viewModel.events.collectAsState()
    val paused by viewModel.paused.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()
    val resumeNoticeShown by viewModel.resumeNoticeShown.collectAsState()
    val lastEventId by viewModel.lastEventId.collectAsState()
    val errorMessage by viewModel.error.collectAsState()

    LaunchedEffect(Unit) { viewModel.connect() }
    DisposableEffect(Unit) {
        onDispose { viewModel.stop() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.paths.title")) },
                actions = { ConnectionDot(connectionState, indicatorTag = "indicator_paths_connection") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(CIRISColors.BackgroundDark)
                .testable("screen_federation_paths"),
        ) {
            Text(
                text = localizedString("network.paths.section_recent"),
                color = CIRISColors.TextSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 12.dp, top = 12.dp, bottom = 4.dp),
            )

            FederationStreamControlBar(
                paused = paused,
                connectionState = connectionState,
                eventCount = events.size,
                onPauseToggle = { if (paused) viewModel.resume() else viewModel.pause() },
                onClear = { viewModel.clear() },
                onReconnect = { viewModel.reconnect() },
                pauseTag = "btn_paths_pause",
                clearTag = "btn_paths_clear",
            )

            if (resumeNoticeShown) {
                ResumeNoticeBanner(onDismiss = { viewModel.acknowledgeResumeNotice() })
            }

            if (errorMessage != null) {
                FederationStreamErrorBanner(
                    message = errorMessage ?: "",
                    lastEventId = lastEventId,
                    onRetry = {
                        viewModel.clearError()
                        viewModel.reconnect()
                    },
                )
            }

            if (events.isEmpty()) {
                Box(
                    modifier = Modifier.weight(1f, fill = true).fillMaxWidth(),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = localizedString("network.paths.empty"),
                        color = CIRISColors.TextTertiary,
                        fontSize = 13.sp,
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .weight(1f, fill = true)
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    items(events, key = { it.eventId }) { envelope ->
                        PathEventRow(envelope)
                    }
                }
            }

            // Bottom note: Edge 1.0 surface limitation.
            Text(
                text = localizedString("network.paths.no_static_table_note"),
                color = CIRISColors.TextTertiary,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(CIRISColors.BackgroundDarker)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            )
        }
    }
}

@Composable
private fun PathEventRow(envelope: FederationEventEnvelope) {
    val payload = envelope.payload
    val kind = payload["kind"]?.jsonPrimitive?.contentOrNull
        ?: envelope.eventType
    val peerKey = payload["peer_key_id"]?.jsonPrimitive?.contentOrNull
    val transportId = payload["transport_id"]?.jsonPrimitive?.contentOrNull
    val message = payload["message"]?.jsonPrimitive?.contentOrNull

    val (chipColor, chipLabelKey) = when {
        kind.contains("added", ignoreCase = true) ||
            kind.contains("discovered", ignoreCase = true) ->
            CIRISColors.StatusOk to "network.paths.kind_added"
        kind.contains("lost", ignoreCase = true) ||
            kind.contains("dropped", ignoreCase = true) ->
            CIRISColors.StatusErr to "network.paths.kind_lost"
        kind.contains("changed", ignoreCase = true) ||
            kind.contains("quality", ignoreCase = true) ->
            CIRISColors.StatusWarn to "network.paths.kind_changed"
        else -> CIRISColors.TextTertiary to "network.paths.kind_other"
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(CIRISColors.BackgroundDarker)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = shortTimestamp(envelope.timestamp.toString()),
                    color = CIRISColors.TextTertiary,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                )
                if (peerKey != null) {
                    Text(
                        text = truncateKey(peerKey),
                        color = CIRISColors.AccentCyan,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                KindChip(label = localizedString(chipLabelKey), color = chipColor)
                if (transportId != null) {
                    Text(
                        text = transportId,
                        color = CIRISColors.TextTertiary,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
            if (message != null) {
                Text(
                    text = message,
                    color = CIRISColors.TextPrimary,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun KindChip(label: String, color: Color) {
    Text(
        text = label,
        color = color,
        fontSize = 10.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.12f))
            .border(
                width = 1.dp,
                color = color.copy(alpha = 0.40f),
                shape = RoundedCornerShape(50),
            )
            .padding(horizontal = 8.dp, vertical = 2.dp),
    )
}
