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

        // Try the programmatic click handler FIRST, before requiring an
        // element-position entry. `testableClickable` registers the handler the
        // moment its modifier composes — popup / dialog content composes its
        // modifiers and registers handlers even though their layout positions
        // never reach the main-window `onGloballyPositioned` callback. Gating
        // on a position entry would 404 the click for handlers that are live
        // and dispatchable.
        val clicked = TestAutomationState.triggerClick(request.testTag)
        if (clicked) {
            return ActionResponse(
                success = true,
                element = request.testTag,
                action = "click",
                coordinates = element?.let { "${it.centerX},${it.centerY}" }
            )
        }

        if (element == null) {
            return ActionResponse(success = false, error = "Element not found: ${request.testTag}")
        }
        // Element is positioned but has no programmatic handler (e.g. a plain
        // `testable()` text). Caller can fall back to a coordinate-based click.
        return ActionResponse(
            success = false,
            error = "No click handler for: ${request.testTag}",
            element = request.testTag,
            coordinates = "${element.centerX},${element.centerY}"
        )
    }

    fun handleInput(request: InputRequest): ActionResponse {
        val element = TestAutomationState.getElement(request.testTag)
            ?: return ActionResponse(success = false, error = "Element not found: ${request.testTag}")

        // Use platform TestAutomation (not TestAutomationState) - dialogs observe the platform flow
        ai.ciris.mobile.shared.platform.TestAutomation.requestTextInput(request.testTag, request.text, request.clearFirst)

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
            // Element-position OR click-handler is a positive signal. Dialog /
            // sheet buttons register click handlers when their modifiers
            // compose (before the popup window's layout pass reaches them), so
            // `wait_for_element("btn_mode_confirm")` resolves the moment the
            // confirm-button's modifier composes inside the dialog content —
            // it does NOT have to wait for a position entry that may never
            // arrive through the popup's separate layout tree.
            if (TestAutomationState.getElement(request.testTag) != null
                || TestAutomationState.hasClickHandler(request.testTag)) {
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

    fun handleScroll(request: ScrollRequest): ActionResponse {
        TestAutomationState.requestScroll(request.testTag, request.direction, request.amount)
        return ActionResponse(
            success = true,
            element = request.testTag,
            action = "scroll",
            text = "${request.direction}:${request.amount}"
        )
    }

    /**
     * Combined action + view handler.
     * Performs action, waits, returns updated UI state.
     * Reduces 3 API calls (action + sleep + tree) to 1.
     */
    suspend fun handleActAndView(request: ActAndViewRequest): ActAndViewResponse {
        // 1. Perform the action
        val actionResult = when (request.action.lowercase()) {
            "click" -> handleClick(ClickRequest(request.testTag))
            "input" -> handleInput(InputRequest(request.testTag, request.text ?: "", request.clearFirst))
            "wait" -> handleWait(WaitRequest(request.testTag, request.waitMs))
            else -> ActionResponse(success = false, error = "Unknown action: ${request.action}")
        }

        // 2. Wait for UI to settle
        if (request.waitMs > 0 && request.action.lowercase() != "wait") {
            delay(request.waitMs.toLong())
        }

        // 3. Get current screen
        val screen = TestAutomationState.currentScreen

        // 4. Get elements (optionally filtered)
        val allElements = TestAutomationState.getAllElements().values.toList()
        val filteredElements = if (request.filterTags.isNullOrEmpty()) {
            allElements
        } else {
            allElements.filter { element ->
                request.filterTags.any { pattern ->
                    element.testTag.contains(pattern, ignoreCase = true)
                }
            }
        }

        return ActAndViewResponse(
            actionResult = actionResult,
            screen = screen,
            elements = filteredElements,
            elementCount = filteredElements.size
        )
    }

    // Platform-independent time
    private fun currentTimeMs(): Long {
        return kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
    }
}
