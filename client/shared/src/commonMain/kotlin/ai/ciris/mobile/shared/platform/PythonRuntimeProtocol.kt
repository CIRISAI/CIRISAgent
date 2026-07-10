package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.MutableStateFlow

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
     * Get prep step status (pydantic setup + code integrity)
     * @return Result with (prepStepsCompleted, totalPrepSteps)
     */
    suspend fun getPrepStatus(): Result<Pair<Int, Int>>

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

    /**
     * Set a callback for console output lines from the Python backend.
     * Used to drive startup light animations from structured console output.
     * Default implementation is a no-op.
     */
    fun setOutputLineCallback(callback: ((String) -> Unit)?) {
        // Default no-op — platforms override as needed
    }

    /**
     * The one-time CLAIM PIN the LOCAL node prints to its console on a fresh,
     * unclaimed boot (the "OWNERSHIP UNCLAIMED" banner), captured from the node's
     * stdout. `null` until a banner is seen (or on platforms that do not launch a
     * local node). The first-run setup flow reads this to self-claim ownership of
     * the local node on COMPLETE.
     *
     * Console-only by design — the PIN is NEVER served over HTTP, so capturing it
     * from the process the app itself launched is the only client-side path.
     *
     * Default: a constant empty flow (platforms that drive a local node override).
     */
    val localClaimPin: StateFlow<String?>
        get() = EMPTY_CLAIM_PIN

    /**
     * THIS node's own NodeCode, if the node printed it alongside the unclaimed
     * banner. May be `null` even when [localClaimPin] is set — in that case the
     * NodeCode is fetched at claim time via `GET /v1/federation/node-code`.
     */
    val localNodeCode: StateFlow<String?>
        get() = EMPTY_NODE_CODE

    companion object {
        private val EMPTY_CLAIM_PIN: StateFlow<String?> = MutableStateFlow(null)
        private val EMPTY_NODE_CODE: StateFlow<String?> = MutableStateFlow(null)
    }
}
