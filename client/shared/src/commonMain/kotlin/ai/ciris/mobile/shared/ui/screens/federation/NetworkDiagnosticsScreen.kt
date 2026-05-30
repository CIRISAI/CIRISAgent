package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationChannel
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.federation.NetworkDiagnosticsViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Network → Diagnostics sub-screen. Unified diagnostic feed across all
 * Edge SSE sub-channels with per-channel filter chips, free-text
 * search over the payload's ``message`` and ``event_type``, and tap-to-
 * expand raw JSON payload per row.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkDiagnosticsScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val viewModel: NetworkDiagnosticsViewModel = viewModel {
        NetworkDiagnosticsViewModel(apiClient)
    }

    val events by viewModel.events.collectAsState()
    val paused by viewModel.paused.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()
    val resumeNoticeShown by viewModel.resumeNoticeShown.collectAsState()
    val lastEventId by viewModel.lastEventId.collectAsState()
    val errorMessage by viewModel.error.collectAsState()
    val channelFilters by viewModel.channelFilters.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()
    val expandedEventIds by viewModel.expandedEventIds.collectAsState()
    val channelCounters by viewModel.channelCounters.collectAsState()

    val displayedEvents by remember(events, channelFilters, searchQuery) {
        derivedStateOf { viewModel.filterEvents(events, channelFilters, searchQuery) }
    }

    LaunchedEffect(Unit) { viewModel.connect() }
    DisposableEffect(Unit) {
        onDispose { viewModel.stop() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("network.diagnostics.title")) },
                actions = { ConnectionDot(connectionState, indicatorTag = "indicator_diagnostics_connection") },
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
                .testable("screen_federation_diagnostics"),
        ) {
            // Channel counters strip
            CountersStrip(channelCounters)

            // Filter chips row
            ChannelFilterChipRow(
                selected = channelFilters,
                onToggle = { viewModel.toggleChannelFilter(it) },
            )

            // Search box
            DiagnosticsSearchBox(
                query = searchQuery,
                onQueryChange = { viewModel.setSearchQuery(it) },
            )

            FederationStreamControlBar(
                paused = paused,
                connectionState = connectionState,
                eventCount = displayedEvents.size,
                onPauseToggle = { if (paused) viewModel.resume() else viewModel.pause() },
                onClear = { viewModel.clear() },
                onReconnect = { viewModel.reconnect() },
                pauseTag = "btn_diagnostics_pause",
                clearTag = "btn_diagnostics_clear",
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

            if (displayedEvents.isEmpty()) {
                Box(
                    modifier = Modifier.weight(1f, fill = true).fillMaxWidth(),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = localizedString("network.diagnostics.empty"),
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
                    items(displayedEvents, key = { it.eventId }) { envelope ->
                        DiagnosticsRow(
                            envelope = envelope,
                            expanded = envelope.eventId in expandedEventIds,
                            onToggle = { viewModel.toggleExpanded(envelope.eventId) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun CountersStrip(counters: Map<FederationChannel, Int>) {
    val scrollState = rememberScrollState()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CIRISColors.BackgroundDarker)
            .horizontalScroll(scrollState)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        listOf(
            FederationChannel.ANNOUNCES,
            FederationChannel.FEED,
            FederationChannel.INTERFACE_EVENTS,
            FederationChannel.LINK_EVENTS,
            FederationChannel.PATH_EVENTS,
            FederationChannel.RESOURCE_EVENTS,
        ).forEach { ch ->
            val count = counters[ch] ?: 0
            val short = channelShortLabel(ch)
            Text(
                text = "$short: $count",
                color = if (count > 0) CIRISColors.TextPrimary else CIRISColors.TextTertiary,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.testable("text_counter_$short"),
            )
        }
    }
}

@Composable
private fun ChannelFilterChipRow(
    selected: Set<FederationChannel>,
    onToggle: (FederationChannel) -> Unit,
) {
    val scrollState = rememberScrollState()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(scrollState)
            .padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        listOf(
            FederationChannel.ANNOUNCES,
            FederationChannel.FEED,
            FederationChannel.INTERFACE_EVENTS,
            FederationChannel.LINK_EVENTS,
            FederationChannel.PATH_EVENTS,
            FederationChannel.RESOURCE_EVENTS,
        ).forEach { ch ->
            val isSelected = ch in selected
            val short = channelShortLabel(ch)
            FilterChip(
                selected = isSelected,
                onClick = { onToggle(ch) },
                label = { Text(short) },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = CIRISColors.AccentCyan.copy(alpha = 0.20f),
                    selectedLabelColor = CIRISColors.AccentCyan,
                ),
                modifier = Modifier.testableClickable("chip_channel_$short") { onToggle(ch) },
            )
        }
    }
}

@Composable
private fun DiagnosticsSearchBox(
    query: String,
    onQueryChange: (String) -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(6.dp))
            .background(CIRISColors.BackgroundDarker)
            .border(
                width = 1.dp,
                color = Color.White.copy(alpha = 0.10f),
                shape = RoundedCornerShape(6.dp),
            )
            .padding(horizontal = 10.dp, vertical = 8.dp)
            .testable("input_diagnostics_search"),
    ) {
        BasicTextField(
            value = query,
            onValueChange = onQueryChange,
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            textStyle = LocalTextStyle.current.copy(
                color = CIRISColors.TextPrimary,
                fontSize = 13.sp,
            ),
            cursorBrush = SolidColor(CIRISColors.AccentCyan),
            decorationBox = { inner ->
                if (query.isEmpty()) {
                    Text(
                        text = localizedString("network.diagnostics.search_hint"),
                        color = CIRISColors.TextTertiary,
                        fontSize = 13.sp,
                    )
                }
                inner()
            },
        )
    }
}

@Composable
private fun DiagnosticsRow(
    envelope: FederationEventEnvelope,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val payload = envelope.payload
    val peerKey = payload["peer_key_id"]?.jsonPrimitive?.contentOrNull
    val message = payload["message"]?.jsonPrimitive?.contentOrNull
    val channel = FederationChannel.fromPathSegment(envelope.channel)

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(CIRISColors.BackgroundDarker)
            .clickable { onToggle() }
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (channel != null) {
                ChannelBadge(channel)
            }
            Text(
                text = shortTimestamp(envelope.timestamp.toString()),
                color = CIRISColors.TextTertiary,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text = envelope.eventType,
                color = CIRISColors.AccentCyan,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
            )
        }

        val summary = buildString {
            if (peerKey != null) {
                append(truncateKey(peerKey))
                append("  ")
            }
            if (message != null) {
                append(message)
            }
        }.ifBlank { localizedString("network.diagnostics.no_summary") }

        val truncated = !expanded && summary.length > 120
        Text(
            text = if (truncated) summary.take(117) + "…" else summary,
            color = CIRISColors.TextPrimary,
            fontSize = 13.sp,
            modifier = Modifier.padding(top = 4.dp),
        )

        if (truncated) {
            Text(
                text = localizedString("network.diagnostics.more"),
                color = CIRISColors.AccentCyan,
                fontSize = 11.sp,
                modifier = Modifier.padding(top = 2.dp),
            )
        }

        if (expanded) {
            ExpandedPayloadView(payload)
        }
    }
}

