package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * iOS implementation of LocalLLMServer.
 *
 * Currently a stub that reports IOS_STUB status since Llamatik's iOS
 * support is still being finalized. When ready, this will use the same
 * Llamatik library as Android/Desktop.
 *
 * The server would provide OpenAI-compatible API on port 8092 for local
 * Gemma 4 inference once iOS support is complete.
 */
class IOSLocalLLMServer : LocalLLMServer {
    private val _state = MutableStateFlow(LocalLLMServerState(
        status = LocalLLMServerStatus.STOPPED,
        errorMessage = "On-device inference coming soon for iOS"
    ))
    override val state: StateFlow<LocalLLMServerState> = _state.asStateFlow()

    override suspend fun start(modelPath: String, port: Int): Boolean {
        // iOS support is still in development
        // When Llamatik iOS bindings are ready, implement similar to Android
        _state.value = LocalLLMServerState(
            status = LocalLLMServerStatus.ERROR,
            errorMessage = "On-device inference coming soon for iOS. Use cloud provider for now."
        )
        return false
    }

    override suspend fun stop() {
        _state.value = LocalLLMServerState(status = LocalLLMServerStatus.STOPPED)
    }

    override fun isRunning(): Boolean = false

    override fun getBaseUrl(): String? = null
}

// Singleton instance
private val localLLMServerInstance = IOSLocalLLMServer()

actual fun getLocalLLMServer(): LocalLLMServer = localLLMServerInstance
