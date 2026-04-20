package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.StateFlow

/**
 * Server status for the local LLM inference server.
 */
enum class LocalLLMServerStatus {
    /** Server is not initialized. */
    STOPPED,
    /** Server is starting up (loading model). */
    STARTING,
    /** Server is running and ready for inference. */
    RUNNING,
    /** Server encountered an error. */
    ERROR
}

/**
 * State snapshot of the local LLM server.
 *
 * @property status Current server status.
 * @property modelName Name of the loaded model (e.g., "gemma-4-e2b").
 * @property port Port the server is listening on.
 * @property errorMessage Error message if status is ERROR.
 * @property loadProgress Model loading progress (0.0 to 1.0) during STARTING.
 */
data class LocalLLMServerState(
    val status: LocalLLMServerStatus = LocalLLMServerStatus.STOPPED,
    val modelName: String? = null,
    val port: Int = 8091,
    val errorMessage: String? = null,
    val loadProgress: Float = 0f
)

/**
 * Interface for managing the on-device LLM inference server.
 *
 * The server provides an OpenAI-compatible HTTP API on port 8091:
 * - POST /v1/chat/completions - Chat completion
 * - GET /v1/models - List available models
 * - GET /health - Health check
 *
 * Implemented via Llamatik library which wraps llama.cpp and provides
 * a Ktor-based HTTP server with OpenAI-compatible endpoints.
 *
 * Test automation server uses port 9091 to avoid collision with local LLM.
 */
interface LocalLLMServer {
    /**
     * Observable server state.
     */
    val state: StateFlow<LocalLLMServerState>

    /**
     * Start the local LLM server with the specified model.
     *
     * @param modelPath Path to the GGUF model file.
     * @param port Port to listen on (default: 8091).
     * @return true if server started successfully.
     */
    suspend fun start(modelPath: String, port: Int = 8091): Boolean

    /**
     * Stop the local LLM server and unload the model.
     */
    suspend fun stop()

    /**
     * Check if the server is running and healthy.
     */
    fun isRunning(): Boolean

    /**
     * Get the base URL for the OpenAI-compatible API.
     * Returns "http://127.0.0.1:8091/v1" when running.
     */
    fun getBaseUrl(): String?
}

/**
 * Get the platform-specific LocalLLMServer instance.
 *
 * Platform expectations:
 * - Android: Uses Llamatik with llama.cpp JNI bindings
 * - iOS: Uses Llamatik with llama.cpp static framework
 * - Desktop: Uses Llamatik with llama.cpp JNI bindings
 *
 * All platforms expose the same OpenAI-compatible HTTP API.
 */
expect fun getLocalLLMServer(): LocalLLMServer
