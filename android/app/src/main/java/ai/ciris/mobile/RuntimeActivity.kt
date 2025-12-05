package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import com.google.gson.JsonParser
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.util.concurrent.TimeUnit

/**
 * RuntimeActivity - Reasoning Stream Viewer
 *
 * Displays the real-time SSE stream of agent reasoning events:
 * - Tasks being processed
 * - Thoughts being generated
 * - Events (actions, observations, etc.)
 *
 * This is a debug/monitoring view, not the main chat interface.
 */
class RuntimeActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: RuntimeAdapter
    private lateinit var statusText: TextView

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // Disable read timeout for SSE
        .build()

    private var sseJob: Job? = null
    private val gson = Gson()

    // Data state
    private val items = mutableListOf<RuntimeItem>()
    private var lastTaskId: String? = null
    private var lastThoughtId: String? = null

    companion object {
        private const val TAG = "RuntimeActivity"
        private const val PREFS_UI = "ciris_ui_prefs"
        private const val KEY_USE_NATIVE = "use_native_runtime"
        private const val SSE_URL = "http://localhost:8080/v1/system/runtime/reasoning-stream"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_runtime)

        // Handle window insets for edge-to-edge
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(insets.left, insets.top, insets.right, insets.bottom)
            WindowInsetsCompat.CONSUMED
        }

        val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.title = "Reasoning Stream"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        statusText = findViewById(R.id.statusText)
        recyclerView = findViewById(R.id.recyclerView)

        adapter = RuntimeAdapter(items)
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter

        startSseStream()
    }

    override fun onDestroy() {
        super.onDestroy()
        sseJob?.cancel()
    }

    override fun onCreateOptionsMenu(menu: android.view.Menu?): Boolean {
        menuInflater.inflate(R.menu.runtime_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_switch_to_web -> {
                getSharedPreferences(PREFS_UI, MODE_PRIVATE)
                    .edit()
                    .putBoolean(KEY_USE_NATIVE, false)
                    .apply()
                finish()
                true
            }
            R.id.action_clear -> {
                items.clear()
                lastTaskId = null
                lastThoughtId = null
                adapter.notifyDataSetChanged()
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
            return
        }

        if (jsonObject.has("events")) {
            val events = jsonObject.getAsJsonArray("events")
            val newItems = mutableListOf<RuntimeItem>()

            for (eventElem in events) {
                val event = eventElem.asJsonObject
                val taskId = if (event.has("task_id") && !event.get("task_id").isJsonNull)
                    event.get("task_id").asString else "System"
                val thoughtId = if (event.has("thought_id") && !event.get("thought_id").isJsonNull)
                    event.get("thought_id").asString else "Unknown"
                val eventType = event.get("event_type").asString

                if (taskId != lastTaskId) {
                    lastTaskId = taskId
                    newItems.add(RuntimeItem.TaskHeader(taskId))
                }

                if (thoughtId != lastThoughtId) {
                    lastThoughtId = thoughtId
                    newItems.add(RuntimeItem.ThoughtHeader(thoughtId, taskId))
                }

                newItems.add(RuntimeItem.EventItem(eventType, event.toString(), thoughtId))
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
sealed class RuntimeItem {
    data class TaskHeader(val taskId: String) : RuntimeItem()
    data class ThoughtHeader(val thoughtId: String, val parentTaskId: String) : RuntimeItem()
    data class EventItem(val eventType: String, val rawJson: String, val parentThoughtId: String) : RuntimeItem()
}

// Adapter
class RuntimeAdapter(private val items: List<RuntimeItem>) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    companion object {
        private const val TYPE_TASK = 0
        private const val TYPE_THOUGHT = 1
        private const val TYPE_EVENT = 2
    }

    override fun getItemViewType(position: Int): Int {
        return when (items[position]) {
            is RuntimeItem.TaskHeader -> TYPE_TASK
            is RuntimeItem.ThoughtHeader -> TYPE_THOUGHT
            is RuntimeItem.EventItem -> TYPE_EVENT
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return when (viewType) {
            TYPE_TASK -> {
                val view = inflater.inflate(R.layout.item_runtime_header, parent, false)
                TaskViewHolder(view)
            }
            TYPE_THOUGHT -> {
                val view = inflater.inflate(R.layout.item_runtime_header, parent, false)
                ThoughtViewHolder(view)
            }
            else -> {
                val view = inflater.inflate(R.layout.item_runtime_event, parent, false)
                EventViewHolder(view)
            }
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (val item = items[position]) {
            is RuntimeItem.TaskHeader -> (holder as TaskViewHolder).bind(item)
            is RuntimeItem.ThoughtHeader -> (holder as ThoughtViewHolder).bind(item)
            is RuntimeItem.EventItem -> (holder as EventViewHolder).bind(item)
        }
    }

    override fun getItemCount() = items.size

    class TaskViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val title: TextView = itemView.findViewById(R.id.headerTitle)
        private val subtitle: TextView = itemView.findViewById(R.id.headerSubtitle)

        fun bind(item: RuntimeItem.TaskHeader) {
            title.text = "Task: ${item.taskId}"
            subtitle.text = "New Task Started"
            title.setTextColor(android.graphics.Color.parseColor("#3B82F6")) // Blue
        }
    }

    class ThoughtViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val title: TextView = itemView.findViewById(R.id.headerTitle)
        private val subtitle: TextView = itemView.findViewById(R.id.headerSubtitle)

        fun bind(item: RuntimeItem.ThoughtHeader) {
            title.text = "Thought: ${item.thoughtId}"
            subtitle.text = "Task: ${item.parentTaskId}"
            title.setTextColor(android.graphics.Color.parseColor("#8B5CF6")) // Purple

            val density = itemView.context.resources.displayMetrics.density
            val paddingLeft = (24 * density).toInt()
            itemView.setPadding(paddingLeft, itemView.paddingTop, itemView.paddingRight, itemView.paddingBottom)
            title.textSize = 15f
        }
    }

    class EventViewHolder(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        private val type: TextView = itemView.findViewById(R.id.eventType)
        private val content: TextView = itemView.findViewById(R.id.eventContent)
        private val timestamp: TextView = itemView.findViewById(R.id.eventTimestamp)

        fun bind(item: RuntimeItem.EventItem) {
            type.text = item.eventType

            val contentStr = if (item.rawJson.length > 200) {
                item.rawJson.substring(0, 200) + "..."
            } else {
                item.rawJson
            }
            content.text = contentStr
            timestamp.text = ""
        }
    }
}
