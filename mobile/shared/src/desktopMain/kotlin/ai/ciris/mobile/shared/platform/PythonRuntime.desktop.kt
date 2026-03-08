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
 * This runtime connects to the already-running server and polls startup-status
 * to drive the startup light animations.
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
    private var _outputLineCallback: ((String) -> Unit)? = null

    // Track last reported service count to emit only new service lines
    private var _lastReportedServiceCount = 0

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
        // On desktop, server is started by CLI before launching the JAR.
        // Wait for it to become healthy, polling startup-status to drive UI lights.
        println("[PythonRuntime.desktop] startServer() called, waiting for server at $_serverUrl")
        repeat(60) { attempt ->
            // Try startup-status first (available before full health)
            pollStartupStatus()

            val health = checkHealth()
            println("[PythonRuntime.desktop] Health check attempt $attempt: ${health.getOrNull()}")
            if (health.getOrNull() == true) {
                // Final poll to capture any remaining services
                pollStartupStatus()
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
        if (response.status != HttpStatusCode.OK) {
            return@runCatching false
        }

        // Parse JSON to check cognitive_state == "WORK"
        val body = response.bodyAsText()
        val stateMatch = Regex(""""cognitive_state"\s*:\s*"(\w+)"""").find(body)
        val cognitiveState = stateMatch?.groupValues?.get(1) ?: ""

        val isWorkState = cognitiveState == "WORK"
        if (!isWorkState) {
            println("[PythonRuntime.desktop] Not ready yet - cognitive_state: $cognitiveState")
        }
        isWorkState
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

    actual override suspend fun getPrepStatus(): Result<Pair<Int, Int>> {
        // Desktop doesn't track prep steps via console - assume complete when server starts
        return Result.success(Pair(8, 8))
    }

    actual override fun shutdown() {
        // On desktop, server lifecycle is managed by CLI - nothing to do here
        _serverStarted = false
    }

    actual override fun isInitialized(): Boolean = _initialized

    actual override fun isServerStarted(): Boolean = _serverStarted

    override fun setOutputLineCallback(callback: ((String) -> Unit)?) {
        _outputLineCallback = callback
    }

    /**
     * Poll /v1/system/startup-status and emit synthetic console output lines
     * for any newly started services since the last poll.
     */
    private suspend fun pollStartupStatus() {
        val callback = _outputLineCallback ?: return

        try {
            val response = httpClient.get("$_serverUrl/v1/system/startup-status")
            if (response.status != HttpStatusCode.OK) return

            val body = response.bodyAsText()

            // Parse services_online count
            val onlineMatch = Regex(""""services_online"\s*:\s*(\d+)""").find(body)
            val totalMatch = Regex(""""services_total"\s*:\s*(\d+)""").find(body)
            val online = onlineMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
            val total = totalMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0

            // Parse service_names array
            val namesMatch = Regex(""""service_names"\s*:\s*\[([^\]]*)\]""").find(body)
            val serviceNames = namesMatch?.groupValues?.get(1)
                ?.split(",")
                ?.map { it.trim().trim('"') }
                ?.filter { it.isNotEmpty() }
                ?: emptyList()

            // Emit [SERVICE n/total] lines for newly started services
            if (online > _lastReportedServiceCount) {
                for (i in (_lastReportedServiceCount + 1)..online) {
                    val name = serviceNames.getOrElse(i - 1) { "Service$i" }
                    callback("[SERVICE $i/$total] $name STARTED")
                }
                _lastReportedServiceCount = online
            }
        } catch (_: Exception) {
            // Server not ready yet — ignore
        }
    }
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
