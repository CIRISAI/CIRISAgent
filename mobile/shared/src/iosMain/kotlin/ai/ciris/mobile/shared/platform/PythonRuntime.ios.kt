@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.*
import kotlinx.coroutines.suspendCancellableCoroutine
import platform.Foundation.*
import kotlin.coroutines.resume

/**
 * iOS implementation of Python runtime.
 *
 * On iOS, Python initialization is handled by the Swift layer (PythonBridge.swift)
 * before the Compose UI is shown. This Kotlin class provides HTTP-based health
 * checks and status monitoring for the running Python server.
 *
 * The initialization flow is:
 * 1. Swift ContentView initializes Python via PythonBridge
 * 2. Swift waits for health endpoint to respond
 * 3. Compose UI (and this class) is created
 * 4. This class monitors health and service status via HTTP
 */
actual class PythonRuntime : PythonRuntimeProtocol {

    private var _initialized = false
    private var _serverStarted = false

    actual override val serverUrl: String = "http://localhost:8080"

    /**
     * On iOS, Python is initialized by Swift before Compose UI loads.
     * This method just marks the Kotlin state as initialized.
     */
    actual override suspend fun initialize(pythonHome: String): Result<Unit> {
        println("[PythonRuntime.iOS] initialize called - Python should already be initialized by Swift")
        _initialized = true
        return Result.success(Unit)
    }

    /**
     * On iOS, the server is started by Swift before Compose UI loads.
     * This method checks if the server is actually running.
     */
    actual override suspend fun startServer(): Result<String> {
        println("[PythonRuntime.iOS] startServer called - checking if server is running...")

        val healthResult = checkHealth()
        return if (healthResult.getOrNull() == true) {
            _serverStarted = true
            println("[PythonRuntime.iOS] Server is running at $serverUrl")
            Result.success(serverUrl)
        } else {
            Result.failure(Exception("Server not responding at $serverUrl"))
        }
    }

    /**
     * Full lifecycle management - on iOS this is handled by Swift.
     * We just verify the server is running and report status.
     */
    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> {
        onStatus?.invoke("Checking Python server status...")

        // On iOS, Python is already initialized by Swift
        _initialized = true
        onStatus?.invoke("Python initialized by iOS runtime")

        // Check if server is healthy
        val healthResult = checkHealth()
        if (healthResult.getOrNull() == true) {
            _serverStarted = true
            onStatus?.invoke("Server is running")
            return Result.success(serverUrl)
        }

        // Server might still be starting, wait a bit
        onStatus?.invoke("Waiting for server to start...")
        for (i in 1..10) {
            kotlinx.coroutines.delay(1000)
            if (checkHealth().getOrNull() == true) {
                _serverStarted = true
                onStatus?.invoke("Server ready after ${i}s")
                return Result.success(serverUrl)
            }
        }

        return Result.failure(Exception("Server did not start within 10 seconds"))
    }

    /**
     * Inject configuration - on iOS, config is set via environment variables
     * before Python starts.
     */
    actual override fun injectPythonConfig(config: Map<String, String>) {
        // On iOS, we can't modify Python config after it's started
        // Configuration should be set via environment variables in Swift
        println("[PythonRuntime.iOS] injectPythonConfig called - config should be set in Swift/ObjC layer")
    }

    /**
     * Check server health via HTTP request to /v1/system/health
     */
    actual override suspend fun checkHealth(): Result<Boolean> {
        return suspendCancellableCoroutine { continuation ->
            val nsUrl = NSURL.URLWithString("$serverUrl/v1/system/health")
            if (nsUrl == null) {
                continuation.resume(Result.failure(Exception("Invalid URL")))
                return@suspendCancellableCoroutine
            }

            val request = NSMutableURLRequest.requestWithURL(nsUrl)
            request.setHTTPMethod("GET")
            request.setTimeoutInterval(5.0)

            val task = NSURLSession.sharedSession.dataTaskWithRequest(request) { _, response, error ->
                if (error != null) {
                    continuation.resume(Result.success(false))
                } else {
                    val httpResponse = response as? NSHTTPURLResponse
                    val isHealthy = httpResponse?.statusCode?.toInt() == 200
                    continuation.resume(Result.success(isHealthy))
                }
            }
            task.resume()
        }
    }

    /**
     * Get services status from /v1/telemetry/unified endpoint.
     * Returns (online count, total count).
     */
    actual override suspend fun getServicesStatus(): Result<Pair<Int, Int>> {
        return suspendCancellableCoroutine { continuation ->
            val nsUrl = NSURL.URLWithString("$serverUrl/v1/telemetry/unified")
            if (nsUrl == null) {
                continuation.resume(Result.success(0 to 22))
                return@suspendCancellableCoroutine
            }

            val request = NSMutableURLRequest.requestWithURL(nsUrl)
            request.setHTTPMethod("GET")
            request.setTimeoutInterval(10.0)

            val task = NSURLSession.sharedSession.dataTaskWithRequest(request) { data, response, error ->
                if (error != null || data == null) {
                    continuation.resume(Result.success(0 to 22))
                    return@dataTaskWithRequest
                }

                val httpResponse = response as? NSHTTPURLResponse
                if (httpResponse?.statusCode?.toInt() != 200) {
                    continuation.resume(Result.success(0 to 22))
                    return@dataTaskWithRequest
                }

                // Parse JSON response to get services_online and services_total
                try {
                    val jsonString = NSString.create(data = data, encoding = NSUTF8StringEncoding)
                    // Simple JSON parsing - look for "services_online" and "services_total"
                    val onlineMatch = Regex(""""services_online"\s*:\s*(\d+)""").find(jsonString.toString())
                    val totalMatch = Regex(""""services_total"\s*:\s*(\d+)""").find(jsonString.toString())

                    val online = onlineMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                    val total = totalMatch?.groupValues?.get(1)?.toIntOrNull() ?: 22

                    continuation.resume(Result.success(online to total))
                } catch (e: Exception) {
                    continuation.resume(Result.success(0 to 22))
                }
            }
            task.resume()
        }
    }

    /**
     * Shutdown is handled by the app lifecycle on iOS.
     */
    actual override fun shutdown() {
        println("[PythonRuntime.iOS] shutdown called - will be handled by app lifecycle")
        _serverStarted = false
        _initialized = false
    }

    actual override fun isInitialized(): Boolean = _initialized

    actual override fun isServerStarted(): Boolean = _serverStarted
}

/**
 * Factory function to create iOS Python runtime
 */
actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
