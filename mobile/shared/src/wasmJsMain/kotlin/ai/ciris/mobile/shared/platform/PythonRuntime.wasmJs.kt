package ai.ciris.mobile.shared.platform

/**
 * Web implementation of PythonRuntime - no-op since backend handles Python.
 * The web UI connects to a remote CIRIS agent via HTTP API.
 *
 * CRITICAL: This class implements PythonRuntimeProtocol and ALL interface
 * methods MUST have the `override` modifier. Missing `override` causes
 * ClassCastException at runtime when code casts to PythonRuntimeProtocol.
 */
actual class PythonRuntime actual constructor() : PythonRuntimeProtocol {
    private var _initialized = false
    private var _serverStarted = false

    actual override suspend fun initialize(pythonHome: String): Result<Unit> = runCatching {
        _initialized = true
    }

    actual override suspend fun startServer(): Result<String> = runCatching {
        _serverStarted = true
        serverUrl
    }

    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> = runCatching {
        onStatus?.invoke("Web mode - connecting to remote server...")
        _serverStarted = true
        serverUrl
    }

    actual override fun injectPythonConfig(config: Map<String, String>) {
        // No-op on web - config is on server side
    }

    actual override suspend fun checkHealth(): Result<Boolean> = Result.success(true)

    actual override suspend fun getServicesStatus(): Result<Pair<Int, Int>> = Result.success(22 to 22)

    actual override suspend fun getPrepStatus(): Result<Pair<Int, Int>> = Result.success(2 to 2)

    actual override fun shutdown() {
        _serverStarted = false
    }

    actual override fun isInitialized(): Boolean = _initialized

    actual override fun isServerStarted(): Boolean = _serverStarted

    actual override val serverUrl: String = ""  // Empty = relative URLs for ingress
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
