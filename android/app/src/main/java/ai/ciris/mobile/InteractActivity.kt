package ai.ciris.mobile

import android.content.Context
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.BufferedReader
import java.util.concurrent.TimeUnit

class InteractActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: InteractAdapter
    private lateinit var statusText: TextView

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // Disable read timeout for SSE
        .build()

    private var sseJob: Job? = null
    private val gson = Gson()

    // Data state
    private val items = mutableListOf<InteractItem>()
    private var lastTaskId: String? = null
    private var lastThoughtId: String? = null

    companion object {
        private const val TAG = "InteractActivity"
        private const val PREFS_UI = "ciris_ui_prefs"
        private const val KEY_USE_NATIVE = "use_native_interact"
        // Use 127.0.0.1 instead of localhost for slightly better reliability in some envs,
        // though Chaquopy is local. Matching MainActivity logic.
        private const val SSE_URL = "http://localhost:8080/v1/system/runtime/reasoning-stream"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_interact)

        val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.title = "Interact Stream"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        statusText = findViewById(R.id.statusText)
        recyclerView = findViewById(R.id.recyclerView)

        adapter = InteractAdapter(items)
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter

        startSseStream()
    }

    override fun onDestroy() {
        super.onDestroy()
        sseJob?.cancel()
    }

    override fun onCreateOptionsMenu(menu: android.view.Menu?): Boolean {
        menuInflater.inflate(R.menu.interact_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_switch_to_web -> {
                // Disable native UI preference
                getSharedPreferences(PREFS_UI, MODE_PRIVATE)
                    .edit()
                    .putBoolean(KEY_USE_NATIVE, false)
                    .apply()

                // Finish activity to return to WebView
                // Note: The user will need to reload or navigate again in WebView,
                // but since they just came from there or invoked it, they are likely
                // still on the runtime page (which was intercepted) or dashboard.
                finish()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun startSseStream() {
        sseJob = CoroutineScope(Dispatchers.IO).launch {
            try {
                withContext(Dispatchers.Main) {
                    statusText.text = "Status: Connecting..."
                }

                val token = intent.getStringExtra("access_token")
                val requestBuilder = Request.Builder()
                    .url(SSE_URL)
                    .addHeader("Accept", "text/event-stream")

                if (!token.isNullOrEmpty()) {
                    requestBuilder.addHeader("Authorization", "Bearer $token")
                }

                val request = requestBuilder.build()
                val response: Response = client.newCall(request).execute()

                if (!response.isSuccessful) {
                    withContext(Dispatchers.Main) {
                        statusText.text = "Status: Error ${response.code}"
                    }
                    return@launch
                }

                withContext(Dispatchers.Main) {
                    statusText.text = "Status: Connected"
                }

                val source = response.body?.source()
                if (source == null) {
                    withContext(Dispatchers.Main) {
                        statusText.text = "Status: Empty Body"
                    }
                    return@launch
                }

                while (!source.exhausted()) {
                    val line = source.readUtf8Line() ?: continue
                    if (line.startsWith("data:")) {
                        val jsonStr = line.substring(5).trim()
                        try {
                            processSseData(jsonStr)
                        } catch (e: Exception) {
                            Log.e(TAG, "Error parsing SSE data: ${e.message}")
                        }
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "SSE Error", e)
                withContext(Dispatchers.Main) {
                    statusText.text = "Status: Disconnected (${e.message})"
                }
                // Retry logic could go here
            }
        }
    }

    private suspend fun processSseData(jsonStr: String) {
        val jsonObject = JsonParser.parseString(jsonStr).asJsonObject

        // Handle keepalive or simple status
        if (jsonObject.has("status") && jsonObject.get("status").asString == "connected") {
            return
        }
        if (jsonObject.has("timestamp") && jsonObject.size() == 1) {
            // Keepalive
            return
        }

        if (jsonObject.has("events")) {
            val events = jsonObject.getAsJsonArray("events")
            val newItems = mutableListOf<InteractItem>()

            for (eventElem in events) {
                val event = eventElem.asJsonObject
                val taskId = if (event.has("task_id") && !event.get("task_id").isJsonNull) event.get("task_id").asString else "System"
                val thoughtId = if (event.has("thought_id") && !event.get("thought_id").isJsonNull) event.get("thought_id").asString else "Unknown Thought"
                val eventType = event.get("event_type").asString

                // 1. Check/Add Task Header
                if (taskId != lastTaskId) {
                    lastTaskId = taskId
                    newItems.add(InteractItem.TaskHeader(taskId))
                }

                // 2. Check/Add Thought Header
                if (thoughtId != lastThoughtId) {
                    lastThoughtId = thoughtId
                    newItems.add(InteractItem.ThoughtHeader(thoughtId, taskId))
                }

                // 3. Add Event
                newItems.add(InteractItem.EventItem(eventType, event.toString(), thoughtId))
            }

            if (newItems.isNotEmpty()) {
                withContext(Dispatchers.Main) {
                    val startPos = items.size
                    items.addAll(newItems)
                    adapter.notifyItemRangeInserted(startPos, newItems.size)
                    recyclerView.scrollToPosition(items.size - 1)
                }
            }
        }
    }
}

// Data Models
sealed class InteractItem {
    data class TaskHeader(val taskId: String) : InteractItem()
    data class ThoughtHeader(val thoughtId: String, val parentTaskId: String) : InteractItem()
    data class EventItem(val eventType: String, val rawJson: String, val parentThoughtId: String) : InteractItem()
}

// Adapter
class InteractAdapter(private val items: List<InteractItem>) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    companion object {
        private const val TYPE_TASK = 0
        private const val TYPE_THOUGHT = 1
        private const val TYPE_EVENT = 2
    }

    override fun getItemViewType(position: Int): Int {
        return when (items[position]) {
            is InteractItem.TaskHeader -> TYPE_TASK
            is InteractItem.ThoughtHeader -> TYPE_THOUGHT
            is InteractItem.EventItem -> TYPE_EVENT
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return when (viewType) {
            TYPE_TASK -> {
                val view = inflater.inflate(R.layout.item_interact_header, parent, false)
                TaskViewHolder(view)
            }
            TYPE_THOUGHT -> {
                val view = inflater.inflate(R.layout.item_interact_header, parent, false)
                ThoughtViewHolder(view)
            }
            else -> {
                val view = inflater.inflate(R.layout.item_interact_event, parent, false)
                EventViewHolder(view)
            }
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (val item = items[position]) {
            is InteractItem.TaskHeader -> (holder as TaskViewHolder).bind(item)
            is InteractItem.ThoughtHeader -> (holder as ThoughtViewHolder).bind(item)
            is InteractItem.EventItem -> (holder as EventViewHolder).bind(item)
        }
    }

    override fun getItemCount() = items.size

    class TaskViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val title: TextView = itemView.findViewById(R.id.headerTitle)
        private val subtitle: TextView = itemView.findViewById(R.id.headerSubtitle)

        fun bind(item: InteractItem.TaskHeader) {
            title.text = "Task: ${item.taskId}"
            subtitle.text = "New Task Started"
            title.setTextColor(android.graphics.Color.BLUE)
        }
    }

    class ThoughtViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val title: TextView = itemView.findViewById(R.id.headerTitle)
        private val subtitle: TextView = itemView.findViewById(R.id.headerSubtitle)

        fun bind(item: InteractItem.ThoughtHeader) {
            title.text = "Thought: ${item.thoughtId}"
            subtitle.text = "Under Task: ${item.parentTaskId}"

            val density = itemView.context.resources.displayMetrics.density
            val paddingLeft = (24 * density).toInt()
            itemView.setPadding(paddingLeft, itemView.paddingTop, itemView.paddingRight, itemView.paddingBottom)

            title.textSize = 16f
        }
    }

    class EventViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val type: TextView = itemView.findViewById(R.id.eventType)
        private val content: TextView = itemView.findViewById(R.id.eventContent)
        private val timestamp: TextView = itemView.findViewById(R.id.eventTimestamp)

        fun bind(item: InteractItem.EventItem) {
            type.text = item.eventType

            // Basic pretty print or just show part of JSON
            val contentStr = if (item.rawJson.length > 200) {
                 item.rawJson.substring(0, 200) + "..."
            } else {
                item.rawJson
            }
            content.text = contentStr

            // Parse timestamp if possible or just use current
            timestamp.text = ""
        }
    }
}
