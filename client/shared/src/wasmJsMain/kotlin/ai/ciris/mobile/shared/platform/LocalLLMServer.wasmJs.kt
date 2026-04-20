package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Web/WASM stub implementation of LocalLLMServer.
 * Local LLM inference is not supported in browser environment.
 */
actual fun getLocalLLMServer(): LocalLLMServer = object : LocalLLMServer {
    private val _state = MutableStateFlow(LocalLLMServerState(
        status = LocalLLMServerStatus.STOPPED,
        errorMessage = "Local LLM not available on web platform"
    ))

    override val state: StateFlow<LocalLLMServerState> = _state.asStateFlow()

    override suspend fun start(modelPath: String, port: Int): Boolean {
        _state.value = _state.value.copy(
            status = LocalLLMServerStatus.ERROR,
            errorMessage = "Local LLM not supported on web platform"
        )
        return false
    }

    override suspend fun stop() {
        _state.value = LocalLLMServerState(status = LocalLLMServerStatus.STOPPED)
    }

    override fun isRunning(): Boolean = false

    override fun getBaseUrl(): String? = null
}
