package ai.ciris.mobile.shared.platform

/**
 * Protocol/interface for Python runtime operations.
 * Allows dependency injection and testability without subclassing expect classes.
 *
 * Implementations:
 * - PythonRuntime (actual platform implementations)
 * - Test fakes in commonTest
 */
interface PythonRuntimeProtocol {
    /**
     * Initialize Python interpreter
     * @param pythonHome Path to Python installation (platform-specific)
     * @return Result with Unit on success, exception on failure
     */
    suspend fun initialize(pythonHome: String): Result<Unit>

    /**
     * Start CIRIS FastAPI server on localhost:8080
     * Calls mobile_main.py to launch the CIRIS engine
     * @return Result with server URL on success
     */
    suspend fun startServer(): Result<String>

    /**
     * Start Python server with full lifecycle management
     *
     * This handles:
     * - SmartStartup detection (reconnect vs restart)
     * - Orphan server shutdown
     * - Python mobile_main.main() invocation
     * - Health check polling
     *
     * @param onStatus Callback for status updates (for UI)
     * @return Result with server URL on success
     */
    suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String>

    /**
     * Inject Python configuration from encrypted preferences
     *
     * Sets environment variables:
     * - OPENAI_API_BASE
     * - OPENAI_API_KEY
     *
     * @param config Map of config key-value pairs
     */
    fun injectPythonConfig(config: Map<String, String>)

    /**
     * Check if CIRIS server is responding to health checks
     * Polls http://localhost:8080/v1/system/health
     * @return Result with true if healthy, false if not yet ready
     */
    suspend fun checkHealth(): Result<Boolean>

    /**
     * Get number of services online
     * Parses telemetry from /v1/telemetry/unified
     * @return Result with (servicesOnline, servicesTotal)
     */
    suspend fun getServicesStatus(): Result<Pair<Int, Int>>

    /**
     * Shutdown Python runtime gracefully
     * Note: On Android (Chaquopy), Python persists for app lifetime
     * On iOS, this calls Py_Finalize()
     */
    fun shutdown()

    /**
     * Check if Python is already initialized
     */
    fun isInitialized(): Boolean

    /**
     * Check if server has been started
     */
    fun isServerStarted(): Boolean

    /**
     * Get the server URL
     * Default: http://localhost:8080
     */
    val serverUrl: String
}
