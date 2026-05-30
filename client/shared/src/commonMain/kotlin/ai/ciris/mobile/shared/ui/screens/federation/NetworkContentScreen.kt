package ai.ciris.mobile.shared.ui.screens.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationContentResponse
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.viewmodels.federation.ContentStep
import ai.ciris.mobile.shared.viewmodels.federation.NetworkContentViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * Network → Content sub-screen.
 *
 * Two-step flow:
 *  1. PICK_PEER — search/list peers, tap one to advance.
 *  2. FETCH    — read-only peer chip, content_id field, timeout slider,
 *                Fetch button, result panel.
 *
 * Backend contract: ``peer_key_id`` is required on every fetch; there is
 * no global content directory, so the peer must be picked first.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NetworkContentScreen(
    apiClient: CIRISApiClient,
    onIssueClick: (String) -> Unit = {},
) {
    val vm = remember { NetworkContentViewModel(apiClient) }
    val step by vm.step.collectAsState()
    val loading by vm.loading.collectAsState()

    LaunchedEffect(vm) { vm.loadPeers() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when (step) {
                            ContentStep.PICK_PEER -> localizedString("network.content.step1.title")
                            ContentStep.FETCH -> localizedString("network.content.step2.title")
                        },
                    )
                },
                navigationIcon = {
                    if (step == ContentStep.FETCH) {
                        IconButton(onClick = { vm.backToPicker() }) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("network.content.back"),
                            )
                        }
                    }
                },
                actions = {
                    if (step == ContentStep.PICK_PEER) {
                        IconButton(onClick = { vm.loadPeers() }) {
                            Icon(
                                imageVector = CIRISIcons.refresh,
                                contentDescription = localizedString("network.content.refresh"),
                            )
                        }
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .testable("screen_federation_content"),
        ) {
            when (step) {
                ContentStep.PICK_PEER -> PeerPickerStep(vm = vm, loading = loading)
                ContentStep.FETCH -> FetchStep(vm = vm, loading = loading)
            }
        }
    }
}

// ─── Step 1: Peer picker ─────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PeerPickerStep(vm: NetworkContentViewModel, loading: Boolean) {
    val peers by vm.peers.collectAsState()
    val search by vm.peerSearch.collectAsState()
    val error by vm.error.collectAsState()
    val filtered = remember(peers, search) { vm.filteredPeers() }

    Column(modifier = Modifier.fillMaxSize()) {
        // Search box
        OutlinedTextField(
            value = search,
            onValueChange = { vm.setPeerSearch(it) },
            label = { Text(localizedString("network.content.peer.search")) },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .testable("input_peer_search"),
        )

        error?.let { msg ->
            ElevatedCard(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                colors = CardDefaults.elevatedCardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                ),
            ) {
                Text(
                    text = msg,
                    modifier = Modifier.padding(12.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

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
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = localizedString("network.content.peer.empty"),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(filtered, key = { it.keyId }) { peer ->
                        PeerRow(peer = peer, onClick = { vm.selectPeer(peer) })
                    }
                }
            }
        }
    }
}

