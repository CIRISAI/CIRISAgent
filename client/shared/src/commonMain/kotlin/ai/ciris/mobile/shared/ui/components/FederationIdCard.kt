package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
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
            val keyId = aggregate?.keyId
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SelectionContainer(modifier = Modifier.weight(1f)) {
                    Text(
                        text = keyId ?: localizedString("network.federation_id.initializing"),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        color = if (keyId != null) {
                            MaterialTheme.colorScheme.onSurface
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontSize = 13.sp,
                        modifier = Modifier.testable("federation_id_key"),
                    )
                }
                // Always render the copy IconButton — `enabled` gates the
                // actual copy/state change (same composition-timing-race
                // rationale as btn_copy_signer_key above).
                run {
                    val hasKey = !keyId.isNullOrBlank()
                    IconButton(
                        onClick = {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                                scope.launch {
                                    delay(1500)
                                    copied = false
                                }
                            }
                        },
                        enabled = hasKey,
                        modifier = Modifier.testableClickable("federation_id_copy") {
                            if (hasKey) {
                                clipboard.setText(AnnotatedString(keyId!!))
                                copied = true
                            }
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
            }
            if (copied) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = localizedString("network.identity_card.copied"),
                    style = MaterialTheme.typography.labelSmall,
                    color = CIRISColors.SuccessGreen,
                )
            }

            if (aggregate != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = localizedString("network.federation_id.pubkey_label") +
                        ": " + pubkeyShortForm(aggregate.ed25519PubkeyB64),
                    style = MaterialTheme.typography.labelMedium,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
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

