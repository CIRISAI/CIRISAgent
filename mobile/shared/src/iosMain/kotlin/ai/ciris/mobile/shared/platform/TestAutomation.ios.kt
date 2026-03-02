package ai.ciris.mobile.shared.platform

import androidx.compose.foundation.clickable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * iOS implementation of test automation.
 * No-op on mobile platforms - test automation is desktop-only.
 */
actual object TestAutomation {
    private val _textInputRequests = MutableStateFlow<TextInputRequest?>(null)
    actual val textInputRequests: StateFlow<TextInputRequest?> = _textInputRequests

    actual fun isEnabled(): Boolean = false

    actual fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String?) {
        // No-op on iOS
    }

    actual fun unregisterElement(testTag: String) {
        // No-op on iOS
    }

    actual fun setCurrentScreen(screen: String) {
        // No-op on iOS
    }

    actual fun clearElements() {
        // No-op on iOS
    }

    actual fun registerClickHandler(testTag: String, handler: () -> Unit) {
        // No-op on iOS
    }

    actual fun unregisterClickHandler(testTag: String) {
        // No-op on iOS
    }

    actual fun triggerClick(testTag: String): Boolean {
        // No-op on iOS
        return false
    }

    actual fun requestTextInput(testTag: String, text: String, clearFirst: Boolean) {
        // No-op on iOS
    }

    actual fun clearTextInputRequest() {
        // No-op on iOS
    }
}

/**
 * iOS implementation - just applies testTag without position tracking.
 */
actual fun Modifier.testable(tag: String, text: String?): Modifier = this.testTag(tag)

/**
 * iOS implementation - applies testTag and clickable without test handler registration.
 */
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier =
    this.testTag(tag).clickable { onClick() }
