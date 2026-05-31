package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.federation.FederationStreamConnectionState
import ai.ciris.mobile.shared.viewmodels.federation.NetworkAnnouncesViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Network → Announces sub-screen. Live SSE-driven announce feed —
 * Sideband-style row anatomy with severity icon, timestamp, truncated
 * peer-key, message, and optional radio metrics in brackets (RSSI/SNR).
 *
 * Ring buffer is 200 envelopes (oldest dropped). Reconnect after error
 * uses the last seen ``event_id`` so the bridge can surface a
 * ``resume-notice`` if it cares to.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkAnnouncesScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val viewModel: NetworkAnnouncesViewModel = viewModel {
        NetworkAnnouncesViewModel(apiClient)
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
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(localizedString("network.announces.title"))
                    }
                },
                actions = {
                    ConnectionDot(connectionState, indicatorTag = "indicator_announces_connection")
                },
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
                .testable("screen_federation_announces"),
        ) {
            FederationStreamControlBar(
                paused = paused,
                connectionState = connectionState,
                eventCount = events.size,
                onPauseToggle = { if (paused) viewModel.resume() else viewModel.pause() },
                onClear = { viewModel.clear() },
                onReconnect = { viewModel.reconnect() },
                pauseTag = "btn_announces_pause",
                clearTag = "btn_announces_clear",
            )

            if (resumeNoticeShown) {
                ResumeNoticeBanner(
                    onDismiss = { viewModel.acknowledgeResumeNotice() },
                )
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
                EmptyStreamPlaceholder(
                    message = localizedString("network.announces.empty"),
                )
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    items(events, key = { it.eventId }) { envelope ->
                        AnnounceRow(envelope)
                    }
                }
            }
        }
    }
}

@Composable
private fun AnnounceRow(envelope: FederationEventEnvelope) {
    val payload = envelope.payload
    val severity = payload["severity"]?.jsonPrimitive?.contentOrNull ?: "info"
    val message = payload["message"]?.jsonPrimitive?.contentOrNull
        ?: localizedString("network.announces.no_message")
    val peerKey = payload["peer_key_id"]?.jsonPrimitive?.contentOrNull
    val rssi = payload["rssi_dbm"]?.jsonPrimitive?.intOrNull
        ?: payload["rssi_dbm"]?.jsonPrimitive?.doubleOrNull?.toInt()
    val snr = payload["snr_db"]?.jsonPrimitive?.doubleOrNull

    val severityColor = when (severity) {
        "error" -> CIRISColors.StatusErr
        "warning" -> CIRISColors.StatusWarn
        else -> CIRISColors.StatusInfo
    }
    val severityIcon = when (severity) {
        "error" -> CIRISIcons.error
        "warning" -> CIRISIcons.warning
        else -> CIRISIcons.info
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(CIRISColors.BackgroundDarker)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            imageVector = severityIcon,
            contentDescription = severity,
            tint = severityColor,
            modifier = Modifier.size(18.dp),
        )
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
            }
            Text(
                text = message,
                color = CIRISColors.TextPrimary,
                fontSize = 13.sp,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (rssi != null || snr != null) {
                Row(
                    modifier = Modifier.padding(top = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (rssi != null) {
                        RadioMetricChip(label = "RSSI", value = "$rssi dBm")
                    }
                    if (snr != null) {
                        RadioMetricChip(label = "SNR", value = "${formatOneDecimal(snr)} dB")
                    }
                }
            }
        }
    }
}

