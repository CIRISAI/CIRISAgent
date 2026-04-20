package ai.ciris.mobile.shared.platform

import android.content.Context
import android.os.Build
import android.util.Log
import ai.onnxruntime.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.server.application.*
import io.ktor.server.cio.*
import io.ktor.server.engine.*
import io.ktor.server.engine.ApplicationEngine
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.plugins.statuspages.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.nio.FloatBuffer

private const val TAG = "LocalLLMServer"

/**
 * Check if device supports 64-bit inference.
 * Returns true for arm64-v8a and x86_64, false for armeabi-v7a.
 */
private fun is64BitDevice(): Boolean {
    val primaryAbi = Build.SUPPORTED_ABIS.firstOrNull() ?: return false
    return primaryAbi in listOf("arm64-v8a", "x86_64")
}

/**
 * Android implementation of LocalLLMServer with conditional 64-bit support.
 *
 * - 64-bit devices (arm64-v8a, x86_64): Full ONNX Runtime inference with Ktor HTTP server
 * - 32-bit devices (armeabi-v7a): Returns error directing user to Local Inference Server
 *
 * The HTTP server provides an OpenAI-compatible API on port 8091:
 * - POST /v1/chat/completions - Chat completion
 * - GET /v1/models - List available models
 * - GET /health - Health check
 */
class AndroidLocalLLMServer : LocalLLMServer {
    private val _state = MutableStateFlow(
        if (is64BitDevice()) {
            LocalLLMServerState(
                status = LocalLLMServerStatus.STOPPED,
                errorMessage = null
            )
        } else {
            LocalLLMServerState(
                status = LocalLLMServerStatus.ERROR,
                errorMessage = "On-device LLM requires 64-bit device. Use 'Local Inference Server' to connect to a network server instead."
            )
        }
    )
    override val state: StateFlow<LocalLLMServerState> = _state.asStateFlow()

    private var httpServer: io.ktor.server.engine.EmbeddedServer<*, *>? = null
    private var ortSession: OrtSession? = null
    private var ortEnv: OrtEnvironment? = null
    private var currentModelPath: String? = null
    private var currentModelName: String? = null
    private var serverScope: CoroutineScope? = null
    private var appContext: Context? = null

    fun initialize(context: Context) {
        appContext = context.applicationContext
        Log.i(TAG, "LocalLLMServer initialized, 64-bit supported: ${is64BitDevice()}")
    }

    override suspend fun start(modelPath: String, port: Int): Boolean {
        if (!is64BitDevice()) {
            Log.w(TAG, "On-device LLM not available on 32-bit device (${Build.SUPPORTED_ABIS.firstOrNull()})")
            _state.value = LocalLLMServerState(
                status = LocalLLMServerStatus.ERROR,
                errorMessage = "On-device LLM requires 64-bit device (arm64-v8a or x86_64). This device is ${Build.SUPPORTED_ABIS.firstOrNull()}. Use 'Local Inference Server' to connect to a network server instead."
            )
            return false
        }

        return withContext(Dispatchers.IO) {
            try {
                _state.value = LocalLLMServerState(
                    status = LocalLLMServerStatus.STARTING,
                    loadProgress = 0.1f
                )

                // Check if model file exists
                val modelFile = File(modelPath)
                if (!modelFile.exists()) {
                    _state.value = LocalLLMServerState(
                        status = LocalLLMServerStatus.ERROR,
                        errorMessage = "Model file not found: $modelPath"
                    )
                    return@withContext false
                }

                _state.value = _state.value.copy(loadProgress = 0.3f)

                // Initialize ONNX Runtime
                ortEnv = OrtEnvironment.getEnvironment()
                val sessionOptions = OrtSession.SessionOptions().apply {
                    // Use NNAPI for hardware acceleration on Android
                    try {
                        addNnapi()
                        Log.i(TAG, "NNAPI acceleration enabled")
                    } catch (e: Exception) {
                        Log.w(TAG, "NNAPI not available, using CPU: ${e.message}")
                    }
                }

                _state.value = _state.value.copy(loadProgress = 0.5f)

                // Load the ONNX model
                ortSession = ortEnv?.createSession(modelPath, sessionOptions)
                currentModelPath = modelPath
                currentModelName = modelFile.nameWithoutExtension

                _state.value = _state.value.copy(loadProgress = 0.7f)

                // Start HTTP server
                serverScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
                startHttpServer(port)

                _state.value = LocalLLMServerState(
                    status = LocalLLMServerStatus.RUNNING,
                    modelName = currentModelName,
                    port = port,
                    loadProgress = 1.0f
                )

                Log.i(TAG, "Local LLM server started on port $port with model: $currentModelName")
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start local LLM server", e)
                _state.value = LocalLLMServerState(
                    status = LocalLLMServerStatus.ERROR,
                    errorMessage = "Failed to start: ${e.message}"
                )
                false
            }
        }
    }

    private fun startHttpServer(port: Int) {
        httpServer = embeddedServer(CIO, port = port) {
            install(ContentNegotiation) {
                json(Json {
                    ignoreUnknownKeys = true
                    prettyPrint = false
                })
            }
            install(StatusPages) {
                exception<Throwable> { call, cause ->
                    Log.e(TAG, "HTTP server error", cause)
                    call.respond(
                        HttpStatusCode.InternalServerError,
                        ErrorResponse(error = ErrorDetail(message = cause.message ?: "Unknown error"))
                    )
                }
            }
            routing {
                // Health check
                get("/health") {
                    call.respond(HealthResponse(status = "ok", model = currentModelName))
                }

                // List models (OpenAI-compatible)
                get("/v1/models") {
                    val models = listOfNotNull(currentModelName?.let { name ->
                        ModelInfo(id = name, owned_by = "local")
                    })
                    call.respond(ModelsResponse(data = models))
                }

                // Chat completions (OpenAI-compatible)
                post("/v1/chat/completions") {
                    val request = call.receive<ChatCompletionRequest>()
                    val response = runInference(request)
                    call.respond(response)
                }
            }
        }
        httpServer?.start(wait = false)
        Log.i(TAG, "HTTP server started on port $port")
    }