@Composable
private fun PeerRow(peer: LocalPeerState, onClick: () -> Unit) {
    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .testableClickable("peer_pick_row_${peer.keyId}") { onClick() },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TrustGlyph(peer.trust)
            Spacer(Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = peer.aliasOverride ?: shortKey(peer.keyId),
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = shortKey(peer.keyId),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(
                imageVector = CIRISIcons.arrowForward,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun TrustGlyph(trust: PeerTrustState) {
    val color = when (trust) {
        PeerTrustState.TRUSTED -> Color(0xFF2E7D32)
        PeerTrustState.UNTRUSTED -> Color(0xFFF9A825)
        PeerTrustState.BLOCKED -> Color(0xFFC62828)
        PeerTrustState.UNKNOWN -> MaterialTheme.colorScheme.outline
    }
    Box(
        modifier = Modifier
            .size(28.dp)
            .clip(CircleShape)
            .background(color.copy(alpha = 0.15f)),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(12.dp)
                .clip(CircleShape)
                .background(color),
        )
    }
}

private fun shortKey(keyId: String): String =
    if (keyId.length <= 16) keyId else "${keyId.take(8)}…${keyId.takeLast(6)}"

// ─── Step 2: Content fetch ───────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FetchStep(vm: NetworkContentViewModel, loading: Boolean) {
    val peer = vm.selectedPeer.collectAsState().value ?: return
    val contentId by vm.contentIdInput.collectAsState()
    val timeoutMs by vm.timeoutMs.collectAsState()
    val fetching by vm.fetching.collectAsState()
    val result by vm.result.collectAsState()
    val cidError by vm.contentIdError.collectAsState()
    val vmError by vm.error.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Selected-peer chip + change link
        ElevatedCard(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TrustGlyph(peer.trust)
                Spacer(Modifier.size(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = peer.aliasOverride ?: shortKey(peer.keyId),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = shortKey(peer.keyId),
                        style = MaterialTheme.typography.labelSmall,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(onClick = { vm.backToPicker() }) {
                    Text(localizedString("network.content.peer.change"))
                }
            }
        }

        // Content ID input
        OutlinedTextField(
            value = contentId,
            onValueChange = { vm.setContentId(it) },
            label = { Text(localizedString("network.content.fetch.content_id_label")) },
            placeholder = { Text(localizedString("network.content.fetch.content_id_placeholder")) },
            isError = cidError != null,
            supportingText = {
                if (cidError != null) {
                    Text(localizedString("network.content.fetch.invalid_id"))
                }
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
            modifier = Modifier.fillMaxWidth(),
        )

        // Timeout slider
        Column {
            Text(
                text = "${localizedString("network.content.fetch.timeout_label")}: ${timeoutMs}ms",
                style = MaterialTheme.typography.bodyMedium,
            )
            Slider(
                value = timeoutMs.toFloat(),
                onValueChange = { vm.setTimeout(it.toInt()) },
                valueRange = 1_000f..30_000f,
                steps = 28,
            )
        }

        Button(
            onClick = { vm.fetch() },
            enabled = !fetching && vm.validateContentId(contentId),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (fetching) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                )
                Spacer(Modifier.size(8.dp))
            }
            Text(localizedString("network.content.fetch.button"))
        }

        // Error / result panel
        if (vmError != null) {
            ErrorPanel(message = mapError(vmError ?: ""))
        }
        result?.let { ResultPanel(it) }
    }
}

@Composable
private fun ErrorPanel(message: String) {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(16.dp),
            color = MaterialTheme.colorScheme.onErrorContainer,
        )
    }
}

@OptIn(ExperimentalEncodingApi::class)
@Composable
private fun ResultPanel(res: FederationContentResponse) {
    val payloadPreview = remember(res.payloadBase64) { decodePreview(res.payloadBase64) }
    ElevatedCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.content.result.title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            ResultRow(
                key = localizedString("network.content.result.content_type"),
                value = res.contentType ?: "—",
            )
            ResultRow(
                key = localizedString("network.content.result.size"),
                value = "${res.sizeBytes} B",
            )
            ResultRow(
                key = localizedString("network.content.result.fetched_at"),
                value = res.fetchedAt.toString(),
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = localizedString("network.content.result.preview"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(6.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(8.dp),
            ) {
                Text(
                    text = payloadPreview,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

@Composable
private fun ResultRow(key: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = key,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = value,
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp,
        )
    }
}

/**
 * Decode the first 200 bytes of a base64 payload — render as ASCII when
 * printable, otherwise hex. We intentionally cap the visible window so a
 * multi-MB asset doesn't blow up composition.
 */
@OptIn(ExperimentalEncodingApi::class)
internal fun decodePreview(payloadBase64: String): String {
    return try {
        val bytes = Base64.decode(payloadBase64)
        val window = bytes.take(200).toByteArray()
        if (window.all { it.toInt().toChar().let { c -> c == '\n' || c == '\r' || c == '\t' || c.code in 32..126 } }) {
            window.decodeToString()
        } else {
            window.joinToString(" ") { byte ->
                val v = byte.toInt() and 0xFF
                v.toString(16).padStart(2, '0')
            }
        }
    } catch (_: Throwable) {
        "(invalid base64)"
    }
}

/**
 * Map a backend error string to a user-facing message. The backend
 * surfaces 404 / 503 as exception messages containing the status code;
 * we substring-match rather than parse the status object because the
 * [CIRISApiClient.fetchFederationContent] surface only gives us the
 * exception message.
 */
@Composable
private fun mapError(raw: String): String = when {
    "404" in raw -> localizedString("network.content.error.not_found")
    "503" in raw -> localizedString("network.content.error.edge_unavailable")
    else -> raw
}
