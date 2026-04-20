@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.services

import kotlinx.cinterop.*
import platform.Foundation.*
import platform.darwin.*
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

/**
 * iOS platform-specific HTTP operations for ServerManager
 *
 * Uses NSURLSession for HTTP requests with async/await pattern.
 */

actual suspend fun platformHttpGet(url: String): Int {
    return suspendCoroutine { continuation ->
        val nsUrl = NSURL.URLWithString(url)
        if (nsUrl == null) {
            continuation.resume(-1)
            return@suspendCoroutine
        }

        val request = NSMutableURLRequest.requestWithURL(nsUrl)
        request.setHTTPMethod("GET")
        request.setTimeoutInterval(5.0)

        val task = NSURLSession.sharedSession.dataTaskWithRequest(request) { _, response, error ->
            if (error != null) {
                continuation.resume(-1)
            } else {
                val httpResponse = response as? NSHTTPURLResponse
                val code = httpResponse?.statusCode?.toInt() ?: -1
                continuation.resume(code)
            }
        }
        task.resume()
    }
}

actual suspend fun platformHttpPost(
    url: String,
    body: String
): Pair<Int, ServerManager.ShutdownResponse> {
    return suspendCoroutine { continuation ->
        val nsUrl = NSURL.URLWithString(url)
        if (nsUrl == null) {
            continuation.resume(Pair(-1, createErrorResponse("Invalid URL")))
            return@suspendCoroutine
        }

        val request = NSMutableURLRequest.requestWithURL(nsUrl)
        request.setHTTPMethod("POST")
        request.setValue("application/json", forHTTPHeaderField = "Content-Type")
        request.setHTTPBody(body.encodeToByteArray().toNSData())
        request.setTimeoutInterval(10.0)

        val task = NSURLSession.sharedSession.dataTaskWithRequest(request) { _, response, error ->
            if (error != null) {
                continuation.resume(Pair(-1, createErrorResponse(error.localizedDescription)))
            } else {
                val httpResponse = response as? NSHTTPURLResponse
                val code = httpResponse?.statusCode?.toInt() ?: -1
                // TODO: Parse response body for ShutdownResponse
                continuation.resume(Pair(code, createErrorResponse("Response parsing not implemented")))
            }
        }
        task.resume()
    }
}

actual suspend fun platformHttpPostWithAuth(
    url: String,
    body: String,
    token: String?
): Int {
    return suspendCoroutine { continuation ->
        val nsUrl = NSURL.URLWithString(url)
        if (nsUrl == null) {
            continuation.resume(-1)
            return@suspendCoroutine
        }

        val request = NSMutableURLRequest.requestWithURL(nsUrl)
        request.setHTTPMethod("POST")
        request.setValue("application/json", forHTTPHeaderField = "Content-Type")
        if (token != null) {
            request.setValue("Bearer $token", forHTTPHeaderField = "Authorization")
        }
        request.setHTTPBody(body.encodeToByteArray().toNSData())
        request.setTimeoutInterval(10.0)

        val task = NSURLSession.sharedSession.dataTaskWithRequest(request) { _, response, error ->
            if (error != null) {
                continuation.resume(-1)
            } else {
                val httpResponse = response as? NSHTTPURLResponse
                val code = httpResponse?.statusCode?.toInt() ?: -1
                continuation.resume(code)
            }
        }
        task.resume()
    }
}

actual suspend fun platformGetAuthToken(): String? {
    // TODO: Get token from Keychain via SecureStorage
    return null
}

private fun createErrorResponse(reason: String): ServerManager.ShutdownResponse {
    return ServerManager.ShutdownResponse(
        status = "error",
        reason = reason,
        retryAfterMs = null,
        serverState = null,
        uptimeSeconds = null,
        resumeElapsedSeconds = null,
        resumeTimeoutSeconds = null
    )
}

// Helper extension to convert ByteArray to NSData
private fun ByteArray.toNSData(): NSData {
    if (this.isEmpty()) return NSData()
    return this.usePinned { pinned ->
        NSData.dataWithBytes(pinned.addressOf(0), this.size.toULong())
    }
}
