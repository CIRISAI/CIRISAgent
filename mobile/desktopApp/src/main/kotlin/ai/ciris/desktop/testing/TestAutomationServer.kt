package ai.ciris.desktop.testing

import ai.ciris.mobile.shared.platform.TestAutomation
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.server.application.*
import io.ktor.server.cio.*
import io.ktor.server.engine.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.coroutines.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.concurrent.ConcurrentHashMap

/**
 * Test Automation Server for CIRIS Desktop App
 *
 * Provides HTTP endpoints for UI automation:
 * - GET /health - Server health check
 * - GET /tree - Get UI element tree (testTags and positions)
 * - POST /click - Click element by testTag
 * - POST /input - Input text to element
 * - GET /screen - Get current screen name
 * - POST /navigate - Navigate to a screen
 *
 * Enable by setting CIRIS_TEST_MODE=true environment variable.
 */
class TestAutomationServer(
    private val port: Int = 8091
) {
    private var server: ApplicationEngine? = null

    // Registry of UI elements with their positions and testTags
    // Updated by Compose via registerElement() calls
    private val elements = ConcurrentHashMap<String, ElementInfo>()

    // Window position offset (for converting window coords to screen coords)
    @Volatile
    var windowX: Int = 0
    @Volatile
    var windowY: Int = 0

    // Current screen name
    @Volatile
    var currentScreen: String = "unknown"

    // Callback for navigation requests
    var onNavigationRequest: ((String) -> Unit)? = null

    /**
     * Update window position (call when window moves)
     */
    fun updateWindowPosition(x: Int, y: Int) {
        windowX = x
        windowY = y
    }

    /**
     * Register a UI element for automation
     * Call this from Compose modifiers when elements are positioned
     * Coordinates are converted to absolute screen position using window offset
     */
    fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String? = null) {
        // Convert window-relative to screen-absolute coordinates
        val screenX = x + windowX
        val screenY = y + windowY
        elements[testTag] = ElementInfo(
            testTag = testTag,
            x = screenX,
            y = screenY,
            width = width,
            height = height,
            text = text,
            centerX = screenX + width / 2,
            centerY = screenY + height / 2
        )
    }

    /**
     * Unregister a UI element (when it leaves composition)
     */
    fun unregisterElement(testTag: String) {
        elements.remove(testTag)
    }

    /**
     * Clear all registered elements (on screen transition)
     */
    fun clearElements() {
        elements.clear()
    }

    /**
     * Start the automation server
     */
    fun start() {
        server = embeddedServer(CIO, port = port) {
            install(ContentNegotiation) {
                json(Json {
                    prettyPrint = true
                    isLenient = true
                    ignoreUnknownKeys = true
                })
            }

            // Global exception handling
            install(io.ktor.server.plugins.statuspages.StatusPages) {
                exception<Throwable> { call, cause ->
                    println("[TestAutomation] Error: ${cause.message}")
                    cause.printStackTrace()
                    call.respondText(
                        text = """{"error": "${cause.message?.replace("\"", "'")}"}""",
                        contentType = io.ktor.http.ContentType.Application.Json,
                        status = io.ktor.http.HttpStatusCode.InternalServerError
                    )
                }
            }

            routing {
                // Health check
                get("/health") {
                    call.respond(HealthResponse(status = "ok", testMode = true))
                }

                // Get UI element tree
                get("/tree") {
                    val tree = elements.values.toList().sortedBy { it.testTag }
                    call.respond(TreeResponse(
                        screen = currentScreen,
                        elements = tree,
                        count = tree.size
                    ))
                }

                // Get current screen
                get("/screen") {
                    call.respond(ScreenResponse(screen = currentScreen))
                }

                // Click element by testTag (programmatic - no mouse movement)
                post("/click") {
                    val request = call.receive<ClickRequest>()
                    val element = elements[request.testTag]

                    if (element == null) {
                        call.respond(
                            HttpStatusCode.NotFound,
                            ActionResponse(success = false, error = "Element not found: ${request.testTag}")
                        )
                        return@post
                    }

                    // Trigger click via registered handler (programmatic, no Robot)
                    val clicked = TestAutomation.triggerClick(request.testTag)

                    if (!clicked) {
                        call.respond(
                            HttpStatusCode.NotFound,
                            ActionResponse(
                                success = false,
                                error = "No click handler registered for: ${request.testTag}. Use testableClickable modifier."
                            )
                        )
                        return@post
                    }

                    call.respond(ActionResponse(
                        success = true,
                        element = element.testTag,
                        action = "click",
                        coordinates = "${element.centerX},${element.centerY}"
                    ))
                }

                // Input text to element (programmatic - no keyboard input)
                post("/input") {
                    val request = call.receive<InputRequest>()
                    val element = elements[request.testTag]

                    if (element == null) {
                        call.respond(
                            HttpStatusCode.NotFound,
                            ActionResponse(success = false, error = "Element not found: ${request.testTag}")
                        )
                        return@post
                    }

                    // Request text input via flow (UI will pick it up)
                    TestAutomation.requestTextInput(request.testTag, request.text, request.clearFirst)

                    // Give UI time to process the request
                    delay(100)

                    call.respond(ActionResponse(
                        success = true,
                        element = element.testTag,
                        action = "input",
                        text = request.text
                    ))
                }

                // Navigate to screen
                post("/navigate") {
                    val request = call.receive<NavigateRequest>()
                    val callback = onNavigationRequest

                    if (callback == null) {
                        call.respond(
                            HttpStatusCode.ServiceUnavailable,
                            ActionResponse(success = false, error = "Navigation callback not configured")
                        )
                        return@post
                    }

                    callback(request.screen)

                    // Wait for navigation to complete
                    delay(500)

                    call.respond(ActionResponse(
                        success = true,
                        action = "navigate",
                        screen = request.screen
                    ))
                }

                // Wait for element to appear
                post("/wait") {
                    val request = call.receive<WaitRequest>()
                    val startTime = System.currentTimeMillis()
                    val timeoutMs = request.timeoutMs ?: 5000

                    while (System.currentTimeMillis() - startTime < timeoutMs) {
                        if (elements.containsKey(request.testTag)) {
                            call.respond(ActionResponse(
                                success = true,
                                element = request.testTag,
                                action = "wait"
                            ))
                            return@post
                        }
                        delay(100)
                    }

                    call.respond(
                        HttpStatusCode.NotFound,
                        ActionResponse(
                            success = false,
                            error = "Element not found within ${timeoutMs}ms: ${request.testTag}"
                        )
                    )
                }

                // Get element info
                get("/element/{testTag}") {
                    val testTag = call.parameters["testTag"] ?: ""
                    val element = elements[testTag]

                    if (element == null) {
                        call.respond(HttpStatusCode.NotFound, mapOf("error" to "Element not found"))
                        return@get
                    }

                    call.respond(element)
                }
            }
        }

        server?.start(wait = false)
        println("[TestAutomation] Server started on http://localhost:$port")
    }

    /**
     * Stop the automation server
     */
    fun stop() {
        server?.stop(1000, 2000)
        server = null
        println("[TestAutomation] Server stopped")
    }

    companion object {
        @Volatile
        private var instance: TestAutomationServer? = null

        /**
         * Get or create the singleton instance
         */
        fun getInstance(port: Int = 8091): TestAutomationServer {
            return instance ?: synchronized(this) {
                instance ?: TestAutomationServer(port).also { instance = it }
            }
        }

        /**
         * Check if test mode is enabled
         */
        fun isTestModeEnabled(): Boolean {
            return System.getenv("CIRIS_TEST_MODE")?.lowercase() in listOf("true", "1", "yes")
        }
    }
}

// Request/Response models
@Serializable
data class ElementInfo(
    val testTag: String,
    val x: Int,
    val y: Int,
    val width: Int,
    val height: Int,
    val text: String? = null,
    val centerX: Int,
    val centerY: Int
)

@Serializable
data class HealthResponse(
    val status: String,
    val testMode: Boolean
)

@Serializable
data class TreeResponse(
    val screen: String,
    val elements: List<ElementInfo>,
    val count: Int
)

@Serializable
data class ScreenResponse(
    val screen: String
)

@Serializable
data class ClickRequest(
    val testTag: String
)

@Serializable
data class InputRequest(
    val testTag: String,
    val text: String,
    val clearFirst: Boolean = true
)

@Serializable
data class NavigateRequest(
    val screen: String
)

@Serializable
data class WaitRequest(
    val testTag: String,
    val timeoutMs: Int? = 5000
)

@Serializable
data class ActionResponse(
    val success: Boolean,
    val element: String? = null,
    val action: String? = null,
    val coordinates: String? = null,
    val text: String? = null,
    val screen: String? = null,
    val error: String? = null
)
