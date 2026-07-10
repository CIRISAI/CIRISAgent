package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.ContactsViewModel
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/**
 * **Contacts / Identities** — browsable list of known federation identities
 * sourced from the local node's peer store (``GET /v1/federation/peers``).
 *
 * Two modes:
 *  - **Browse mode** (default): full-screen peer list, searchable, with a
 *    refresh button. Reached from the Manage group nav entry.
 *  - **Picker mode** ([onPeerPicked] != null): same UI but each row shows a
 *    "Choose" chip; tapping it invokes [onPeerPicked] and the caller
 *    (DelegationsScreen) fills the key_id field and dismisses. In picker
 *    mode [onBack] should return to the delegations form.
 *
 * Test tags:
 *  - ``contacts_list``        — the LazyColumn
 *  - ``input_contacts_search``  — the search field
 *  - ``contacts_row_<keyId>``   — each peer row (full key_id, no truncation)
 *  - ``btn_contacts_pick_<keyId>`` — the "Choose" chip (picker mode only)
 *  - ``btn_contacts_refresh``   — the refresh icon button
 *  - ``btn_contacts_back``      — back navigation
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ContactsScreen(
    viewModel: ContactsViewModel,
    onBack: () -> Unit,
    /** When non-null the screen is in picker mode — each row shows a "Choose" button. */
    onPeerPicked: ((LocalPeerState) -> Unit)? = null,
) {
    val peers by viewModel.peers.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    val pickerMode = onPeerPicked != null

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(if (pickerMode) "Choose Identity" else "Contacts / Identities")
                },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testableClickable("btn_contacts_back") { onBack() },
                        ) {
                            Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                        }
                    } else {
                        Spacer(Modifier.width(56.dp))
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.refresh() },
                        enabled = !loading,
                        modifier = Modifier.testableClickable("btn_contacts_refresh") { viewModel.refresh() },
                    ) {
                        Icon(CIRISIcons.refresh, contentDescription = "Refresh")
                    }
                },
            )
        },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            // ── Search ────────────────────────────────────────────────────────
            OutlinedTextField(
                value = searchQuery,
                onValueChange = viewModel::setSearchQuery,
                singleLine = true,
                label = { Text("Search by alias, key_id, trust…") },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp)
                    .testable("input_contacts_search"),
            )

            // ── Error banner ──────────────────────────────────────────────────
            error?.let { msg ->
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                ) {
                    Text(
                        msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(10.dp),
                    )
                }
            }

            // ── Loading spinner ───────────────────────────────────────────────
            if (loading && peers.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                return@Column
            }

            // ── Empty state ───────────────────────────────────────────────────
            if (peers.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Filled.Person,
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            if (searchQuery.isNotBlank()) "No identities match \"$searchQuery\""
                            else "No federation identities known yet",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                        )
                    }
                }
                return@Column
            }

            // ── Peer list ─────────────────────────────────────────────────────
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .testable("contacts_list"),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(peers, key = { it.keyId }) { peer ->
                    ContactRow(
                        peer = peer,
                        pickerMode = pickerMode,
                        onPick = { onPeerPicked?.invoke(peer) },
                    )
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Peer row
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun ContactRow(
    peer: LocalPeerState,
    pickerMode: Boolean,
    onPick: () -> Unit,
) {
    val (icon, tint) = trustGlyph(peer.trust)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("contacts_row_${peer.keyId}"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Leading: trust glyph circle
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(tint.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = peer.trust.wire,
                    tint = tint,
                    modifier = Modifier.size(22.dp),
                )
            }

            // Body
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        text = peer.aliasOverride ?: (peer.keyId.take(12) + "…"),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    if (peer.canonical) {
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = MaterialTheme.colorScheme.secondaryContainer,
                        ) {
                            Text(
                                "canonical",
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.onSecondaryContainer,
                                modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                            )
                        }
                    }
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = tint.copy(alpha = 0.15f),
                    ) {
                        Text(
                            peer.trust.wire,
                            fontSize = 10.sp,
                            color = tint,
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                        )
                    }
                }
                Spacer(Modifier.height(2.dp))
                Text(
                    text = peer.keyId.take(16) + "…",
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                val pubKeyShort = peer.pubkeyEd25519Base64.take(10) + "…"
                Text(
                    text = "pubkey • $pubKeyShort",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                peer.firstSeen.let { fs ->
                    Text(
                        text = "first seen • ${formatInstant(fs)}",
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                    )
                }
            }

            // Trailing: pick chip (picker mode)
            if (pickerMode) {
                AssistChip(
                    onClick = onPick,
                    label = { Text("Choose", fontSize = 12.sp) },
                    modifier = Modifier.testableClickable("btn_contacts_pick_${peer.keyId}") { onPick() },
                )
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// Helpers
// ═════════════════════════════════════════════════════════════════════════════

private fun trustGlyph(trust: PeerTrustState): Pair<ImageVector, Color> = when (trust) {
    PeerTrustState.TRUSTED -> Icons.Filled.Check to Color(0xFF4CAF50)
    PeerTrustState.UNKNOWN -> Icons.Filled.Person to Color(0xFF9E9E9E)
    PeerTrustState.UNTRUSTED -> Icons.Filled.Warning to Color(0xFFFF9800)
    PeerTrustState.BLOCKED -> Icons.Filled.Warning to Color(0xFFF44336)
}

private fun formatInstant(instant: Instant): String = try {
    val local = instant.toLocalDateTime(TimeZone.currentSystemDefault())
    "${local.year}-${local.monthNumber.toString().padStart(2, '0')}-${local.dayOfMonth.toString().padStart(2, '0')}"
} catch (_: Exception) {
    instant.toString().take(10)
}
