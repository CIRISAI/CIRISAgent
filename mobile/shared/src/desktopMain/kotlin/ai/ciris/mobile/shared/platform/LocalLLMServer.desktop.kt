package ai.ciris.mobile.shared.platform

import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Desktop implementation of LocalLLMServer.
 *
 * This implementation connects to an external OpenAI-compatible server
 * (such as a local llama.cpp server, Ollama, or network-accessible inference server)
 * rather than running inference in-process.
 *
 * The server is expected to be running at http://127.0.0.1:8091/v1 (or the specified port)
 * and provide OpenAI-compatible endpoints.
 *
 * NOTE: For true on-device inference using Llamatik, the project needs
 * to upgrade to Kotlin 2.2+. See build.gradle.kts for details.
 */
class DesktopLocalLLMServer : LocalLLMServer {
    private val _state = MutableStateFlow(LocalLLMServerState())
    override val state: StateFlow<LocalLLMServerState> = _state.asStateFlow()

    private var healthCheckJob: Job? = null
    private var currentPort: Int = 8091
    private val httpClient = HttpClient()

    override suspend fun start(modelPath: String, port: Int): Boolean {
        currentPort = port
        _state.value = LocalLLMServerState(
            status = LocalLLMServerStatus.STARTING,
            port = port,
            loadProgress = 0.5f
        )

        // Check if external server is already running
        return withContext(Dispatchers.IO) {
            try {
                val healthUrl = "http://127.0.0.1:$port/health"
                println("[LocalLLMServer] Checking for external LLM server at $healthUrl")

                val response = httpClient.get(healthUrl)
                if (response.status.isSuccess()) {
                    val modelName = modelPath.substringAfterLast("/").substringBeforeLast(".")
                    _state.value = LocalLLMServerState(
                        status = LocalLLMServerStatus.RUNNING,
                        modelName = modelName,
                        port = port,
                        loadProgress = 1.0f
                    )
                    startHealthCheckLoop()
                    println("[LocalLLMServer] Connected to external LLM server on port $port")
                    true
                } else {
                    _state.value = LocalLLMServerState(
                        status = LocalLLMServerStatus.ERROR,
                        port = port,
                        errorMessage = "External server not responding (status: ${response.status})"
                    )
                    false
                }
            } catch (e: Exception) {
                println("[LocalLLMServer] External LLM server not available: ${e.message}")
                _state.value = LocalLLMServerState(
                    status = LocalLLMServerStatus.ERROR,
                    port = port,
                    errorMessage = "No local LLM server found. Start llama.cpp, Ollama, or external server first."
                )
                false
            }
        }
    }

    private fun startHealthCheckLoop() {
        healthCheckJob?.cancel()
        healthCheckJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                delay(15000) // Check every 15 seconds
                try {
                    val response = httpClient.get("http://127.0.0.1:$currentPort/health")
                    if (!response.status.isSuccess() && _state.value.status == LocalLLMServerStatus.RUNNING) {
                        _state.value = _state.value.copy(
                            status = LocalLLMServerStatus.ERROR,
                            errorMessage = "Server stopped responding"
                        )
                    }
                } catch (e: Exception) {
                    if (_state.value.status == LocalLLMServerStatus.RUNNING) {
                        _state.value = _state.value.copy(
                            status = LocalLLMServerStatus.ERROR,
                            errorMessage = "Lost connection to server"
                        )
                    }
                }
            }
        }
    }

    override suspend fun stop() {
        println("[LocalLLMServer] Stopping connection")
        healthCheckJob?.cancel()
        healthCheckJob = null
        _state.value = LocalLLMServerState(status = LocalLLMServerStatus.STOPPED)
    }

    override fun isRunning(): Boolean {
        return _state.value.status == LocalLLMServerStatus.RUNNING
    }

    override fun getBaseUrl(): String? {
        return if (isRunning()) "http://127.0.0.1:$currentPort/v1" else null
    }
}

// Singleton instance
private val localLLMServerInstance = DesktopLocalLLMServer()

actual fun getLocalLLMServer(): LocalLLMServer = localLLMServerInstance
