package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.PythonRuntime
import ai.ciris.mobile.shared.platform.SecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Connection status for the server.
 */
enum class ConnectionStatus {
    CONNECTED_LOCAL,   // Connected to localhost
    CONNECTED_REMOTE,  // Connected to remote URL
    DISCONNECTED,      // No connection
    CONNECTING,        // Attempting to connect
    ERROR              // Connection error
}

/**
 * ViewModel for Server Connection Manager screen.
 *
 * Manages:
 * - Server connection status monitoring
 * - Local server restart (desktop only)
 * - Remote server connection
 * - Recent connections history
 */
class ServerConnectionViewModel(
    private val apiClient: CIRISApiClient,
    private val pythonRuntime: PythonRuntime?,
    private val secureStorage: SecureStorage
) : ViewModel() {

    companion object {
        private const val TAG = "ServerConnectionVM"
        private const val POLL_INTERVAL_MS = 5000L
        private const val KEY_RECENT_CONNECTIONS = "recent_server_connections"
        private const val KEY_CURRENT_SERVER_URL = "current_server_url"
        private const val MAX_RECENT_CONNECTIONS = 5
    }

    private fun logDebug(method: String, message: String) = PlatformLogger.d(TAG, "[$method] $message")
    private fun logInfo(method: String, message: String) = PlatformLogger.i(TAG, "[$method] $message")
    private fun logError(method: String, message: String) = PlatformLogger.e(TAG, "[$method] $message")

    // Connection status
    private val _connectionStatus = MutableStateFlow(ConnectionStatus.DISCONNECTED)
    val connectionStatus: StateFlow<ConnectionStatus> = _connectionStatus.asStateFlow()

    // Current URL
    private val _currentUrl = MutableStateFlow(apiClient.baseUrl)
    val currentUrl: StateFlow<String> = _currentUrl.asStateFlow()

    // Is local server (localhost)
    private val _isLocalServer = MutableStateFlow(true)
    val isLocalServer: StateFlow<Boolean> = _isLocalServer.asStateFlow()

    // Recent connections
    private val _recentConnections = MutableStateFlow<List<String>>(emptyList())
    val recentConnections: StateFlow<List<String>> = _recentConnections.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error message
    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Status message
    private val _statusMessage = MutableStateFlow<String?>(null)
    val statusMessage: StateFlow<String?> = _statusMessage.asStateFlow()

    // Is desktop platform (for showing local server controls)
    private val _isDesktop = MutableStateFlow(pythonRuntime != null)
    val isDesktop: StateFlow<Boolean> = _isDesktop.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null

    init {
        logInfo("init", "ServerConnectionViewModel initialized")
        viewModelScope.launch {
            loadRecentConnections()
            updateLocalServerStatus()
            startPolling()
        }
    }

    /**
     * Start polling for connection status.
     */
    fun startPolling() {
        if (pollingJob?.isActive == true) return

        logInfo("startPolling", "Starting connection status polling")
        pollingJob = viewModelScope.launch {
            while (isActive) {
                checkConnectionStatus()
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Stop polling.
     */
    fun stopPolling() {
        logInfo("stopPolling", "Stopping connection status polling")
        pollingJob?.cancel()
        pollingJob = null
    }

    /**
     * Check current connection status.
     */
    private suspend fun checkConnectionStatus() {
        try {
            val status = apiClient.getSystemStatus()
            val cogState = status.cognitive_state?.uppercase() ?: ""

            if (cogState in listOf("WORK", "SETUP", "WAKEUP", "PLAY", "SOLITUDE", "DREAM")) {
                _connectionStatus.value = if (_isLocalServer.value) {
                    ConnectionStatus.CONNECTED_LOCAL
                } else {
                    ConnectionStatus.CONNECTED_REMOTE
                }
                _errorMessage.value = null
            } else if (cogState == "SHUTDOWN") {
                _connectionStatus.value = ConnectionStatus.ERROR
                _errorMessage.value = "Server is shutting down"
            } else {
                _connectionStatus.value = ConnectionStatus.CONNECTING
            }
        } catch (e: Exception) {
            logError("checkConnectionStatus", "Health check failed: ${e.message}")
            _connectionStatus.value = ConnectionStatus.DISCONNECTED
            _errorMessage.value = "Cannot connect to server"
        }
    }

    /**
     * Update whether we're connected to local or remote server.
     */
    private fun updateLocalServerStatus() {
        val url = _currentUrl.value.lowercase()
        _isLocalServer.value = url.contains("localhost") ||
                               url.contains("127.0.0.1") ||
                               url.contains("0.0.0.0")
    }

    /**
     * Connect to a remote server URL.
     */
    fun connectToUrl(url: String) {
        val method = "connectToUrl"

        // Validate URL
        val normalizedUrl = normalizeUrl(url)
        if (normalizedUrl == null) {
            _errorMessage.value = "Invalid URL format. Use http(s)://host:port"
            return
        }

        logInfo(method, "Connecting to: $normalizedUrl")
        _connectionStatus.value = ConnectionStatus.CONNECTING
        _isLoading.value = true
        _errorMessage.value = null

        viewModelScope.launch {
            try {
                // Update API client URL
                apiClient.updateBaseUrl(normalizedUrl)
                _currentUrl.value = normalizedUrl
                updateLocalServerStatus()

                // Save to storage
                secureStorage.save(KEY_CURRENT_SERVER_URL, normalizedUrl)

                // Add to recent connections
                addToRecentConnections(normalizedUrl)

                // Check connection
                checkConnectionStatus()

                if (_connectionStatus.value == ConnectionStatus.CONNECTED_LOCAL ||
                    _connectionStatus.value == ConnectionStatus.CONNECTED_REMOTE) {
                    _statusMessage.value = "Connected to $normalizedUrl"
                    logInfo(method, "Successfully connected to $normalizedUrl")
                } else {
                    _errorMessage.value = "Could not verify connection to server"
                }
            } catch (e: Exception) {
                logError(method, "Failed to connect: ${e.message}")
                _connectionStatus.value = ConnectionStatus.ERROR
                _errorMessage.value = "Connection failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Disconnect from remote and return to local server.
     */
    fun disconnectFromRemote() {
        val method = "disconnectFromRemote"
        logInfo(method, "Disconnecting from remote, returning to localhost")

        val localUrl = "http://localhost:8080"
        connectToUrl(localUrl)
    }

    /**
     * Restart the local server (desktop only).
     */
    fun restartLocalServer() {
        val method = "restartLocalServer"

        if (pythonRuntime == null) {
            logError(method, "PythonRuntime not available - not a desktop platform")
            _errorMessage.value = "Server restart only available on desktop"
            return
        }

        logInfo(method, "Restarting local server...")
        _isLoading.value = true
        _connectionStatus.value = ConnectionStatus.CONNECTING
        _statusMessage.value = "Restarting server..."
        _errorMessage.value = null

        viewModelScope.launch {
            try {
                // Shutdown existing server
                pythonRuntime.shutdown()
                delay(2000) // Wait for cleanup

                // Start server again
                val result = pythonRuntime.startServer()
                result.fold(
                    onSuccess = { url ->
                        logInfo(method, "Server restarted successfully at $url")
                        _currentUrl.value = url
                        apiClient.updateBaseUrl(url)
                        updateLocalServerStatus()
                        checkConnectionStatus()
                        _statusMessage.value = "Server restarted successfully"
                    },
                    onFailure = { e ->
                        logError(method, "Server restart failed: ${e.message}")
                        _connectionStatus.value = ConnectionStatus.ERROR
                        _errorMessage.value = "Restart failed: ${e.message}"
                    }
                )
            } catch (e: Exception) {
                logError(method, "Server restart exception: ${e.message}")
                _connectionStatus.value = ConnectionStatus.ERROR
                _errorMessage.value = "Restart error: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Stop the local server (desktop only).
     */
    fun stopLocalServer() {
        val method = "stopLocalServer"

        if (pythonRuntime == null) {
            _errorMessage.value = "Server control only available on desktop"
            return
        }

        logInfo(method, "Stopping local server...")
        _isLoading.value = true

        viewModelScope.launch {
            try {
                pythonRuntime.shutdown()
                _connectionStatus.value = ConnectionStatus.DISCONNECTED
                _statusMessage.value = "Server stopped"
                logInfo(method, "Server stopped successfully")
            } catch (e: Exception) {
                logError(method, "Stop failed: ${e.message}")
                _errorMessage.value = "Stop failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Remove a URL from recent connections.
     */
    fun removeRecentConnection(url: String) {
        viewModelScope.launch {
            val updated = _recentConnections.value.filter { it != url }
            _recentConnections.value = updated
            saveRecentConnections(updated)
        }
    }

    /**
     * Clear status message.
     */
    fun clearStatus() {
        _statusMessage.value = null
    }

    /**
     * Clear error message.
     */
    fun clearError() {
        _errorMessage.value = null
    }

    /**
     * Normalize URL to ensure it has protocol and port.
     */
    private fun normalizeUrl(url: String): String? {
        var normalized = url.trim()

        // Add protocol if missing
        if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
            normalized = "http://$normalized"
        }

        // Basic validation
        try {
            // Check for valid host:port pattern
            val afterProtocol = normalized.substringAfter("://")
            if (!afterProtocol.contains(":") || afterProtocol.isEmpty()) {
                // No port specified, add default
                normalized = if (normalized.startsWith("https://")) {
                    normalized.trimEnd('/') + ":443"
                } else {
                    normalized.trimEnd('/') + ":8080"
                }
            }

            // Remove trailing slash
            normalized = normalized.trimEnd('/')

            return normalized
        } catch (e: Exception) {
            return null
        }
    }

    /**
     * Add URL to recent connections.
     */
    private suspend fun addToRecentConnections(url: String) {
        val current = _recentConnections.value.toMutableList()

        // Remove if already exists
        current.remove(url)

        // Add to front
        current.add(0, url)

        // Limit size
        val limited = current.take(MAX_RECENT_CONNECTIONS)

        _recentConnections.value = limited
        saveRecentConnections(limited)
    }

    /**
     * Load recent connections from storage.
     */
    private suspend fun loadRecentConnections() {
        try {
            val json = secureStorage.get(KEY_RECENT_CONNECTIONS).getOrNull()
            if (!json.isNullOrBlank()) {
                val list = Json.decodeFromString<List<String>>(json)
                _recentConnections.value = list
                logDebug("loadRecentConnections", "Loaded ${list.size} recent connections")
            }

            // Load current server URL
            val savedUrl = secureStorage.get(KEY_CURRENT_SERVER_URL).getOrNull()
            if (!savedUrl.isNullOrBlank() && savedUrl != apiClient.baseUrl) {
                logInfo("loadRecentConnections", "Restoring saved server URL: $savedUrl")
                apiClient.updateBaseUrl(savedUrl)
                _currentUrl.value = savedUrl
                updateLocalServerStatus()
            }
        } catch (e: Exception) {
            logError("loadRecentConnections", "Failed to load: ${e.message}")
        }
    }

    /**
     * Save recent connections to storage.
     */
    private suspend fun saveRecentConnections(connections: List<String>) {
        try {
            val json = Json.encodeToString(connections)
            secureStorage.save(KEY_RECENT_CONNECTIONS, json)
        } catch (e: Exception) {
            logError("saveRecentConnections", "Failed to save: ${e.message}")
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopPolling()
        logInfo("onCleared", "ViewModel cleared")
    }
}
