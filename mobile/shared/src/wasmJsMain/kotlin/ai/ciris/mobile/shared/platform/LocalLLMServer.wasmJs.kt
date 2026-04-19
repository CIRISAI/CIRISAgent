package ai.ciris.mobile.shared.platform

actual fun getLocalLLMServer(): LocalLLMServer = object : LocalLLMServer {
    override suspend fun start(): Result<String> = Result.failure(
        UnsupportedOperationException("Local LLM not available on web")
    )
    override suspend fun stop(): Result<Unit> = Result.success(Unit)
    override fun isRunning(): Boolean = false
    override fun getModelInfo(): String? = null
}
