package ai.ciris.mobile

import android.os.Bundle
import android.text.InputType
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.floatingactionbutton.FloatingActionButton
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
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
 * AdaptersFragment - Adapter Management UI
 *
 * Displays a list of adapters (Discord, API, CLI, etc.) with their status
 * and provides options to reload, remove, or add new adapters.
 * Uses the /v1/system/adapters/types endpoint to dynamically display
 * available adapter types and their configuration fields.
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
    private lateinit var addAdapterFab: FloatingActionButton

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
    private var cachedModuleTypes: ModuleTypesData? = null
    private var cachedConfigurableAdapters: List<ConfigurableAdapterInfo> = emptyList()
    private var currentConfigSession: ConfigSessionData? = null

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
        addAdapterFab = view.findViewById(R.id.addAdapterFab)

        // Setup RecyclerView
        adapter = AdapterListAdapter(adapterItems, ::onReloadAdapter, ::onRemoveAdapter)
        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        // Refresh button
        refreshButton.setOnClickListener {
            fetchAdapters()
        }

        // Add adapter FAB - show menu with options
        addAdapterFab.setOnClickListener {
            showAdapterActionsMenu()
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
            // Determine status - use explicit status field or derive from is_running
            val statusText = adapterInfo.status
                ?: if (adapterInfo.isRunning == true) "running" else "stopped"
            val isHealthy = adapterInfo.isRunning == true || adapterInfo.status == "running"

            adapterItems.add(
                AdapterItem(
                    id = adapterInfo.adapterId,
                    name = adapterInfo.adapterType.replaceFirstChar { it.uppercase() },
                    type = adapterInfo.adapterType.uppercase(),
                    status = statusText,
                    isHealthy = isHealthy
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
                // Find the adapter to get its config for reload
                val adapterItem = adapterItems.find { it.id == adapterId }
                val reloadBody = mapOf(
                    "config" to mapOf(
                        "adapter_type" to (adapterItem?.type?.lowercase() ?: "unknown"),
                        "enabled" to true
                    ),
                    "auto_start" to true
                )
                val jsonBody = gson.toJson(reloadBody)
                    .toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/$adapterId/reload")
                    .put(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        // Parse response to check if reload succeeded
                        val result = try {
                            gson.fromJson(responseBody, GenericResponse::class.java)
                        } catch (e: Exception) { null }

                        if (result?.data?.success != false) {
                            Toast.makeText(context, "Adapter reloaded", Toast.LENGTH_SHORT).show()
                            fetchAdapters()
                        } else {
                            val error = result.data?.error ?: "Unknown error"
                            Toast.makeText(context, "Reload failed: $error", Toast.LENGTH_SHORT).show()
                        }
                    } else {
                        Toast.makeText(context, "Failed to reload adapter: ${response.code}", Toast.LENGTH_SHORT).show()
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

    // ===== Adapter Actions Menu =====

    private fun showAdapterActionsMenu() {
        val options = arrayOf(
            "Add Adapter (Manual)",
            "Configure Adapter (Wizard)"
        )

        AlertDialog.Builder(requireContext())
            .setTitle("Adapter Options")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showAddAdapterDialog()
                    1 -> showConfigureAdapterDialog()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ===== Add Adapter Functionality =====

    private fun showAddAdapterDialog() {
        // First fetch available module types
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val moduleTypes = fetchModuleTypes()
                withContext(Dispatchers.Main) {
                    if (moduleTypes != null) {
                        cachedModuleTypes = moduleTypes
                        showModuleTypeSelectionDialog(moduleTypes)
                    } else {
                        Toast.makeText(context, "Failed to load adapter types", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching module types", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private suspend fun fetchModuleTypes(): ModuleTypesData? {
        val request = Request.Builder()
            .url("$BASE_URL/v1/system/adapters/types")
            .apply {
                accessToken?.let { addHeader("Authorization", "Bearer $it") }
            }
            .build()

        val response = client.newCall(request).execute()
        val body = response.body?.string() ?: return null

        if (response.isSuccessful) {
            val typesResponse = gson.fromJson(body, ModuleTypesResponse::class.java)
            return typesResponse.data
        }
        return null
    }

    private fun showModuleTypeSelectionDialog(data: ModuleTypesData) {
        val allModules = data.coreModules + data.adapters
        if (allModules.isEmpty()) {
            Toast.makeText(context, "No adapter types available", Toast.LENGTH_SHORT).show()
            return
        }

        val moduleNames = allModules.map { module ->
            val source = if (module.moduleSource == "core") "[Core]" else "[Modular]"
            "$source ${module.name}"
        }.toTypedArray()

        AlertDialog.Builder(requireContext())
            .setTitle("Select Adapter Type")
            .setItems(moduleNames) { _, which ->
                val selectedModule = allModules[which]
                showConfigurationDialog(selectedModule)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showConfigurationDialog(module: ModuleTypeInfo) {
        val context = requireContext()
        val configParams = module.configurationSchema

        // Create a scrollable container for config fields
        val scrollView = ScrollView(context).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }

        val container = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 32, 48, 16)
        }
        scrollView.addView(container)

        // Add description
        val descText = TextView(context).apply {
            text = module.description
            setTextColor(resources.getColor(android.R.color.darker_gray, null))
            setPadding(0, 0, 0, 24)
        }
        container.addView(descText)

        // Track input fields for later retrieval
        val inputFields = mutableMapOf<String, TextInputEditText>()

        // Add external dependencies warning if needed
        if (module.requiresExternalDeps && module.externalDependencies.isNotEmpty()) {
            val depsWarning = TextView(context).apply {
                text = "Requires: ${module.externalDependencies.keys.joinToString(", ")}"
                setTextColor(resources.getColor(android.R.color.holo_orange_dark, null))
                setPadding(0, 0, 0, 16)
            }
            container.addView(depsWarning)
        }

        // Create input fields for each configuration parameter
        configParams.forEach { param ->
            val inputLayout = TextInputLayout(context).apply {
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = 16
                }
                hint = buildParamHint(param)
                boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            }

            val editText = TextInputEditText(context).apply {
                // Don't set layoutParams - TextInputLayout handles it internally
                // Set input type based on parameter type
                inputType = when (param.paramType) {
                    "integer", "float" -> InputType.TYPE_CLASS_NUMBER
                    "boolean" -> InputType.TYPE_CLASS_TEXT
                    else -> {
                        if (param.sensitivity == "HIGH") {
                            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                        } else {
                            InputType.TYPE_CLASS_TEXT
                        }
                    }
                }
                // Set default value if available
                param.default?.let { default ->
                    setText(default.toString())
                }
            }

            inputLayout.addView(editText)
            container.addView(inputLayout)
            inputFields[param.name] = editText
        }

        AlertDialog.Builder(context)
            .setTitle("Configure ${module.name}")
            .setView(scrollView)
            .setPositiveButton("Add") { _, _ ->
                submitAdapterConfig(module, inputFields)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun buildParamHint(param: ModuleConfigParameter): String {
        val builder = StringBuilder(param.name)
        if (param.required) {
            builder.append(" *")
        }
        param.envVar?.let {
            builder.append(" (env: $it)")
        }
        if (param.description.isNotEmpty()) {
            builder.append("\n${param.description}")
        }
        return builder.toString()
    }

    private fun submitAdapterConfig(module: ModuleTypeInfo, fields: Map<String, TextInputEditText>) {
        // Collect configuration values
        val settings = mutableMapOf<String, Any?>()
        var hasError = false

        module.configurationSchema.forEach { param ->
            val value = fields[param.name]?.text?.toString() ?: ""

            if (param.required && value.isEmpty()) {
                Toast.makeText(context, "${param.name} is required", Toast.LENGTH_SHORT).show()
                hasError = true
                return@forEach
            }

            if (value.isNotEmpty()) {
                // Convert to appropriate type
                val typedValue: Any? = when (param.paramType) {
                    "integer" -> value.toIntOrNull()
                    "float" -> value.toDoubleOrNull()
                    "boolean" -> value.lowercase() in listOf("true", "1", "yes")
                    else -> value
                }
                settings[param.name] = typedValue
            }
        }

        if (hasError) return

        // Generate a unique adapter ID
        val adapterId = "${module.moduleId}_${System.currentTimeMillis()}"

        // Submit to API
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Build config based on adapter type
                // MCP adapters need nested adapter_config, others use flat settings
                val config: Map<String, Any?> = if (module.moduleId in listOf("mcp", "mcp_server")) {
                    mapOf(
                        "adapter_type" to module.moduleId,
                        "enabled" to true,
                        "settings" to emptyMap<String, Any>(),  // Simple settings (flat primitives)
                        "adapter_config" to settings  // Complex nested config for MCP
                    )
                } else {
                    mapOf(
                        "adapter_type" to module.moduleId,
                        "enabled" to true,
                        "settings" to settings
                    )
                }

                val requestBody = mapOf(
                    "config" to config,
                    "auto_start" to true
                )
                val jsonBody = gson.toJson(requestBody)
                    .toRequestBody("application/json".toMediaType())

                // Include adapter_id as query parameter (per MCP tests pattern)
                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/${module.moduleId}?adapter_id=$adapterId")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        // Parse response to check if operation succeeded
                        val result = try {
                            gson.fromJson(responseBody, GenericResponse::class.java)
                        } catch (e: Exception) { null }

                        if (result?.data?.success != false) {
                            Toast.makeText(context, "Adapter added successfully", Toast.LENGTH_SHORT).show()
                            fetchAdapters()
                        } else {
                            val error = result.data?.error ?: result.data?.message ?: "Operation failed"
                            Toast.makeText(context, "Failed: $error", Toast.LENGTH_LONG).show()
                        }
                    } else {
                        val errorMsg = try {
                            gson.fromJson(responseBody, ErrorResponse::class.java).detail
                                ?: "Failed to add adapter"
                        } catch (e: Exception) {
                            "Failed to add adapter: ${response.code}"
                        }
                        Toast.makeText(context, errorMsg, Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error adding adapter", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    // ===== Dynamic Configuration Wizard =====

    private fun showConfigureAdapterDialog() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val adapters = fetchConfigurableAdapters()
                withContext(Dispatchers.Main) {
                    if (adapters.isNotEmpty()) {
                        cachedConfigurableAdapters = adapters
                        showConfigurableAdapterSelectionDialog(adapters)
                    } else {
                        Toast.makeText(context, "No configurable adapters available", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching configurable adapters", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private suspend fun fetchConfigurableAdapters(): List<ConfigurableAdapterInfo> {
        val request = Request.Builder()
            .url("$BASE_URL/v1/system/adapters/configurable")
            .apply {
                accessToken?.let { addHeader("Authorization", "Bearer $it") }
            }
            .build()

        val response = client.newCall(request).execute()
        val body = response.body?.string() ?: return emptyList()

        if (response.isSuccessful) {
            val configResponse = gson.fromJson(body, ConfigurableAdaptersResponse::class.java)
            return configResponse.data?.adapters ?: emptyList()
        }
        return emptyList()
    }

    private fun showConfigurableAdapterSelectionDialog(adapters: List<ConfigurableAdapterInfo>) {
        val adapterNames = adapters.map { "${it.name}\n${it.description}" }.toTypedArray()

        AlertDialog.Builder(requireContext())
            .setTitle("Configure Adapter")
            .setItems(adapterNames) { _, which ->
                val selectedAdapter = adapters[which]
                startConfigurationSession(selectedAdapter)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun startConfigurationSession(adapterInfo: ConfigurableAdapterInfo) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/${adapterInfo.adapterType}/configure/start")
                    .post("{}".toRequestBody("application/json".toMediaType()))
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && body != null) {
                        val sessionResponse = gson.fromJson(body, ConfigSessionResponse::class.java)
                        sessionResponse.data?.let { session ->
                            currentConfigSession = session
                            showConfigurationStep(adapterInfo, session, adapterInfo.steps[session.currentStep])
                        }
                    } else {
                        Toast.makeText(context, "Failed to start configuration", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error starting configuration session", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showConfigurationStep(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        Log.i(TAG, "Showing step: ${step.stepId} (${step.stepType})")

        when (step.stepType) {
            "discovery" -> executeDiscoveryStep(adapterInfo, session, step)
            "oauth" -> executeOAuthStep(adapterInfo, session, step)
            "select" -> executeSelectStep(adapterInfo, session, step)
            "input" -> showInputStepDialog(adapterInfo, session, step)
            "confirm" -> showConfirmStepDialog(adapterInfo, session, step)
            else -> {
                Toast.makeText(context, "Unknown step type: ${step.stepType}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun executeDiscoveryStep(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        // Show progress dialog
        val progressDialog = AlertDialog.Builder(context)
            .setTitle(step.title)
            .setMessage("${step.description}\n\nSearching...")
            .setCancelable(false)
            .create()
        progressDialog.show()

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf(
                    "step_type" to "discovery",
                    "discovery_type" to (step.discoveryMethod ?: "auto")
                )
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/step")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    progressDialog.dismiss()

                    if (response.isSuccessful && body != null) {
                        val stepResponse = gson.fromJson(body, StepExecutionResponse::class.java)
                        stepResponse.data?.let { result ->
                            val items = result.result?.discoveredItems ?: emptyList()
                            showDiscoveryResultsDialog(adapterInfo, session, step, items)
                        }
                    } else {
                        Toast.makeText(context, "Discovery failed", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error in discovery step", e)
                withContext(Dispatchers.Main) {
                    progressDialog.dismiss()
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showDiscoveryResultsDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo,
        items: List<DiscoveredItem>
    ) {
        val context = requireContext()

        if (items.isEmpty()) {
            // No items discovered - allow manual entry
            showManualUrlEntryDialog(adapterInfo, session)
            return
        }

        val itemLabels = (items.map { it.label } + listOf("Enter URL manually...")).toTypedArray()

        AlertDialog.Builder(context)
            .setTitle("Select ${adapterInfo.name}")
            .setItems(itemLabels) { _, which ->
                if (which < items.size) {
                    // Selected a discovered item
                    val selectedItem = items[which]
                    val url = selectedItem.metadata?.get("url") as? String
                        ?: selectedItem.metadata?.get("host")?.let { "http://$it:${selectedItem.metadata["port"]}" }

                    if (url != null) {
                        proceedToNextStep(adapterInfo, session, mapOf("base_url" to url, "selected_instance" to selectedItem.id))
                    }
                } else {
                    // Manual entry
                    showManualUrlEntryDialog(adapterInfo, session)
                }
            }
            .setNegativeButton("Cancel") { _, _ ->
                cancelConfigSession(session)
            }
            .show()
    }

    private fun showManualUrlEntryDialog(adapterInfo: ConfigurableAdapterInfo, session: ConfigSessionData) {
        val context = requireContext()
        val editText = EditText(context).apply {
            hint = "http://192.168.1.100:8123"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setPadding(48, 32, 48, 32)
        }

        AlertDialog.Builder(context)
            .setTitle("Enter ${adapterInfo.name} URL")
            .setView(editText)
            .setPositiveButton("Continue") { _, _ ->
                val url = editText.text.toString().trim()
                if (url.isNotEmpty()) {
                    proceedToNextStep(adapterInfo, session, mapOf("base_url" to url))
                }
            }
            .setNegativeButton("Cancel") { _, _ ->
                cancelConfigSession(session)
            }
            .show()
    }

    private fun executeOAuthStep(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf("step_type" to "oauth")
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/step")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && body != null) {
                        val stepResponse = gson.fromJson(body, StepExecutionResponse::class.java)
                        val oauthUrl = stepResponse.data?.result?.oauthUrl

                        if (oauthUrl != null) {
                            showOAuthDialog(adapterInfo, session, step, oauthUrl)
                        } else {
                            Toast.makeText(context, "Failed to get OAuth URL", Toast.LENGTH_SHORT).show()
                        }
                    } else {
                        Toast.makeText(context, "OAuth step failed", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error in OAuth step", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showOAuthDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo,
        oauthUrl: String
    ) {
        val context = requireContext()
        val providerName = step.oauthConfig?.providerName ?: adapterInfo.name

        AlertDialog.Builder(context)
            .setTitle("Sign in to $providerName")
            .setMessage("You will be redirected to sign in to $providerName.\n\nAfter signing in, return here to continue setup.")
            .setPositiveButton("Open Browser") { _, _ ->
                // Launch OAuth in browser
                try {
                    val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(oauthUrl))
                    startActivity(intent)

                    // Show waiting dialog
                    showOAuthWaitingDialog(adapterInfo, session, step)
                } catch (e: Exception) {
                    Toast.makeText(context, "Failed to open browser", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel") { _, _ ->
                cancelConfigSession(session)
            }
            .show()
    }

    private fun showOAuthWaitingDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        AlertDialog.Builder(context)
            .setTitle("Waiting for Authorization")
            .setMessage("After you've signed in, tap 'Check Status' to continue.")
            .setPositiveButton("Check Status") { _, _ ->
                checkOAuthCallback(adapterInfo, session, step)
            }
            .setNeutralButton("Re-open Browser") { _, _ ->
                // Re-execute OAuth step to get fresh URL
                executeOAuthStep(adapterInfo, session, step)
            }
            .setNegativeButton("Cancel") { _, _ ->
                cancelConfigSession(session)
            }
            .show()
    }

    private fun checkOAuthCallback(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        // Check session status to see if OAuth completed
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/status")
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && body != null) {
                        val statusResponse = gson.fromJson(body, ConfigSessionResponse::class.java)
                        statusResponse.data?.let { updatedSession ->
                            currentConfigSession = updatedSession

                            // Check if we've moved past OAuth step
                            val oauthStepIndex = adapterInfo.steps.indexOfFirst { it.stepType == "oauth" }
                            if (updatedSession.currentStep > oauthStepIndex) {
                                // OAuth completed, proceed to next step
                                val nextStep = adapterInfo.steps[updatedSession.currentStep]
                                showConfigurationStep(adapterInfo, updatedSession, nextStep)
                            } else {
                                // Still waiting for OAuth
                                showOAuthWaitingDialog(adapterInfo, updatedSession, step)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error checking OAuth status", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun executeSelectStep(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf(
                    "step_type" to "select",
                    "step_id" to step.stepId,
                    "get_options" to true
                )
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/step")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && body != null) {
                        val stepResponse = gson.fromJson(body, StepExecutionResponse::class.java)
                        val options = stepResponse.data?.result?.options ?: emptyList()
                        showSelectOptionsDialog(adapterInfo, session, step, options)
                    } else {
                        // If no options, skip to next step
                        proceedToNextStep(adapterInfo, session, emptyMap())
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error in select step", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showSelectOptionsDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo,
        options: List<ConfigOption>
    ) {
        val context = requireContext()

        if (options.isEmpty()) {
            // No options available, skip step
            if (step.optional) {
                proceedToNextStep(adapterInfo, session, emptyMap())
            } else {
                Toast.makeText(context, "No options available for ${step.title}", Toast.LENGTH_SHORT).show()
            }
            return
        }

        val optionLabels = options.map { it.label }.toTypedArray()
        val checkedItems = BooleanArray(options.size) { i ->
            (options[i].metadata?.get("default") as? Boolean) ?: false
        }

        AlertDialog.Builder(context)
            .setTitle(step.title)
            .setMultiChoiceItems(optionLabels, checkedItems) { _, which, isChecked ->
                checkedItems[which] = isChecked
            }
            .setPositiveButton("Continue") { _, _ ->
                val selectedOptions = options.filterIndexed { index, _ -> checkedItems[index] }
                val selectedIds = selectedOptions.map { it.id }
                proceedWithSelection(adapterInfo, session, step, selectedIds)
            }
            .setNegativeButton("Cancel") { _, _ ->
                if (step.optional) {
                    proceedToNextStep(adapterInfo, session, emptyMap())
                } else {
                    cancelConfigSession(session)
                }
            }
            .show()
    }

    private fun proceedWithSelection(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo,
        selectedIds: List<String>
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf(
                    "step_type" to "select",
                    "step_id" to step.stepId,
                    "selected" to selectedIds
                )
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/step")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && body != null) {
                        val stepResponse = gson.fromJson(body, StepExecutionResponse::class.java)
                        stepResponse.data?.let { result ->
                            if (result.success) {
                                val nextStepIndex = result.nextStep ?: (session.currentStep + 1)
                                if (nextStepIndex < adapterInfo.steps.size) {
                                    val updatedSession = session.copy(currentStep = nextStepIndex)
                                    currentConfigSession = updatedSession
                                    showConfigurationStep(adapterInfo, updatedSession, adapterInfo.steps[nextStepIndex])
                                } else {
                                    completeConfiguration(session)
                                }
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error submitting selection", e)
            }
        }
    }

    private fun showInputStepDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        // Simple input step - for now just show a continue button
        AlertDialog.Builder(context)
            .setTitle(step.title)
            .setMessage(step.description)
            .setPositiveButton("Continue") { _, _ ->
                proceedToNextStep(adapterInfo, session, emptyMap())
            }
            .setNegativeButton("Cancel") { _, _ ->
                cancelConfigSession(session)
            }
            .show()
    }

    private fun showConfirmStepDialog(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        step: ConfigurationStepInfo
    ) {
        val context = requireContext()

        // Execute confirm step to get config preview
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf(
                    "step_type" to "confirm",
                    "get_preview" to true
                )
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/step")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    val preview = if (response.isSuccessful && body != null) {
                        val stepResponse = gson.fromJson(body, StepExecutionResponse::class.java)
                        stepResponse.data?.result?.configPreview?.entries
                            ?.filter { !it.key.contains("token", ignoreCase = true) }
                            ?.joinToString("\n") { "${it.key}: ${it.value}" }
                            ?: "Configuration ready"
                    } else {
                        "Configuration ready"
                    }

                    AlertDialog.Builder(context)
                        .setTitle(step.title)
                        .setMessage("${step.description}\n\n$preview")
                        .setPositiveButton("Apply Configuration") { _, _ ->
                            completeConfiguration(session)
                        }
                        .setNeutralButton("Apply & Save") { _, _ ->
                            completeConfiguration(session, persist = true)
                        }
                        .setNegativeButton("Cancel") { _, _ ->
                            cancelConfigSession(session)
                        }
                        .show()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error in confirm step", e)
                withContext(Dispatchers.Main) {
                    // Fallback to simple confirm dialog
                    AlertDialog.Builder(context)
                        .setTitle(step.title)
                        .setMessage(step.description)
                        .setPositiveButton("Apply") { _, _ ->
                            completeConfiguration(session)
                        }
                        .setNegativeButton("Cancel") { _, _ ->
                            cancelConfigSession(session)
                        }
                        .show()
                }
            }
        }
    }

    private fun proceedToNextStep(
        adapterInfo: ConfigurableAdapterInfo,
        session: ConfigSessionData,
        context: Map<String, Any>
    ) {
        val nextStepIndex = session.currentStep + 1
        if (nextStepIndex < adapterInfo.steps.size) {
            val updatedSession = session.copy(currentStep = nextStepIndex, context = session.context?.plus(context))
            currentConfigSession = updatedSession
            showConfigurationStep(adapterInfo, updatedSession, adapterInfo.steps[nextStepIndex])
        } else {
            completeConfiguration(session)
        }
    }

    private fun completeConfiguration(session: ConfigSessionData, persist: Boolean = false) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val requestBody = mapOf("persist" to persist)
                val jsonBody = gson.toJson(requestBody).toRequestBody("application/json".toMediaType())

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/adapters/configure/${session.sessionId}/complete")
                    .post(jsonBody)
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                        addHeader("Content-Type", "application/json")
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        val persistMsg = if (persist) " (saved for startup)" else ""
                        Toast.makeText(context, "Adapter configured successfully$persistMsg", Toast.LENGTH_SHORT).show()
                        currentConfigSession = null
                        fetchAdapters()
                    } else {
                        val error = try {
                            gson.fromJson(body, ErrorResponse::class.java).detail
                        } catch (e: Exception) { "Configuration failed" }
                        Toast.makeText(context, error, Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error completing configuration", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun cancelConfigSession(session: ConfigSessionData) {
        // Just clear local state - sessions expire automatically
        currentConfigSession = null
        Toast.makeText(context, "Configuration cancelled", Toast.LENGTH_SHORT).show()
    }
}

// Data classes for existing adapter list
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
    @SerializedName("adapter_id") val adapterId: String = "",
    @SerializedName("adapter_type") val adapterType: String = "",
    val status: String? = null,
    @SerializedName("is_running") val isRunning: Boolean? = null,
    @SerializedName("channels_count") val channelsCount: Int = 0,
    @SerializedName("services_registered") val servicesRegistered: List<String> = emptyList()
)

// Data classes for module types API
// Note: API returns SuccessResponse format with just data (no success field at top level)
data class ModuleTypesResponse(
    val data: ModuleTypesData?
)

data class ModuleTypesData(
    @SerializedName("core_modules") val coreModules: List<ModuleTypeInfo>,
    @SerializedName("adapters") val adapters: List<ModuleTypeInfo>,
    @SerializedName("total_core") val totalCore: Int,
    @SerializedName("total_adapters") val totalAdapters: Int
)

data class ModuleTypeInfo(
    @SerializedName("module_id") val moduleId: String,
    val name: String,
    val version: String,
    val description: String,
    val author: String,
    @SerializedName("module_source") val moduleSource: String,
    @SerializedName("service_types") val serviceTypes: List<String> = emptyList(),
    val capabilities: List<String> = emptyList(),
    @SerializedName("configuration_schema") val configurationSchema: List<ModuleConfigParameter> = emptyList(),
    @SerializedName("requires_external_deps") val requiresExternalDeps: Boolean = false,
    @SerializedName("external_dependencies") val externalDependencies: Map<String, String> = emptyMap(),
    @SerializedName("is_mock") val isMock: Boolean = false,
    @SerializedName("safe_domain") val safeDomain: String? = null,
    val prohibited: List<String> = emptyList(),
    val metadata: Map<String, Any>? = null
)

data class ModuleConfigParameter(
    val name: String,
    @SerializedName("param_type") val paramType: String,
    val default: Any? = null,
    val description: String = "",
    @SerializedName("env_var") val envVar: String? = null,
    val required: Boolean = true,
    val sensitivity: String? = null
)

data class ErrorResponse(
    val detail: String?
)

// Generic response for adapter operations (matches MCP tests response format)
data class GenericResponse(
    val success: Boolean? = null,
    val data: AdapterOperationResult? = null
)

data class AdapterOperationResult(
    val success: Boolean? = null,
    @SerializedName("adapter_id") val adapterId: String? = null,
    val error: String? = null,
    val message: String? = null,
    @SerializedName("is_running") val isRunning: Boolean? = null
)

// ===== Dynamic Configuration Data Classes =====

data class ConfigurableAdaptersResponse(
    val data: ConfigurableAdaptersData?
)

data class ConfigurableAdaptersData(
    val adapters: List<ConfigurableAdapterInfo>,
    @SerializedName("total_count") val totalCount: Int
)

data class ConfigurableAdapterInfo(
    @SerializedName("adapter_type") val adapterType: String,
    val name: String,
    val description: String,
    @SerializedName("workflow_type") val workflowType: String,
    val steps: List<ConfigurationStepInfo>
)

data class ConfigurationStepInfo(
    @SerializedName("step_id") val stepId: String,
    @SerializedName("step_type") val stepType: String,
    val title: String,
    val description: String,
    @SerializedName("discovery_method") val discoveryMethod: String? = null,
    @SerializedName("oauth_config") val oauthConfig: OAuthConfigInfo? = null,
    @SerializedName("depends_on") val dependsOn: List<String> = emptyList(),
    val optional: Boolean = false
)

data class OAuthConfigInfo(
    @SerializedName("provider_name") val providerName: String,
    @SerializedName("authorization_path") val authorizationPath: String,
    @SerializedName("token_path") val tokenPath: String,
    @SerializedName("client_id_source") val clientIdSource: String,
    val scopes: List<String> = emptyList(),
    @SerializedName("pkce_required") val pkceRequired: Boolean = true
)

data class ConfigSessionResponse(
    val data: ConfigSessionData?
)

data class ConfigSessionData(
    @SerializedName("session_id") val sessionId: String,
    val status: String,
    @SerializedName("adapter_type") val adapterType: String,
    @SerializedName("current_step") val currentStep: Int,
    @SerializedName("steps_completed") val stepsCompleted: List<String> = emptyList(),
    val context: Map<String, Any>? = null
)

data class StepExecutionResponse(
    val data: StepExecutionData?
)

data class StepExecutionData(
    val success: Boolean,
    @SerializedName("step_id") val stepId: String? = null,
    @SerializedName("step_type") val stepType: String? = null,
    val result: StepResult? = null,
    @SerializedName("next_step") val nextStep: Int? = null,
    val message: String? = null
)

data class StepResult(
    @SerializedName("discovered_items") val discoveredItems: List<DiscoveredItem>? = null,
    @SerializedName("oauth_url") val oauthUrl: String? = null,
    val options: List<ConfigOption>? = null,
    @SerializedName("config_preview") val configPreview: Map<String, Any>? = null
)

data class DiscoveredItem(
    val id: String,
    val label: String,
    val description: String,
    val metadata: Map<String, Any>? = null
)

data class ConfigOption(
    val id: String,
    val label: String,
    val description: String,
    val metadata: Map<String, Any>? = null
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