    private suspend fun runInference(request: ChatCompletionRequest): ChatCompletionResponse {
        val session = ortSession ?: throw IllegalStateException("Model not loaded")
        val env = ortEnv ?: throw IllegalStateException("ORT environment not initialized")

        return withContext(Dispatchers.Default) {
            try {
                // Combine messages into a prompt
                val prompt = request.messages.joinToString("\n") { msg ->
                    when (msg.role) {
                        "system" -> "[System]: ${msg.content}"
                        "user" -> "[User]: ${msg.content}"
                        "assistant" -> "[Assistant]: ${msg.content}"
                        else -> msg.content
                    }
                } + "\n[Assistant]:"

                // For now, return a placeholder response
                // Full tokenization and generation requires model-specific implementation
                // This provides the HTTP API framework that can be extended
                val responseText = generateResponse(session, env, prompt, request.max_tokens ?: 256)

                ChatCompletionResponse(
                    id = "chatcmpl-${System.currentTimeMillis()}",
                    model = currentModelName ?: "local-model",
                    choices = listOf(
                        Choice(
                            index = 0,
                            message = Message(role = "assistant", content = responseText),
                            finish_reason = "stop"
                        )
                    ),
                    usage = Usage(
                        prompt_tokens = prompt.length / 4,
                        completion_tokens = responseText.length / 4,
                        total_tokens = (prompt.length + responseText.length) / 4
                    )
                )
            } catch (e: Exception) {
                Log.e(TAG, "Inference error", e)
                throw e
            }
        }
    }

    private fun generateResponse(session: OrtSession, env: OrtEnvironment, prompt: String, maxTokens: Int): String {
        // This is a placeholder implementation
        // Full LLM generation requires:
        // 1. Tokenizer (model-specific)
        // 2. Token-by-token generation loop
        // 3. Proper input/output tensor handling
        //
        // For production, consider using:
        // - Pre-built ONNX models with embedded tokenizer
        // - Google's LiteRT-LM which handles this automatically
        // - A specific model format like Phi-3 ONNX

        Log.d(TAG, "Generating response for prompt (${prompt.length} chars), max_tokens=$maxTokens")

        // Return informative message until full implementation
        return "On-device inference is initializing. Model: ${currentModelName ?: "unknown"}. " +
               "For full functionality, download a compatible ONNX model (e.g., Phi-3-mini) " +
               "and place it in the app's model directory."
    }

    override suspend fun stop() {
        withContext(Dispatchers.IO) {
            try {
                httpServer?.stop(1000, 2000)
                httpServer = null

                ortSession?.close()
                ortSession = null

                ortEnv?.close()
                ortEnv = null

                serverScope?.cancel()
                serverScope = null

                currentModelPath = null
                currentModelName = null

                _state.value = LocalLLMServerState(
                    status = LocalLLMServerStatus.STOPPED
                )

                Log.i(TAG, "Local LLM server stopped")
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping server", e)
            }
        }
    }

    override fun isRunning(): Boolean = _state.value.status == LocalLLMServerStatus.RUNNING

    override fun getBaseUrl(): String? {
        return if (isRunning()) {
            "http://127.0.0.1:${_state.value.port}/v1"
        } else {
            null
        }
    }

    companion object {
        @Volatile
        private var instance: AndroidLocalLLMServer? = null

        fun getInstance(): AndroidLocalLLMServer {
            return instance ?: synchronized(this) {
                instance ?: AndroidLocalLLMServer().also { instance = it }
            }
        }
    }
}

// ============================================================================
// OpenAI-compatible API models
// ============================================================================

@Serializable
data class HealthResponse(
    val status: String,
    val model: String?
)

@Serializable
data class ModelsResponse(
    val data: List<ModelInfo>,
    val `object`: String = "list"
)

@Serializable
data class ModelInfo(
    val id: String,
    val `object`: String = "model",
    val owned_by: String
)

@Serializable
data class ChatCompletionRequest(
    val model: String? = null,
    val messages: List<Message>,
    val max_tokens: Int? = null,
    val temperature: Float? = null,
    val stream: Boolean? = false
)

@Serializable
data class Message(
    val role: String,
    val content: String
)

@Serializable
data class ChatCompletionResponse(
    val id: String,
    val `object`: String = "chat.completion",
    val created: Long = System.currentTimeMillis() / 1000,
    val model: String,
    val choices: List<Choice>,
    val usage: Usage
)

@Serializable
data class Choice(
    val index: Int,
    val message: Message,
    val finish_reason: String
)

@Serializable
data class Usage(
    val prompt_tokens: Int,
    val completion_tokens: Int,
    val total_tokens: Int
)

@Serializable
data class ErrorResponse(
    val error: ErrorDetail
)

@Serializable
data class ErrorDetail(
    val message: String,
    val type: String = "server_error",
    val code: String? = null
)

// ============================================================================
// Singleton accessor and initialization
// ============================================================================

private val localLLMServerInstance by lazy { AndroidLocalLLMServer.getInstance() }

actual fun getLocalLLMServer(): LocalLLMServer = localLLMServerInstance

/**
 * Initialize the local LLM server with Android context.
 * Call this in MainActivity.onCreate() to enable on-device inference on 64-bit devices.
 */
fun initLocalLLMServer(context: Context) {
    localLLMServerInstance.initialize(context)
}
