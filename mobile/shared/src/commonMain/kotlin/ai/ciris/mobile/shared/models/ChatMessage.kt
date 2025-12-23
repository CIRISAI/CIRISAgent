package ai.ciris.mobile.shared.models

import kotlinx.datetime.Instant
import kotlinx.serialization.Serializable

@Serializable
data class ChatMessage(
    val id: String,
    val text: String,
    val type: MessageType,
    val timestamp: Instant,
    val reasoning: String? = null
)

@Serializable
enum class MessageType {
    USER,
    AGENT,
    SYSTEM
}

@Serializable
data class InteractRequest(
    val message: String,
    val channel_id: String = "mobile_app"
)

@Serializable
data class InteractResponse(
    val response: String,
    val reasoning: String? = null,
    val message_id: String
)
