package ai.ciris.mobile.shared.platform

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android implementation of Python runtime using Chaquopy
 * Based on android/app/.../MainActivity.kt Python initialization
 */
actual class PythonRuntime {

    private var python: Python? = null
    private var serverStarted = false

    actual suspend fun initialize(pythonHome: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            // Initialize Chaquopy if not already started
            if (!Python.isStarted()) {
                // Note: AndroidPlatform requires Context
                // This will be provided by the Android application
                // For now, we'll assume it's already initialized by MainActivity
                // TODO: Pass context through dependency injection
                if (!Python.isStarted()) {
                    return@withContext Result.failure(
                        Exception("Python not initialized. Call Python.start(AndroidPlatform(context)) first.")
                    )
                }
            }

            python = Python.getInstance()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to initialize Python: ${e.message}", e))
        }
    }

    actual suspend fun startServer(): Result<String> = withContext(Dispatchers.IO) {
        try {
            val py = python ?: return@withContext Result.failure(
                Exception("Python not initialized")
            )

            // Import mobile_main module
            val mobileMain = try {
                py.getModule("mobile_main")
            } catch (e: Exception) {
                return@withContext Result.failure(
                    Exception("Failed to import mobile_main: ${e.message}", e)
                )
            }

            // Call start_ciris_runtime() function
            // This starts the FastAPI server in a background thread
            try {
                mobileMain.callAttr("start_ciris_runtime")
            } catch (e: Exception) {
                return@withContext Result.failure(
                    Exception("Failed to start CIRIS runtime: ${e.message}", e)
                )
            }

            serverStarted = true
            Result.success("http://localhost:8080")
        } catch (e: Exception) {
            Result.failure(Exception("Failed to start server: ${e.message}", e))
        }
    }

    actual suspend fun checkHealth(): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val url = URL("http://localhost:8080/v1/system/health")
            val connection = url.openConnection() as HttpURLConnection

            connection.apply {
                requestMethod = "GET"
                connectTimeout = 5000
                readTimeout = 5000
            }

            val healthy = connection.responseCode == 200
            connection.disconnect()

            Result.success(healthy)
        } catch (e: Exception) {
            // Server not ready yet, return false (not an error)
            Result.success(false)
        }
    }

    actual suspend fun getServicesStatus(): Result<Pair<Int, Int>> = withContext(Dispatchers.IO) {
        try {
            val url = URL("http://localhost:8080/v1/telemetry/unified")
            val connection = url.openConnection() as HttpURLConnection

            connection.apply {
                requestMethod = "GET"
                connectTimeout = 5000
                readTimeout = 5000
            }

            if (connection.responseCode != 200) {
                return@withContext Result.success(0 to 22) // Default
            }

            val response = connection.inputStream.bufferedReader().use { it.readText() }
            connection.disconnect()

            // Parse JSON response
            val json = JSONObject(response)
            val online = json.optInt("services_online", 0)
            val total = json.optInt("services_total", 22)

            Result.success(online to total)
        } catch (e: Exception) {
            // Server not ready yet, return default
            Result.success(0 to 22)
        }
    }

    actual fun shutdown() {
        // Chaquopy Python persists for app lifetime
        // We just mark server as not started
        serverStarted = false
    }

    actual fun isInitialized(): Boolean {
        return Python.isStarted() && python != null
    }

    actual fun isServerStarted(): Boolean {
        return serverStarted
    }
}

/**
 * Factory function to create Android Python runtime
 */
actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
