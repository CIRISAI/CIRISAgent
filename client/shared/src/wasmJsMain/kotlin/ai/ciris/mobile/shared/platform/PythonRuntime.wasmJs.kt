package ai.ciris.mobile.shared.platform

/**
 * Web implementation of PythonRuntime - no-op since backend handles Python.
 * The web UI connects to a remote CIRIS agent via HTTP API.
 */
actual class PythonRuntime actual constructor() {
    private var _initialized = false
    private var _serverStarted = false

    actual suspend fun initialize(pythonHome: String): Result<Unit> = runCatching {
        _initialized = true
    }

    actual suspend fun startServer(): Result<String> = runCatching {
        _serverStarted = true
        serverUrl
    }

    actual suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> = runCatching {
        onStatus?.invoke("Web mode - connecting to remote server...")
        _serverStarted = true
        serverUrl
    }

    actual fun injectPythonConfig(config: Map<String, String>) {
        // No-op on web - config is on server side
    }

    actual suspend fun checkHealth(): Result<Boolean> = Result.success(true)

    actual suspend fun getServicesStatus(): Result<Pair<Int, Int>> = Result.success(22 to 22)

    actual suspend fun getPrepStatus(): Result<Pair<Int, Int>> = Result.success(2 to 2)

    actual fun shutdown() {
        _serverStarted = false
    }

    actual fun isInitialized(): Boolean = _initialized

    actual fun isServerStarted(): Boolean = _serverStarted

    actual val serverUrl: String = ""  // Empty = relative URLs for ingress
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
