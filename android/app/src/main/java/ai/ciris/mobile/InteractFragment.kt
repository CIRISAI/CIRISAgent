package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import android.widget.LinearLayout
import com.google.gson.Gson
import com.google.gson.JsonParser
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit
import java.util.concurrent.ConcurrentHashMap

/**
 * InteractFragment - Chat Interface with Reasoning Stream
 *
 * Main chat interface for interacting with the CIRIS agent.
 * Shows real-time reasoning progress for each message via SSE.
 */
class InteractFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: ChatWithReasoningAdapter
    private lateinit var messageInput: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var shutdownButton: Button
    private lateinit var emergencyButton: Button
    private lateinit var loadingIndicator: ProgressBar
    // SSE status is shown in the statusText instead

    // Standard HTTP client for API calls
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // SSE client with no read timeout
    private val sseClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // No timeout for SSE
        .build()

    private val gson = Gson()
    private val chatItems = mutableListOf<ChatItem>()
    private var accessToken: String? = null
    private var pollingJob: Job? = null
    private var statusJob: Job? = null
    private var sseJob: Job? = null
    private var isConnected = false
    private var isSseConnected = false
    private var isSending = false
    private var isFirstLoad = true

    // Task tracking: message_id -> task_id
    private val messageToTaskMap = ConcurrentHashMap<String, String>()
    // Task reasoning: task_id -> ReasoningState
    private val taskReasoningMap = ConcurrentHashMap<String, ReasoningState>()

    companion object {
        private const val TAG = "InteractFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val CHANNEL_ID = "api_0.0.0.0_8080"
        private const val SSE_URL = "$BASE_URL/v1/system/runtime/reasoning-stream"
        private const val POLL_INTERVAL_MS = 3000L
        private const val STATUS_POLL_INTERVAL_MS = 5000L
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): InteractFragment {
            return InteractFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_ACCESS_TOKEN, accessToken)
                }
            }
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_interact, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)
        Log.i(TAG, "InteractFragment started, hasToken=${accessToken != null}")

        // Handle keyboard visibility
        val rootView = view.findViewById<LinearLayout>(R.id.interactRoot)
        rootView.viewTreeObserver.addOnGlobalLayoutListener {
            val rect = android.graphics.Rect()
            rootView.getWindowVisibleDisplayFrame(rect)
            val screenHeight = rootView.rootView.height
            val keypadHeight = screenHeight - rect.bottom
            if (keypadHeight > screenHeight * 0.15) {
                rootView.updatePadding(bottom = keypadHeight)
            } else {
                rootView.updatePadding(bottom = 0)
            }
        }

        // Bind views
        recyclerView = view.findViewById(R.id.chatRecyclerView)
        messageInput = view.findViewById(R.id.messageInput)
        sendButton = view.findViewById(R.id.sendButton)
        statusDot = view.findViewById(R.id.statusDot)
        statusText = view.findViewById(R.id.statusText)
        shutdownButton = view.findViewById(R.id.shutdownButton)
        emergencyButton = view.findViewById(R.id.emergencyButton)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)

        // Setup RecyclerView
        adapter = ChatWithReasoningAdapter(chatItems) { taskId ->
            // Toggle reasoning expansion
            taskReasoningMap[taskId]?.let { reasoning ->
                reasoning.isExpanded = !reasoning.isExpanded
                // Force refresh the adapter
                adapter.notifyDataSetChanged()
            }
        }
        val layoutManager = LinearLayoutManager(requireContext())
        layoutManager.stackFromEnd = true
        recyclerView.layoutManager = layoutManager
        recyclerView.adapter = adapter

        // Setup click listeners
        sendButton.setOnClickListener { sendMessage() }
        shutdownButton.setOnClickListener { showShutdownDialog() }
        emergencyButton.setOnClickListener { showEmergencyShutdownDialog() }

        // Handle Enter key to send
        messageInput.setOnEditorActionListener { _, actionId, event ->
            if (actionId == EditorInfo.IME_ACTION_SEND ||
                (event?.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)) {
                sendMessage()
                true
            } else {
                false
            }
        }

        // Start polling and SSE
        startPolling()
        startStatusPolling()
        startSseStream()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        pollingJob?.cancel()
        statusJob?.cancel()
        sseJob?.cancel()
    }

    private fun startPolling() {
        pollingJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                loadHistory()
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private fun startStatusPolling() {
        statusJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                fetchStatus()
                delay(STATUS_POLL_INTERVAL_MS)
            }
        }
    }

    private fun startSseStream() {
        sseJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                try {
                    connectSse()
                } catch (e: Exception) {
                    Log.e(TAG, "SSE connection error", e)
                }
                // Reconnect after delay
                delay(2000)
            }
        }
    }

    private suspend fun connectSse() {
        val token = accessToken ?: return

        withContext(Dispatchers.Main) {
            updateSseStatus(false)
        }

        val request = Request.Builder()
            .url(SSE_URL)
            .addHeader("Accept", "text/event-stream")
            .addHeader("Authorization", "Bearer $token")
            .build()

        try {
            val response = sseClient.newCall(request).execute()

            if (!response.isSuccessful) {
                Log.e(TAG, "SSE HTTP error: ${response.code}")
                return
            }

            withContext(Dispatchers.Main) {
                updateSseStatus(true)
            }

            val source = response.body?.source() ?: return

            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: continue
                if (line.startsWith("data:")) {
                    val jsonStr = line.substring(5).trim()
                    try {
                        processSseData(jsonStr)
                    } catch (e: Exception) {
                        Log.e(TAG, "Error parsing SSE: ${e.message}")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "SSE stream error", e)
            withContext(Dispatchers.Main) {
                updateSseStatus(false)
            }
        }
    }

    private suspend fun processSseData(jsonStr: String) {
        val jsonObject = JsonParser.parseString(jsonStr).asJsonObject

        // Skip keepalive
        if (jsonObject.has("status") && jsonObject.get("status").asString == "connected") {
            return
        }
        if (jsonObject.has("timestamp") && jsonObject.size() == 1) {
            return
        }

        if (jsonObject.has("events")) {
            val events = jsonObject.getAsJsonArray("events")
            var needsUpdate = false

            for (eventElem in events) {
                val event = eventElem.asJsonObject
                val taskId = if (event.has("task_id") && !event.get("task_id").isJsonNull)
                    event.get("task_id").asString else continue
                val thoughtId = if (event.has("thought_id") && !event.get("thought_id").isJsonNull)
                    event.get("thought_id").asString else "unknown"
                val eventType = event.get("event_type").asString

                // Get or create reasoning state for this task
                val reasoning = taskReasoningMap.getOrPut(taskId) {
                    ReasoningState(taskId = taskId)
                }

                // Get or create thought
                val thought = reasoning.thoughts.getOrPut(thoughtId) {
                    ThoughtState(thoughtId = thoughtId)
                }

                // Convert JsonObject to Map for storage (recursively parse nested objects)
                val eventData = jsonObjectToMap(event)
                Log.d(TAG, "SSE event type=$eventType, keys=${eventData.keys}, contextType=${eventData["context"]?.javaClass?.simpleName}")

                // Update stage based on event type
                when (eventType) {
                    "thought_start" -> {
                        thought.stages[ReasoningStage.START] = StageState(completed = true, data = eventData)
                        if (event.has("thought_content")) {
                            thought.content = event.get("thought_content").asString
                        }
                        if (event.has("task_description")) {
                            reasoning.description = event.get("task_description").asString
                        }
                    }
                    "snapshot_and_context" -> {
                        thought.stages[ReasoningStage.CONTEXT] = StageState(completed = true, data = eventData)
                    }
                    "dma_results" -> {
                        thought.stages[ReasoningStage.DMA] = StageState(completed = true, data = eventData)
                    }
                    "aspdma_result" -> {
                        thought.stages[ReasoningStage.ACTION] = StageState(completed = true, data = eventData)
                        thought.selectedAction = event.get("selected_action")?.asString
                    }
                    "conscience_result" -> {
                        val passed = event.get("conscience_passed")?.asBoolean ?: true
                        thought.stages[ReasoningStage.CONSCIENCE] = StageState(completed = true, data = eventData)
                        thought.consciencePassed = passed
                    }
                    "action_result" -> {
                        val executed = event.get("action_executed")?.asString ?: ""
                        thought.stages[ReasoningStage.RESULT] = StageState(completed = true, data = eventData)
                        thought.executedAction = executed

                        // Check if task is complete
                        if (executed.contains("task_complete") || executed.contains("task_reject")) {
                            reasoning.isComplete = true
                        }
                    }
                }

                needsUpdate = true
            }

            if (needsUpdate) {
                withContext(Dispatchers.Main) {
                    updateChatItemsFromHistory()
                }
            }
        }
    }

    // Recursively convert JsonObject to Map<String, Any>
    private fun jsonObjectToMap(jsonObject: com.google.gson.JsonObject): Map<String, Any> {
        val map = mutableMapOf<String, Any>()
        for (key in jsonObject.keySet()) {
            map[key] = jsonElementToAny(jsonObject.get(key))
        }
        return map
    }

    // Recursively convert JsonArray to List<Any>
    private fun jsonArrayToList(jsonArray: com.google.gson.JsonArray): List<Any> {
        return jsonArray.map { jsonElementToAny(it) }
    }

    // Convert any JsonElement to the appropriate Kotlin type
    private fun jsonElementToAny(element: com.google.gson.JsonElement): Any {
        return when {
            element.isJsonNull -> "null"
            element.isJsonPrimitive -> {
                val prim = element.asJsonPrimitive
                when {
                    prim.isBoolean -> prim.asBoolean
                    prim.isNumber -> prim.asNumber
                    else -> prim.asString
                }
            }
            element.isJsonObject -> jsonObjectToMap(element.asJsonObject)
            element.isJsonArray -> jsonArrayToList(element.asJsonArray)
            else -> element.toString()
        }
    }

    private fun updateSseStatus(connected: Boolean) {
        if (!isAdded) return
        isSseConnected = connected
        // SSE status is reflected in the connection status text
    }

    private fun loadHistory() {
        CoroutineScope(Dispatchers.IO).launch {
            if (isFirstLoad) {
                withContext(Dispatchers.Main) {
                    loadingIndicator.visibility = View.VISIBLE
                }
            }
            try {
                fetchHistory()
            } catch (e: Exception) {
                Log.e(TAG, "Error loading history", e)
            } finally {
                if (isFirstLoad) {
                    withContext(Dispatchers.Main) {
                        loadingIndicator.visibility = View.GONE
                    }
                    isFirstLoad = false
                }
            }
        }
    }

    private var cachedMessages: List<HistoryMessage> = emptyList()

    private suspend fun fetchHistory() {
        val url = "$BASE_URL/v1/agent/history?channel_id=$CHANNEL_ID&limit=20"
        val requestBuilder = Request.Builder().url(url).get()
        accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

        try {
            val response = client.newCall(requestBuilder.build()).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val historyResponse = gson.fromJson(body, HistoryResponse::class.java)
                val messages = historyResponse.data?.messages ?: emptyList()
                cachedMessages = messages

                withContext(Dispatchers.Main) {
                    updateChatItemsFromHistory()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "History fetch error", e)
        }
    }

    private fun updateChatItemsFromHistory() {
        if (!isAdded) return

        val sorted = cachedMessages.sortedBy { it.timestamp }
        val newItems = mutableListOf<ChatItem>()

        for (msg in sorted) {
            val isAgent = msg.author?.equals("CIRIS", ignoreCase = true) == true || msg.isAgent == true

            // Add message item
            newItems.add(ChatItem.Message(
                id = msg.id ?: "",
                content = msg.content ?: "",
                isAgent = isAgent,
                author = msg.author ?: if (isAgent) "CIRIS" else "You",
                timestamp = formatTimestamp(msg.timestamp)
            ))

            // If this is a user message, check for associated reasoning
            if (!isAgent && msg.id != null) {
                val taskId = messageToTaskMap[msg.id]
                if (taskId != null) {
                    val reasoning = taskReasoningMap[taskId]
                    if (reasoning != null) {
                        newItems.add(ChatItem.Reasoning(reasoning))
                    }
                }
            }
        }

        // Only update if changed
        val changed = newItems.size != chatItems.size ||
                newItems.zip(chatItems).any { (new, old) -> new != old }

        if (changed) {
            chatItems.clear()
            chatItems.addAll(newItems)
            adapter.notifyDataSetChanged()
            if (chatItems.isNotEmpty()) {
                recyclerView.scrollToPosition(chatItems.size - 1)
            }
        }
    }

    private suspend fun fetchStatus() {
        val url = "$BASE_URL/v1/agent/status"
        val requestBuilder = Request.Builder().url(url).get()
        accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

        try {
            val response = client.newCall(requestBuilder.build()).execute()
            val body = response.body?.string()

            withContext(Dispatchers.Main) {
                if (response.isSuccessful && body != null) {
                    val status = gson.fromJson(body, AgentStatusResponse::class.java)
                    updateConnectionStatus(true, status.cognitiveState)
                } else {
                    updateConnectionStatus(false, null)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Status fetch error", e)
            withContext(Dispatchers.Main) {
                updateConnectionStatus(false, null)
            }
        }
    }

    private fun updateConnectionStatus(connected: Boolean, cognitiveState: String?) {
        if (!isAdded) return
        isConnected = connected
        if (connected) {
            statusDot.setBackgroundResource(R.drawable.status_dot_green)
            val sseStatus = if (isSseConnected) " • Live" else ""
            statusText.text = "Connected$sseStatus"
            statusText.setTextColor(resources.getColor(R.color.status_green, null))
        } else {
            statusDot.setBackgroundResource(R.drawable.status_dot_red)
            statusText.text = "Disconnected"
            statusText.setTextColor(resources.getColor(R.color.status_red, null))
        }
    }

    private fun formatTimestamp(timestamp: String?): String {
        if (timestamp == null) return ""
        return try {
            val inputFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
            val date = inputFormat.parse(timestamp.substringBefore("."))
            val outputFormat = SimpleDateFormat("h:mm a", Locale.getDefault())
            outputFormat.format(date ?: Date())
        } catch (e: Exception) {
            timestamp.substringAfter("T").substringBefore(".")
        }
    }

    private fun sendMessage() {
        val text = messageInput.text.toString().trim()
        if (text.isEmpty() || isSending) return

        Log.d(TAG, "Sending message: $text")
        isSending = true
        sendButton.isEnabled = false
        messageInput.isEnabled = false

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = "$BASE_URL/v1/agent/message"
                val jsonBody = gson.toJson(mapOf("message" to text))

                val requestBuilder = Request.Builder()
                    .url(url)
                    .post(jsonBody.toRequestBody("application/json".toMediaType()))
                accessToken?.let {
                    requestBuilder.addHeader("Authorization", "Bearer $it")
                }

                val response = client.newCall(requestBuilder.build()).execute()
                val isSuccess = response.isSuccessful
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (!isAdded) return@withContext
                    if (isSuccess) {
                        messageInput.text.clear()

                        if (!body.isNullOrEmpty()) {
                            try {
                                val submitResponse = gson.fromJson(body, MessageSubmitResponse::class.java)
                                if (submitResponse.data?.accepted == true) {
                                    // Track task_id for this message
                                    val messageId = submitResponse.data.messageId
                                    val taskId = submitResponse.data.taskId
                                    if (messageId != null && taskId != null) {
                                        messageToTaskMap[messageId] = taskId
                                        Log.i(TAG, "Tracking task $taskId for message $messageId")
                                    }
                                    Toast.makeText(requireContext(), "Processing...", Toast.LENGTH_SHORT).show()
                                } else {
                                    val reason = submitResponse.data?.rejectionDetail ?: "Unknown"
                                    Toast.makeText(requireContext(), "Rejected: $reason", Toast.LENGTH_LONG).show()
                                }
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing response", e)
                            }
                        }

                        loadHistory()
                    } else {
                        Toast.makeText(requireContext(), "Error: ${response.code}", Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending message", e)
                withContext(Dispatchers.Main) {
                    if (!isAdded) return@withContext
                    Toast.makeText(requireContext(), "Failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            } finally {
                withContext(Dispatchers.Main) {
                    if (!isAdded) return@withContext
                    isSending = false
                    sendButton.isEnabled = true
                    messageInput.isEnabled = true
                }
            }
        }
    }

    private fun showShutdownDialog() {
        val input = EditText(requireContext())
        input.setText("User requested graceful shutdown")
        input.hint = "Shutdown reason"

        AlertDialog.Builder(requireContext())
            .setTitle("Graceful Shutdown")
            .setMessage("This will initiate a graceful shutdown of the agent.")
            .setView(input)
            .setPositiveButton("Shutdown") { _, _ ->
                performShutdown(input.text.toString(), false)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showEmergencyShutdownDialog() {
        AlertDialog.Builder(requireContext())
            .setTitle("Emergency Stop")
            .setMessage("This will immediately halt the agent. Use only in emergencies!")
            .setPositiveButton("STOP NOW") { _, _ ->
                performShutdown("Emergency stop triggered by user", true)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performShutdown(reason: String, emergency: Boolean) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val endpoint = if (emergency) "emergency-stop" else "shutdown"
                val url = "$BASE_URL/v1/system/$endpoint"
                val jsonBody = gson.toJson(mapOf("reason" to reason))

                val requestBuilder = Request.Builder()
                    .url(url)
                    .post(jsonBody.toRequestBody("application/json".toMediaType()))
                accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

                val response = client.newCall(requestBuilder.build()).execute()

                withContext(Dispatchers.Main) {
                    if (!isAdded) return@withContext
                    if (response.isSuccessful) {
                        Toast.makeText(
                            requireContext(),
                            if (emergency) "Emergency stop initiated" else "Shutdown initiated",
                            Toast.LENGTH_LONG
                        ).show()
                    } else {
                        Toast.makeText(
                            requireContext(),
                            "Shutdown failed: ${response.code}",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Shutdown error", e)
                withContext(Dispatchers.Main) {
                    if (!isAdded) return@withContext
                    Toast.makeText(requireContext(), "Shutdown error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}

// Data classes are defined in InteractActivity.kt to avoid redeclaration

// Reasoning tracking
enum class ReasoningStage {
    START, CONTEXT, DMA, ACTION, CONSCIENCE, RESULT
}

data class StageState(
    val completed: Boolean = false,
    val data: Map<String, Any> = emptyMap()
)

data class ThoughtState(
    val thoughtId: String,
    var content: String = "",
    var selectedAction: String? = null,
    var consciencePassed: Boolean? = null,
    var executedAction: String? = null,
    val stages: MutableMap<ReasoningStage, StageState> = mutableMapOf()
)

data class ReasoningState(
    val taskId: String,
    var description: String = "",
    var isComplete: Boolean = false,
    var isExpanded: Boolean = true,
    val thoughts: MutableMap<String, ThoughtState> = mutableMapOf()
)

// Chat items (messages + reasoning)
sealed class ChatItem {
    data class Message(
        val id: String,
        val content: String,
        val isAgent: Boolean,
        val author: String,
        val timestamp: String
    ) : ChatItem()

    data class Reasoning(val state: ReasoningState) : ChatItem()
}

// ============== Adapter ==============

class ChatWithReasoningAdapter(
    private val items: List<ChatItem>,
    private val onReasoningClick: (String) -> Unit
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    companion object {
        private const val TYPE_USER_MESSAGE = 0
        private const val TYPE_AGENT_MESSAGE = 1
        private const val TYPE_REASONING = 2
    }

    override fun getItemViewType(position: Int): Int {
        return when (val item = items[position]) {
            is ChatItem.Message -> if (item.isAgent) TYPE_AGENT_MESSAGE else TYPE_USER_MESSAGE
            is ChatItem.Reasoning -> TYPE_REASONING
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return when (viewType) {
            TYPE_AGENT_MESSAGE -> {
                val view = inflater.inflate(R.layout.item_chat_agent, parent, false)
                MessageViewHolder(view)
            }
            TYPE_USER_MESSAGE -> {
                val view = inflater.inflate(R.layout.item_chat_user, parent, false)
                MessageViewHolder(view)
            }
            else -> {
                val view = inflater.inflate(R.layout.item_reasoning, parent, false)
                ReasoningViewHolder(view, onReasoningClick)
            }
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (val item = items[position]) {
            is ChatItem.Message -> (holder as MessageViewHolder).bind(item)
            is ChatItem.Reasoning -> (holder as ReasoningViewHolder).bind(item.state)
        }
    }

    override fun getItemCount() = items.size

    class MessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val authorText: TextView = itemView.findViewById(R.id.authorText)
        private val contentText: TextView = itemView.findViewById(R.id.contentText)
        private val timestampText: TextView = itemView.findViewById(R.id.timestampText)

        fun bind(message: ChatItem.Message) {
            authorText.text = message.author
            contentText.text = message.content
            timestampText.text = message.timestamp
        }
    }

    class ReasoningViewHolder(
        itemView: View,
        private val onClick: (String) -> Unit
    ) : RecyclerView.ViewHolder(itemView) {

        private val headerLayout: View = itemView.findViewById(R.id.reasoningHeader)
        private val headerText: TextView = itemView.findViewById(R.id.reasoningHeaderText)
        private val progressIndicator: TextView = itemView.findViewById(R.id.progressIndicator)
        private val detailsContainer: LinearLayout = itemView.findViewById(R.id.detailsContainer)
        private val statusDot: View = itemView.findViewById(R.id.reasoningStatusDot)
        private val expandChevron: TextView = itemView.findViewById(R.id.expandChevron)

        fun bind(state: ReasoningState) {
            // Header text
            val shortId = state.taskId.takeLast(8)
            headerText.text = state.description.ifEmpty { "Task $shortId" }

            // Status dot
            statusDot.setBackgroundResource(
                if (state.isComplete) R.drawable.status_dot_green
                else R.drawable.status_dot_yellow
            )

            // Build compact progress indicator
            val progressParts = mutableListOf<String>()
            val latestThought = state.thoughts.values.lastOrNull()

            if (latestThought != null) {
                // Show DMA completion
                if (latestThought.stages.containsKey(ReasoningStage.DMA)) {
                    progressParts.add("CS·DS·E")
                }

                // Show selected action
                latestThought.selectedAction?.let { action ->
                    val actionLabel = action.substringAfterLast(".").uppercase()
                    progressParts.add(actionLabel)
                }

                // Show conscience result
                latestThought.consciencePassed?.let { passed ->
                    val exemptActions = listOf("TASK_COMPLETE", "DEFER", "REJECT", "OBSERVE", "RECALL")
                    val actionLabel = latestThought.selectedAction?.substringAfterLast(".")?.uppercase() ?: ""
                    if (exemptActions.contains(actionLabel)) {
                        progressParts.add("EXEMPT")
                    } else {
                        progressParts.add(if (passed) "PASSED" else "FAILED")
                    }
                }

                // Show executed action
                latestThought.executedAction?.let { executed ->
                    val executedLabel = executed.substringAfterLast(".").uppercase()
                    progressParts.add(executedLabel)
                }
            }

            // Display progress or dots
            if (progressParts.isNotEmpty()) {
                progressIndicator.text = progressParts.joinToString(" → ")
            } else {
                // Show progress dots
                val thought = latestThought
                val dots = ReasoningStage.values().map { stage ->
                    if (thought?.stages?.containsKey(stage) == true) "●" else "○"
                }.joinToString("")
                progressIndicator.text = dots
            }

            // Toggle details visibility and chevron
            detailsContainer.visibility = if (state.isExpanded) View.VISIBLE else View.GONE
            expandChevron.text = if (state.isExpanded) "▲" else "▼"

            // Populate details
            detailsContainer.removeAllViews()
            if (state.isExpanded) {
                for ((thoughtId, thought) in state.thoughts) {
                    addThoughtDetails(thought)
                }
            }

            // Click to expand/collapse
            headerLayout.setOnClickListener {
                onClick(state.taskId)
            }
        }

        private fun addThoughtDetails(thought: ThoughtState) {
            val context = itemView.context
            val density = context.resources.displayMetrics.density

            // Thought content preview
            if (thought.content.isNotEmpty()) {
                val contentView = TextView(context).apply {
                    text = thought.content.take(100) + if (thought.content.length > 100) "..." else ""
                    textSize = 12f
                    setTextColor(android.graphics.Color.parseColor("#666666"))
                    setPadding(0, (4 * density).toInt(), 0, (8 * density).toInt())
                }
                detailsContainer.addView(contentView)
            }

            // Stage list - each is expandable
            for (stage in ReasoningStage.values()) {
                val stageState = thought.stages[stage]
                val label = when (stage) {
                    ReasoningStage.START -> "1. Start"
                    ReasoningStage.CONTEXT -> "2. Context"
                    ReasoningStage.DMA -> "3. Analysis (CS·DS·E)"
                    ReasoningStage.ACTION -> "4. Action Selection"
                    ReasoningStage.CONSCIENCE -> "5. Ethics Check"
                    ReasoningStage.RESULT -> "6. Result"
                }
                val isCompleted = stageState?.completed == true
                val hasData = stageState?.data?.isNotEmpty() == true

                // Create expandable stage container
                val stageContainer = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding((4 * density).toInt(), (2 * density).toInt(), 0, (2 * density).toInt())
                }

                // Stage header (clickable if has data)
                val stageHeader = TextView(context).apply {
                    val status = if (isCompleted) "✓" else "○"
                    val chevron = if (hasData) " ▶" else ""
                    text = "$status $label$chevron"
                    textSize = 12f
                    setTextColor(android.graphics.Color.parseColor(if (isCompleted) "#10B981" else "#9CA3AF"))
                    if (hasData) {
                        setBackgroundResource(android.R.drawable.list_selector_background)
                    }
                }

                // Stage data container (initially hidden)
                val stageDataContainer = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    visibility = View.GONE
                    setPadding((16 * density).toInt(), (4 * density).toInt(), 0, (8 * density).toInt())
                    setBackgroundColor(android.graphics.Color.parseColor("#F9FAFB"))
                }

                // Populate data if available
                if (hasData && stageState != null) {
                    addStageData(stageDataContainer, stage, stageState.data, density)
                }

                // Toggle on click
                if (hasData) {
                    stageHeader.setOnClickListener {
                        val isExpanded = stageDataContainer.visibility == View.VISIBLE
                        stageDataContainer.visibility = if (isExpanded) View.GONE else View.VISIBLE
                        val status = if (isCompleted) "✓" else "○"
                        val chevron = if (isExpanded) " ▶" else " ▼"
                        stageHeader.text = "$status $label$chevron"
                    }
                }

                stageContainer.addView(stageHeader)
                stageContainer.addView(stageDataContainer)
                detailsContainer.addView(stageContainer)
            }
        }

        private fun addStageData(container: LinearLayout, stage: ReasoningStage, data: Map<String, Any>, density: Float) {
            val context = container.context

            // Filter out common/uninteresting fields
            val skipFields = setOf("event_type", "thought_id", "task_id", "timestamp", "stream_sequence")

            // Highlight important fields based on stage
            val importantFields = when (stage) {
                ReasoningStage.START -> listOf("thought_content", "task_description")
                ReasoningStage.CONTEXT -> listOf("context", "snapshot")
                ReasoningStage.DMA -> listOf("csdma", "dsdma", "pdma", "dma_outputs")
                ReasoningStage.ACTION -> listOf("selected_action", "action_rationale", "action_reasoning")
                ReasoningStage.CONSCIENCE -> listOf("conscience_passed", "epistemic_data", "reasoning")
                ReasoningStage.RESULT -> listOf("action_executed", "execution_success", "tokens_total", "carbon_grams")
            }

            // Show important fields first
            for (field in importantFields) {
                if (data.containsKey(field)) {
                    addDataField(container, field, data[field], density, isImportant = true)
                }
            }

            // Show other fields
            val otherFields = data.keys.filter { it !in skipFields && it !in importantFields }
            if (otherFields.isNotEmpty()) {
                // Add "More details" expandable section
                val moreHeader = TextView(context).apply {
                    text = "📋 More (${otherFields.size} fields) ▶"
                    textSize = 10f
                    setTextColor(android.graphics.Color.parseColor("#6B7280"))
                    setPadding(0, (8 * density).toInt(), 0, (4 * density).toInt())
                    setBackgroundResource(android.R.drawable.list_selector_background)
                }

                val moreContainer = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    visibility = View.GONE
                    setPadding((8 * density).toInt(), 0, 0, 0)
                }

                for (field in otherFields) {
                    addDataField(moreContainer, field, data[field], density, isImportant = false)
                }

                moreHeader.setOnClickListener {
                    val isExpanded = moreContainer.visibility == View.VISIBLE
                    moreContainer.visibility = if (isExpanded) View.GONE else View.VISIBLE
                    moreHeader.text = "📋 More (${otherFields.size} fields) ${if (isExpanded) "▶" else "▼"}"
                }

                container.addView(moreHeader)
                container.addView(moreContainer)
            }
        }

        private fun addDataField(container: LinearLayout, key: String, value: Any?, density: Float, isImportant: Boolean) {
            val ctx = container.context

            val fieldLayout = LinearLayout(ctx).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, (2 * density).toInt(), 0, (2 * density).toInt())
            }

            // Check if this is a complex object (Map or List)
            val isComplex = value is Map<*, *> || value is List<*>

            // Field name with expand indicator for complex objects
            val keyView = TextView(ctx).apply {
                val displayKey = key.replace("_", " ").replaceFirstChar { it.uppercase() }
                text = if (isComplex) "$displayKey ▶" else displayKey
                textSize = if (isImportant) 11f else 10f
                setTextColor(android.graphics.Color.parseColor(if (isImportant) "#3B82F6" else "#6B7280"))
                setTypeface(null, android.graphics.Typeface.BOLD)
                if (isComplex) {
                    setBackgroundResource(android.R.drawable.list_selector_background)
                }
            }
            fieldLayout.addView(keyView)

            if (isComplex) {
                // Create expandable container for complex objects
                val expandContainer = LinearLayout(ctx).apply {
                    orientation = LinearLayout.VERTICAL
                    visibility = View.GONE
                    setPadding((8 * density).toInt(), (4 * density).toInt(), 0, (4 * density).toInt())
                    setBackgroundColor(android.graphics.Color.parseColor("#F3F4F6"))
                }

                // Add scrollable JSON view
                val scrollView = android.widget.HorizontalScrollView(ctx).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {
                        topMargin = (4 * density).toInt()
                    }
                }

                val jsonView = TextView(ctx).apply {
                    text = formatJsonPretty(value)
                    textSize = 10f
                    setTextColor(android.graphics.Color.parseColor("#374151"))
                    setTypeface(android.graphics.Typeface.MONOSPACE)
                    setTextIsSelectable(true)
                }
                scrollView.addView(jsonView)
                expandContainer.addView(scrollView)

                // Toggle on click
                keyView.setOnClickListener {
                    val isExpanded = expandContainer.visibility == View.VISIBLE
                    expandContainer.visibility = if (isExpanded) View.GONE else View.VISIBLE
                    val displayKey = key.replace("_", " ").replaceFirstChar { it.uppercase() }
                    keyView.text = "$displayKey ${if (isExpanded) "▶" else "▼"}"
                }

                fieldLayout.addView(expandContainer)
            } else {
                // Simple value display
                val valueStr = when (value) {
                    is Boolean -> if (value) "✓ Yes" else "✗ No"
                    is Number -> value.toString()
                    is String -> {
                        if (value.length > 500) {
                            value.take(500) + "... [${value.length} chars]"
                        } else {
                            value
                        }
                    }
                    else -> value?.toString() ?: "null"
                }

                val valueView = TextView(ctx).apply {
                    text = valueStr
                    textSize = if (isImportant) 12f else 10f
                    setTextColor(android.graphics.Color.parseColor(
                        when (value) {
                            is Boolean -> if (value) "#10B981" else "#EF4444"
                            is Number -> "#7C3AED"
                            else -> "#374151"
                        }
                    ))
                    setPadding((4 * density).toInt(), 0, 0, 0)
                    setTextIsSelectable(true)

                    // Make long strings expandable
                    if (value is String && value.length > 500) {
                        var isExpanded = false
                        setOnClickListener {
                            isExpanded = !isExpanded
                            text = if (isExpanded) value else value.take(500) + "... [${value.length} chars]"
                        }
                        setBackgroundResource(android.R.drawable.list_selector_background)
                    }
                }
                fieldLayout.addView(valueView)
            }

            container.addView(fieldLayout)
        }

        private fun formatJsonPretty(value: Any?, indent: Int = 0): String {
            val indentStr = "  ".repeat(indent)
            val nextIndent = "  ".repeat(indent + 1)

            return when (value) {
                null -> "null"
                is Boolean -> value.toString()
                is Number -> value.toString()
                is String -> "\"$value\""
                is Map<*, *> -> {
                    if (value.isEmpty()) {
                        "{}"
                    } else {
                        val entries = value.entries.joinToString(",\n") { (k, v) ->
                            "$nextIndent\"$k\": ${formatJsonPretty(v, indent + 1)}"
                        }
                        "{\n$entries\n$indentStr}"
                    }
                }
                is List<*> -> {
                    if (value.isEmpty()) {
                        "[]"
                    } else {
                        val items = value.joinToString(",\n") { item ->
                            "$nextIndent${formatJsonPretty(item, indent + 1)}"
                        }
                        "[\n$items\n$indentStr]"
                    }
                }
                else -> value.toString()
            }
        }
    }
}
