package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.AccordSettingsData
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.LensDeletionResult
import ai.ciris.mobile.shared.api.LensIdentifierData
import ai.ciris.mobile.shared.platform.AppRestarter
import ai.ciris.mobile.shared.platform.EnvFileUpdater
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel for the Data Management screen.
 * Handles DSAR self-service for local data and CIRISLens trace deletion.
 */
class DataManagementViewModel(
    private val apiClient: CIRISApiClient,
    private val secureStorage: SecureStorage,
    private val envFileUpdater: EnvFileUpdater
) : ViewModel() {

    companion object {
        private const val TAG = "DataManagementVM"
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
            else -> PlatformLogger.i(TAG, fullMessage)
        }
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // ========== State Flows ==========

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _lensIdentifier = MutableStateFlow<LensIdentifierData?>(null)
    val lensIdentifier: StateFlow<LensIdentifierData?> = _lensIdentifier.asStateFlow()

    private val _accordSettings = MutableStateFlow<AccordSettingsData?>(null)
    val accordSettings: StateFlow<AccordSettingsData?> = _accordSettings.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Deletion state
    private val _isDeletingLensTraces = MutableStateFlow(false)
    val isDeletingLensTraces: StateFlow<Boolean> = _isDeletingLensTraces.asStateFlow()

    private val _lensDeletionResult = MutableStateFlow<LensDeletionResult?>(null)
    val lensDeletionResult: StateFlow<LensDeletionResult?> = _lensDeletionResult.asStateFlow()

    // Reset state (soft reset - preserves signing key)
    private val _isResetting = MutableStateFlow(false)
    val isResetting: StateFlow<Boolean> = _isResetting.asStateFlow()

    private val _resetSuccess = MutableStateFlow(false)
    val resetSuccess: StateFlow<Boolean> = _resetSuccess.asStateFlow()

    // Wipe signing key state (DANGER - destroys wallet access)
    private val _isWipingSigningKey = MutableStateFlow(false)
    val isWipingSigningKey: StateFlow<Boolean> = _isWipingSigningKey.asStateFlow()

    private val _wipeSigningKeySuccess = MutableStateFlow(false)
    val wipeSigningKeySuccess: StateFlow<Boolean> = _wipeSigningKeySuccess.asStateFlow()

    // Legacy aliases for backwards compatibility
    val isFactoryResetting: StateFlow<Boolean> = _isResetting
    val factoryResetSuccess: StateFlow<Boolean> = _resetSuccess

    init {
        logDebug("init", "DataManagementViewModel created")
    }

    /**
     * Load lens identifier and accord settings.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing data management info")

        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null

            try {
                // Load lens identifier (shows agent hash and trace count)
                val lensData = apiClient.getLensIdentifier()
                _lensIdentifier.value = lensData
                logInfo(method, "Lens identifier loaded: hash=${lensData.agentIdHash.take(8)}..., " +
                        "consent=${lensData.consentGiven}, tracesSent=${lensData.tracesSent}")

                // Also load accord settings for more detailed info
                try {
                    logDebug(method, "Fetching accord settings...")
                    val accordData = apiClient.getAccordSettings()
                    _accordSettings.value = accordData
                    logInfo(method, "Accord settings loaded: consent=${accordData.consentGiven}, " +
                            "level=${accordData.traceLevel}, eventsSent=${accordData.eventsSent}, " +
                            "agentIdHash=${accordData.agentIdHash.take(8)}...")
                } catch (e: Exception) {
                    // Accord adapter might not be loaded - this causes UI to show "Enable" button
                    _accordSettings.value = null
                    logWarn(method, "Accord settings not available (adapter not loaded?): ${e.message}")
                    logWarn(method, "Exception type: ${e::class.simpleName}, full: $e")
                }

            } catch (e: Exception) {
                logError(method, "Failed to load data: ${e.message}")
                _errorMessage.value = "Failed to load data management info: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Request deletion of CIRISLens traces.
     * This is an irreversible GDPR Article 17 self-service operation.
     */
    fun deleteLensTraces(reason: String? = null) {
        val method = "deleteLensTraces"
        logInfo(method, "Requesting deletion of CIRISLens traces")

        viewModelScope.launch {
            _isDeletingLensTraces.value = true
            _lensDeletionResult.value = null
            _errorMessage.value = null

            try {
                val result = apiClient.deleteLensTraces(reason)
                _lensDeletionResult.value = result

                if (result.success) {
                    logInfo(method, "Deletion request accepted: " +
                            "lensAccepted=${result.lensRequestAccepted}, " +
                            "localRevoked=${result.localConsentRevoked}")
                    // Refresh to show updated state
                    refresh()
                } else {
                    logError(method, "Deletion request failed: ${result.message}")
                    _errorMessage.value = result.message
                }

            } catch (e: Exception) {
                logError(method, "Failed to request deletion: ${e.message}")
                _errorMessage.value = "Failed to request trace deletion: ${e.message}"
            } finally {
                _isDeletingLensTraces.value = false
            }
        }
    }

    /**
     * Reset account - wipe local data but PRESERVE signing key.
     * This allows wallet access to be retained after reset.
     *
     * Deletes:
     * - .env file (configuration)
     * - data directory (databases, audit logs, memory graphs)
     *
     * Preserves:
     * - Signing key (wallet access maintained)
     *
     * @param onSuccess Callback before app restart
     */
    fun factoryReset(onSuccess: () -> Unit = {}) {
        val method = "factoryReset"
        logInfo(method, "Reset account - clearing data but PRESERVING signing key")

        viewModelScope.launch {
            _isResetting.value = true
            _errorMessage.value = null

            try {
                // Clear data directory (databases, audit logs, etc.) but PRESERVE signing key
                logInfo(method, "Clearing data directory (preserving signing key for wallet access)...")
                envFileUpdater.clearDataOnly().getOrThrow()
                logInfo(method, "Data cleared, signing key preserved")

                // Delete the .env file to trigger setup wizard
                envFileUpdater.deleteEnvFile().getOrThrow()
                logInfo(method, ".env file deleted")

                logInfo(method, "Reset complete - restarting app for setup wizard")
                _resetSuccess.value = true

                // Invoke callback for any cleanup before restart
                onSuccess()

                // Small delay to let UI update
                kotlinx.coroutines.delay(100)

                // Restart the app completely
                logInfo(method, "Triggering app restart...")
                AppRestarter.restartApp()

            } catch (e: Exception) {
                logError(method, "Failed to reset: ${e.message}")
                _errorMessage.value = "Failed to reset: ${e.message}"
                _isResetting.value = false
            }
        }
    }

    /**
     * DANGER: Wipe the agent signing key.
     *
     * WARNING: This will PERMANENTLY DESTROY wallet access!
     * The signing key is used to derive the wallet address.
     * Without the key, any funds in the wallet are LOST FOREVER.
     *
     * Only use this if:
     * - User explicitly confirms they understand the risk
     * - User has verified wallet balance is zero
     * - User wants a completely fresh agent identity
     *
     * Deletes:
     * - Signing key (encrypted file + keystore entry)
     * - Data directory (databases, audit logs, memory graphs)
     * - .env file (configuration)
     *
     * @param onSuccess Callback before app restart
     */
    fun wipeSigningKey(onSuccess: () -> Unit = {}) {
        val method = "wipeSigningKey"
        logWarn(method, "DANGER: Wiping agent signing key - wallet access will be DESTROYED")

        viewModelScope.launch {
            _isWipingSigningKey.value = true
            _errorMessage.value = null

            try {
                // Clear signing key AND data directory
                logWarn(method, "Clearing signing key and data directory...")
                envFileUpdater.clearSigningKey().getOrThrow()
                logWarn(method, "Signing key DESTROYED - wallet access lost")

                // Delete the .env file
                envFileUpdater.deleteEnvFile().getOrThrow()
                logInfo(method, ".env file deleted")

                logInfo(method, "Complete wipe finished - restarting app for setup wizard")
                _wipeSigningKeySuccess.value = true

                // Invoke callback for any cleanup before restart
                onSuccess()

                // Small delay to let UI update
                kotlinx.coroutines.delay(100)

                // Restart the app completely
                logInfo(method, "Triggering app restart...")
                AppRestarter.restartApp()

            } catch (e: Exception) {
                logError(method, "Failed to wipe signing key: ${e.message}")
                _errorMessage.value = "Failed to wipe signing key: ${e.message}"
                _isWipingSigningKey.value = false
            }
        }
    }

    /**
     * Update accord metrics consent setting.
     */
    fun updateAccordConsent(consent: Boolean) {
        val method = "updateAccordConsent"
        logInfo(method, "Updating accord consent to: $consent")

        viewModelScope.launch {
            try {
                val result = apiClient.updateAccordSettings(consentGiven = consent)
                if (result.success) {
                    logInfo(method, "Consent updated: ${result.changes}")
                    refresh()
                } else {
                    logError(method, "Failed to update consent: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Failed to update consent: ${e.message}")
                _errorMessage.value = "Failed to update consent: ${e.message}"
            }
        }
    }

    // Loading adapter state
    private val _isLoadingAdapter = MutableStateFlow(false)
    val isLoadingAdapter: StateFlow<Boolean> = _isLoadingAdapter.asStateFlow()

    /**
     * Load the accord metrics adapter and enable consent.
     * This allows users to opt-in to CIRISAccord without using command line.
     */
    fun enableAccordMetrics() {
        val method = "enableAccordMetrics"
        logInfo(method, "Loading accord metrics adapter with consent enabled")

        viewModelScope.launch {
            _isLoadingAdapter.value = true
            _errorMessage.value = null

            try {
                // Load adapter with consent_given=true and persist=true
                val config = mapOf(
                    "consent_given" to true,
                    "trace_level" to "detailed"
                )
                val result = apiClient.loadAdapterWithConfig(
                    adapterType = "ciris_accord_metrics",
                    config = config,
                    persist = true
                )

                if (result.success) {
                    logInfo(method, "Accord metrics adapter loaded: ${result.adapterId}")
                    // Refresh to show the new adapter state
                    refresh()
                } else {
                    logError(method, "Failed to load adapter: ${result.message}")
                    _errorMessage.value = result.message ?: "Failed to load accord metrics adapter"
                }
            } catch (e: Exception) {
                logError(method, "Failed to load adapter: ${e.message}")
                _errorMessage.value = "Failed to enable accord metrics: ${e.message}"
            } finally {
                _isLoadingAdapter.value = false
            }
        }
    }

    // ========== Utilities ==========

    fun clearError() {
        _errorMessage.value = null
    }

    fun clearDeletionResult() {
        _lensDeletionResult.value = null
    }

    fun clearFactoryResetSuccess() {
        _resetSuccess.value = false
    }

    fun clearWipeSigningKeySuccess() {
        _wipeSigningKeySuccess.value = false
    }
}
