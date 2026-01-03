package ai.ciris.mobile.shared.services

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android platform implementation for HTTP operations
 * Used by ServerManager for health checks and shutdown requests
 */

private const val TAG = "PlatformHttp"

/**
 * Perform HTTP GET request
 * @return HTTP response code
 */
actual suspend fun platformHttpGet(url: String): Int = withContext(Dispatchers.IO) {
    try {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.apply {
            requestMethod = "GET"
            connectTimeout = 2000
            readTimeout = 2000
        }
        val responseCode = connection.responseCode
        connection.disconnect()
        responseCode
    } catch (e: Exception) {
        Log.w(TAG, "HTTP GET failed: ${e.message}")
        0  // Return 0 for connection errors
    }
}

/**
 * Perform HTTP POST request
 * @return Pair of (responseCode, ShutdownResponse)
 */
actual suspend fun platformHttpPost(url: String, body: String): Pair<Int, ServerManager.ShutdownResponse> = withContext(Dispatchers.IO) {
    try {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.apply {
            requestMethod = "POST"
            connectTimeout = 3000
            readTimeout = 5000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
        }

        connection.outputStream.bufferedWriter().use { it.write(body) }

        val responseCode = connection.responseCode

        // Read response body for JSON data
        val responseBody = try {
            if (responseCode in 200..499) {
                val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
                stream?.bufferedReader()?.readText() ?: "{}"
            } else {
                "{}"
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read response body: ${e.message}")
            "{}"
        }
        connection.disconnect()

        val shutdownResponse = parseShutdownResponse(responseBody)
        Pair(responseCode, shutdownResponse)
    } catch (e: Exception) {
        Log.w(TAG, "HTTP POST failed: ${e.message}")
        Pair(0, ServerManager.ShutdownResponse("error", e.message, null, null, null, null, null))
    }
}

/**
 * Perform HTTP POST request with authentication
 * @return HTTP response code
 */
actual suspend fun platformHttpPostWithAuth(url: String, body: String, token: String?): Int = withContext(Dispatchers.IO) {
    try {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.apply {
            requestMethod = "POST"
            connectTimeout = 3000
            readTimeout = 5000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            if (token != null) {
                setRequestProperty("Authorization", "Bearer $token")
            }
        }

        connection.outputStream.bufferedWriter().use { it.write(body) }
        val responseCode = connection.responseCode
        connection.disconnect()
        responseCode
    } catch (e: Exception) {
        Log.w(TAG, "HTTP POST with auth failed: ${e.message}")
        0
    }
}

/**
 * Get saved auth token from platform-specific storage
 * NOTE: This should be implemented to read from SharedPreferences
 * For now, returns null (will be implemented later)
 */
actual suspend fun platformGetAuthToken(): String? {
    // TODO: Implement SharedPreferences access
    // This requires Android Context which should be injected
    return null
}

/**
 * Parse JSON response from local-shutdown endpoint
 * Copied from MainActivity.kt lines 1272-1290
 */
private fun parseShutdownResponse(json: String): ServerManager.ShutdownResponse {
    return try {
        val obj = JSONObject(json)
        ServerManager.ShutdownResponse(
            status = obj.optString("status", "unknown"),
            reason = obj.optString("reason", null),
            retryAfterMs = if (obj.has("retry_after_ms")) obj.getLong("retry_after_ms") else null,
            serverState = obj.optString("server_state", null),
            uptimeSeconds = if (obj.has("uptime_seconds")) obj.getDouble("uptime_seconds") else null,
            resumeElapsedSeconds = if (obj.has("resume_elapsed_seconds") && !obj.isNull("resume_elapsed_seconds"))
                obj.getDouble("resume_elapsed_seconds") else null,
            resumeTimeoutSeconds = if (obj.has("resume_timeout_seconds"))
                obj.getDouble("resume_timeout_seconds") else null
        )
    } catch (e: Exception) {
        Log.w(TAG, "Failed to parse JSON response: ${e.message}")
        ServerManager.ShutdownResponse("unknown", null, null, null, null, null, null)
    }
}
