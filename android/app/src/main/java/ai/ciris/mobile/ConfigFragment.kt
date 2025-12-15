package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit
import androidx.lifecycle.lifecycleScope

class ConfigFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var configCountText: TextView
    private lateinit var loadingIndicator: ProgressBar
    private lateinit var emptyState: TextView
    private lateinit var adapter: ConfigAdapter

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()
    private var accessToken: String? = null

    companion object {
        private const val TAG = "ConfigFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): ConfigFragment {
            return ConfigFragment().apply {
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
        return inflater.inflate(R.layout.fragment_config, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)

        recyclerView = view.findViewById(R.id.configRecyclerView)
        configCountText = view.findViewById(R.id.configCountText)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        emptyState = view.findViewById(R.id.emptyState)

        adapter = ConfigAdapter()
        recyclerView.layoutManager = LinearLayoutManager(context)
        recyclerView.adapter = adapter

        fetchConfigs()
    }

    private fun fetchConfigs() {
        loadingIndicator.visibility = View.VISIBLE
        configCountText.text = "Loading..."

        viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            try {
                val requestBuilder = Request.Builder()
                    .url("$BASE_URL/v1/config")
                accessToken?.let { requestBuilder.addHeader("Authorization", "Bearer $it") }

                val request = requestBuilder.build()
                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        if (response.isSuccessful && body != null) {
                            try {
                                val configResponse = gson.fromJson(body, ConfigListResponse::class.java)
                                updateUI(configResponse.data.configs)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing config data", e)
                                showErrorState()
                            }
                        } else {
                            Log.e(TAG, "Config fetch failed: ${response.code}")
                            showErrorState()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching configs", e)
                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        showErrorState()
                    }
                }
            }
        }
    }

    private fun updateUI(configs: List<ConfigItem>) {
        if (configs.isEmpty()) {
            emptyState.visibility = View.VISIBLE
            recyclerView.visibility = View.GONE
            configCountText.text = "0 entries found"
        } else {
            emptyState.visibility = View.GONE
            recyclerView.visibility = View.VISIBLE
            configCountText.text = "${configs.size} entries found"
            adapter.setConfigs(configs)
        }
    }

    private fun showErrorState() {
        configCountText.text = "Error loading config"
        emptyState.text = "Failed to load configuration"
        emptyState.visibility = View.VISIBLE
    }

    data class ConfigListResponse(val data: ConfigListData)
    data class ConfigListData(val configs: List<ConfigItem>)
    data class ConfigItem(
        val key: String,
        val value: ConfigValueWrapper,
        @SerializedName("updated_at") val updatedAt: String?,
        @SerializedName("updated_by") val updatedBy: String?,
        @SerializedName("is_sensitive") val isSensitive: Boolean
    )
    data class ConfigValueWrapper(
        @SerializedName("string_value") val stringValue: String?,
        @SerializedName("bool_value") val boolValue: Boolean?,
        @SerializedName("int_value") val intValue: Int?,
        @SerializedName("float_value") val floatValue: Double?,
        @SerializedName("list_value") val listValue: List<Any>?,
        @SerializedName("dict_value") val dictValue: Map<String, Any>?
    ) {
        override fun toString(): String {
            return when {
                stringValue != null -> "\"$stringValue\""
                boolValue != null -> boolValue.toString()
                intValue != null -> intValue.toString()
                floatValue != null -> floatValue.toString()
                listValue != null -> listValue.toString()
                dictValue != null -> dictValue.toString()
                else -> "null"
            }
        }
    }

    class ConfigAdapter : RecyclerView.Adapter<ConfigAdapter.ViewHolder>() {
        private var configs: List<ConfigItem> = emptyList()

        fun setConfigs(newConfigs: List<ConfigItem>) {
            configs = newConfigs
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_config, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = configs[position]
            holder.key.text = item.key
            holder.value.text = item.value.toString()
            holder.sensitiveIcon.visibility = if (item.isSensitive) View.VISIBLE else View.GONE

            val updatedText = if (item.updatedAt != null) {
                "Updated by ${item.updatedBy} at ${formatTimestamp(item.updatedAt)}"
            } else {
                "Default value"
            }
            holder.meta.text = updatedText
        }

        private fun formatTimestamp(timestamp: String): String {
            return try {
                timestamp.replace("T", " ").substringBefore(".")
            } catch (e: Exception) {
                timestamp
            }
        }

        override fun getItemCount() = configs.size

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val key: TextView = view.findViewById(R.id.configKey)
            val value: TextView = view.findViewById(R.id.configValue)
            val meta: TextView = view.findViewById(R.id.configMeta)
            val sensitiveIcon: ImageView = view.findViewById(R.id.sensitiveIcon)
        }
    }
}
