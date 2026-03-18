package ai.ciris.mobile.shared.api
import ai.ciris.mobile.shared.platform.PlatformLogger

import io.ktor.client.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.utils.io.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.*

/**
 * SSE client for reasoning stream events.
 * Connects to /v1/system/runtime/reasoning-stream and emits emoji events.
 */
class ReasoningStreamClient(
    private val baseUrl: String,
    private val getToken: suspend () -> String?
) {
    private val json = Json { ignoreUnknownKeys = true }

    // Event type to emoji mapping
    private val eventEmojis = mapOf(
        "thought_start" to "🤔",
        "snapshot_and_context" to "📋",
        "dma_results" to "⚖️",
        "aspdma_result" to "🎯",
        "conscience_result" to "🧭",
        "action_result" to "⚡"
    )

    // All 10 action verbs with their emojis
    // External: observe, speak, tool
    // Control: reject, ponder, defer
    // Memory: memorize, recall, forget
    // Terminal: task_complete
    private fun getActionEmoji(action: String?): String {
        return when {
            action == null -> "⚡"
            // External actions
            action.contains("observe") -> "👀"
            action.contains("speak") -> "💬"
            action.contains("tool") -> "🔧"
            // Control responses
            action.contains("reject") -> "❌"
            action.contains("ponder") -> "💭"
            action.contains("defer") -> "⏸️"
            // Memory operations
            action.contains("memorize") -> "💾"
            action.contains("recall") -> "🔍"
            action.contains("forget") -> "🗑️"
            // Terminal
            action.contains("task_complete") -> "✅"
            else -> "⚡"
        }
    }

    /**
     * Connect to SSE stream and emit emoji events
     */
    fun connect(): Flow<ReasoningEvent> = flow {
        val token = getToken() ?: return@flow

        val client = HttpClient {
            install(HttpTimeout) {
                requestTimeoutMillis = Long.MAX_VALUE
                socketTimeoutMillis = Long.MAX_VALUE
            }
        }

        try {
            client.prepareGet("$baseUrl/v1/system/runtime/reasoning-stream") {
                header(HttpHeaders.Accept, "text/event-stream")
                header(HttpHeaders.Authorization, "Bearer $token")
            }.execute { response ->
                if (!response.status.isSuccess()) {
                    PlatformLogger.d("SSE"," HTTP error: ${response.status}")
                    emit(ReasoningEvent.Disconnected)
                    return@execute
                }

                emit(ReasoningEvent.Connected)

                val channel: ByteReadChannel = response.bodyAsChannel()

                while (!channel.isClosedForRead) {
                    val line = channel.readUTF8Line() ?: continue

                    if (line.startsWith("data:")) {
                        val jsonStr = line.substring(5).trim()
                        try {
                            val events = parseEvents(jsonStr)
                            events.forEach { emit(it) }
                        } catch (e: Exception) {
                            PlatformLogger.d("SSE"," Parse error: ${e.message}")
                        }
                    }
                }
            }
        } catch (e: Exception) {
            PlatformLogger.d("SSE"," Connection error: ${e.message}")
            emit(ReasoningEvent.Disconnected)
        } finally {
            client.close()
        }
    }

    private fun parseEvents(jsonStr: String): List<ReasoningEvent> {
        val result = mutableListOf<ReasoningEvent>()

        try {
            val jsonObject = json.parseToJsonElement(jsonStr).jsonObject

            // Skip keepalive/status messages
            if (jsonObject["status"]?.jsonPrimitive?.content == "connected") {
                return result
            }
            if (jsonObject.size == 1 && jsonObject.containsKey("timestamp")) {
                return result
            }

            // Process events array
            val events = jsonObject["events"]?.jsonArray ?: return result

            for (eventElem in events) {
                val event = eventElem.jsonObject
                val eventType = event["event_type"]?.jsonPrimitive?.content ?: continue

                val emoji = when (eventType) {
                    "action_result" -> {
                        val action = event["action_executed"]?.jsonPrimitive?.content
                        getActionEmoji(action)
                    }
                    "aspdma_result" -> {
                        val action = event["selected_action"]?.jsonPrimitive?.content
                        if (action != null) "🎯" else eventEmojis[eventType] ?: "⏳"
                    }
                    else -> eventEmojis[eventType] ?: "⏳"
                }

                // Check if this is a completion event (task_complete or reject)
                val isComplete = eventType == "action_result" &&
                    (event["action_executed"]?.jsonPrimitive?.content?.let {
                        it.contains("task_complete") || it.contains("reject")
                    } == true)

                // Emit pipeline step for scaffolding visualization
                result.add(ReasoningEvent.PipelineStep(
                    eventType = eventType,
                    isNewThought = eventType == "thought_start"
                ))

                result.add(ReasoningEvent.Emoji(emoji, eventType, isComplete))
            }
        } catch (e: Exception) {
            PlatformLogger.d("SSE"," JSON parse error: ${e.message}")
        }

        return result
    }
}

/**
 * Events emitted by the reasoning stream
 */
sealed class ReasoningEvent {
    data object Connected : ReasoningEvent()
    data object Disconnected : ReasoningEvent()
    data class Emoji(
        val emoji: String,
        val eventType: String,
        val isComplete: Boolean = false
    ) : ReasoningEvent()

    /**
     * Raw pipeline step event for scaffolding visualization.
     * Emitted for every SSE event type so the UI can light up
     * the corresponding H3ERE pipeline ring.
     */
    data class PipelineStep(
        val eventType: String,
        val isNewThought: Boolean = false  // true for thought_start (resets pipeline)
    ) : ReasoningEvent()
}
