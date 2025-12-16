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
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
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

/**
 * InteractActivity - Chat Interface
 *
 * Main chat interface for interacting with the CIRIS agent.
 * Features:
 * - Send/receive messages
 * - Conversation history (last 20 messages)
 * - Agent status display (connection + cognitive state)
 * - Shutdown controls (graceful + emergency)
 */
class InteractActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: ChatAdapter
    private lateinit var messageInput: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var shutdownButton: Button
    private lateinit var emergencyButton: Button
    private lateinit var loadingIndicator: ProgressBar

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val messages = mutableListOf<ChatMessage>()
    private var accessToken: String? = null
    private var pollingJob: Job? = null
    private var statusJob: Job? = null
    private var isConnected = false
    private var isSending = false

    companion object {
        private const val TAG = "InteractActivity"
        private const val BASE_URL = "http://localhost:8080"
        private const val CHANNEL_ID = "api_0.0.0.0_8080"
        private const val POLL_INTERVAL_MS = 2000L
        private const val STATUS_POLL_INTERVAL_MS = 5000L
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_interact)

        accessToken = intent.getStringExtra("access_token")
        Log.i(TAG, "InteractActivity started, hasToken=${accessToken != null}")

        val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.title = "Chat with CIRIS"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        // Bind views
        recyclerView = findViewById(R.id.chatRecyclerView)
        messageInput = findViewById(R.id.messageInput)
        sendButton = findViewById(R.id.sendButton)
        statusDot = findViewById(R.id.statusDot)
        statusText = findViewById(R.id.statusText)
        shutdownButton = findViewById(R.id.shutdownButton)
        emergencyButton = findViewById(R.id.emergencyButton)
        loadingIndicator = findViewById(R.id.loadingIndicator)

        // Setup RecyclerView
        adapter = ChatAdapter(messages)
        val layoutManager = LinearLayoutManager(this)
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

        // Start polling
        startPolling()
        startStatusPolling()
    }

    override fun onDestroy() {
        super.onDestroy()
        pollingJob?.cancel()
        statusJob?.cancel()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    override fun onCreateOptionsMenu(menu: android.view.Menu?): Boolean {
        menuInflater.inflate(R.menu.interact_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_view_runtime -> {
                // Launch RuntimeActivity
                val intent = android.content.Intent(this, RuntimeActivity::class.java)
                intent.putExtra("access_token", accessToken)
                startActivity(intent)
                true
            }
            R.id.action_refresh -> {
                loadHistory()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun startPolling() {
        pollingJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                try {
                    fetchHistory()
                } catch (e: Exception) {
                    Log.e(TAG, "Error fetching history", e)
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private fun startStatusPolling() {
        statusJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                try {
                    fetchStatus()
                } catch (e: Exception) {
                    Log.e(TAG, "Error fetching status", e)
                    withContext(Dispatchers.Main) {
                        updateConnectionStatus(false, null)
                    }
                }
                delay(STATUS_POLL_INTERVAL_MS)
            }
        }
    }

    private fun loadHistory() {
        CoroutineScope(Dispatchers.IO).launch {
            withContext(Dispatchers.Main) {
                loadingIndicator.visibility = View.VISIBLE
            }
            try {
                fetchHistory()
            } catch (e: Exception) {
                Log.e(TAG, "Error loading history", e)
            } finally {
                withContext(Dispatchers.Main) {
                    loadingIndicator.visibility = View.GONE
                }
            }
        }
    }

    private suspend fun fetchHistory() {
        val url = "$BASE_URL/v1/agent/history?channel_id=$CHANNEL_ID&limit=20"
        Log.d(TAG, "Fetching history from: $url")
        val requestBuilder = Request.Builder().url(url).get()
        accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

        try {
            val response = client.newCall(requestBuilder.build()).execute()
            val body = response.body?.string()
            Log.d(TAG, "History response: code=${response.code}, body=${body?.take(200)}")

            if (response.isSuccessful && body != null) {
                val historyResponse = gson.fromJson(body, HistoryResponse::class.java)
                val messages = historyResponse.data?.messages ?: emptyList()
                Log.d(TAG, "Parsed ${messages.size} messages")

                withContext(Dispatchers.Main) {
                    updateMessages(messages)
                }
            } else {
                Log.e(TAG, "History fetch failed: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "History fetch error", e)
        }
    }

    private suspend fun fetchStatus() {
        val url = "$BASE_URL/v1/agent/status"
        val requestBuilder = Request.Builder().url(url).get()
        accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

        val response = client.newCall(requestBuilder.build()).execute()
        if (response.isSuccessful) {
            val body = response.body?.string() ?: return
            val status = gson.fromJson(body, AgentStatusResponse::class.java)

            withContext(Dispatchers.Main) {
                updateConnectionStatus(true, status.cognitiveState)
            }
        } else {
            withContext(Dispatchers.Main) {
                updateConnectionStatus(false, null)
            }
        }
    }

    private fun updateConnectionStatus(connected: Boolean, cognitiveState: String?) {
        isConnected = connected
        if (connected) {
            statusDot.setBackgroundResource(R.drawable.status_dot_green)
            statusText.text = "Connected"
            statusText.setTextColor(resources.getColor(R.color.status_green, null))
        } else {
            statusDot.setBackgroundResource(R.drawable.status_dot_red)
            statusText.text = "Disconnected"
            statusText.setTextColor(resources.getColor(R.color.status_red, null))
        }
    }

    private fun updateMessages(newMessages: List<HistoryMessage>) {
        // Sort by timestamp (oldest first)
        val sorted = newMessages.sortedBy { it.timestamp }

        // Convert to ChatMessage
        val chatMessages = sorted.map { msg ->
            ChatMessage(
                id = msg.id ?: "",
                content = msg.content ?: "",
                isAgent = msg.isAgent ?: false,
                author = msg.author ?: if (msg.isAgent == true) "CIRIS" else "You",
                timestamp = msg.timestamp ?: ""
            )
        }

        // Only update if changed
        if (chatMessages != messages) {
            messages.clear()
            messages.addAll(chatMessages)
            adapter.notifyDataSetChanged()
            if (messages.isNotEmpty()) {
                recyclerView.scrollToPosition(messages.size - 1)
            }
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
                // Use non-blocking /message endpoint
                val url = "$BASE_URL/v1/agent/message"
                val jsonBody = gson.toJson(mapOf("message" to text))
                Log.d(TAG, "POST $url with body: $jsonBody")

                val requestBuilder = Request.Builder()
                    .url(url)
                    .post(jsonBody.toRequestBody("application/json".toMediaType()))
                accessToken?.let {
                    requestBuilder.addHeader("Authorization", "Bearer $it")
                    Log.d(TAG, "Added auth header: Bearer ${it.take(20)}...")
                }

                val response = client.newCall(requestBuilder.build()).execute()
                val responseCode = response.code
                val isSuccess = response.isSuccessful
                val body = response.body?.string()  // Read body on IO thread
                Log.d(TAG, "Send response: code=$responseCode, success=$isSuccess, body=${body?.take(200)}")

                withContext(Dispatchers.Main) {
                    if (isSuccess) {
                        messageInput.text.clear()

                        // Check if message was accepted
                        if (!body.isNullOrEmpty()) {
                            try {
                                val submitResponse = gson.fromJson(body, MessageSubmitResponse::class.java)
                                if (submitResponse.data?.accepted == true) {
                                    Toast.makeText(
                                        this@InteractActivity,
                                        "Message sent",
                                        Toast.LENGTH_SHORT
                                    ).show()
                                } else {
                                    val reason = submitResponse.data?.rejectionDetail ?: "Unknown"
                                    Toast.makeText(
                                        this@InteractActivity,
                                        "Rejected: $reason",
                                        Toast.LENGTH_LONG
                                    ).show()
                                }
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing response", e)
                            }
                        }

                        // Refresh history to see response when ready
                        loadHistory()
                    } else {
                        Toast.makeText(
                            this@InteractActivity,
                            "Error: $responseCode - $body",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending message", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@InteractActivity,
                        "Failed to send: ${e.message}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } finally {
                withContext(Dispatchers.Main) {
                    isSending = false
                    sendButton.isEnabled = true
                    messageInput.isEnabled = true
                }
            }
        }
    }

    private fun showShutdownDialog() {
        val input = EditText(this)
        input.setText("User requested graceful shutdown")
        input.setHint("Shutdown reason")

        AlertDialog.Builder(this)
            .setTitle("Initiate Graceful Shutdown")
            .setMessage("The agent will complete critical tasks and perform clean shutdown procedures.")
            .setView(input)
            .setPositiveButton("Shutdown") { _, _ ->
                val reason = input.text.toString()
                performShutdown(reason, force = false)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showEmergencyShutdownDialog() {
        AlertDialog.Builder(this)
            .setTitle("⚠️ EMERGENCY SHUTDOWN")
            .setMessage("WARNING: This will IMMEDIATELY terminate the agent!\n\n• NO graceful shutdown\n• NO task completion\n• NO final messages\n• IMMEDIATE termination")
            .setPositiveButton("EXECUTE") { _, _ ->
                performShutdown("EMERGENCY: Immediate shutdown required", force = true)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performShutdown(reason: String, force: Boolean) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = "$BASE_URL/v1/system/shutdown"
                val jsonBody = gson.toJson(mapOf(
                    "reason" to reason,
                    "force" to force,
                    "confirm" to true  // Required confirmation flag
                ))

                val requestBuilder = Request.Builder()
                    .url(url)
                    .post(jsonBody.toRequestBody("application/json".toMediaType()))
                accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

                val response = client.newCall(requestBuilder.build()).execute()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        val msg = if (force) "EMERGENCY SHUTDOWN INITIATED" else "Shutdown initiated"
                        Toast.makeText(this@InteractActivity, msg, Toast.LENGTH_LONG).show()
                    } else {
                        Toast.makeText(
                            this@InteractActivity,
                            "Shutdown failed: ${response.code}",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Shutdown error", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@InteractActivity,
                        "Shutdown error: ${e.message}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }
}

// Data classes
data class HistoryResponse(
    val data: HistoryData?
)

data class HistoryData(
    val messages: List<HistoryMessage>?,
    @SerializedName("total_count") val totalCount: Int?
)

data class HistoryMessage(
    val id: String?,
    val content: String?,
    @SerializedName("is_agent") val isAgent: Boolean?,
    val author: String?,
    val timestamp: String?
)

data class AgentStatusResponse(
    @SerializedName("cognitive_state") val cognitiveState: String?,
    val status: String?
)

// Message submission response (non-blocking endpoint)
data class MessageSubmitResponse(
    val data: MessageSubmitData?
)

data class MessageSubmitData(
    @SerializedName("message_id") val messageId: String?,
    @SerializedName("task_id") val taskId: String?,
    @SerializedName("channel_id") val channelId: String?,
    @SerializedName("submitted_at") val submittedAt: String?,
    val accepted: Boolean?,
    @SerializedName("rejection_reason") val rejectionReason: String?,
    @SerializedName("rejection_detail") val rejectionDetail: String?
)

data class ChatMessage(
    val id: String,
    val content: String,
    val isAgent: Boolean,
    val author: String,
    val timestamp: String
)

// Chat Adapter
class ChatAdapter(private val messages: List<ChatMessage>) : RecyclerView.Adapter<ChatAdapter.ViewHolder>() {

    companion object {
        private const val VIEW_TYPE_USER = 0
        private const val VIEW_TYPE_AGENT = 1
    }

    override fun getItemViewType(position: Int): Int {
        return if (messages[position].isAgent) VIEW_TYPE_AGENT else VIEW_TYPE_USER
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val layout = if (viewType == VIEW_TYPE_AGENT)
            R.layout.item_chat_agent
        else
            R.layout.item_chat_user
        val view = inflater.inflate(layout, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(messages[position])
    }

    override fun getItemCount() = messages.size

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val authorText: TextView = itemView.findViewById(R.id.authorText)
        private val contentText: TextView = itemView.findViewById(R.id.contentText)
        private val timestampText: TextView = itemView.findViewById(R.id.timestampText)

        fun bind(message: ChatMessage) {
            authorText.text = message.author
            contentText.text = message.content

            // Format timestamp
            try {
                val inputFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
                val outputFormat = SimpleDateFormat("h:mm a", Locale.getDefault())
                val date = inputFormat.parse(message.timestamp.substringBefore("."))
                timestampText.text = date?.let { outputFormat.format(it) } ?: ""
            } catch (e: Exception) {
                timestampText.text = ""
            }
        }
    }
}
