package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
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
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * TelemetryFragment - System Metrics & OTEL Export UI
 *
 * Displays system telemetry including service health, resource usage,
 * and provides OpenTelemetry export configuration.
 */
class TelemetryFragment : Fragment() {

    private lateinit var loadingIndicator: ProgressBar
    private lateinit var refreshButton: ImageButton
    private lateinit var servicesOnline: TextView
    private lateinit var cognitiveState: TextView
    private lateinit var cpuUsage: TextView
    private lateinit var cpuProgress: ProgressBar
    private lateinit var memoryUsage: TextView
    private lateinit var memoryProgress: ProgressBar
    private lateinit var dbSize: TextView
    private lateinit var dbProgress: ProgressBar
    private lateinit var otelStatusDot: View
    private lateinit var otelStatus: TextView
    private lateinit var otelEndpoint: EditText
    private lateinit var exportMetricsButton: Button
    private lateinit var exportTracesButton: Button
    private lateinit var exportLogsButton: Button
    private lateinit var servicesRecyclerView: RecyclerView

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val serviceItems = mutableListOf<ServiceHealthItem>()
    private lateinit var servicesAdapter: ServiceHealthAdapter
    private var accessToken: String? = null
    private var pollingJob: Job? = null

    companion object {
        private const val TAG = "TelemetryFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val POLL_INTERVAL_MS = 5000L
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): TelemetryFragment {
            return TelemetryFragment().apply {
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
        return inflater.inflate(R.layout.fragment_telemetry, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)
        Log.i(TAG, "TelemetryFragment started, hasToken=${accessToken != null}")

        // Bind views
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        refreshButton = view.findViewById(R.id.refreshButton)
        servicesOnline = view.findViewById(R.id.servicesOnline)
        cognitiveState = view.findViewById(R.id.cognitiveState)
        cpuUsage = view.findViewById(R.id.cpuUsage)
        cpuProgress = view.findViewById(R.id.cpuProgress)
        memoryUsage = view.findViewById(R.id.memoryUsage)
        memoryProgress = view.findViewById(R.id.memoryProgress)
        dbSize = view.findViewById(R.id.dbSize)
        dbProgress = view.findViewById(R.id.dbProgress)
        otelStatusDot = view.findViewById(R.id.otelStatusDot)
        otelStatus = view.findViewById(R.id.otelStatus)
        otelEndpoint = view.findViewById(R.id.otelEndpoint)
        exportMetricsButton = view.findViewById(R.id.exportMetricsButton)
        exportTracesButton = view.findViewById(R.id.exportTracesButton)
        exportLogsButton = view.findViewById(R.id.exportLogsButton)
        servicesRecyclerView = view.findViewById(R.id.servicesRecyclerView)

        // Setup services RecyclerView
        servicesAdapter = ServiceHealthAdapter(serviceItems)
        servicesRecyclerView.layoutManager = LinearLayoutManager(requireContext())
        servicesRecyclerView.adapter = servicesAdapter
        servicesRecyclerView.isNestedScrollingEnabled = false

        // Setup click listeners
        refreshButton.setOnClickListener { fetchTelemetry() }
        exportMetricsButton.setOnClickListener { exportOtel("metrics") }
        exportTracesButton.setOnClickListener { exportOtel("traces") }
        exportLogsButton.setOnClickListener { exportOtel("logs") }

        // Initial fetch
        fetchTelemetry()
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
                fetchTelemetryInternal()
            }
        }
    }

    private fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    private fun fetchTelemetry() {
        loadingIndicator.visibility = View.VISIBLE
        CoroutineScope(Dispatchers.IO).launch {
            fetchTelemetryInternal()
            withContext(Dispatchers.Main) {
                loadingIndicator.visibility = View.GONE
            }
        }
    }

    private suspend fun fetchTelemetryInternal() {
        try {
            val request = Request.Builder()
                .url("$BASE_URL/v1/telemetry/unified")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: return

            if (response.isSuccessful) {
                val telemetry = gson.fromJson(body, UnifiedTelemetryResponse::class.java)
                withContext(Dispatchers.Main) {
                    updateUI(telemetry)
                }
            } else {
                Log.w(TAG, "Failed to fetch telemetry: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching telemetry", e)
        }
    }

    private fun updateUI(telemetry: UnifiedTelemetryResponse) {
        // Services overview
        servicesOnline.text = "${telemetry.servicesOnline}/${telemetry.servicesTotal}"
        servicesOnline.setTextColor(
            if (telemetry.servicesOnline == telemetry.servicesTotal)
                resources.getColor(R.color.status_green, null)
            else
                resources.getColor(R.color.status_yellow, null)
        )

        // Cognitive state
        cognitiveState.text = telemetry.cognitiveState ?: "UNKNOWN"

        // Resource usage
        val cpuPercent = (telemetry.cpuPercent ?: 0.0).toInt()
        cpuUsage.text = "$cpuPercent%"
        cpuProgress.progress = cpuPercent

        val memoryMb = ((telemetry.memoryBytes ?: 0) / 1024 / 1024).toInt()
        val memoryPercent = ((telemetry.memoryPercent ?: 0.0) * 100).toInt()
        memoryUsage.text = "$memoryMb MB"
        memoryProgress.progress = memoryPercent.coerceIn(0, 100)

        val dbMb = ((telemetry.databaseBytes ?: 0) / 1024 / 1024).toInt()
        dbSize.text = "$dbMb MB"
        dbProgress.progress = (dbMb * 100 / 1024).coerceIn(0, 100) // Assuming 1GB max

        // Service health list
        serviceItems.clear()
        telemetry.services?.forEach { (name, info) ->
            serviceItems.add(
                ServiceHealthItem(
                    name = name,
                    healthy = info.healthy,
                    status = if (info.healthy) "Healthy" else "Unhealthy"
                )
            )
        }
        serviceItems.sortBy { it.name }
        servicesAdapter.notifyDataSetChanged()
    }

    private fun exportOtel(signal: String) {
        val endpoint = otelEndpoint.text.toString().trim()
        if (endpoint.isEmpty()) {
            Toast.makeText(context, "Please enter an OTLP endpoint", Toast.LENGTH_SHORT).show()
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Fetch OTLP data from CIRIS
                val request = Request.Builder()
                    .url("$BASE_URL/v1/telemetry/otlp/$signal")
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                if (response.isSuccessful && body != null) {
                    // Forward to OTLP endpoint
                    val otlpRequest = Request.Builder()
                        .url("$endpoint/v1/$signal")
                        .post(body.toRequestBody("application/json".toMediaType()))
                        .build()

                    val otlpResponse = client.newCall(otlpRequest).execute()

                    withContext(Dispatchers.Main) {
                        if (otlpResponse.isSuccessful) {
                            Toast.makeText(context, "Exported $signal successfully", Toast.LENGTH_SHORT).show()
                            updateOtelStatus(true)
                        } else {
                            Toast.makeText(context, "Export failed: ${otlpResponse.code}", Toast.LENGTH_SHORT).show()
                            updateOtelStatus(false)
                        }
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(context, "Failed to fetch $signal data", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error exporting $signal", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    updateOtelStatus(false)
                }
            }
        }
    }

    private fun updateOtelStatus(connected: Boolean) {
        if (connected) {
            otelStatusDot.setBackgroundResource(R.drawable.status_dot_green)
            otelStatus.text = "Connected"
        } else {
            otelStatusDot.setBackgroundResource(R.drawable.status_dot_red)
            otelStatus.text = "Disconnected"
        }
    }
}

// Data classes
data class UnifiedTelemetryResponse(
    @SerializedName("services_online") val servicesOnline: Int,
    @SerializedName("services_total") val servicesTotal: Int,
    @SerializedName("cognitive_state") val cognitiveState: String?,
    @SerializedName("cpu_percent") val cpuPercent: Double?,
    @SerializedName("memory_bytes") val memoryBytes: Long?,
    @SerializedName("memory_percent") val memoryPercent: Double?,
    @SerializedName("database_bytes") val databaseBytes: Long?,
    val services: Map<String, ServiceInfo>?
)

data class ServiceInfo(
    val healthy: Boolean,
    val status: String?
)

data class ServiceHealthItem(
    val name: String,
    val healthy: Boolean,
    val status: String
)

// RecyclerView Adapter for Service Health
class ServiceHealthAdapter(
    private val items: List<ServiceHealthItem>
) : RecyclerView.Adapter<ServiceHealthAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val dot: View = view.findViewById(R.id.serviceDot)
        val name: TextView = view.findViewById(R.id.serviceName)
        val status: TextView = view.findViewById(R.id.serviceStatus)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_service_health, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]

        holder.name.text = item.name
        holder.status.text = item.status

        if (item.healthy) {
            holder.dot.setBackgroundResource(R.drawable.status_dot_green)
            holder.status.setTextColor(holder.itemView.context.getColor(R.color.status_green))
        } else {
            holder.dot.setBackgroundResource(R.drawable.status_dot_red)
            holder.status.setTextColor(holder.itemView.context.getColor(R.color.status_red))
        }
    }

    override fun getItemCount() = items.size
}
