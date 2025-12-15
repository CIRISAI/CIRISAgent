package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit
import androidx.lifecycle.lifecycleScope

class AuditFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var auditCountText: TextView
    private lateinit var loadingIndicator: ProgressBar
    private lateinit var emptyState: TextView
    private lateinit var adapter: AuditAdapter

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()
    private var accessToken: String? = null

    companion object {
        private const val TAG = "AuditFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): AuditFragment {
            return AuditFragment().apply {
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
        return inflater.inflate(R.layout.fragment_audit, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)

        recyclerView = view.findViewById(R.id.auditRecyclerView)
        auditCountText = view.findViewById(R.id.auditCountText)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        emptyState = view.findViewById(R.id.emptyState)

        adapter = AuditAdapter()
        recyclerView.layoutManager = LinearLayoutManager(context)
        recyclerView.adapter = adapter

        fetchAuditLogs()
    }

    private fun fetchAuditLogs() {
        loadingIndicator.visibility = View.VISIBLE
        auditCountText.text = "Loading..."

        viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            try {
                val requestBuilder = Request.Builder()
                    .url("$BASE_URL/v1/audit/entries?limit=50")
                accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

                val request = requestBuilder.build()
                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        if (response.isSuccessful && body != null) {
                            try {
                                val auditResponse = gson.fromJson(body, AuditEntriesResponse::class.java)
                                updateUI(auditResponse.data.entries)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing audit data", e)
                                showErrorState()
                            }
                        } else {
                            Log.e(TAG, "Audit fetch failed: ${response.code}")
                            showErrorState()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching audit logs", e)
                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        showErrorState()
                    }
                }
            }
        }
    }

    private fun updateUI(entries: List<AuditEntry>) {
        if (entries.isEmpty()) {
            emptyState.visibility = View.VISIBLE
            recyclerView.visibility = View.GONE
            auditCountText.text = "0 entries found"
        } else {
            emptyState.visibility = View.GONE
            recyclerView.visibility = View.VISIBLE
            auditCountText.text = "${entries.size} entries found"
            adapter.setEntries(entries)
        }
    }

    private fun showErrorState() {
        auditCountText.text = "Error loading audit logs"
        emptyState.text = "Failed to load audit logs"
        emptyState.visibility = View.VISIBLE
    }

    data class AuditEntriesResponse(val data: AuditData)
    data class AuditData(val entries: List<AuditEntry>)
    data class AuditEntry(
        val id: String,
        val action: String,
        val actor: String,
        val timestamp: String,
        val context: AuditContext
    )
    data class AuditContext(
        val description: String?,
        val operation: String?
    )

    class AuditAdapter : RecyclerView.Adapter<AuditAdapter.ViewHolder>() {
        private var entries: List<AuditEntry> = emptyList()

        fun setEntries(newEntries: List<AuditEntry>) {
            entries = newEntries
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_audit_log, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val entry = entries[position]
            holder.action.text = entry.action.uppercase()
            holder.actor.text = entry.actor
            holder.timestamp.text = formatTimestamp(entry.timestamp)

            val description = entry.context.description ?: entry.context.operation ?: "No description"
            holder.description.text = description
        }

        private fun formatTimestamp(timestamp: String): String {
            return try {
                timestamp.replace("T", " ").substringBefore(".")
            } catch (e: Exception) {
                timestamp
            }
        }

        override fun getItemCount() = entries.size

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val action: TextView = view.findViewById(R.id.auditAction)
            val actor: TextView = view.findViewById(R.id.auditActor)
            val timestamp: TextView = view.findViewById(R.id.auditTimestamp)
            val description: TextView = view.findViewById(R.id.auditDescription)
        }
    }
}
