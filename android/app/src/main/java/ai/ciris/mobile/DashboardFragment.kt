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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit
import androidx.lifecycle.lifecycleScope

class DashboardFragment : Fragment() {

    private lateinit var textSystemStatus: TextView
    private lateinit var textVersion: TextView
    private lateinit var textUptime: TextView
    private lateinit var textCognitiveState: TextView
    private lateinit var recyclerServices: RecyclerView
    private lateinit var loadingIndicator: ProgressBar
    private lateinit var servicesAdapter: ServicesAdapter

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()
    private var accessToken: String? = null

    companion object {
        private const val TAG = "DashboardFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): DashboardFragment {
            return DashboardFragment().apply {
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
        return inflater.inflate(R.layout.fragment_dashboard, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)

        textSystemStatus = view.findViewById(R.id.textSystemStatus)
        textVersion = view.findViewById(R.id.textVersion)
        textUptime = view.findViewById(R.id.textUptime)
        textCognitiveState = view.findViewById(R.id.textCognitiveState)
        recyclerServices = view.findViewById(R.id.recyclerServices)
        loadingIndicator = view.findViewById(R.id.loadingIndicator)

        servicesAdapter = ServicesAdapter()
        recyclerServices.layoutManager = LinearLayoutManager(context)
        recyclerServices.adapter = servicesAdapter

        loadDashboardData()
    }

    private fun loadDashboardData() {
        loadingIndicator.visibility = View.VISIBLE
        // Use lifecycleScope which is bound to the fragment's view lifecycle
        // Launch on IO dispatcher for network operations
        viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            try {
                // Fetch Health
                val healthRequest = Request.Builder()
                    .url("$BASE_URL/v1/system/health")
                    .build()

                val healthResponse = client.newCall(healthRequest).execute()
                val healthBody = healthResponse.body?.string()

                // Fetch Services
                val servicesRequestBuilder = Request.Builder()
                    .url("$BASE_URL/v1/system/services")
                accessToken?.let { servicesRequestBuilder.addHeader("Authorization", "Bearer $it") }
                val servicesRequest = servicesRequestBuilder.build()

                val servicesResponse = client.newCall(servicesRequest).execute()
                val servicesBody = servicesResponse.body?.string()

                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        if (healthResponse.isSuccessful && healthBody != null) {
                            try {
                                val healthData = gson.fromJson(healthBody, SystemHealthResponse::class.java).data
                                updateHealthUI(healthData)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing health data", e)
                                setErrorStatus()
                            }
                        } else {
                            Log.e(TAG, "Health check failed: ${healthResponse.code}")
                            setErrorStatus()
                        }

                        if (servicesResponse.isSuccessful && servicesBody != null) {
                            try {
                                val servicesData = gson.fromJson(servicesBody, ServicesStatusResponse::class.java).data
                                servicesAdapter.setServices(servicesData.services)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing services data", e)
                            }
                        } else {
                            Log.e(TAG, "Services check failed: ${servicesResponse.code}")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error loading dashboard", e)
                withContext(Dispatchers.Main) {
                    if (isAdded) {
                        loadingIndicator.visibility = View.GONE
                        setErrorStatus()
                    }
                }
            }
        }
    }

    private fun setErrorStatus() {
        textSystemStatus.text = "Error"
        textSystemStatus.setTextColor(resources.getColor(android.R.color.holo_red_dark, null))
    }

    private fun updateHealthUI(data: SystemHealthData) {
        textSystemStatus.text = data.status.uppercase()
        val statusColor = when(data.status.lowercase()) {
            "healthy" -> try { resources.getColor(R.color.status_green, null) } catch (e: Exception) { 0xFF10B981.toInt() }
            "degraded" -> try { resources.getColor(R.color.status_yellow, null) } catch (e: Exception) { 0xFFFFCC00.toInt() }
            else -> try { resources.getColor(R.color.status_red, null) } catch (e: Exception) { 0xFFFF4444.toInt() }
        }
        textSystemStatus.setTextColor(statusColor)

        textVersion.text = data.version
        textUptime.text = formatUptime(data.uptime_seconds)
        textCognitiveState.text = data.cognitive_state ?: "UNKNOWN"
    }

    private fun formatUptime(seconds: Double): String {
        val s = seconds.toLong()
        val d = s / 86400
        val h = (s % 86400) / 3600
        val m = (s % 3600) / 60

        return if (d > 0) "${d}d ${h}h"
        else if (h > 0) "${h}h ${m}m"
        else "${m}m ${s%60}s"
    }

    data class SystemHealthResponse(val data: SystemHealthData)
    data class SystemHealthData(
        val status: String,
        val version: String,
        val uptime_seconds: Double,
        val initialization_complete: Boolean,
        val cognitive_state: String?
    )

    data class ServicesStatusResponse(val data: ServicesData)
    data class ServicesData(
        val services: List<ServiceStatus>,
        val total_services: Int,
        val healthy_services: Int
    )
    data class ServiceStatus(
        val name: String,
        val type: String,
        val healthy: Boolean
    )

    class ServicesAdapter : RecyclerView.Adapter<ServicesAdapter.ViewHolder>() {
        private var services: List<ServiceStatus> = emptyList()

        fun setServices(newServices: List<ServiceStatus>) {
            services = newServices
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_service_health, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val service = services[position]
            holder.name.text = service.name
            holder.status.text = if (service.healthy) "Healthy" else "Unhealthy"

            val color = if (service.healthy)
                try { holder.itemView.context.resources.getColor(R.color.status_green, null) } catch (e: Exception) { 0xFF10B981.toInt() }
            else
                try { holder.itemView.context.resources.getColor(R.color.status_red, null) } catch (e: Exception) { 0xFFFF4444.toInt() }

            holder.status.setTextColor(color)

            val dotDrawable = if (service.healthy) R.drawable.status_dot_green else R.drawable.status_dot_red
            holder.dot.setBackgroundResource(dotDrawable)
        }

        override fun getItemCount() = services.size

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val name: TextView = view.findViewById(R.id.serviceName)
            val status: TextView = view.findViewById(R.id.serviceStatus)
            val dot: View = view.findViewById(R.id.serviceDot)
        }
    }
}
