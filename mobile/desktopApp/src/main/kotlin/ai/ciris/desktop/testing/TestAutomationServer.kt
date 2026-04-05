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
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.awt.Rectangle
import java.awt.Robot
import java.io.ByteArrayOutputStream
import java.util.concurrent.ConcurrentHashMap
import javax.imageio.ImageIO

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

    // AWT window reference for screenshot capture
    @Volatile
    var awtWindow: java.awt.Window? = null

    // AWT Robot for screen capture (lazy init)
    private val robot: Robot by lazy { Robot() }

    // Callback for navigation requests
    var onNavigationRequest: ((String) -> Unit)? = null

    /**
     * Perform a real mouse click at screen coordinates using java.awt.Robot.
     * This works for ALL UI elements including dropdowns, menus, and popups
     * that don't have programmatic click handlers.
     */
    private fun performMouseClick(screenX: Int, screenY: Int) {
        robot.mouseMove(screenX, screenY)
        Thread.sleep(50)
        robot.mousePress(java.awt.event.InputEvent.BUTTON1_DOWN_MASK)
        Thread.sleep(30)
        robot.mouseRelease(java.awt.event.InputEvent.BUTTON1_DOWN_MASK)
    }

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

                    // Try programmatic click first (fastest, works for testableClickable)
                    val clicked = TestAutomation.triggerClick(request.testTag)

                    if (clicked) {
                        call.respond(ActionResponse(
                            success = true,
                            element = element.testTag,
                            action = "click",
                            coordinates = "${element.centerX},${element.centerY}"
                        ))
                        return@post
                    }

                    // Fallback: use Robot mouse click (works for dropdowns, ExposedDropdownMenuBox, etc.)
                    println("[TestAutomation] Programmatic click failed for ${request.testTag}, falling back to mouse click at (${element.centerX}, ${element.centerY})")
                    performMouseClick(element.centerX, element.centerY)

                    call.respond(ActionResponse(
                        success = true,
                        element = element.testTag,
                        action = "mouse-click",
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

                // Mouse click - real AWT Robot click at element or coordinates
                // Works for dropdowns, popup menus, and any element
                post("/mouse-click") {
                    val request = call.receive<ClickRequest>()
                    val element = elements[request.testTag]

                    if (element == null) {
                        call.respond(
                            HttpStatusCode.NotFound,
                            ActionResponse(success = false, error = "Element not found: ${request.testTag}")
                        )
                        return@post
                    }

                    performMouseClick(element.centerX, element.centerY)

                    call.respond(ActionResponse(
                        success = true,
                        element = element.testTag,
                        action = "mouse-click",
                        coordinates = "${element.centerX},${element.centerY}"
                    ))
                }

                // Mouse click at raw screen coordinates
                post("/mouse-click-xy") {
                    val body = call.receiveText()
                    val json = kotlinx.serialization.json.Json.parseToJsonElement(body)
                    val x = json.jsonObject["x"]?.jsonPrimitive?.int ?: 0
                    val y = json.jsonObject["y"]?.jsonPrimitive?.int ?: 0

                    performMouseClick(x, y)

                    call.respond(ActionResponse(
                        success = true,
                        action = "mouse-click-xy",
                        coordinates = "$x,$y"
                    ))
                }

                // Scroll - programmatic scroll on an element (uses Robot mouse wheel)
                post("/scroll") {
                    val body = call.receiveText()
                    val json = kotlinx.serialization.json.Json.parseToJsonElement(body)
                    val testTag = json.jsonObject["testTag"]?.jsonPrimitive?.content ?: ""
                    val direction = json.jsonObject["direction"]?.jsonPrimitive?.content ?: "down"
                    val amount = json.jsonObject["amount"]?.jsonPrimitive?.int ?: 300

                    val element = elements[testTag]
                    if (element != null) {
                        // Move mouse to element center then scroll
                        robot.mouseMove(element.centerX, element.centerY)
                        Thread.sleep(50)
                        val wheelAmount = if (direction == "up") -(amount / 30) else (amount / 30)
                        robot.mouseWheel(wheelAmount)
                    }

                    // Also dispatch via shared handler for cross-platform state
                    ai.ciris.mobile.shared.testing.TestAutomationState.requestScroll(testTag, direction, amount)

                    call.respond(ai.ciris.mobile.shared.testing.ActionResponse(
                        success = true,
                        element = testTag,
                        action = "scroll",
                        text = "$direction:$amount"
                    ))
                }

                // Act and View - combined action + tree fetch in one call
                // Reduces 3 API calls (action + sleep + tree) to 1
                post("/act") {
                    val request = call.receive<ai.ciris.mobile.shared.testing.ActAndViewRequest>()

                    // 1. Perform the action
                    val actionResult: ai.ciris.mobile.shared.testing.ActionResponse = when (request.action.lowercase()) {
                        "click" -> {
                            val element = elements[request.testTag]
                            if (element == null) {
                                ai.ciris.mobile.shared.testing.ActionResponse(
                                    success = false,
                                    error = "Element not found: ${request.testTag}"
                                )
                            } else {
                                val clicked = TestAutomation.triggerClick(request.testTag)
                                if (clicked) {
                                    ai.ciris.mobile.shared.testing.ActionResponse(
                                        success = true,
                                        element = request.testTag,
                                        action = "click",
                                        coordinates = "${element.centerX},${element.centerY}"
                                    )
                                } else {
                                    // Fallback to mouse click
                                    performMouseClick(element.centerX, element.centerY)
                                    ai.ciris.mobile.shared.testing.ActionResponse(
                                        success = true,
                                        element = request.testTag,
                                        action = "mouse-click",
                                        coordinates = "${element.centerX},${element.centerY}"
                                    )
                                }
                            }
                        }
                        "input" -> {
                            val element = elements[request.testTag]
                            if (element == null) {
                                ai.ciris.mobile.shared.testing.ActionResponse(
                                    success = false,
                                    error = "Element not found: ${request.testTag}"
                                )
                            } else {
                                TestAutomation.requestTextInput(request.testTag, request.text ?: "", request.clearFirst)
                                ai.ciris.mobile.shared.testing.ActionResponse(
                                    success = true,
                                    element = request.testTag,
                                    action = "input",
                                    text = request.text
                                )
                            }
                        }
                        else -> ai.ciris.mobile.shared.testing.ActionResponse(
                            success = false,
                            error = "Unknown action: ${request.action}"
                        )
                    }

                    // 2. Wait for UI to settle
                    if (request.waitMs > 0) {
                        delay(request.waitMs.toLong())
                    }

                    // 3. Get filtered elements
                    val allElements = elements.values.toList()
                    val filterPatterns = request.filterTags
                    val filteredElements = if (filterPatterns.isNullOrEmpty()) {
                        allElements
                    } else {
                        allElements.filter { element ->
                            filterPatterns.any { pattern ->
                                element.testTag.contains(pattern, ignoreCase = true)
                            }
                        }
                    }

                    call.respond(ai.ciris.mobile.shared.testing.ActAndViewResponse(
                        actionResult = actionResult,
                        screen = currentScreen,
                        elements = filteredElements.map { e ->
                            ai.ciris.mobile.shared.testing.ElementInfo(
                                testTag = e.testTag,
                                x = e.x,
                                y = e.y,
                                width = e.width,
                                height = e.height,
                                text = e.text,
                                centerX = e.centerX,
                                centerY = e.centerY
                            )
                        },
                        elementCount = filteredElements.size
                    ))
                }

                // Inject a file attachment (bypasses native file picker for test automation)
                post("/inject-file") {
                    val request = call.receive<InjectFileRequest>()

                    // Validate size
                    if (request.sizeBytes > 10L * 1024 * 1024) {
                        call.respond(
                            HttpStatusCode.BadRequest,
                            ActionResponse(success = false, error = "File too large: ${request.sizeBytes} bytes (max 10MB)")
                        )
                        return@post
                    }

                    // Inject via TestAutomation flow (ViewModel will pick it up)
                    TestAutomation.injectFile(
                        name = request.filename,
                        mediaType = request.mediaType,
                        dataBase64 = request.dataBase64,
                        sizeBytes = request.sizeBytes
                    )

                    // Give UI time to process
                    delay(200)

                    call.respond(ActionResponse(
                        success = true,
                        action = "inject-file",
                        text = "${request.filename} (${request.mediaType}, ${request.sizeBytes} bytes)"
                    ))
                }

                // Clear all injected file attachments
                post("/clear-attachments") {
                    // Trigger clear by injecting a sentinel (ViewModel checks for this)
                    // Actually, we just clear the injection request
                    TestAutomation.clearFileInjectionRequest()

                    call.respond(ActionResponse(
                        success = true,
                        action = "clear-attachments"
                    ))
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

                // Screenshot - capture the CIRIS window as PNG (test mode only)
                get("/screenshot") {
                    if (!isTestModeEnabled()) {
                        call.respond(HttpStatusCode.Forbidden, mapOf("error" to "Screenshots require CIRIS_TEST_MODE=true"))
                        return@get
                    }
                    val window = awtWindow
                    if (window == null) {
                        call.respond(HttpStatusCode.ServiceUnavailable, mapOf("error" to "Window not available"))
                        return@get
                    }

                    try {
                        val bounds = window.bounds
                        val screenRect = Rectangle(bounds.x, bounds.y, bounds.width, bounds.height)
                        val image = robot.createScreenCapture(screenRect)

                        val format = call.request.queryParameters["format"] ?: "png"

                        // Check if caller wants base64 JSON response
                        if (call.request.queryParameters["base64"] == "true") {
                            val baos = ByteArrayOutputStream()
                            ImageIO.write(image, format, baos)
                            val encoded = java.util.Base64.getEncoder().encodeToString(baos.toByteArray())
                            call.respond(mapOf(
                                "success" to true,
                                "width" to bounds.width,
                                "height" to bounds.height,
                                "format" to format,
                                "data" to encoded
                            ))
                        } else {
                            // Return raw PNG bytes
                            val baos = ByteArrayOutputStream()
                            ImageIO.write(image, format, baos)
                            call.respondBytes(
                                bytes = baos.toByteArray(),
                                contentType = ContentType.Image.PNG,
                                status = HttpStatusCode.OK
                            )
                        }
                    } catch (e: Exception) {
                        call.respond(
                            HttpStatusCode.InternalServerError,
                            mapOf("error" to "Screenshot failed: ${e.message}")
                        )
                    }
                }

                // Save screenshot to file path (test mode only)
                post("/screenshot") {
                    if (!isTestModeEnabled()) {
                        call.respond(HttpStatusCode.Forbidden, mapOf("error" to "Screenshots require CIRIS_TEST_MODE=true"))
                        return@post
                    }
                    val window = awtWindow
                    if (window == null) {
                        call.respond(HttpStatusCode.ServiceUnavailable, mapOf("error" to "Window not available"))
                        return@post
                    }

                    try {
                        val request = call.receive<ScreenshotRequest>()
                        val bounds = window.bounds
                        val screenRect = Rectangle(bounds.x, bounds.y, bounds.width, bounds.height)
                        val image = robot.createScreenCapture(screenRect)

                        val file = java.io.File(request.path)
                        file.parentFile?.mkdirs()
                        ImageIO.write(image, request.format ?: "png", file)

                        call.respond(ActionResponse(
                            success = true,
                            action = "screenshot",
                            text = request.path
                        ))
                    } catch (e: Exception) {
                        call.respond(ActionResponse(
                            success = false,
                            action = "screenshot",
                            error = "Screenshot failed: ${e.message}"
                        ))
                    }
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
data class InjectFileRequest(
    val filename: String,
    val mediaType: String,
    val dataBase64: String,
    val sizeBytes: Long
)

@Serializable
data class ScreenshotRequest(
    val path: String,
    val format: String? = "png"
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
