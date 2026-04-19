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
        "idma_result" to "〰️",       // Intuition DMA - seismograph trace sensing fragility in reasoning (k_eff/CCA)
        "aspdma_result" to "🎯",
        "tsaspdma_result" to "🔧",   // Tool-Specific ASPDMA - wrench for tool parameter refinement
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

    /**
     * Extract a compact one-line summary of an SSE event for the bubble payload.
     *
     * Returns null when nothing useful can be said about the event — in that case
     * the floating bubble falls back to just its emoji.
     *
     * The returned string is hard-capped at [ReasoningEvent.PAYLOAD_MAX_CHARS] so
     * the client never holds a runaway string from a noisy SSE burst.
     */
    private fun extractPayload(eventType: String, event: JsonObject): String? {
        fun s(key: String): String? = event[key]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }

        val raw: String? = when (eventType) {
            "thought_start" -> s("thought_content") ?: s("content")
            "snapshot_and_context" -> s("context_summary") ?: s("task_description")
            "dma_results" -> s("csdma_conclusion") ?: s("pdma_conclusion")
            "idma_result" -> s("tension") ?: s("conclusion")
            "aspdma_result" -> s("selected_action")?.let { "→ $it" }
            "tsaspdma_result" -> s("refined_tool") ?: s("selected_tool")?.let { "tool: $it" }
            "conscience_result" -> s("reason") ?: s("status")?.let { "conscience: $it" }
            "action_result" -> {
                val action = s("action_executed") ?: "?"
                val detail = s("content") ?: s("message") ?: s("tool_name") ?: s("result_summary")
                if (detail != null) "$action · $detail" else action
            }
            else -> null
        }

        return raw?.trim()?.take(ReasoningEvent.PAYLOAD_MAX_CHARS)
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

                // Extract a compact human-readable payload summary.
                // Intentionally small — bounded at PAYLOAD_MAX_CHARS — so the
                // bubble can carry it in-flight without us retaining the full
                // SSE event in memory.
                val payload = extractPayload(eventType, event)

                result.add(ReasoningEvent.Emoji(emoji, eventType, isComplete, payload))
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
        val isComplete: Boolean = false,
        // Compact, pre-truncated human-readable summary of the event.
        // Carried only for the bubble's lifetime; caller decides whether to retain.
        // Hard-capped at PAYLOAD_MAX_CHARS at parse time so worst-case memory
        // is MAX_BUBBLES × PAYLOAD_MAX_CHARS — fits 32-bit ARM budget.
        val payload: String? = null
    ) : ReasoningEvent()

    companion object {
        const val PAYLOAD_MAX_CHARS = 160
    }

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
