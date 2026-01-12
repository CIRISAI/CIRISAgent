package ai.ciris.mobile.shared.platform

/**
 * Python runtime abstraction for CIRIS mobile
 * Manages Python interpreter and FastAPI server lifecycle
 *
 * Implementations:
 * - Android: Chaquopy (com.chaquo.python)
 * - iOS: Python C API (Py_Initialize, etc.)
 */
expect class PythonRuntime() {
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
}

/**
 * Factory function to create PythonRuntime instance
 * Allows dependency injection for testing
 */
expect fun createPythonRuntime(): PythonRuntime
