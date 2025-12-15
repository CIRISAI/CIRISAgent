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

class ToolsFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var toolsCountText: TextView
    private lateinit var loadingIndicator: ProgressBar
    private lateinit var emptyState: TextView
    private lateinit var adapter: ToolsAdapter

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()
    private var accessToken: String? = null

    companion object {
        private const val TAG = "ToolsFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): ToolsFragment {
            return ToolsFragment().apply {
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
        return inflater.inflate(R.layout.fragment_tools, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)

        recyclerView = view.findViewById(R.id.toolsRecyclerView)
        toolsCountText = view.findViewById(R.id.toolsCountText)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        emptyState = view.findViewById(R.id.emptyState)

        adapter = ToolsAdapter()
        recyclerView.layoutManager = LinearLayoutManager(context)
        recyclerView.adapter = adapter

        fetchTools()
    }

    private fun fetchTools() {
        loadingIndicator.visibility = View.VISIBLE
        toolsCountText.text = "Loading..."

        viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            try {
                val requestBuilder = Request.Builder()
                    .url("$BASE_URL/v1/system/tools")
                accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

                val request = requestBuilder.build()
                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        if (response.isSuccessful && body != null) {
                            try {
                                val toolsResponse = gson.fromJson(body, ToolsResponse::class.java)
                                updateUI(toolsResponse.data)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing tools data", e)
                                showErrorState()
                            }
                        } else {
                            Log.e(TAG, "Tools fetch failed: ${response.code}")
                            showErrorState()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching tools", e)
                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        showErrorState()
                    }
                }
            }
        }
    }

    private fun updateUI(tools: List<ToolInfo>) {
        if (tools.isEmpty()) {
            emptyState.visibility = View.VISIBLE
            recyclerView.visibility = View.GONE
            toolsCountText.text = "0 tools available"
        } else {
            emptyState.visibility = View.GONE
            recyclerView.visibility = View.VISIBLE
            toolsCountText.text = "${tools.size} tools available"
            adapter.setTools(tools)
        }
    }

    private fun showErrorState() {
        toolsCountText.text = "Error loading tools"
        emptyState.text = "Failed to load tools"
        emptyState.visibility = View.VISIBLE
    }

    data class ToolsResponse(val data: List<ToolInfo>)
    data class ToolInfo(
        val name: String,
        val description: String,
        val provider: String,
        val category: String,
        val cost: Double?
    )

    class ToolsAdapter : RecyclerView.Adapter<ToolsAdapter.ViewHolder>() {
        private var tools: List<ToolInfo> = emptyList()

        fun setTools(newTools: List<ToolInfo>) {
            tools = newTools
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_tool, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val tool = tools[position]
            holder.name.text = tool.name
            holder.description.text = tool.description
            holder.provider.text = "Provider: ${tool.provider}"
            holder.category.text = tool.category.uppercase()
        }

        override fun getItemCount() = tools.size

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val name: TextView = view.findViewById(R.id.toolName)
            val description: TextView = view.findViewById(R.id.toolDescription)
            val provider: TextView = view.findViewById(R.id.toolProvider)
            val category: TextView = view.findViewById(R.id.toolCategory)
        }
    }
}
