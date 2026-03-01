package ai.ciris.mobile.shared.platform

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.coroutines.delay

/**
 * Desktop PythonRuntime implementation.
 *
 * On desktop, the Python server is started by the CLI before launching this app.
 * This runtime simply connects to the already-running server.
 *
 * The server URL can be configured via CIRIS_API_URL environment variable.
 */
actual class PythonRuntime actual constructor() : PythonRuntimeProtocol {
    private var _serverUrl: String = run {
        val envUrl = System.getenv("CIRIS_API_URL")
        println("[PythonRuntime.desktop] CIRIS_API_URL env: $envUrl")
        envUrl ?: "http://localhost:8080"
    }
    private var _initialized = false
    private var _serverStarted = false

    private val httpClient = HttpClient(CIO) {
        engine {
            requestTimeout = 5000
        }
    }

    actual override val serverUrl: String get() = _serverUrl

    actual override suspend fun initialize(pythonHome: String): Result<Unit> = runCatching {
        _initialized = true
    }

    actual override suspend fun startServer(): Result<String> = runCatching {
        // On desktop, server should already be running (started by CLI)
        // Just wait for it to be ready
        println("[PythonRuntime.desktop] startServer() called, waiting for server at $_serverUrl")
        repeat(60) { attempt ->
            val health = checkHealth()
            println("[PythonRuntime.desktop] Health check attempt $attempt: ${health.getOrNull()}")
            if (health.getOrNull() == true) {
                println("[PythonRuntime.desktop] Server is healthy!")
                _serverStarted = true
                return@runCatching _serverUrl
            }
            delay(1000)
        }
        throw RuntimeException("Cannot connect to CIRIS server at $_serverUrl. Please ensure the server is running.")
    }

    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> {
        onStatus?.invoke("Connecting to CIRIS server...")

        // Check if server is already running
        if (checkHealth().getOrNull() == true) {
            onStatus?.invoke("Connected to server")
            _serverStarted = true
            return Result.success(_serverUrl)
        }

        onStatus?.invoke("Waiting for server...")
        return startServer()
    }

    actual override fun injectPythonConfig(config: Map<String, String>) {
        // On desktop, config is managed by the Python server
        // The setup wizard sends config via API, not via file injection
        println("[PythonRuntime.desktop] Config injection skipped - server handles config")
    }

    actual override suspend fun checkHealth(): Result<Boolean> = runCatching {
        val response = httpClient.get("$_serverUrl/v1/system/health")
        response.status == HttpStatusCode.OK
    }

    actual override suspend fun getServicesStatus(): Result<Pair<Int, Int>> = runCatching {
        val response = httpClient.get("$_serverUrl/v1/telemetry/unified")
        if (response.status != HttpStatusCode.OK) {
            return@runCatching Pair(0, 0)
        }
        val body = response.bodyAsText()
        // Simple JSON parsing for services_online and services_total
        val onlineMatch = Regex(""""services_online"\s*:\s*(\d+)""").find(body)
        val totalMatch = Regex(""""services_total"\s*:\s*(\d+)""").find(body)
        val online = onlineMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
        val total = totalMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
        Pair(online, total)
    }

    actual override fun shutdown() {
        // On desktop, server lifecycle is managed by CLI - nothing to do here
        _serverStarted = false
    }

    actual override fun isInitialized(): Boolean = _initialized

    actual override fun isServerStarted(): Boolean = _serverStarted
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
