package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
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
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * AdaptersFragment - Adapter Management UI
 *
 * Displays a list of adapters (Discord, API, CLI, etc.) with their status
 * and provides options to reload or remove adapters.
 */
class AdaptersFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: AdapterListAdapter
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var adapterCountText: TextView
    private lateinit var loadingIndicator: ProgressBar
    private lateinit var emptyState: View
    private lateinit var refreshButton: ImageButton

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val adapterItems = mutableListOf<AdapterItem>()
    private var accessToken: String? = null
    private var pollingJob: Job? = null
    private var isConnected = false

    companion object {
        private const val TAG = "AdaptersFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val POLL_INTERVAL_MS = 10000L
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): AdaptersFragment {
            return AdaptersFragment().apply {
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
        return inflater.inflate(R.layout.fragment_adapters, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)
        Log.i(TAG, "AdaptersFragment started, hasToken=${accessToken != null}")

        // Bind views
        recyclerView = view.findViewById(R.id.adaptersRecyclerView)
        statusDot = view.findViewById(R.id.statusDot)
        statusText = view.findViewById(R.id.statusText)
        adapterCountText = view.findViewById(R.id.adapterCountText)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        emptyState = view.findViewById(R.id.emptyState)
        refreshButton = view.findViewById(R.id.refreshButton)

        // Setup RecyclerView
        adapter = AdapterListAdapter(adapterItems, ::onReloadAdapter, ::onRemoveAdapter)
        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        // Refresh button
        refreshButton.setOnClickListener {
            fetchAdapters()
        }

        // Initial fetch
        fetchAdapters()
    }

    override fun onResume() {
        super.onResume()
        startPolling()
    }

    override fun onPause() {
        super.onPause()
        stopPolling()
    }

    private fun startPolling() {
        pollingJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                delay(POLL_INTERVAL_MS)
                fetchAdaptersInternal()
            }
        }
    }

    private fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    private fun fetchAdapters() {
        loadingIndicator.visibility = View.VISIBLE
        CoroutineScope(Dispatchers.IO).launch {
            fetchAdaptersInternal()
            withContext(Dispatchers.Main) {
                loadingIndicator.visibility = View.GONE
            }
        }
    }

    private suspend fun fetchAdaptersInternal() {
        try {
            val request = Request.Builder()
                .url("$BASE_URL/v1/system/adapters")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: return

            if (response.isSuccessful) {
                val adapterResponse = gson.fromJson(body, AdapterListResponse::class.java)
                withContext(Dispatchers.Main) {
                    updateUI(adapterResponse.data)
                    updateStatus(true)
                }
            } else {
                Log.w(TAG, "Failed to fetch adapters: ${response.code}")
                withContext(Dispatchers.Main) {
                    updateStatus(false)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching adapters", e)
            withContext(Dispatchers.Main) {
                updateStatus(false)
            }
        }
    }

    private fun updateUI(data: AdapterListData?) {
        if (data == null) return

        adapterItems.clear()
        data.adapters.forEach { adapterInfo ->
            adapterItems.add(
                AdapterItem(
                    id = adapterInfo.adapterId,
                    name = adapterInfo.adapterType.replaceFirstChar { it.uppercase() },
                    type = adapterInfo.adapterType.uppercase(),
                    status = adapterInfo.status,
                    isHealthy = adapterInfo.status == "running"
                )
            )
        }
        adapter.notifyDataSetChanged()

        // Update counter
        adapterCountText.text = "${adapterItems.size} adapters"

        // Show/hide empty state
        emptyState.visibility = if (adapterItems.isEmpty()) View.VISIBLE else View.GONE
        recyclerView.visibility = if (adapterItems.isEmpty()) View.GONE else View.VISIBLE
    }

    private fun updateStatus(connected: Boolean) {
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

    private fun onReloadAdapter(adapterId: String) {
        AlertDialog.Builder(requireContext())
            .setTitle("Reload Adapter")
            .setMessage("Reload adapter $adapterId?")
            .setPositiveButton("Reload") { _, _ ->
                performReload(adapterId)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performReload(adapterId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/$adapterId/reload")
                    .put(okhttp3.RequestBody.create(null, ByteArray(0)))
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                    }
                    .build()

                val response = client.newCall(request).execute()
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        Toast.makeText(context, "Adapter reloaded", Toast.LENGTH_SHORT).show()
                        fetchAdapters()
                    } else {
                        Toast.makeText(context, "Failed to reload adapter", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error reloading adapter", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun onRemoveAdapter(adapterId: String) {
        AlertDialog.Builder(requireContext())
            .setTitle("Remove Adapter")
            .setMessage("Are you sure you want to remove adapter $adapterId?")
            .setPositiveButton("Remove") { _, _ ->
                performRemove(adapterId)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performRemove(adapterId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/$adapterId")
                    .delete()
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                    }
                    .build()

                val response = client.newCall(request).execute()
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        Toast.makeText(context, "Adapter removed", Toast.LENGTH_SHORT).show()
                        fetchAdapters()
                    } else {
                        Toast.makeText(context, "Failed to remove adapter", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error removing adapter", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}

// Data classes
data class AdapterItem(
    val id: String,
    val name: String,
    val type: String,
    val status: String,
    val isHealthy: Boolean
)

data class AdapterListResponse(
    val success: Boolean,
    val data: AdapterListData?
)

data class AdapterListData(
    val adapters: List<AdapterInfo>,
    @SerializedName("total_count") val totalCount: Int
)

data class AdapterInfo(
    @SerializedName("adapter_id") val adapterId: String,
    @SerializedName("adapter_type") val adapterType: String,
    val status: String,
    @SerializedName("channels_count") val channelsCount: Int
)

// RecyclerView Adapter
class AdapterListAdapter(
    private val items: List<AdapterItem>,
    private val onReload: (String) -> Unit,
    private val onRemove: (String) -> Unit
) : RecyclerView.Adapter<AdapterListAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val statusDot: View = view.findViewById(R.id.adapterStatusDot)
        val name: TextView = view.findViewById(R.id.adapterName)
        val type: TextView = view.findViewById(R.id.adapterType)
        val adapterId: TextView = view.findViewById(R.id.adapterId)
        val status: TextView = view.findViewById(R.id.adapterStatus)
        val reloadButton: View = view.findViewById(R.id.reloadButton)
        val removeButton: View = view.findViewById(R.id.removeButton)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_adapter, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]

        holder.name.text = item.name
        holder.type.text = item.type
        holder.adapterId.text = "ID: ${item.id}"
        holder.status.text = item.status.replaceFirstChar { it.uppercase() }

        if (item.isHealthy) {
            holder.statusDot.setBackgroundResource(R.drawable.status_dot_green)
            holder.status.setTextColor(holder.itemView.context.getColor(R.color.status_green))
        } else {
            holder.statusDot.setBackgroundResource(R.drawable.status_dot_red)
            holder.status.setTextColor(holder.itemView.context.getColor(R.color.status_red))
        }

        holder.reloadButton.setOnClickListener { onReload(item.id) }
        holder.removeButton.setOnClickListener { onRemove(item.id) }
    }

    override fun getItemCount() = items.size
}