@Composable
internal fun RadioMetricChip(label: String, value: String) {
    Text(
        text = "[$label $value]",
        color = CIRISColors.BusComm,
        fontSize = 10.sp,
        fontFamily = FontFamily.Monospace,
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(CIRISColors.BusComm.copy(alpha = 0.10f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

@Composable
internal fun ConnectionDot(
    state: FederationStreamConnectionState,
    indicatorTag: String? = null,
) {
    val color = when (state) {
        FederationStreamConnectionState.CONNECTED -> CIRISColors.StatusOk
        FederationStreamConnectionState.CONNECTING -> CIRISColors.StatusWarn
        FederationStreamConnectionState.PAUSED -> CIRISColors.TextTertiary
        FederationStreamConnectionState.ERROR -> CIRISColors.StatusErr
        FederationStreamConnectionState.DISCONNECTED -> CIRISColors.TextDim
    }
    val base = Modifier
        .padding(end = 12.dp)
        .size(10.dp)
        .clip(CircleShape)
        .background(color)
    Box(
        modifier = if (indicatorTag != null) base.testable(indicatorTag) else base,
    )
}

@Composable
internal fun FederationStreamControlBar(
    paused: Boolean,
    connectionState: FederationStreamConnectionState,
    eventCount: Int,
    onPauseToggle: () -> Unit,
    onClear: () -> Unit,
    onReconnect: () -> Unit,
    pauseTag: String? = null,
    clearTag: String? = null,
    reconnectTag: String? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CIRISColors.BackgroundDarker)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedButton(
            onClick = onPauseToggle,
            modifier = if (pauseTag != null) {
                Modifier.testableClickable(pauseTag) { onPauseToggle() }
            } else {
                Modifier
            },
        ) {
            Text(
                text = if (paused) {
                    localizedString("network.stream.resume")
                } else {
                    localizedString("network.stream.pause")
                },
            )
        }
        OutlinedButton(
            onClick = onClear,
            modifier = if (clearTag != null) {
                Modifier.testableClickable(clearTag) { onClear() }
            } else {
                Modifier
            },
        ) {
            Text(localizedString("network.stream.clear"))
        }
        if (connectionState == FederationStreamConnectionState.ERROR ||
            connectionState == FederationStreamConnectionState.DISCONNECTED
        ) {
            OutlinedButton(
                onClick = onReconnect,
                modifier = if (reconnectTag != null) {
                    Modifier.testableClickable(reconnectTag) { onReconnect() }
                } else {
                    Modifier
                },
            ) {
                Text(localizedString("network.stream.reconnect"))
            }
        }
        Text(
            text = localizedString(
                key = "network.stream.event_count",
                paramName = "count",
                paramValue = eventCount.toString(),
            ),
            color = CIRISColors.TextTertiary,
            fontSize = 11.sp,
            modifier = Modifier.padding(start = 4.dp),
        )
    }
}

@Composable
internal fun ResumeNoticeBanner(onDismiss: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CIRISColors.StatusWarn.copy(alpha = 0.15f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = CIRISIcons.warning,
            contentDescription = null,
            tint = CIRISColors.StatusWarn,
            modifier = Modifier.size(16.dp),
        )
        Text(
            text = localizedString("network.stream.resume_notice"),
            color = CIRISColors.TextPrimary,
            fontSize = 12.sp,
            modifier = Modifier
                .padding(start = 8.dp)
                .weight(1f, fill = true),
        )
        TextButton(onClick = onDismiss) {
            Text(localizedString("network.stream.dismiss"))
        }
    }
}

@Composable
internal fun FederationStreamErrorBanner(
    message: String,
    lastEventId: String?,
    onRetry: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CIRISColors.StatusErr.copy(alpha = 0.15f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = CIRISIcons.error,
            contentDescription = null,
            tint = CIRISColors.StatusErr,
            modifier = Modifier.size(16.dp),
        )
        Column(
            modifier = Modifier
                .padding(horizontal = 8.dp)
                .weight(1f, fill = true),
        ) {
            Text(
                text = message,
                color = CIRISColors.TextPrimary,
                fontSize = 12.sp,
            )
            if (lastEventId != null) {
                Text(
                    text = localizedString(
                        key = "network.stream.last_event_id",
                        paramName = "id",
                        paramValue = lastEventId,
                    ),
                    color = CIRISColors.TextTertiary,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
        TextButton(onClick = onRetry) {
            Text(localizedString("network.stream.retry"))
        }
    }
}

@Composable
internal fun EmptyStreamPlaceholder(message: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = message,
            color = CIRISColors.TextTertiary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

/** Format an ISO-8601 instant as ``HH:MM`` for the row prefix. */
internal fun shortTimestamp(iso: String): String {
    // Instant.toString() is "1970-01-01T00:00:00Z" style — pluck the
    // HH:MM after the 'T' so we don't pull a date-time formatter into
    // shared just for this.
    val t = iso.indexOf('T').takeIf { it >= 0 } ?: return iso
    val rest = iso.substring(t + 1)
    val colon = rest.indexOf(':')
    if (colon <= 0 || rest.length < colon + 3) return iso
    return rest.substring(0, colon + 3)
}

/** Render a peer_key_id as ``<…last10>``. */
internal fun truncateKey(key: String): String {
    if (key.length <= 10) return "<…$key>"
    return "<…${key.takeLast(10)}>"
}

internal fun formatOneDecimal(d: Double): String {
    val whole = d.toInt()
    val frac = ((d - whole) * 10).toInt()
    val absFrac = if (frac < 0) -frac else frac
    return "$whole.$absFrac"
}

