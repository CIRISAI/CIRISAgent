package ai.ciris.mobile.shared.platform

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.CoroutineScope
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android implementation of Python runtime
 * Note: Actual Python/Chaquopy initialization must happen in MainActivity
 * This implementation manages state and reads logcat for service status
 */
actual class PythonRuntime : PythonRuntimeProtocol {

    companion object {
        private const val TAG = "PythonRuntime"

        // Track unique services that have started
        private val startedServices = mutableSetOf<Int>()

        // Shared state for service count (updated by logcat reader)
        @Volatile
        var servicesOnline: Int = 0
            private set

        @Volatile
        var totalServices: Int = 22
            private set

        /**
         * Track if server was started by THIS process (not orphaned)
         * Prevents SmartStartup from killing our own server on activity recreation
         * Reset only when process dies (JVM static lifetime).
         * Copied from MainActivity.kt lines 187-189
         */
        @Volatile
        private var serverStartedByThisProcess = false

        /**
         * Update service count (called from logcat reader)
         * Tracks unique service numbers since they don't start sequentially
         */
        fun updateServiceCount(serviceNum: Int, total: Int = 22) {
            synchronized(startedServices) {
                startedServices.add(serviceNum)
                servicesOnline = startedServices.size
                totalServices = total
            }
            Log.d(TAG, "Service $serviceNum started, total: $servicesOnline/$total")
        }

        /**
         * Reset service tracking (for app restart)
         */
        fun resetServiceCount() {
            synchronized(startedServices) {
                startedServices.clear()
                servicesOnline = 0
            }
        }

        /**
         * Reset server ownership flag
         */
        fun resetServerOwnership() {
            serverStartedByThisProcess = false
        }
    }

    private var pythonInitialized = false
    private var serverStarted = false

    // Server URL - must use localhost (not 127.0.0.1) for Same-Origin Policy
    actual override val serverUrl: String = "http://localhost:8080"

    /**
     * Mark Python as initialized (called from MainActivity after Chaquopy starts)
     */
    fun markPythonInitialized() {
        pythonInitialized = true
    }

    /**
     * Mark server as started (called from MainActivity after mobile_main runs)
     */
    fun markServerStarted() {
        serverStarted = true
    }

    actual override suspend fun initialize(pythonHome: String): Result<Unit> = withContext(Dispatchers.IO) {
        pythonInitialized = true
        Result.success(Unit)
    }

    actual override suspend fun startServer(): Result<String> = withContext(Dispatchers.IO) {
        serverStarted = true
        Result.success("http://localhost:8080")
    }

    actual override suspend fun checkHealth(): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val url = URL("http://localhost:8080/v1/system/health")
            val connection = url.openConnection() as HttpURLConnection

            connection.apply {
                requestMethod = "GET"
                connectTimeout = 5000
                readTimeout = 5000
            }

            val healthy = connection.responseCode == 200
            connection.disconnect()

            Result.success(healthy)
        } catch (e: Exception) {
            Result.success(false)
        }
    }

    actual override suspend fun getServicesStatus(): Result<Pair<Int, Int>> = withContext(Dispatchers.IO) {
        // Return the cached values from logcat parsing
        Result.success(servicesOnline to totalServices)
    }

    actual override fun shutdown() {
        serverStarted = false
    }

    actual override fun isInitialized(): Boolean {
        return pythonInitialized
    }

    actual override fun isServerStarted(): Boolean {
        return serverStarted
    }

    /**
     * Start Python server with full lifecycle management
     * Extracted from MainActivity.kt lines 1485-1660
     *
     * NOTE: This is a simplified version for the shared module.
     * The full implementation with Chaquopy calls must remain in MainActivity.
     * This provides the interface for future migration.
     */
    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> = withContext(Dispatchers.IO) {
        try {
            onStatus?.invoke("Starting CIRIS runtime...")
            Log.i(TAG, "Starting Python server...")

            // CRITICAL: Check if we already started a server in this process
            // This prevents SmartStartup from killing our own server on activity recreation
            if (serverStartedByThisProcess && isExistingServerRunning()) {
                Log.i(TAG, "[SmartStartup] ⏩ SKIPPING - server was started by THIS process")
                Log.i(TAG, "[SmartStartup] Activity was recreated but server is still running - reconnecting")
                onStatus?.invoke("Reconnecting to existing session...")

                // Go straight to health check polling to reconnect
                val maxAttempts = 30  // Shorter wait for reconnect
                var attempts = 0
                var isHealthy = false

                while (attempts < maxAttempts && !isHealthy) {
                    delay(500)
                    attempts++
                    isHealthy = checkServerHealth().getOrDefault(false)
                }

                if (isHealthy) {
                    serverStarted = true
                    onStatus?.invoke("✓ Reconnected to CIRIS runtime")
                    return@withContext Result.success(serverUrl)
                } else {
                    // Server died while we were reconnecting - clear flag and restart
                    Log.w(TAG, "[SmartStartup] Server died during reconnect - will restart")
                    serverStartedByThisProcess = false
                    onStatus?.invoke("⚠ Server stopped - restarting...")
                    // Fall through to normal startup
                }
            }

            // Smart startup: Check for and handle existing server session (orphan from previous app session)
            if (isExistingServerRunning()) {
                Log.i(TAG, "[SmartStartup] Detected ORPHAN server on port 8080 (not started by this process)")
                onStatus?.invoke("Found orphan server - shutting down...")

                // Try graceful shutdown first
                if (shutdownExistingServer(onStatus)) {
                    onStatus?.invoke("Waiting for previous session to end...")
                    val shutdownOk = waitForServerShutdown(10)
                    if (shutdownOk) {
                        onStatus?.invoke("✓ Previous session ended")
                        // Add a small delay to ensure port is fully released
                        delay(500)
                    } else {
                        onStatus?.invoke("⚠ Previous session still running - may fail to bind")
                    }
                } else {
                    onStatus?.invoke("⚠ Could not reach previous session - proceeding anyway")
                }
            }

            // NOTE: Actual Python.getInstance() and mobile_main.main() call
            // must happen in MainActivity with Chaquopy context.
            // This is a placeholder for the shared module interface.
            onStatus?.invoke("Python server start NOT IMPLEMENTED in shared module")
            Log.w(TAG, "startPythonServer() must be implemented in MainActivity with Chaquopy")

            Result.failure(Exception("Not implemented - call from MainActivity"))
        } catch (e: Exception) {
            serverStartedByThisProcess = false  // Clear flag on exception
            Log.e(TAG, "Failed to start server: ${e.message}", e)
            onStatus?.invoke("❌ Failed to start CIRIS: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Inject Python configuration from map
     * Extracted from MainActivity.kt lines 822-852
     *
     * Sets System properties for Python to read
     */
    actual override fun injectPythonConfig(config: Map<String, String>) {
        try {
            val apiBase = config["OPENAI_API_BASE"]
            val apiKey = config["OPENAI_API_KEY"]

            if (!apiBase.isNullOrEmpty()) {
                System.setProperty("OPENAI_API_BASE", apiBase)
                Log.i(TAG, "Injected OPENAI_API_BASE from config")
            }

            if (!apiKey.isNullOrEmpty()) {
                System.setProperty("OPENAI_API_KEY", apiKey)
                Log.i(TAG, "Injected OPENAI_API_KEY from config")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to inject Python config: ${e.message}")
        }
    }

    /**
     * Check if existing server is running
     * Copied from MainActivity.kt lines 1241-1254
     */
    private suspend fun isExistingServerRunning(): Boolean = withContext(Dispatchers.IO) {
        try {
            val url = URL("$serverUrl/v1/system/health")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 1000
            connection.readTimeout = 1000
            connection.requestMethod = "GET"
            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Check server health, returning Result for compatibility with SmartStartup logic
     */
    private suspend fun checkServerHealth(): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            Result.success(isExistingServerRunning())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Wait for an existing server to fully shut down
     * Copied from MainActivity.kt lines 1471-1483
     */
    private suspend fun waitForServerShutdown(maxWaitSeconds: Int = 10): Boolean {
        var waitedSeconds = 0
        while (waitedSeconds < maxWaitSeconds) {
            if (!isExistingServerRunning()) {
                Log.i(TAG, "[SmartStartup] Existing server has shut down after ${waitedSeconds}s")
                return true
            }
            delay(1000)
            waitedSeconds++
        }
        Log.w(TAG, "[SmartStartup] Existing server did not shut down within ${maxWaitSeconds}s")
        return false
    }

    /**
     * Attempt to shut down an existing server gracefully via API
     * Simplified version - uses ServerManager internally
     * Copied from MainActivity.kt lines 1305-1410
     */
    private suspend fun shutdownExistingServer(onStatus: ((String) -> Unit)?): Boolean {
        // This is a simplified stub - the full implementation should use ServerManager
        // For now, just return false to indicate we can't shut down
        Log.w(TAG, "[SmartStartup] shutdownExistingServer() - simplified stub")
        return false
    }
}

/**
 * Factory function to create Android Python runtime
 */
actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