@Composable
private fun ChannelBadge(channel: FederationChannel) {
    val color = channelColor(channel)
    Text(
        text = channelShortLabel(channel),
        color = color,
        fontSize = 9.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.15f))
            .border(
                width = 1.dp,
                color = color.copy(alpha = 0.40f),
                shape = RoundedCornerShape(50),
            )
            .padding(horizontal = 6.dp, vertical = 1.dp),
    )
}

@Composable
private fun ExpandedPayloadView(payload: JsonObject) {
    val pretty = remember(payload) { prettyPrintJson(payload) }
    val scroll = rememberScrollState()
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .clip(RoundedCornerShape(6.dp))
            .background(CIRISColors.BackgroundDark)
            .horizontalScroll(scroll)
            .padding(10.dp),
    ) {
        Text(
            text = pretty,
            color = CIRISColors.TextSecondary,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            style = TextStyle(lineHeight = 14.sp),
        )
    }
}

@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
private val prettyJson = Json {
    prettyPrint = true
    prettyPrintIndent = "  "
    encodeDefaults = true
}

private fun prettyPrintJson(payload: JsonObject): String =
    try {
        prettyJson.encodeToString(JsonObject.serializer(), payload)
    } catch (_: Exception) {
        payload.toString()
    }

internal fun channelShortLabel(channel: FederationChannel): String = when (channel) {
    FederationChannel.ANNOUNCES -> "announces"
    FederationChannel.FEED -> "feed"
    FederationChannel.INTERFACE_EVENTS -> "interface"
    FederationChannel.LINK_EVENTS -> "link"
    FederationChannel.PATH_EVENTS -> "path"
    FederationChannel.RESOURCE_EVENTS -> "resource"
    FederationChannel.ALL -> "all"
}

private fun channelColor(channel: FederationChannel): Color = when (channel) {
    FederationChannel.ANNOUNCES -> CIRISColors.BusComm
    FederationChannel.FEED -> CIRISColors.BusLLM
    FederationChannel.INTERFACE_EVENTS -> CIRISColors.BusTool
    FederationChannel.LINK_EVENTS -> CIRISColors.BusMemory
    FederationChannel.PATH_EVENTS -> CIRISColors.BusWise
    FederationChannel.RESOURCE_EVENTS -> CIRISColors.BusRuntime
    FederationChannel.ALL -> CIRISColors.AccentCyan
}
