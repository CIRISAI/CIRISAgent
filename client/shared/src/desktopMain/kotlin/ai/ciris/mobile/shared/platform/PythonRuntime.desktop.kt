package ai.ciris.mobile.shared.platform

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.BufferedReader

/**
 * Desktop PythonRuntime implementation.
 *
 * Starts the CIRIS Python backend automatically if not already running,
 * then reads stdout to drive the UI with real service startup progress.
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

    // ── First-run ownership claim PIN / NodeCode, captured from node stdout ──
    // The local node prints an "OWNERSHIP UNCLAIMED" banner on a fresh,
    // unclaimed boot. The banner carries the PUBLIC NodeCode and the one-time
    // CLAIM PIN. The PIN is CONSOLE-ONLY (never served over HTTP), so the only
    // client-side way to obtain it is to scrape the stdout of the process we
    // ourselves launched. The setup flow reads these to self-claim ownership of
    // this local node on COMPLETE.
    private val _localClaimPin = MutableStateFlow<String?>(null)
    private val _localNodeCode = MutableStateFlow<String?>(null)
    override val localClaimPin: StateFlow<String?> get() = _localClaimPin.asStateFlow()
    override val localNodeCode: StateFlow<String?> get() = _localNodeCode.asStateFlow()

    // Server process we launched (null if server was already running)
    private var _serverProcess: Process? = null

    // Stdout reader coroutine scope
    private val _readerScope = CoroutineScope(Dispatchers.IO)

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
            val health = checkHealth()
            println("[PythonRuntime.desktop] Health check attempt $attempt: ${health.getOrNull()}")
            if (health.getOrNull() == true) {
                println("[PythonRuntime.desktop] Server is healthy!")
                _serverStarted = true
                // The one-time CLAIM PIN is console-only (never over HTTP). We capture
                // it from the node's stdout banner WHEN WE LAUNCH the node — but if the
                // node was already running (we didn't own its stdout), fall back to its
                // durable `<home>/claim_pin` file (0600). Local-FS access to the node's
                // home IS first-run operator-level access, so this is a legitimate
                // capture of the same secret — NOT a weakening (setup/root still
                // verifies the PIN). Only fills if the stdout capture missed it.
                readClaimPinFromFileIfMissing()
                return@runCatching _serverUrl
            }
            delay(1000)
        }
        throw RuntimeException("Cannot connect to CIRIS server at $_serverUrl. Please ensure the server is running.")
    }

    /**
     * Fallback CLAIM-PIN capture: read the local node's durable `<home>/claim_pin`
     * file when the stdout banner capture missed it (e.g. the node was already
     * running, so we never owned its stdout). Console-only-over-HTTP is preserved —
     * this is a same-machine file read (first-run op-level access). No-op if the PIN
     * is already captured or the file is absent/empty.
     */
    private fun readClaimPinFromFileIfMissing() {
        if (_localClaimPin.value != null) return
        val pin = runCatching { readClaimPinFile() }.getOrNull()
        if (!pin.isNullOrEmpty()) {
            _localClaimPin.value = pin
            println("[PythonRuntime.desktop] Captured CLAIM PIN from ${nodeHomeDir().path}/claim_pin (file fallback).")
        }
    }

    /**
     * Race-free, on-demand read of the durable `<home>/claim_pin` file (0600).
     * The node writes claim_pin a few seconds after health answers, so the
     * boot-time latch above can miss it; the setup flow calls this at claim time
     * (well after boot) when the file is guaranteed present. See
     * [PythonRuntimeProtocol.readLocalClaimPin].
     */
    override suspend fun readLocalClaimPin(): String? = runCatching { readClaimPinFile() }.getOrNull()

    private fun readClaimPinFile(): String? {
        val pinFile = java.io.File(nodeHomeDir(), "claim_pin")
        return if (pinFile.canRead()) pinFile.readText().trim().ifEmpty { null } else null
    }

    /**
     * Per-user data directory for the local node's substrate/keyring. Mirrors
     * `ciris_engine.logic.utils.path_resolution.get_ciris_home()` so the agent
     * backend and this fallback resolve the SAME home:
     *   1. `/app` when CIRIS-Manager-managed,
     *   2. `$CIRIS_HOME` when set (explicit override),
     *   3. `~/ciris` otherwise (installed mode).
     */
    private fun nodeHomeDir(): java.io.File {
        val managed = java.io.File("/app/agent").isDirectory ||
            java.io.File("/app/.ciris_manager").isDirectory
        return when {
            managed -> java.io.File("/app")
            else -> {
                val env = System.getenv("CIRIS_HOME")
                if (!env.isNullOrBlank()) java.io.File(env)
                else java.io.File(System.getProperty("user.home", "."), "ciris")
            }
        }
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
     * Captures stdout and forwards to the output callback for UI updates.
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
                .redirectErrorStream(true)  // Merge stderr into stdout
                .start()
            println("[PythonRuntime.desktop] Started ciris-agent (PID: ${_serverProcess?.pid()})")
            startStdoutReader()
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
                .redirectErrorStream(true)  // Merge stderr into stdout
                .start()
            println("[PythonRuntime.desktop] Started python server (PID: ${_serverProcess?.pid()})")
            startStdoutReader()
            return
        }

        println("[PythonRuntime.desktop] WARNING: Could not find ciris-agent or main.py - waiting for external server")
    }

    /**
     * Start a coroutine to read stdout from the server process and forward to callback.
     * This enables the UI to see real service startup messages.
     */
    private fun startStdoutReader() {
        val process = _serverProcess ?: return

        _readerScope.launch {
            try {
                val reader = process.inputStream.bufferedReader()
                var line: String?
                while (reader.readLine().also { line = it } != null) {
                    val l = line ?: continue
                    // Always print to console for debugging
                    println("[CIRIS] $l")
                    // Capture the first-run ownership claim PIN / NodeCode from the
                    // node's "OWNERSHIP UNCLAIMED" banner so the setup flow can
                    // self-claim this local node on COMPLETE.
                    parseOwnershipBanner(l)
                    // Forward to callback for UI processing
                    _outputLineCallback?.invoke(l)
                }
            } catch (e: Exception) {
                println("[PythonRuntime.desktop] Stdout reader stopped: ${e.message}")
            }
        }
    }

    /**
     * Parse one stdout line from the node's "OWNERSHIP UNCLAIMED" banner and, when
     * found, latch the one-time CLAIM PIN and/or the NodeCode into the StateFlows
     * the setup flow reads.
     *
     * Matches the banner form (one token per line, inside a box):
     *
     *     ║    NodeCode : CIRIS-V1-AAAA-BBBB-CCCC-...
     *     ║    CLAIM PIN: 7F3K-Q9MZ   (one-time; console-only — NEVER over HTTP)
     *
     * The PIN is 8 Crockford-base32 chars (alphabet 0-9 A-Z minus I/L/O/U)
     * rendered XXXX-XXXX. The NodeCode is a `CIRIS-V1-...` string. Both are
     * captured leniently (the surrounding box-drawing chars / trailing notes are
     * ignored). Idempotent: only the first match per token is latched.
     */
    private fun parseOwnershipBanner(line: String) {
        if (_localClaimPin.value == null && line.contains("CLAIM PIN", ignoreCase = true)) {
            // Take the text after the "CLAIM PIN:" label, then the first
            // XXXX-XXXX Crockford-base32 token on it.
            val after = line.substringAfter(":", "").substringAfter("CLAIM PIN", "")
            val pin = CLAIM_PIN_REGEX.find(after.ifBlank { line })?.value
            if (pin != null) {
                println("[PythonRuntime.desktop] Captured one-time CLAIM PIN from node banner (console-only).")
                _localClaimPin.value = pin
            }
        }
        if (_localNodeCode.value == null && line.contains("NodeCode", ignoreCase = true)) {
            val code = NODE_CODE_REGEX.find(line)?.value
            if (code != null) {
                println("[PythonRuntime.desktop] Captured NodeCode from node banner: ${code.take(24)}…")
                _localNodeCode.value = code
            }
        }
    }

    private companion object {
        /** One-time claim PIN: two dash-separated groups of 4 Crockford-base32
         *  chars (alphabet 0-9 A-Z minus I, L, O, U), as rendered by the node. */
        val CLAIM_PIN_REGEX = Regex("[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}")
        /** NodeCode handle the node prints: `CIRIS-V1-...` (dashes/alnum). */
        val NODE_CODE_REGEX = Regex("CIRIS-V1-[0-9A-Za-z\\-]+")
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
        // Use unauthenticated startup-status endpoint for service counts
        val response = httpClient.get("$_serverUrl/v1/system/startup-status")
        if (response.status != HttpStatusCode.OK) {
            return@runCatching Pair(0, 0)
        }
        val body = response.bodyAsText()
        // Parse services_online and services_total from startup-status response
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
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
