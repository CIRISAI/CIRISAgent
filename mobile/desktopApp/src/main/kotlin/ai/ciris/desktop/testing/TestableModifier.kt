package ai.ciris.desktop.testing

import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.testTag
import kotlin.math.roundToInt

/**
 * Modifier that registers an element for test automation.
 *
 * This combines testTag() with position tracking to enable
 * the TestAutomationServer to find and interact with elements.
 *
 * Usage:
 * ```
 * Button(
 *     onClick = { ... },
 *     modifier = Modifier.testable("login_button")
 * )
 * ```
 */
fun Modifier.testable(
    tag: String,
    text: String? = null
): Modifier = composed {
    val server = remember { TestAutomationServer.getInstance() }
    var registered by remember { mutableStateOf(false) }

    DisposableEffect(tag) {
        onDispose {
            if (registered) {
                server.unregisterElement(tag)
            }
        }
    }

    this
        .testTag(tag)
        .onGloballyPositioned { coordinates ->
            val position = coordinates.positionInWindow()
            val size = coordinates.size

            // Convert to screen coordinates (window position + element position)
            // Note: This assumes the window is at (0,0) - for proper positioning,
            // we'd need to track window position as well
            server.registerElement(
                testTag = tag,
                x = position.x.roundToInt(),
                y = position.y.roundToInt(),
                width = size.width,
                height = size.height,
                text = text
            )
            registered = true
        }
}

/**
 * Simplified testable modifier for when text content isn't needed.
 */
fun Modifier.testable(tag: String): Modifier = testable(tag, null)

/**
 * Extension to make existing testTag modifiers also trackable.
 * Use when you want to keep using testTag but also enable automation.
 */
fun Modifier.trackable(
    tag: String,
    text: String? = null
): Modifier = composed {
    val server = remember { TestAutomationServer.getInstance() }
    var registered by remember { mutableStateOf(false) }

    DisposableEffect(tag) {
        onDispose {
            if (registered) {
                server.unregisterElement(tag)
            }
        }
    }

    this.onGloballyPositioned { coordinates ->
        val position = coordinates.positionInWindow()
        val size = coordinates.size

        server.registerElement(
            testTag = tag,
            x = position.x.roundToInt(),
            y = position.y.roundToInt(),
            width = size.width,
            height = size.height,
            text = text
        )
        registered = true
    }
}
