package ai.ciris.mobile.shared.services

/**
 * Web implementation - server is remote, not local.
 */
actual class ServerManager {
    actual suspend fun startServer(): Result<String> = Result.success("")  // Use relative URLs
    actual fun stopServer() {}
    actual fun isRunning(): Boolean = true  // Always "running" (remote server)
    actual fun getServerUrl(): String = ""  // Relative URLs for ingress
}
