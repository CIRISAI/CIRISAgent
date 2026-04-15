package ai.ciris.mobile.shared.platform

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

private const val TAG = "LocalLLMServer"

/**
 * Android stub implementation of LocalLLMServer.
 *
 * ON-DEVICE LLM NOT AVAILABLE ON ANDROID:
 * Available Kotlin libraries (llmedge, kotlinllamacpp) require Kotlin 2.x,
 * but this project must stay on Kotlin 1.9.x to maintain ARMv7 (32-bit) support.
 * Kotlin 2.x dropped ARMv7 support, so upgrading is not an option.
 *
 * Alternatives for Android users:
 * - Use "Local Inference Server" provider to discover network LLM servers
 *   (Ollama, llama.cpp, vLLM, LM Studio on a PC or Jetson)
 * - Use cloud providers (OpenRouter, OpenAI, Anthropic, etc.)
 *
 * Future options if a Kotlin 1.9-compatible library becomes available:
 * 1. Add the dependency to build.gradle.kts androidMain block
 * 2. Implement inference + Ktor HTTP wrapper here
 * 3. Call initLocalLLMServer(context) in MainActivity.onCreate()
 */
class AndroidLocalLLMServer : LocalLLMServer {
    private val _state = MutableStateFlow(LocalLLMServerState(
        status = LocalLLMServerStatus.ERROR,
        errorMessage = "On-device LLM not available on Android (use Local Inference Server instead)"
    ))
    override val state: StateFlow<LocalLLMServerState> = _state.asStateFlow()

    override suspend fun start(modelPath: String, port: Int): Boolean {
        Log.w(TAG, "On-device LLM not available on Android (Kotlin 1.9 for ARMv7 support)")
        _state.value = LocalLLMServerState(
            status = LocalLLMServerStatus.ERROR,
            errorMessage = "On-device LLM not available on Android. Use 'Local Inference Server' to connect to a network server instead."
        )
        return false
    }

    override suspend fun stop() {
        // No-op for stub
    }

    override fun isRunning(): Boolean = false

    override fun getBaseUrl(): String? = null

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

// Singleton accessor
private val localLLMServerInstance by lazy { AndroidLocalLLMServer.getInstance() }

actual fun getLocalLLMServer(): LocalLLMServer = localLLMServerInstance

/**
 * Initialize the local LLM server with Android context.
 * No-op on Android - on-device LLM not available (Kotlin 1.9 for ARMv7 support).
 */
@Suppress("UNUSED_PARAMETER")
fun initLocalLLMServer(context: android.content.Context) {
    // No-op: On-device LLM not available on Android
}
