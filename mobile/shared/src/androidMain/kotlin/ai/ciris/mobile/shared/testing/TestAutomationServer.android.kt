package ai.ciris.mobile.shared.testing

import android.util.Log
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.server.application.*
import io.ktor.server.cio.*
import io.ktor.server.engine.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.plugins.statuspages.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.coroutines.delay
import kotlinx.serialization.json.Json

private const val TAG = "TestAutomation.android"

/**
 * Test Automation HTTP Server for Android.
 * Uses Ktor CIO engine (same as Desktop).
 * Provides HTTP endpoints for UI automation on port 8091.
 * Only starts when CIRIS_TEST_MODE=true.
 */
class AndroidTestAutomationServer(private val port: Int = 8091) {

    private var server: ApplicationEngine? = null

    private val json = Json {
        prettyPrint = true
        isLenient = true
        ignoreUnknownKeys = true
    }

    fun start() {
        if (server != null) return

        server = embeddedServer(CIO, port = port) {
            install(ContentNegotiation) {
                json(json)
            }

            install(StatusPages) {
                exception<Throwable> { call, cause ->
                    Log.e(TAG, "Error: ${cause.message}", cause)
                    call.respondText(
                        text = """{"error": "${cause.message?.replace("\"", "'")}"}""",
                        contentType = ContentType.Application.Json,
                        status = HttpStatusCode.InternalServerError
                    )
                }
            }

            routing {
                // Health check
                get("/health") {
                    call.respond(TestAutomationHandler.handleHealth())
                }

                // Get UI element tree
                get("/tree") {
                    call.respond(TestAutomationHandler.handleTree())
                }

                // Get current screen
                get("/screen") {
                    call.respond(TestAutomationHandler.handleScreen())
                }

                // Click element by testTag
                post("/click") {
                    val request = call.receive<ClickRequest>()
                    val resp = TestAutomationHandler.handleClick(request)
                    call.respond(
                        if (resp.success) HttpStatusCode.OK else HttpStatusCode.NotFound,
                        resp
                    )
                }

                // Input text to element
                post("/input") {
                    val request = call.receive<InputRequest>()
                    call.respond(TestAutomationHandler.handleInput(request))
                }

                // Wait for element to appear
                post("/wait") {
                    val request = call.receive<WaitRequest>()
                    val resp = TestAutomationHandler.handleWait(request)
                    call.respond(
                        if (resp.success) HttpStatusCode.OK else HttpStatusCode.NotFound,
                        resp
                    )
                }

                // Get element info
                get("/element/{testTag}") {
                    val testTag = call.parameters["testTag"] ?: ""
                    val elem = TestAutomationHandler.handleGetElement(testTag)
                    if (elem != null) {
                        call.respond(elem)
                    } else {
                        call.respond(HttpStatusCode.NotFound, mapOf("error" to "Element not found"))
                    }
                }
            }
        }

        server?.start(wait = false)
        Log.i(TAG, "Server started on http://localhost:$port")
    }

    fun stop() {
        server?.stop(1000, 2000)
        server = null
        Log.i(TAG, "Server stopped")
    }

    companion object {
        private var instance: AndroidTestAutomationServer? = null

        // Can be set programmatically before app starts (e.g., from test runner)
        @Volatile
        var forceTestMode: Boolean = false

        /**
         * Start the test server if CIRIS_TEST_MODE is enabled.
         * Call this from the main activity or application class.
         *
         * Test mode can be enabled via:
         * 1. forceTestMode = true (set programmatically)
         * 2. File /data/local/tmp/ciris_test_mode exists
         * 3. System property (via adb shell setprop)
         */
        fun startIfEnabled() {
            if (isTestModeEnabled()) {
                val port = 8091
                Log.i(TAG, "Test mode enabled, starting server on port $port")
                instance = AndroidTestAutomationServer(port).also { it.start() }
            } else {
                Log.d(TAG, "Test mode not enabled")
            }
        }

        fun stop() {
            instance?.stop()
            instance = null
        }

        fun isTestModeEnabled(): Boolean {
            // Check programmatic flag first
            if (forceTestMode) return true

            // Check for test mode file (can be created via: adb shell touch /data/local/tmp/ciris_test_mode)
            try {
                if (java.io.File("/data/local/tmp/ciris_test_mode").exists()) {
                    Log.i(TAG, "Test mode enabled via /data/local/tmp/ciris_test_mode file")
                    return true
                }
            } catch (e: Exception) {
                // Ignore permission errors
            }

            // Check system properties and environment
            val testMode = System.getenv("CIRIS_TEST_MODE")?.lowercase()
                ?: System.getProperty("CIRIS_TEST_MODE")?.lowercase()
            return testMode in listOf("true", "1", "yes")
        }
    }
}
