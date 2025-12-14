package ai.ciris.mobile.llm

import android.util.Log
import ai.ciris.mobile.config.CIRISConfig
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Client for CIRIS LLM Proxy.
 *
 * Authentication: Bearer google:{google_user_id}
 * Billing: 1 credit per interaction_id (supports multiple LLM calls)
 */
class CIRISProxyClient(private val googleUserId: String) {

    companion object {
        private const val TAG = "CIRISProxyClient"
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()

        // Get base URL from centralized config
        private fun getBaseUrl(): String = CIRISConfig.getLLMProxyUrl().removeSuffix("/v1")

        /**
         * Generate a unique interaction ID for billing.
         * All LLM calls with the same interaction_id are billed as ONE credit.
         */
        fun generateInteractionId(): String = UUID.randomUUID().toString()
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    data class Message(val role: String, val content: String)

    data class ChatResponse(
        val id: String,
        val model: String,
        val content: String,
        val finishReason: String?,
        val promptTokens: Int,
        val completionTokens: Int,
        val totalTokens: Int
    )

    class CIRISProxyException(
        val statusCode: Int,
        val errorType: String?,
        val errorMessage: String?
    ) : Exception("HTTP $statusCode: $errorMessage")

    /**
     * Send a chat completion request to the LLM proxy.
     *
     * @param messages List of messages in the conversation
     * @param interactionId Unique ID for billing - reuse for multiple calls in same interaction
     * @param model Model to use (default, fast, groq/llama-3.3-70b, etc.)
     * @param stream Whether to stream the response (not yet supported)
     * @return ChatResponse with the assistant's reply
     */
    fun chat(
        messages: List<Message>,
        interactionId: String,
        model: String = "default",
        stream: Boolean = false
    ): ChatResponse {
        val messagesArray = JSONArray().apply {
            messages.forEach { msg ->
                put(JSONObject().apply {
                    put("role", msg.role)
                    put("content", msg.content)
                })
            }
        }

        val requestBody = JSONObject().apply {
            put("model", model)
            put("messages", messagesArray)
            put("stream", stream)
            put("metadata", JSONObject().apply {
                put("interaction_id", interactionId)
            })
        }.toString().toRequestBody(JSON_MEDIA_TYPE)

        val request = Request.Builder()
            .url("${getBaseUrl()}/v1/chat/completions")
            .addHeader("Authorization", "Bearer google:$googleUserId")
            .addHeader("Content-Type", "application/json")
            .post(requestBody)
            .build()

        Log.d(TAG, "Sending chat request with interaction_id: $interactionId")

        client.newCall(request).execute().use { response ->
            val responseBody = response.body?.string()

            if (!response.isSuccessful) {
                val errorJson = responseBody?.let {
                    try {
                        JSONObject(it)
                    } catch (e: Exception) {
                        null
                    }
                }

                val errorObj = errorJson?.optJSONObject("error")
                throw CIRISProxyException(
                    statusCode = response.code,
                    errorType = errorObj?.optString("type"),
                    errorMessage = errorObj?.optString("message") ?: responseBody
                )
            }

            return parseResponse(responseBody ?: throw IOException("Empty response body"))
        }
    }

    /**
     * Check if the proxy is healthy (no auth required).
     */
    fun healthCheck(): Boolean {
        val request = Request.Builder()
            .url("${getBaseUrl()}/health/liveliness")
            .get()
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                response.isSuccessful
            }
        } catch (e: Exception) {
            Log.e(TAG, "Health check failed: ${e.message}")
            false
        }
    }

    private fun parseResponse(body: String): ChatResponse {
        val json = JSONObject(body)
        val choices = json.getJSONArray("choices")
        val firstChoice = choices.getJSONObject(0)
        val message = firstChoice.getJSONObject("message")
        val usage = json.optJSONObject("usage")

        return ChatResponse(
            id = json.getString("id"),
            model = json.getString("model"),
            content = message.getString("content"),
            finishReason = firstChoice.optString("finish_reason"),
            promptTokens = usage?.optInt("prompt_tokens") ?: 0,
            completionTokens = usage?.optInt("completion_tokens") ?: 0,
            totalTokens = usage?.optInt("total_tokens") ?: 0
        )
    }
}
