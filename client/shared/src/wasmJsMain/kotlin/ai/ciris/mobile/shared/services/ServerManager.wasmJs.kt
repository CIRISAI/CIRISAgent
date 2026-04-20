package ai.ciris.mobile.shared.services

import ai.ciris.mobile.shared.platform.createSecureStorage
import kotlinx.browser.localStorage

/**
 * WASM/JS implementation of platform HTTP operations.
 *
 * Note: Browser environments have CORS restrictions, so these operations
 * are stub implementations. A production web version would need a same-origin
 * backend proxy or CORS-enabled API endpoints.
 */

actual suspend fun platformHttpGet(url: String): Int {
    // Browser environment - HTTP operations limited by CORS
    // Return -1 to indicate not available
    println("[ServerManager] platformHttpGet not available in browser: $url")
    return -1
}

actual suspend fun platformHttpPost(url: String, body: String): Pair<Int, ServerManager.ShutdownResponse> {
    // Browser environment - HTTP operations limited by CORS
    println("[ServerManager] platformHttpPost not available in browser: $url")
    return Pair(
        -1,
        ServerManager.ShutdownResponse(
            status = "unavailable",
            reason = "Browser HTTP operations not supported",
            retryAfterMs = null,
            serverState = null,
            uptimeSeconds = null,
            resumeElapsedSeconds = null,
            resumeTimeoutSeconds = null
        )
    )
}

actual suspend fun platformHttpPostWithAuth(url: String, body: String, token: String?): Int {
    // Browser environment - HTTP operations limited by CORS
    println("[ServerManager] platformHttpPostWithAuth not available in browser: $url")
    return -1
}

actual suspend fun platformGetAuthToken(): String? {
    // Return token from localStorage if available
    return localStorage.getItem("ciris_access_token")
}
