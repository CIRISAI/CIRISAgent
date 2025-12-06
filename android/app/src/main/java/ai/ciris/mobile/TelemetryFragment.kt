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
            // Fetch overview data
            val overviewRequest = Request.Builder()
                .url("$BASE_URL/v1/telemetry/overview")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val overviewResponse = client.newCall(overviewRequest).execute()
            val overviewBody = overviewResponse.body?.string()

            // Fetch runtime state (for cognitive state)
            val runtimeRequest = Request.Builder()
                .url("$BASE_URL/v1/system/runtime/state")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val runtimeResponse = client.newCall(runtimeRequest).execute()
            val runtimeBody = runtimeResponse.body?.string()

            // Fetch resources (for disk usage)
            val resourcesRequest = Request.Builder()
                .url("$BASE_URL/v1/system/resources")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val resourcesResponse = client.newCall(resourcesRequest).execute()
            val resourcesBody = resourcesResponse.body?.string()

            if (overviewResponse.isSuccessful && overviewBody != null) {
                Log.d(TAG, "Telemetry overview: $overviewBody")
                val overview = gson.fromJson(overviewBody, TelemetryOverviewWrapper::class.java)

                // Parse runtime state for cognitive state
                var cogState = overview.data.cognitiveState
                if (runtimeResponse.isSuccessful && runtimeBody != null) {
                    try {
                        Log.d(TAG, "Runtime state: $runtimeBody")
                        val runtime = gson.fromJson(runtimeBody, RuntimeStateWrapper::class.java)
                        if (runtime.data.cognitiveState.isNotEmpty() && runtime.data.cognitiveState != "UNKNOWN") {
                            cogState = runtime.data.cognitiveState
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to parse runtime state", e)
                    }
                }
                // Fall back to WORK if still UNKNOWN
                if (cogState == "UNKNOWN") {
                    cogState = "WORK"
                }

                // Parse resources for disk usage
                var diskUsedMb = 0.0
                if (resourcesResponse.isSuccessful && resourcesBody != null) {
                    try {
                        Log.d(TAG, "Resources: $resourcesBody")
                        val resources = gson.fromJson(resourcesBody, ResourcesWrapper::class.java)
                        diskUsedMb = resources.data.currentUsage.diskUsedMb
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to parse resources", e)
                    }
                }

                withContext(Dispatchers.Main) {
                    updateUI(overview.data, cogState, diskUsedMb)
                }
            } else {
                Log.w(TAG, "Failed to fetch telemetry: ${overviewResponse.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching telemetry", e)
        }
    }

    private fun updateUI(telemetry: SystemOverviewData, cogState: String, diskUsedMb: Double) {
        // Services overview
        val totalServices = telemetry.healthyServices + telemetry.degradedServices
        servicesOnline.text = "${telemetry.healthyServices}/$totalServices"
        servicesOnline.setTextColor(
            if (telemetry.degradedServices == 0)
                resources.getColor(R.color.status_green, null)
            else
                resources.getColor(R.color.status_yellow, null)
        )

        // Cognitive state - display properly formatted (from runtime state)
        val stateText = cogState.uppercase()
        cognitiveState.text = stateText
        // Color code the cognitive state
        val stateColor = when (stateText) {
            "WORK" -> resources.getColor(R.color.status_green, null)
            "PLAY" -> resources.getColor(R.color.status_blue, null)
            "SOLITUDE", "DREAM" -> resources.getColor(R.color.status_yellow, null)
            "WAKEUP", "SHUTDOWN" -> resources.getColor(R.color.status_orange, null)
            else -> resources.getColor(R.color.text_secondary, null)
        }
        cognitiveState.setTextColor(stateColor)

        // Resource usage - using the actual fields from SystemOverview
        val cpuPercent = telemetry.cpuPercent.toInt()
        cpuUsage.text = "$cpuPercent%"
        cpuProgress.progress = cpuPercent.coerceIn(0, 100)

        val memoryMb = telemetry.memoryMb.toInt()
        memoryUsage.text = "$memoryMb MB"
        // Assume 4GB max for progress bar (CIRIS targets 4GB RAM max)
        val memoryPercent = (memoryMb * 100 / 4096).coerceIn(0, 100)
        memoryProgress.progress = memoryPercent

        // Disk usage - from /system/resources endpoint
        val diskGb = diskUsedMb / 1024.0
        dbSize.text = if (diskGb >= 1.0) {
            String.format("%.1f GB", diskGb)
        } else {
            String.format("%.0f MB", diskUsedMb)
        }
        // Assume 10GB max for progress bar
        val diskPercent = ((diskUsedMb / 10240.0) * 100).toInt().coerceIn(0, 100)
        dbProgress.progress = diskPercent

        // Service health list - we don't have individual service info from overview
        // but we can show summary
        serviceItems.clear()
        // Add summary items based on healthy/degraded counts
        if (telemetry.healthyServices > 0) {
            serviceItems.add(
                ServiceHealthItem(
                    name = "Healthy Services",
                    healthy = true,
                    status = "${telemetry.healthyServices} services"
                )
            )
        }
        if (telemetry.degradedServices > 0) {
            serviceItems.add(
                ServiceHealthItem(
                    name = "Degraded Services",
                    healthy = false,
                    status = "${telemetry.degradedServices} services"
                )
            )
        }
        // Add activity metrics
        serviceItems.add(
            ServiceHealthItem(
                name = "Messages (24h)",
                healthy = true,
                status = "${telemetry.messagesProcessed24h}"
            )
        )
        serviceItems.add(
            ServiceHealthItem(
                name = "Tasks (24h)",
                healthy = true,
                status = "${telemetry.tasksCompleted24h}"
            )
        )
        if (telemetry.errors24h > 0) {
            serviceItems.add(
                ServiceHealthItem(
                    name = "Errors (24h)",
                    healthy = false,
                    status = "${telemetry.errors24h}"
                )
            )
        }
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

// Data classes - matches SystemOverview from /telemetry/overview

/**
 * Wrapper for SuccessResponse format from API.
 */
data class TelemetryOverviewWrapper(
    val data: SystemOverviewData,
    val metadata: ResponseMetadata?
)

data class ResponseMetadata(
    val timestamp: String?,
    @SerializedName("request_id") val requestId: String?,
    @SerializedName("duration_ms") val durationMs: Int?
)

/**
 * SystemOverview data from /telemetry/overview endpoint.
 * Matches ciris_engine.logic.adapters.api.routes.telemetry_models.SystemOverview
 */
data class SystemOverviewData(
    // Core metrics
    @SerializedName("uptime_seconds") val uptimeSeconds: Double = 0.0,
    @SerializedName("cognitive_state") val cognitiveState: String = "UNKNOWN",
    @SerializedName("messages_processed_24h") val messagesProcessed24h: Int = 0,
    @SerializedName("thoughts_processed_24h") val thoughtsProcessed24h: Int = 0,
    @SerializedName("tasks_completed_24h") val tasksCompleted24h: Int = 0,
    @SerializedName("errors_24h") val errors24h: Int = 0,

    // Resource usage
    @SerializedName("tokens_last_hour") val tokensLastHour: Double = 0.0,
    @SerializedName("cost_last_hour_cents") val costLastHourCents: Double = 0.0,
    @SerializedName("tokens_24h") val tokens24h: Double = 0.0,
    @SerializedName("cost_24h_cents") val cost24hCents: Double = 0.0,
    @SerializedName("memory_mb") val memoryMb: Double = 0.0,
    @SerializedName("cpu_percent") val cpuPercent: Double = 0.0,

    // Service health
    @SerializedName("healthy_services") val healthyServices: Int = 0,
    @SerializedName("degraded_services") val degradedServices: Int = 0,
    @SerializedName("error_rate_percent") val errorRatePercent: Double = 0.0,

    // Agent activity
    @SerializedName("current_task") val currentTask: String? = null,
    @SerializedName("reasoning_depth") val reasoningDepth: Int = 0,
    @SerializedName("active_deferrals") val activeDeferrals: Int = 0,
    @SerializedName("recent_incidents") val recentIncidents: Int = 0,

    // Telemetry metrics
    @SerializedName("total_metrics") val totalMetrics: Int = 0,
    @SerializedName("active_services") val activeServices: Int = 0,
    @SerializedName("metrics_per_second") val metricsPerSecond: Double = 0.0,
    @SerializedName("cache_hit_rate") val cacheHitRate: Double = 0.0
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

// Data classes for /system/runtime/state endpoint
data class RuntimeStateWrapper(
    val data: RuntimeStateData,
    val metadata: ResponseMetadata?
)

data class RuntimeStateData(
    @SerializedName("cognitive_state") val cognitiveState: String = "UNKNOWN",
    @SerializedName("processor_state") val processorState: String = "",
    @SerializedName("queue_depth") val queueDepth: Int = 0
)

// Data classes for /system/resources endpoint
data class ResourcesWrapper(
    val data: ResourcesData,
    val metadata: ResponseMetadata?
)

data class ResourcesData(
    @SerializedName("current_usage") val currentUsage: CurrentUsage = CurrentUsage()
)

data class CurrentUsage(
    @SerializedName("cpu_percent") val cpuPercent: Double = 0.0,
    @SerializedName("memory_mb") val memoryMb: Double = 0.0,
    @SerializedName("memory_percent") val memoryPercent: Double = 0.0,
    @SerializedName("disk_used_mb") val diskUsedMb: Double = 0.0
)
