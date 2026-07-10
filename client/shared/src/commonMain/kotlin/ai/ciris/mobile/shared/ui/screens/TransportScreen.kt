package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.TransportScreenState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * Transport — node transports + serial LoRa (RNode) radio configuration.
 *
 * Top: a read-only "Current transports" card sourced from the node's federation
 * identity (signer/Reticulum address, peer counts, advertised transport
 * capabilities). Bottom: the radio configuration form whose Apply persists
 * `net.radio.*` config via the owner-gated /v1/config write path.
 *
 * Radio support is desktop-only (a sandboxed mobile node cannot open a serial
 * port); Apply always persists config and a hint explains where it activates.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransportScreen(
    state: TransportScreenState,
    onRefresh: () -> Unit,
    onEnabledChange: (Boolean) -> Unit,
    onSerialPortChange: (String) -> Unit,
    onFrequencyChange: (String) -> Unit,
    onBandwidthChange: (String) -> Unit,
    onSpreadingFactorChange: (String) -> Unit,
    onCodingRateChange: (String) -> Unit,
    onTxPowerChange: (String) -> Unit,
    onApply: () -> Unit,
    isNodeMode: Boolean = true,
    modifier: Modifier = Modifier,
) {
    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
                .testable("screen_transport"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Spacer(Modifier.height(36.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(
                        text = localizedString("transport.title").ifEmpty { "Transport" },
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = localizedString("transport.subtitle").ifEmpty { "Reticulum + radio · this node" },
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(
                    onClick = onRefresh,
                    modifier = Modifier.testableClickable("btn_transport_refresh") { onRefresh() },
                ) {
                    Text(localizedString("transport.refresh").ifEmpty { "Refresh" })
                }
            }

            // ── Current transports (read-only) ──────────────────────────────────
            TransportCard(
                title = localizedString("transport.current_transports").ifEmpty { "Current transports" },
                testTag = "card_transport_current",
            ) {
                val identity = state.identity
                if (state.isLoading && identity == null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(8.dp))
                        Text(localizedString("transport.loading").ifEmpty { "Loading…" })
                    }
                } else if (identity == null) {
                    Text(
                        text = localizedString("transport.unavailable")
                            .ifEmpty { "Transport facts unavailable (node degraded?)." },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    TransportRow(
                        localizedString("transport.reticulum_address").ifEmpty { "Reticulum address" },
                        identity.signerKeyId.ifBlank { "—" },
                        "row_transport_address",
                        mono = true,
                    )
                    TransportRow(
                        localizedString("transport.peers").ifEmpty { "Peers" },
                        "${identity.peerCountTotal} (${identity.peerCountCanonical} canonical)",
                        "row_transport_peers",
                    )
                    if (identity.capabilities.isNotEmpty()) {
                        TransportRow(
                            localizedString("transport.capabilities").ifEmpty { "Capabilities" },
                            identity.capabilities.joinToString(", "),
                            "row_transport_capabilities",
                        )
                    }
                }
            }

            // ── Radio (LoRa / RNode) configuration ──────────────────────────────
            TransportCard(
                title = localizedString("transport.radio_title").ifEmpty { "Radio (LoRa / RNode)" },
                testTag = "card_transport_radio",
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().testable("row_radio_enabled"),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        localizedString("transport.radio_enable").ifEmpty { "Enable radio" },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Switch(
                        checked = state.radioEnabled,
                        onCheckedChange = onEnabledChange,
                        modifier = Modifier.testable("toggle_radio_enabled"),
                    )
                }

                RadioField(
                    label = localizedString("transport.radio_serial_port").ifEmpty { "Serial port" },
                    value = state.serialPort,
                    onValueChange = onSerialPortChange,
                    testTag = "input_radio_serial_port",
                    placeholder = "/dev/tty.usbserial-XXXX  or  COM3",
                )
                RadioField(
                    label = localizedString("transport.radio_frequency").ifEmpty { "Frequency (Hz)" },
                    value = state.frequencyHz,
                    onValueChange = onFrequencyChange,
                    testTag = "input_radio_frequency",
                    numeric = true,
                    placeholder = "868000000",
                )
                RadioField(
                    label = localizedString("transport.radio_bandwidth").ifEmpty { "Bandwidth (Hz)" },
                    value = state.bandwidthHz,
                    onValueChange = onBandwidthChange,
                    testTag = "input_radio_bandwidth",
                    numeric = true,
                    placeholder = "125000",
                )
                RadioField(
                    label = localizedString("transport.radio_spreading_factor").ifEmpty { "Spreading factor (7–12)" },
                    value = state.spreadingFactor,
                    onValueChange = onSpreadingFactorChange,
                    testTag = "input_radio_spreading_factor",
                    numeric = true,
                    placeholder = "7",
                )
                RadioField(
                    label = localizedString("transport.radio_coding_rate").ifEmpty { "Coding rate (5–8)" },
                    value = state.codingRate,
                    onValueChange = onCodingRateChange,
                    testTag = "input_radio_coding_rate",
                    numeric = true,
                    placeholder = "5",
                )
                RadioField(
                    label = localizedString("transport.radio_tx_power").ifEmpty { "TX power (dBm)" },
                    value = state.txPowerDbm,
                    onValueChange = onTxPowerChange,
                    testTag = "input_radio_tx_power",
                    numeric = true,
                    placeholder = "17",
                )

                // Honest note: desktop-only activation.
                Text(
                    text = localizedString("transport.radio_desktop_only").ifEmpty {
                        "Radio support is desktop-only — a sandboxed mobile node cannot open a serial port. " +
                            "Apply still persists this configuration; it activates on a desktop node with the radio backend."
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (!isNodeMode) {
                    Text(
                        text = localizedString("transport.agent_mode_hint")
                            .ifEmpty { "This node is in agent mode; transport config applies to the underlying node." },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                state.error?.let { err ->
                    Text(err, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
                state.successMessage?.let { msg ->
                    Text(msg, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                }

                Button(
                    onClick = onApply,
                    enabled = !state.isSaving,
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_radio_apply") { onApply() },
                ) {
                    if (state.isSaving) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary,
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(localizedString("transport.radio_apply").ifEmpty { "Apply" })
                }
            }
        }
    }
}

@Composable
private fun TransportCard(title: String, testTag: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RadioField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    testTag: String,
    numeric: Boolean = false,
    placeholder: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        placeholder = placeholder?.let { { Text(it, style = MaterialTheme.typography.bodySmall) } },
        keyboardOptions = if (numeric) {
            KeyboardOptions(keyboardType = KeyboardType.Number)
        } else {
            KeyboardOptions.Default
        },
        modifier = Modifier.fillMaxWidth().testable(testTag),
    )
}

@Composable
private fun TransportRow(label: String, value: String, testTag: String, mono: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth().testable(testTag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
        )
    }
}
