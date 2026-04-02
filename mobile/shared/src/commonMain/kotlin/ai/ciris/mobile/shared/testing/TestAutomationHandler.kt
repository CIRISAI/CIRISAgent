package ai.ciris.mobile.shared.testing

import kotlinx.coroutines.delay
import kotlinx.serialization.json.Json

/**
 * Pure handler logic for test automation endpoints.
 * Platform-independent — operates on TestAutomation shared state.
 * Used by Ktor server (JVM) and POSIX server (iOS).
 */
object TestAutomationHandler {

    private val json = Json {
        prettyPrint = true
        isLenient = true
        ignoreUnknownKeys = true
    }

    fun getJson(): Json = json

    fun handleHealth(): HealthResponse {
        return HealthResponse(status = "ok", testMode = true)
    }

    fun handleTree(): TreeResponse {
        val screen = TestAutomationState.currentScreen
        val elements = TestAutomationState.getAllElements().values.toList()
        return TreeResponse(screen = screen, elements = elements, count = elements.size)
    }

    fun handleScreen(): ScreenResponse {
        return ScreenResponse(screen = TestAutomationState.currentScreen)
    }

    fun handleClick(request: ClickRequest): ActionResponse {
        val element = TestAutomationState.getElement(request.testTag)
            ?: return ActionResponse(success = false, error = "Element not found: ${request.testTag}")

        val clicked = TestAutomationState.triggerClick(request.testTag)
        return if (clicked) {
            ActionResponse(
                success = true,
                element = request.testTag,
                action = "click",
                coordinates = "${element.centerX},${element.centerY}"
            )
        } else {
            // No programmatic click handler — return info for mouse click fallback
            ActionResponse(
                success = false,
                error = "No click handler for: ${request.testTag}",
                element = request.testTag,
                coordinates = "${element.centerX},${element.centerY}"
            )
        }
    }

    fun handleInput(request: InputRequest): ActionResponse {
        val element = TestAutomationState.getElement(request.testTag)
            ?: return ActionResponse(success = false, error = "Element not found: ${request.testTag}")

        TestAutomationState.requestTextInput(request.testTag, request.text, request.clearFirst)

        return ActionResponse(
            success = true,
            element = request.testTag,
            action = "input",
            text = request.text
        )
    }

    suspend fun handleWait(request: WaitRequest): ActionResponse {
        val timeoutMs = request.timeoutMs ?: 5000
        val startTime = currentTimeMs()

        while (currentTimeMs() - startTime < timeoutMs) {
            if (TestAutomationState.getElement(request.testTag) != null) {
                return ActionResponse(success = true, element = request.testTag, action = "wait")
            }
            delay(100)
        }

        return ActionResponse(
            success = false,
            error = "Element not found within ${timeoutMs}ms: ${request.testTag}"
        )
    }

    fun handleGetElement(testTag: String): ElementInfo? {
        return TestAutomationState.getElement(testTag)
    }

    // Platform-independent time
    private fun currentTimeMs(): Long {
        return kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
    }
}
