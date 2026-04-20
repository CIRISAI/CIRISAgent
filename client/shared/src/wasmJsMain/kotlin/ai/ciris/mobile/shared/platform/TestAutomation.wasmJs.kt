package ai.ciris.mobile.shared.platform

import androidx.compose.foundation.clickable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * WASM implementation of TestAutomation.
 * Test automation is not fully supported in browser environment.
 */
actual object TestAutomation {
    actual fun isEnabled(): Boolean = false

    actual fun registerElement(testTag: String, x: Int, y: Int, width: Int, height: Int, text: String?) {
        // No-op in browser
    }

    actual fun unregisterElement(testTag: String) {
        // No-op in browser
    }

    actual fun setCurrentScreen(screen: String) {
        // No-op in browser
    }

    actual fun clearElements() {
        // No-op in browser
    }

    actual fun registerClickHandler(testTag: String, handler: () -> Unit) {
        // No-op in browser
    }

    actual fun unregisterClickHandler(testTag: String) {
        // No-op in browser
    }

    actual fun triggerClick(testTag: String): Boolean {
        return false
    }

    private val _textInputRequests = MutableStateFlow<TextInputRequest?>(null)
    actual val textInputRequests: StateFlow<TextInputRequest?> = _textInputRequests.asStateFlow()

    actual fun requestTextInput(testTag: String, text: String, clearFirst: Boolean) {
        // No-op in browser
    }

    actual fun clearTextInputRequest() {
        _textInputRequests.value = null
    }

    private val _fileInjectionRequests = MutableStateFlow<PickedFile?>(null)
    actual val fileInjectionRequests: StateFlow<PickedFile?> = _fileInjectionRequests.asStateFlow()

    actual fun injectFile(name: String, mediaType: String, dataBase64: String, sizeBytes: Long) {
        // No-op in browser
    }

    actual fun clearFileInjectionRequest() {
        _fileInjectionRequests.value = null
    }
}

/**
 * WASM implementation - just applies testTag, no position tracking.
 */
actual fun Modifier.testable(tag: String, text: String?): Modifier = this.testTag(tag)

/**
 * WASM implementation - applies testTag and clickable.
 */
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier =
    this.testTag(tag).clickable(onClick = onClick)

/**
 * WASM implementation - just applies testTag, no handler registration.
 */
actual fun Modifier.testableWithHandler(tag: String, onClick: () -> Unit): Modifier = this.testTag(tag)
