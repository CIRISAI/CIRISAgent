package ai.ciris.mobile.shared.services

import kotlinx.coroutines.delay

/**
 * Server health management for CIRIS mobile
 * Handles health checks, shutdown coordination, and server state polling
 *
 * Extracted from MainActivity.kt (lines 1241-1660) for KMP shared module
 */
class ServerManager(
    private val serverUrl: String = "http://localhost:8080"
) {
    companion object {
        private const val TAG = "ServerManager"
    }

    /**
     * Response from local-shutdown endpoint for SmartStartup negotiation.
     * Copied from MainActivity.kt lines 1259-1267
     */
    data class ShutdownResponse(
        val status: String,           // "accepted", "busy", "error"
        val reason: String?,
        val retryAfterMs: Long?,
        val serverState: String?,     // "STARTING", "INITIALIZING", "RESUMING", "READY", "SHUTTING_DOWN"
        val uptimeSeconds: Double?,
        val resumeElapsedSeconds: Double?,
        val resumeTimeoutSeconds: Double?
    )

    /**
     * Check if server is running and responding to health checks.
     * Copied from MainActivity.kt lines 1241-1254
     *
     * @return true if server responds with 200 OK
     */
    suspend fun isExistingServerRunning(): Boolean {
        return try {
            checkServerHealth()
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Check server health via HTTP GET to /v1/system/health
     * Copied from MainActivity.kt lines 1839-1852
     *
     * @return true if server responds with 200 OK
     */
    suspend fun checkServerHealth(): Boolean {
        return try {
            // Platform-specific HTTP implementation will be injected via expect/actual
            performHealthCheck(serverUrl)
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Wait for an existing server to fully shut down.
     * Polls health endpoint until it fails (server is down).
     *
     * Copied from MainActivity.kt lines 1471-1483
     *
     * @param maxWaitSeconds Maximum time to wait for shutdown
     * @return true if server shut down within timeout
     */
    suspend fun waitForServerShutdown(maxWaitSeconds: Int = 10): Boolean {
        var waitedSeconds = 0
        while (waitedSeconds < maxWaitSeconds) {
            if (!isExistingServerRunning()) {
                println("[$TAG] Existing server has shut down after ${waitedSeconds}s")
                return true
            }
            delay(1000)
            waitedSeconds++
        }
        println("[$TAG] WARNING: Existing server did not shut down within ${maxWaitSeconds}s")
        return false
    }

    /**
     * Attempt to shut down an existing server gracefully via API.
     *
     * SmartStartup Protocol (from MainActivity.kt lines 1305-1410):
     * 1. Try local-shutdown endpoint (no auth required)
     *    - 200: Shutdown initiated - wait for death
     *    - 202: Already shutting down - wait for death
     *    - 409: Resume in progress - RETRY with backoff
     *    - 503: Server not ready - retry
     * 2. Fall back to authenticated shutdown if local fails
     *
     * @param onStatus Optional callback for status updates (for UI)
     * @return true if shutdown was triggered successfully
     */
    suspend fun shutdownExistingServer(
        onStatus: ((String) -> Unit)? = null
    ): Boolean {
        val maxRetries = 10  // Up to 10 retries for 409 (resume in progress)
        var retryCount = 0
        var totalWaitMs = 0L

        println("[$TAG] [SmartStartup] Starting shutdown negotiation (max retries: $maxRetries)")
        onStatus?.invoke("Shutting down existing server...")

        while (retryCount < maxRetries) {
            try {
                println("[$TAG] [SmartStartup] Trying local-shutdown (attempt ${retryCount + 1}/$maxRetries)...")

                val response = performLocalShutdown(serverUrl)

                println("[$TAG] [SmartStartup] Response: code=${response.first}, status=${response.second.status}, " +
                        "state=${response.second.serverState}, uptime=${response.second.uptimeSeconds}s, " +
                        "resumeElapsed=${response.second.resumeElapsedSeconds}s")

                val responseCode = response.first
                val shutdownResponse = response.second

                when (responseCode) {
                    200 -> {
                        println("[$TAG] [SmartStartup] ✓ Shutdown initiated: ${shutdownResponse.reason}")
                        onStatus?.invoke("Shutdown initiated")
                        return true
                    }
                    202 -> {
                        println("[$TAG] [SmartStartup] ✓ Server already shutting down: ${shutdownResponse.reason}")
                        onStatus?.invoke("Server already shutting down")
                        return true
                    }
                    409 -> {
                        // Resume in progress - retry with backoff
                        val retryDelay = shutdownResponse.retryAfterMs ?: 2000L
                        val resumeTimeout = shutdownResponse.resumeTimeoutSeconds ?: 30.0
                        val resumeElapsed = shutdownResponse.resumeElapsedSeconds ?: 0.0

                        println("[$TAG] [SmartStartup] Server busy (resume ${resumeElapsed}s / ${resumeTimeout}s), " +
                                "retry in ${retryDelay}ms...")
                        onStatus?.invoke("Server initializing... waiting (${resumeElapsed.toInt()}s)")

                        delay(retryDelay)
                        totalWaitMs += retryDelay
                        retryCount++

                        // Safety limit - don't wait forever
                        if (totalWaitMs > 60000) {
                            println("[$TAG] [SmartStartup] Exceeded 60s total wait time, giving up on retries")
                            break
                        }
                        continue  // Retry
                    }
                    503 -> {
                        // Server not ready - brief retry
                        val retryDelay = shutdownResponse.retryAfterMs ?: 1000L
                        println("[$TAG] [SmartStartup] Server not ready (503), retry in ${retryDelay}ms...")
                        delay(retryDelay)
                        totalWaitMs += retryDelay
                        retryCount++
                        continue
                    }
                    403 -> {
                        println("[$TAG] [SmartStartup] Local-shutdown rejected (403) - not localhost?!")
                        break  // Fall through to auth
                    }
                    else -> {
                        println("[$TAG] [SmartStartup] Unexpected response $responseCode, falling back to auth")
                        break  // Fall through to auth
                    }
                }
            } catch (e: Exception) {
                println("[$TAG] [SmartStartup] Local-shutdown failed: ${e.message}")
                break  // Fall through to auth
            }
        }

        if (retryCount >= maxRetries) {
            println("[$TAG] [SmartStartup] Exhausted $maxRetries retries (${totalWaitMs}ms total), trying auth shutdown")
        }

        // Fall back to authenticated shutdown
        return tryAuthenticatedShutdown(serverUrl, onStatus)
    }

    /**
     * Platform-specific health check implementation
     * Will be implemented via expect/actual pattern
     */
    private suspend fun performHealthCheck(serverUrl: String): Boolean {
        // This will be implemented in platform-specific code
        // For now, use the HTTP client abstraction
        return platformHttpGet("$serverUrl/v1/system/health") == 200
    }

    /**
     * Platform-specific local shutdown implementation
     * Returns (responseCode, shutdownResponse)
     */
    private suspend fun performLocalShutdown(serverUrl: String): Pair<Int, ShutdownResponse> {
        return platformHttpPost(
            "$serverUrl/v1/system/local-shutdown",
            "{}"
        )
    }

    /**
     * Try authenticated shutdown endpoint as fallback.
     * Copied from MainActivity.kt lines 1415-1465
     *
     * @param serverUrl The server base URL
     * @param onStatus Optional status callback
     * @return true if shutdown succeeded
     */
    private suspend fun tryAuthenticatedShutdown(
        serverUrl: String,
        onStatus: ((String) -> Unit)?
    ): Boolean {
        return try {
            println("[$TAG] [SmartStartup] Trying authenticated shutdown...")
            onStatus?.invoke("Trying authenticated shutdown...")

            // Get saved token from platform-specific storage
            val savedToken = platformGetAuthToken()

            val responseCode = platformHttpPostWithAuth(
                "$serverUrl/v1/system/shutdown",
                "{}",
                savedToken
            )

            println("[$TAG] [SmartStartup] Auth shutdown response: $responseCode")

            when (responseCode) {
                in 200..299 -> {
                    println("[$TAG] [SmartStartup] ✓ Auth shutdown successful")
                    onStatus?.invoke("Shutdown successful")
                    true
                }
                401 -> {
                    println("[$TAG] [SmartStartup] ✗ Auth failed (401) - token invalid or cleared")
                    onStatus?.invoke("Auth failed - no valid token")
                    false
                }
                403 -> {
                    println("[$TAG] [SmartStartup] ✗ Forbidden (403) - insufficient permissions")
                    onStatus?.invoke("Shutdown forbidden")
                    false
                }
                else -> {
                    println("[$TAG] [SmartStartup] ✗ Auth shutdown failed with $responseCode")
                    onStatus?.invoke("Shutdown failed")
                    false
                }
            }
        } catch (e: Exception) {
            println("[$TAG] [SmartStartup] ✗ Auth shutdown exception: ${e.message}")
            onStatus?.invoke("Shutdown error: ${e.message}")
            false
        }
    }
}

/**
 * Platform-specific HTTP operations
 * These will be implemented via expect/actual pattern for Android/iOS
 */
expect suspend fun platformHttpGet(url: String): Int
expect suspend fun platformHttpPost(url: String, body: String): Pair<Int, ServerManager.ShutdownResponse>
expect suspend fun platformHttpPostWithAuth(url: String, body: String, token: String?): Int
expect suspend fun platformGetAuthToken(): String?
