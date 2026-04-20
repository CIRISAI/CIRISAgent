package ai.ciris.mobile.shared.platform

import androidx.compose.foundation.clickable
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.roundToInt

/**
 * Desktop implementation of test automation.
 * Delegates to TestAutomationServer when test mode is enabled.
 */
actual object TestAutomation {
    // Callback to the TestAutomationServer (set by desktop Main.kt)
    private var registerCallback: ((String, Int, Int, Int, Int, String?) -> Unit)? = null
    private var unregisterCallback: ((String) -> Unit)? = null
    private var setScreenCallback: ((String) -> Unit)? = null
    private var clearCallback: (() -> Unit)? = null
    private var enabledCheck: (() -> Boolean)? = null

    // Click handlers registered by testableClickable
    private val clickHandlers = ConcurrentHashMap<String, () -> Unit>()

    // Text input requests flow
    private val _textInputRequests = MutableStateFlow<TextInputRequest?>(null)
    actual val textInputRequests: StateFlow<TextInputRequest?> = _textInputRequests.asStateFlow()

    // File injection requests flow
    private val _fileInjectionRequests = MutableStateFlow<PickedFile?>(null)
    actual val fileInjectionRequests: StateFlow<PickedFile?> = _fileInjectionRequests.asStateFlow()

    /**
     * Configure callbacks from TestAutomationServer.
     * Called by desktop Main.kt when test mode is enabled.
     */
    fun configure(
        onRegister: (String, Int, Int, Int, Int, String?) -> Unit,
        onUnregister: (String) -> Unit,
        onSetScreen: (String) -> Unit,
        onClear: () -> Unit,
        isEnabled: () -> Boolean
    ) {
        registerCallback = onRegister
        unregisterCallback = onUnregister
        setScreenCallback = onSetScreen
        clearCallback = onClear
        enabledCheck = isEnabled
    }

    actual fun isEnabled(): Boolean {
        return enabledCheck?.invoke() ?: false
    }

    actual fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String?) {
        registerCallback?.invoke(testTag, x, y, width, height, text)
    }

    actual fun unregisterElement(testTag: String) {
        unregisterCallback?.invoke(testTag)
    }

    actual fun setCurrentScreen(screen: String) {
        setScreenCallback?.invoke(screen)
    }

    actual fun clearElements() {
        clearCallback?.invoke()
    }

    actual fun registerClickHandler(testTag: String, handler: () -> Unit) {
        clickHandlers[testTag] = handler
    }

    actual fun unregisterClickHandler(testTag: String) {
        clickHandlers.remove(testTag)
    }

    actual fun triggerClick(testTag: String): Boolean {
        val handler = clickHandlers[testTag]
        return if (handler != null) {
            handler()
            true
        } else {
            false
        }
    }

    actual fun requestTextInput(testTag: String, text: String, clearFirst: Boolean) {
        _textInputRequests.value = TextInputRequest(testTag, text, clearFirst)
    }

    actual fun clearTextInputRequest() {
        _textInputRequests.value = null
    }

    actual fun injectFile(name: String, mediaType: String, dataBase64: String, sizeBytes: Long) {
        _fileInjectionRequests.value = PickedFile(
            name = name,
            mediaType = mediaType,
            dataBase64 = dataBase64,
            sizeBytes = sizeBytes
        )
    }

    actual fun clearFileInjectionRequest() {
        _fileInjectionRequests.value = null
    }
}

/**
 * Desktop implementation of testable modifier.
 * When test mode is enabled, tracks element position for automation.
 */
actual fun Modifier.testable(tag: String, text: String?): Modifier = composed {
    if (TestAutomation.isEnabled()) {
        this
            .testTag(tag)
            .onGloballyPositioned { coordinates ->
                val position = coordinates.positionInWindow()
                val size = coordinates.size

                TestAutomation.registerElement(
                    testTag = tag,
                    x = position.x.roundToInt(),
                    y = position.y.roundToInt(),
                    width = size.width,
                    height = size.height,
                    text = text
                )
            }
    } else {
        this.testTag(tag)
    }
}

/**
 * Desktop implementation of testableClickable modifier.
 * Registers click handler for programmatic triggering by test server.
 */
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier = composed {
    // Register click handler when test mode enabled
    if (TestAutomation.isEnabled()) {
        TestAutomation.registerClickHandler(tag, onClick)
    }

    if (TestAutomation.isEnabled()) {
        this
            .testTag(tag)
            .clickable { onClick() }
            .onGloballyPositioned { coordinates ->
                val position = coordinates.positionInWindow()
                val size = coordinates.size

                TestAutomation.registerElement(
                    testTag = tag,
                    x = position.x.roundToInt(),
                    y = position.y.roundToInt(),
                    width = size.width,
                    height = size.height,
                    text = text
                )
            }
    } else {
        this
            .testTag(tag)
            .clickable { onClick() }
    }
}

/**
 * Desktop implementation of testableWithHandler modifier.
 * Registers click handler WITHOUT adding clickable - for components that handle clicks internally.
 */
actual fun Modifier.testableWithHandler(tag: String, onClick: () -> Unit): Modifier = composed {
    // Register click handler when test mode enabled
    if (TestAutomation.isEnabled()) {
        TestAutomation.registerClickHandler(tag, onClick)
    }

    if (TestAutomation.isEnabled()) {
        this
            .testTag(tag)
            .onGloballyPositioned { coordinates ->
                val position = coordinates.positionInWindow()
                val size = coordinates.size

                TestAutomation.registerElement(
                    testTag = tag,
                    x = position.x.roundToInt(),
                    y = position.y.roundToInt(),
                    width = size.width,
                    height = size.height,
                    text = null
                )
            }
    } else {
        this.testTag(tag)
    }
}
