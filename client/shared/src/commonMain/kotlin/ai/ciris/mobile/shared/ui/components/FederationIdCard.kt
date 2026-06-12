package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.FederationIdentityAggregate
import ai.ciris.mobile.shared.models.federation.FederationIdentityResponse
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ai.ciris.mobile.shared.ui.icons.*

// ═══════════════════════════════════════════════════════════════════════════
// Federation ID card (persist LocalIdentityAggregate)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Compact "Federation ID" card rendered right next to the NodeCode
 * connect/share card. Shows persist's `key_id` — THE address production
 * lens / registry servers use to reach this node (CIRISPersist#198,
 * CEG §5.6.8.8.2) — plus a short form of the Ed25519 pubkey and chips
 * for which capability keys are present.
 *
 * Graceful 503: [federationId] is null both while loading and when the
 * backend reports the persist identity is still initializing, so the
 * card renders an "Identity initializing…" state instead of an error.
 */
@Composable
fun FederationIdCard(federationId: FederationIdentityResponse?) {
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testable("federation_id_card"),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = localizedString("network.federation_id.title"),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = localizedString("network.federation_id.hint"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 16.sp,
            )
            Spacer(Modifier.height(8.dp))

            val aggregate = federationId?.aggregate
            if (aggregate == null) {
                Text(
                    text = localizedString("network.federation_id.initializing"),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp,
                    modifier = Modifier.testable("federation_id_key"),
                )
            } else {
                // ── Reticulum transport — THE federation-routable address ──
                Row(
                    verticalAlignment = Alignment.Top,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = localizedString("network.federation_id.cap_reticulum"),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = CIRISColors.AccentCyan,
                        )
                        SelectionContainer {
                            Text(
                                text = aggregate.reticulumEd25519PubkeyB64
                                    ?: aggregate.reticulumX25519PubkeyB64
                                    ?: localizedString("network.federation_id.initializing"),
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.testable("federation_id_key"),
                            )
                        }
                        aggregate.reticulumX25519PubkeyB64?.let { x ->
                            if (aggregate.reticulumEd25519PubkeyB64 != null) {
                                Text(
                                    text = "x25519: $x",
                                    style = MaterialTheme.typography.labelSmall,
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = 10.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                    // Copy the COMPOSITE identity (every key role, labeled).
                    IconButton(
                        onClick = {
                            clipboard.setText(AnnotatedString(compositeIdentityText(aggregate)))
                            copied = true
                            scope.launch {
                                delay(1500)
                                copied = false
                            }
                        },
                        modifier = Modifier.testableClickable("federation_id_copy") {
                            clipboard.setText(AnnotatedString(compositeIdentityText(aggregate)))
                            copied = true
                        },
                    ) {
                        Icon(
                            imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                            contentDescription = localizedString("network.federation_id.copy_key_id"),
                            tint = CIRISColors.AccentCyan,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
                if (copied) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = localizedString("network.identity_card.copied"),
                        style = MaterialTheme.typography.labelSmall,
                        color = CIRISColors.SuccessGreen,
                    )
                }
                Spacer(Modifier.height(10.dp))

                // ── Composite key material ─────────────────────────────────
                CompositeKeyRow(
                    label = localizedString("network.federation_id.cap_signing"),
                    value = aggregate.ed25519PubkeyB64,
                )
                aggregate.mlDsa65PubkeyB64?.let {
                    CompositeKeyRow(
                        label = localizedString("network.federation_id.cap_signing") +
                            " · " + localizedString("network.federation_id.cap_pqc"),
                        value = it,
                    )
                }
                aggregate.contentX25519PubkeyB64?.let {
                    CompositeKeyRow(
                        label = localizedString("network.federation_id.cap_content"),
                        value = it,
                    )
                }
                aggregate.contentMlKem768PubkeyB64?.let {
                    CompositeKeyRow(
                        label = localizedString("network.federation_id.cap_content") +
                            " · " + localizedString("network.federation_id.cap_pqc"),
                        value = it,
                    )
                }
                Spacer(Modifier.height(6.dp))
                // persist key-id ALIAS (registry lookup handle) — small caption,
                // not the headline: an alias is not a federation address.
                Text(
                    text = "key id: " + aggregate.keyId,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (aggregate != null) {
                Spacer(Modifier.height(8.dp))
                // (stable tag, localized label) — present = non-null key material.
                val capabilities = buildList {
                    add("signing" to localizedString("network.federation_id.cap_signing"))
                    if (aggregate.hasPqc) {
                        add("pqc" to localizedString("network.federation_id.cap_pqc"))
                    }
                    if (aggregate.hasReticulum) {
                        add("reticulum" to localizedString("network.federation_id.cap_reticulum"))
                    }
                    if (aggregate.hasContentEncryption) {
                        add("content" to localizedString("network.federation_id.cap_content"))
                    }
                }
                FederationCapabilityChips(capabilities)
            }
        }
    }
}

/**
 * Capability-key chips for the Federation ID card. Mirrors
 * [FlowRowChips] visually but takes (stable tag, localized label)
 * pairs so test tags stay locale-independent.
 */
@Composable
internal fun FederationCapabilityChips(items: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (tag, label) ->
                    AssistChip(
                        onClick = {},
                        label = {
                            Text(
                                text = label,
                                style = MaterialTheme.typography.labelSmall,
                                fontSize = 11.sp,
                            )
                        },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = CIRISColors.SignetTeal.copy(alpha = 0.15f),
                            labelColor = CIRISColors.AccentCyan,
                        ),
                        modifier = Modifier.testable("chip_federation_id_$tag"),
                    )
                }
            }
        }
    }
}

/**
 * Short display form of a base64 pubkey: hex of the first 6 decoded
 * bytes (12 hex chars) + ellipsis. No multiplatform SHA-256 is wired
 * into commonMain, so this is a key-prefix short form, not a hash
 * fingerprint; falls back to the b64 head when decoding fails.
 */
/** One labeled, wrapping, selectable mono row of composite key material. */
@Composable
private fun CompositeKeyRow(label: String, value: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp)) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        SelectionContainer {
            Text(
                text = value,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                fontSize = 10.sp,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

/** The composite identity as labeled lines — what the copy button copies. */
internal fun compositeIdentityText(a: FederationIdentityAggregate): String = buildString {
    appendLine("key_id: ${a.keyId}")
    appendLine("signing_ed25519: ${a.ed25519PubkeyB64}")
    a.mlDsa65PubkeyB64?.let { appendLine("signing_ml_dsa_65: $it") }
    a.reticulumEd25519PubkeyB64?.let { appendLine("reticulum_ed25519: $it") }
    a.reticulumX25519PubkeyB64?.let { appendLine("reticulum_x25519: $it") }
    a.contentX25519PubkeyB64?.let { appendLine("content_x25519: $it") }
    a.contentMlKem768PubkeyB64?.let { appendLine("content_ml_kem_768: $it") }
}.trimEnd()

@OptIn(ExperimentalEncodingApi::class)
internal fun pubkeyShortForm(pubkeyB64: String): String {
    return try {
        val bytes = Base64.decode(pubkeyB64)
        bytes.take(6).joinToString("") { byte ->
            (byte.toInt() and 0xFF).toString(16).padStart(2, '0')
        } + "…"
    } catch (_: Exception) {
        pubkeyB64.take(12) + "…"
    }
}

