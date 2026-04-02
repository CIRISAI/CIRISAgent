package ai.ciris.mobile.shared.platform

import ai.ciris.mobile.shared.testing.AndroidTestAutomationServer
import ai.ciris.mobile.shared.testing.TestAutomationState
import androidx.compose.foundation.clickable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.StateFlow

/**
 * Android implementation of test automation.
 * Delegates to shared TestAutomationState when test mode is enabled.
 * When CIRIS_TEST_MODE=true, tracks element positions for the Ktor HTTP server.
 */
actual object TestAutomation {
    actual val textInputRequests: StateFlow<TextInputRequest?> = TestAutomationState.textInputRequests
    actual val fileInjectionRequests: StateFlow<PickedFile?> = TestAutomationState.fileInjectionRequests

    actual fun isEnabled(): Boolean {
        if (TestAutomationState.isEnabled) return true
        val enabled = AndroidTestAutomationServer.isTestModeEnabled()
        if (enabled) TestAutomationState.isEnabled = true
        return enabled
    }

    actual fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String?) {
        if (!isEnabled()) return
        TestAutomationState.registerElement(testTag, x, y, width, height, text)
    }

    actual fun unregisterElement(testTag: String) {
        TestAutomationState.unregisterElement(testTag)
    }

    actual fun setCurrentScreen(screen: String) {
        TestAutomationState.currentScreen = screen
    }

    actual fun clearElements() {
        TestAutomationState.clearElements()
    }

    actual fun registerClickHandler(testTag: String, handler: () -> Unit) {
        if (!isEnabled()) return
        TestAutomationState.registerClickHandler(testTag, handler)
    }

    actual fun unregisterClickHandler(testTag: String) {
        TestAutomationState.unregisterClickHandler(testTag)
    }

    actual fun triggerClick(testTag: String): Boolean {
        return TestAutomationState.triggerClick(testTag)
    }

    actual fun requestTextInput(testTag: String, text: String, clearFirst: Boolean) {
        TestAutomationState.requestTextInput(testTag, text, clearFirst)
    }

    actual fun clearTextInputRequest() {
        TestAutomationState.clearTextInputRequest()
    }

    actual fun injectFile(name: String, mediaType: String, dataBase64: String, sizeBytes: Long) {
        TestAutomationState.injectFile(name, mediaType, dataBase64, sizeBytes)
    }

    actual fun clearFileInjectionRequest() {
        TestAutomationState.clearFileInjectionRequest()
    }
}

/**
 * Android implementation — tracks position when test mode enabled, otherwise just testTag.
 */
actual fun Modifier.testable(tag: String, text: String?): Modifier {
    return if (TestAutomation.isEnabled()) {
        this.testTag(tag).onGloballyPositioned { coords ->
            val bounds = coords.boundsInWindow()
            TestAutomation.registerElement(
                tag,
                bounds.left.toInt(), bounds.top.toInt(),
                bounds.width.toInt(), bounds.height.toInt(),
                text
            )
        }
    } else {
        this.testTag(tag)
    }
}

/**
 * Android implementation — tracks position + registers click handler when test mode enabled.
 */
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier {
    return if (TestAutomation.isEnabled()) {
        TestAutomation.registerClickHandler(tag, onClick)
        this.testTag(tag)
            .clickable { onClick() }
            .onGloballyPositioned { coords ->
                val bounds = coords.boundsInWindow()
                TestAutomation.registerElement(
                    tag,
                    bounds.left.toInt(), bounds.top.toInt(),
                    bounds.width.toInt(), bounds.height.toInt(),
                    text
                )
            }
    } else {
        this.testTag(tag).clickable { onClick() }
    }
}

/**
 * Android implementation — registers click handler without adding clickable.
 */
actual fun Modifier.testableWithHandler(tag: String, onClick: () -> Unit): Modifier {
    if (TestAutomation.isEnabled()) {
        TestAutomation.registerClickHandler(tag, onClick)
    }
    return this.testTag(tag)
}
