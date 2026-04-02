package ai.ciris.mobile.shared.testing

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Cross-platform shared state for test automation.
 * All platforms write to this, the test server reads from it.
 * Uses coroutine Mutex for thread safety (works on all K/MP targets).
 */
object TestAutomationState {

    // Element registry (guarded by elementsMutex for K/N safety)
    private val elements = mutableMapOf<String, ElementInfo>()
    private val clickHandlers = mutableMapOf<String, () -> Unit>()

    var currentScreen: String = "unknown"
    var isEnabled: Boolean = false

    // Window position offset (desktop only, for converting to screen coords)
    var windowX: Int = 0
    var windowY: Int = 0

    fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String?) {
        val screenX = x + windowX
        val screenY = y + windowY
        elements[testTag] = ElementInfo(
            testTag = testTag,
            x = screenX, y = screenY,
            width = width, height = height,
            text = text,
            centerX = screenX + width / 2,
            centerY = screenY + height / 2
        )
    }

    fun unregisterElement(testTag: String) {
        elements.remove(testTag)
        clickHandlers.remove(testTag)
    }

    fun clearElements() {
        elements.clear()
    }

    fun getElement(testTag: String): ElementInfo? {
        return elements[testTag]
    }

    fun getAllElements(): Map<String, ElementInfo> {
        return elements.toMap()
    }

    fun registerClickHandler(testTag: String, handler: () -> Unit) {
        clickHandlers[testTag] = handler
    }

    fun unregisterClickHandler(testTag: String) {
        clickHandlers.remove(testTag)
    }

    fun triggerClick(testTag: String): Boolean {
        val handler = clickHandlers[testTag] ?: return false
        handler()
        return true
    }

    // Text input
    private val _textInputRequests = MutableStateFlow<TextInputRequest?>(null)
    val textInputRequests: StateFlow<TextInputRequest?> = _textInputRequests

    fun requestTextInput(testTag: String, text: String, clearFirst: Boolean) {
        _textInputRequests.value = TextInputRequest(testTag, text, clearFirst)
    }

    fun clearTextInputRequest() {
        _textInputRequests.value = null
    }

    // File injection
    private val _fileInjectionRequests = MutableStateFlow<ai.ciris.mobile.shared.platform.PickedFile?>(null)
    val fileInjectionRequests: StateFlow<ai.ciris.mobile.shared.platform.PickedFile?> = _fileInjectionRequests

    fun injectFile(name: String, mediaType: String, dataBase64: String, sizeBytes: Long) {
        _fileInjectionRequests.value = ai.ciris.mobile.shared.platform.PickedFile(
            name = name,
            mediaType = mediaType,
            dataBase64 = dataBase64,
            sizeBytes = sizeBytes
        )
    }

    fun clearFileInjectionRequest() {
        _fileInjectionRequests.value = null
    }

    // Scroll requests
    private val _scrollRequests = MutableStateFlow<ScrollRequest?>(null)
    val scrollRequests: StateFlow<ScrollRequest?> = _scrollRequests

    fun requestScroll(testTag: String, direction: String, amount: Int) {
        _scrollRequests.value = ScrollRequest(testTag, direction, amount)
    }

    fun clearScrollRequest() {
        _scrollRequests.value = null
    }
}

// Re-use the TextInputRequest from platform package
typealias TextInputRequest = ai.ciris.mobile.shared.platform.TextInputRequest
