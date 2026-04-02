package ai.ciris.mobile.shared.testing

import kotlinx.serialization.Serializable

/**
 * Shared data models for the test automation HTTP server.
 * Used by all platforms (Desktop, iOS, Android).
 */

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
data class HealthResponse(val status: String, val testMode: Boolean)

@Serializable
data class TreeResponse(val screen: String, val elements: List<ElementInfo>, val count: Int)

@Serializable
data class ScreenResponse(val screen: String)

@Serializable
data class ClickRequest(val testTag: String)

@Serializable
data class InputRequest(val testTag: String, val text: String, val clearFirst: Boolean = true)

@Serializable
data class NavigateRequest(val screen: String)

@Serializable
data class WaitRequest(val testTag: String, val timeoutMs: Int? = 5000)

@Serializable
data class ScreenshotRequest(val path: String, val format: String? = "png")

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
