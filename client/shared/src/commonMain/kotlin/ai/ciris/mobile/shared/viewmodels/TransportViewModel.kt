package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * ViewModel for the Transport screen (node concern).
 *
 * Two halves:
 *  - **Read**: the node's current transports — reuses [CIRISApiClient.getFederationIdentity]
 *    (GET /v1/federation/identity), which carries the Reticulum federation/signer
 *    address, peer counts, and advertised transport capabilities. No new read
 *    endpoint is invented.
 *  - **Write**: a serial LoRa / RNode radio configuration form persisted as
 *    `net.radio.*` `config:*` values via the existing owner-gated
 *    [CIRISApiClient.updateConfig] (PUT /v1/config/{key}) path.
 *
 * Radio activation is desktop-only (a sandboxed mobile node cannot open a serial
 * port); Apply always persists config, and the screen explains where it takes
 * effect.
 */
class TransportViewModel(
    private val apiClient: CIRISApiClient,
) : ViewModel() {

    companion object {
        private const val TAG = "TransportViewModel"

        // config:* keys written by the radio form (owner-gated /v1/config).
        const val KEY_ENABLED = "net.radio.enabled"
        const val KEY_SERIAL_PORT = "net.radio.serial_port"
        const val KEY_FREQUENCY_HZ = "net.radio.frequency_hz"
        const val KEY_BANDWIDTH_HZ = "net.radio.bandwidth_hz"
        const val KEY_SPREADING_FACTOR = "net.radio.spreading_factor"
        const val KEY_CODING_RATE = "net.radio.coding_rate"
        const val KEY_TX_POWER_DBM = "net.radio.tx_power_dbm"
    }

    private val _state = MutableStateFlow(TransportScreenState())
    val state: StateFlow<TransportScreenState> = _state.asStateFlow()

    private var dataLoadStarted = false

    /** Begin loading current-transport facts. Idempotent; call on screen show. */
    fun startPolling() {
        if (dataLoadStarted) return
        dataLoadStarted = true
        loadTransports()
    }

    /** Allow a fresh load next time the screen becomes visible. */
    fun stopPolling() {
        dataLoadStarted = false
    }

    fun refresh() = loadTransports()

    /** Fetch the node's current transports (federation identity aggregate). */
    fun loadTransports() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val identity = apiClient.getFederationIdentity()
                PlatformLogger.i(
                    TAG,
                    "transports loaded: signer=${identity.signerKeyId.take(12)}…, peers=${identity.peerCountTotal}",
                )
                _state.update { it.copy(identity = identity, isLoading = false, error = null) }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "loadTransports failed: ${e.message}", e)
                _state.update {
                    it.copy(isLoading = false, error = "Failed to load transports: ${e.message}")
                }
            }
        }
    }

    // ─── Radio form field updates ───────────────────────────────────────────────

    fun updateEnabled(value: Boolean) = _state.update { it.copy(radioEnabled = value) }
    fun updateSerialPort(value: String) = _state.update { it.copy(serialPort = value) }
    fun updateFrequencyHz(value: String) = _state.update { it.copy(frequencyHz = value.filter { c -> c.isDigit() }) }
    fun updateBandwidthHz(value: String) = _state.update { it.copy(bandwidthHz = value.filter { c -> c.isDigit() }) }
    fun updateSpreadingFactor(value: String) = _state.update { it.copy(spreadingFactor = value.filter { c -> c.isDigit() }) }
    fun updateCodingRate(value: String) = _state.update { it.copy(codingRate = value.filter { c -> c.isDigit() }) }
    fun updateTxPowerDbm(value: String) = _state.update { it.copy(txPowerDbm = value.filter { c -> c.isDigit() }) }

    fun clearError() = _state.update { it.copy(error = null) }
    fun clearSuccess() = _state.update { it.copy(successMessage = null) }

    /**
     * Persist the radio form as `net.radio.*` config via the owner-gated
     * /v1/config write path. Each key is written as a string value (the backend
     * config store coerces typed values). Activation happens on a desktop node
     * with the serial radio backend; on other nodes the values simply persist.
     */
    fun applyRadioConfig() {
        val s = _state.value
        viewModelScope.launch {
            _state.update { it.copy(isSaving = true, error = null, successMessage = null) }
            try {
                val reason = "Radio (LoRa/RNode) configured via Transport screen"
                apiClient.updateConfig(KEY_ENABLED, s.radioEnabled.toString(), reason)
                apiClient.updateConfig(KEY_SERIAL_PORT, s.serialPort.trim(), reason)
                apiClient.updateConfig(KEY_FREQUENCY_HZ, s.frequencyHz.trim(), reason)
                apiClient.updateConfig(KEY_BANDWIDTH_HZ, s.bandwidthHz.trim(), reason)
                apiClient.updateConfig(KEY_SPREADING_FACTOR, s.spreadingFactor.trim(), reason)
                apiClient.updateConfig(KEY_CODING_RATE, s.codingRate.trim(), reason)
                apiClient.updateConfig(KEY_TX_POWER_DBM, s.txPowerDbm.trim(), reason)
                PlatformLogger.i(TAG, "radio config applied (enabled=${s.radioEnabled}, port=${s.serialPort})")
                _state.update {
                    it.copy(isSaving = false, successMessage = "Radio configuration saved")
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "applyRadioConfig failed: ${e.message}", e)
                _state.update {
                    it.copy(isSaving = false, error = "Failed to save radio configuration: ${e.message}")
                }
            }
        }
    }

    override fun onCleared() {
        stopPolling()
        super.onCleared()
    }
}

/**
 * UI state for the Transport screen: the read-only current-transport facts plus
 * the editable radio form fields. Numeric radio fields are held as strings so the
 * text inputs round-trip cleanly (validated/coerced on write).
 */
data class TransportScreenState(
    // Read-only current transports
    val identity: FederationIdentity? = null,
    val isLoading: Boolean = false,
    val error: String? = null,
    val successMessage: String? = null,
    // Radio (LoRa / RNode) form
    val radioEnabled: Boolean = false,
    val serialPort: String = "",
    val frequencyHz: String = "868000000",
    val bandwidthHz: String = "125000",
    val spreadingFactor: String = "7",
    val codingRate: String = "5",
    val txPowerDbm: String = "17",
    val isSaving: Boolean = false,
)
