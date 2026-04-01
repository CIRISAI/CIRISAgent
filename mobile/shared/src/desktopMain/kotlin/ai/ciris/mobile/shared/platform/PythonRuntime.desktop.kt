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
 * Starts the CIRIS Python backend automatically if not already running,
 * then connects to the server and polls startup-status to drive the UI.
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

    // Server process we launched (null if server was already running)
    private var _serverProcess: Process? = null

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
        println("[PythonRuntime.desktop] startServer() called, checking for server at $_serverUrl")

        // Check if server is already running and in a usable state
        val existingServerState = checkExistingServer()

        when (existingServerState) {
            ExistingServerState.HEALTHY -> {
                println("[PythonRuntime.desktop] Server already running and healthy at $_serverUrl")
            }
            ExistingServerState.STUCK_SHUTDOWN -> {
                println("[PythonRuntime.desktop] Detected stuck server in shutdown state - attempting to kill...")
                if (!killStuckServer()) {
                    throw RuntimeException(
                        "A CIRIS server is stuck in shutdown state on $_serverUrl but could not be killed.\n\n" +
                        "Please manually kill the process:\n" +
                        "  Linux/Mac: lsof -i :${getPort()} | grep LISTEN | awk '{print \$2}' | xargs kill\n" +
                        "  Windows: netstat -ano | findstr :${getPort()} then taskkill /PID <pid> /F\n\n" +
                        "Then restart the application."
                    )
                }
                println("[PythonRuntime.desktop] Killed stuck server, launching fresh instance...")
                launchServerProcess()
            }
            ExistingServerState.NOT_RUNNING -> {
                println("[PythonRuntime.desktop] No server detected, launching backend...")
                launchServerProcess()
            }
        }

        // Wait for server to become healthy
        repeat(120) { attempt ->
            pollStartupStatus()

            val health = checkHealth()
            println("[PythonRuntime.desktop] Health check attempt $attempt: ${health.getOrNull()}")
            if (health.getOrNull() == true) {
                pollStartupStatus()
                println("[PythonRuntime.desktop] Server is healthy!")
                _serverStarted = true
                return@runCatching _serverUrl
            }
            delay(1000)
        }
        throw RuntimeException("Cannot connect to CIRIS server at $_serverUrl. Please ensure the server is running.")
    }

    /**
     * State of an existing server process.
     */
    private enum class ExistingServerState {
        NOT_RUNNING,      // No server on port
        HEALTHY,          // Server running in WORK or SETUP state
        STUCK_SHUTDOWN    // Server responding but in shutdown or other bad state
    }

    /**
     * Check if there's an existing server and what state it's in.
     */
    private suspend fun checkExistingServer(): ExistingServerState {
        return try {
            val response = httpClient.get("$_serverUrl/v1/system/health")
            if (response.status != HttpStatusCode.OK) {
                return ExistingServerState.NOT_RUNNING
            }

            val body = response.bodyAsText()
            val stateMatch = Regex(""""cognitive_state"\s*:\s*"(\w+)"""").find(body)
            val cognitiveState = stateMatch?.groupValues?.get(1)?.uppercase() ?: ""

            when (cognitiveState) {
                "WORK", "SETUP", "WAKEUP", "PLAY", "SOLITUDE", "DREAM" -> ExistingServerState.HEALTHY
                "SHUTDOWN" -> ExistingServerState.STUCK_SHUTDOWN
                "" -> {
                    // Empty cognitive_state means server is still initializing
                    println("[PythonRuntime.desktop] Server responding but cognitive_state empty (still starting)")
                    ExistingServerState.HEALTHY
                }
                else -> {
                    println("[PythonRuntime.desktop] Unknown cognitive_state: $cognitiveState - treating as healthy")
                    ExistingServerState.HEALTHY
                }
            }
        } catch (_: Exception) {
            ExistingServerState.NOT_RUNNING
        }
    }

    /**
     * Get port from server URL.
     */
    private fun getPort(): String {
        return Regex(":(\\d+)").find(_serverUrl)?.groupValues?.get(1) ?: "8080"
    }

    /**
     * Attempt to kill a stuck server process.
     * Returns true if successful or if server is no longer responding.
     */
    private suspend fun killStuckServer(): Boolean {
        val port = getPort()
        val isWindows = System.getProperty("os.name", "").lowercase().contains("win")

        try {
            // Find and kill process on the port
            val killProcess = if (isWindows) {
                // Windows: use netstat + taskkill
                ProcessBuilder("cmd", "/c",
                    "for /f \"tokens=5\" %a in ('netstat -ano ^| findstr :$port ^| findstr LISTENING') do taskkill /PID %a /F"
                ).start()
            } else {
                // Unix: use lsof + kill
                ProcessBuilder("sh", "-c",
                    "lsof -ti :$port | xargs kill -9 2>/dev/null || true"
                ).start()
            }

            killProcess.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)

            // Wait a moment for port to be released
            delay(2000)

            // Verify server is no longer responding
            return try {
                httpClient.get("$_serverUrl/v1/system/health")
                // Still responding - kill failed
                println("[PythonRuntime.desktop] Server still responding after kill attempt")
                false
            } catch (_: Exception) {
                // Not responding - kill succeeded
                println("[PythonRuntime.desktop] Server successfully killed")
                true
            }
        } catch (e: Exception) {
            println("[PythonRuntime.desktop] Error killing stuck server: ${e.message}")
            return false
        }
    }

    /**
     * Launch ciris-agent --adapter api as a subprocess.
     * Tries ciris-agent first (pip-installed), then falls back to python main.py.
     */
    private fun launchServerProcess() {
        println("[PythonRuntime.desktop] Launching backend...")

        // Parse port from server URL
        val port = Regex(":(\\d+)").find(_serverUrl)?.groupValues?.get(1) ?: "8080"

        // Try ciris-agent first (pip-installed command)
        val cirisAgent = findExecutable("ciris-agent")
        if (cirisAgent != null) {
            println("[PythonRuntime.desktop] Found ciris-agent at: $cirisAgent")
            _serverProcess = ProcessBuilder(cirisAgent, "--adapter", "api", "--port", port)
                .redirectErrorStream(true)
                .inheritIO()
                .start()
            println("[PythonRuntime.desktop] Started ciris-agent (PID: ${_serverProcess?.pid()})")
            return
        }

        // Fallback: python main.py from repo root
        val repoRoot = findRepoRoot()
        val mainPy = repoRoot?.resolve("main.py")
        if (mainPy != null && mainPy.exists()) {
            val python = findExecutable("python3") ?: findExecutable("python") ?: "python3"
            println("[PythonRuntime.desktop] Falling back to: $python ${mainPy.absolutePath}")
            _serverProcess = ProcessBuilder(python, mainPy.absolutePath, "--adapter", "api", "--port", port)
                .directory(repoRoot)
                .redirectErrorStream(true)
                .inheritIO()
                .start()
            println("[PythonRuntime.desktop] Started python server (PID: ${_serverProcess?.pid()})")
            return
        }

        println("[PythonRuntime.desktop] WARNING: Could not find ciris-agent or main.py - waiting for external server")
    }

    private fun findExecutable(name: String): String? {
        val isWindows = System.getProperty("os.name", "").lowercase().contains("win")
        val candidates = if (isWindows && !name.contains('.')) {
            listOf("$name.exe", "$name.cmd", "$name.bat", name)
        } else {
            listOf(name)
        }
        val pathDirs = System.getenv("PATH")?.split(java.io.File.pathSeparator) ?: emptyList()
        for (dir in pathDirs) {
            for (candidate in candidates) {
                val f = java.io.File(dir, candidate)
                if (f.exists() && f.canExecute()) return f.absolutePath
            }
        }
        return null
    }

    private fun findRepoRoot(): java.io.File? {
        // Walk up from JAR location to find main.py
        var dir = java.io.File(System.getProperty("user.dir", "."))
        repeat(5) {
            if (java.io.File(dir, "main.py").exists() && java.io.File(dir, "ciris_engine").isDirectory) {
                return dir
            }
            dir = dir.parentFile ?: return null
        }
        return null
    }

    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> {
        onStatus?.invoke("Connecting to CIRIS server...")

        // Check if server is already running
        if (checkHealth().getOrNull() == true) {
            onStatus?.invoke("Connected to server")
            _serverStarted = true
            return Result.success(_serverUrl)
        }

        onStatus?.invoke("Starting server...")
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

        // Parse JSON to check cognitive_state == "WORK" or "SETUP" (first-run)
        val body = response.bodyAsText()
        val stateMatch = Regex(""""cognitive_state"\s*:\s*"(\w+)"""").find(body)
        val cognitiveState = stateMatch?.groupValues?.get(1) ?: ""

        // WORK = normal ready, SETUP = first-run ready (case-insensitive)
        val upper = cognitiveState.uppercase()
        val isReady = upper == "WORK" || upper == "SETUP"
        if (!isReady) {
            println("[PythonRuntime.desktop] Not ready yet - cognitive_state: $cognitiveState")
        }
        isReady
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
        _serverStarted = false
        // Kill the server process if we launched it
        _serverProcess?.let { proc ->
            println("[PythonRuntime.desktop] Shutting down server process (PID: ${proc.pid()})...")
            proc.destroy()
            try {
                proc.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)
            } catch (_: Exception) {
                proc.destroyForcibly()
            }
            _serverProcess = null
        }
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
