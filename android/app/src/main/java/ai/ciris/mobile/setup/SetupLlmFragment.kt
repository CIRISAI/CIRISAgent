package ai.ciris.mobile.setup

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import ai.ciris.mobile.R
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * LLM Configuration Fragment for Setup Wizard.
 *
 * For Google OAuth users:
 * - Shows "Free AI Access Ready" card with CIRIS proxy option
 * - Advanced link to switch to BYOK mode
 *
 * For non-Google users:
 * - Shows BYOK provider selection directly
 *
 * Features:
 * - Model selection with CIRIS compatibility indicators
 * - Test Connection validation button
 */
class SetupLlmFragment : Fragment() {

    companion object {
        private const val TAG = "SetupLlmFragment"
        private const val SERVER_URL = "http://localhost:8080"
    }

    private lateinit var viewModel: SetupViewModel

    // Views
    private lateinit var descText: TextView
    private lateinit var cardCirisProxy: LinearLayout
    private lateinit var textAdvancedOption: TextView
    private lateinit var cardByokMode: LinearLayout
    private lateinit var btnUseFreeAi: Button
    private lateinit var sectionByok: LinearLayout
    private lateinit var apiKeyInput: EditText
    private lateinit var providerSpinner: Spinner
    private lateinit var modelSpinner: Spinner
    private lateinit var btnTestConnection: Button
    private lateinit var textConnectionStatus: TextView

    // Model data
    private data class ModelInfo(
        val id: String,
        val displayName: String,
        val isCompatible: Boolean,
        val isRecommended: Boolean
    )
    private var currentModels: List<ModelInfo> = emptyList()
    private var isLoadingModels = false

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        Log.i(TAG, "onCreateView: Inflating fragment_setup_llm")
        return inflater.inflate(R.layout.fragment_setup_llm, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        Log.i(TAG, "onViewCreated: Setting up views")

        viewModel = ViewModelProvider(requireActivity()).get(SetupViewModel::class.java)

        // Find views
        descText = view.findViewById(R.id.text_llm_desc)
        cardCirisProxy = view.findViewById(R.id.card_ciris_proxy)
        textAdvancedOption = view.findViewById(R.id.text_advanced_option)
        cardByokMode = view.findViewById(R.id.card_byok_mode)
        btnUseFreeAi = view.findViewById(R.id.btn_use_free_ai)
        sectionByok = view.findViewById(R.id.section_byok)
        apiKeyInput = view.findViewById(R.id.edit_api_key)
        providerSpinner = view.findViewById(R.id.spinner_provider)
        modelSpinner = view.findViewById(R.id.spinner_model)
        btnTestConnection = view.findViewById(R.id.btn_test_connection)
        textConnectionStatus = view.findViewById(R.id.text_connection_status)

        // Setup provider spinner
        setupProviderSpinner()

        // Setup model spinner
        setupModelSpinner()

        // Setup click listeners
        setupClickListeners()

        // Setup test connection button
        setupTestConnection()

        // Observe LLM mode changes
        viewModel.llmMode.observe(viewLifecycleOwner) { mode ->
            Log.i(TAG, "llmMode changed to: $mode")
            updateUIForMode(mode)
        }

        // Observe Google auth state
        viewModel.isGoogleAuth.observe(viewLifecycleOwner) { isGoogle ->
            Log.i(TAG, "isGoogleAuth changed to: $isGoogle")
            updateUIForGoogleAuth(isGoogle)
        }

        // Restore state
        restoreState()

        // Log initial state
        viewModel.logCurrentState()
    }

    private fun setupProviderSpinner() {
        Log.i(TAG, "setupProviderSpinner: Setting up provider dropdown with custom layouts")
        val providers = arrayOf("OpenAI", "Anthropic", "Azure OpenAI", "LocalAI")
        // Use custom spinner layouts with dark text color
        val adapter = ArrayAdapter(requireContext(), R.layout.spinner_item, providers)
        adapter.setDropDownViewResource(R.layout.spinner_dropdown_item)
        providerSpinner.adapter = adapter

        providerSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, position: Int, id: Long) {
                val provider = providers[position]
                Log.d(TAG, "Provider selected: $provider")
                viewModel.setLlmProvider(provider)
                // Reset connection status when provider changes
                textConnectionStatus.visibility = View.GONE
                // Load models for this provider
                loadProviderModels(provider)
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }

        apiKeyInput.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setLlmApiKey(s.toString())
                // Reset connection status when API key changes
                textConnectionStatus.visibility = View.GONE
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })
    }

    private fun setupModelSpinner() {
        Log.d(TAG, "setupModelSpinner: Setting up model dropdown")
        // Initial empty state
        updateModelSpinner(emptyList())

        modelSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, position: Int, id: Long) {
                if (currentModels.isNotEmpty() && position < currentModels.size) {
                    val model = currentModels[position]
                    Log.d(TAG, "Model selected: ${model.id}")
                    viewModel.setLlmModel(model.id)
                    // Reset connection status when model changes
                    textConnectionStatus.visibility = View.GONE
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }
    }

    private fun setupTestConnection() {
        btnTestConnection.setOnClickListener {
            validateLLMConnection()
        }
    }

    /**
     * Load available models for the selected provider from the backend.
     */
    private fun loadProviderModels(providerName: String) {
        if (isLoadingModels) return
        isLoadingModels = true

        val providerId = when (providerName) {
            "OpenAI" -> "openai"
            "Anthropic" -> "anthropic"
            "Azure OpenAI" -> "other"
            "LocalAI" -> "local"
            else -> "openai"
        }

        Log.d(TAG, "loadProviderModels: Loading models for $providerId")

        // Show loading state
        updateModelSpinner(listOf(ModelInfo("loading", getString(R.string.setup_loading_models), true, false)))

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val url = URL("$SERVER_URL/v1/setup/providers/$providerId/models")
                Log.d(TAG, "Fetching models from: $url")

                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.connectTimeout = 5000
                conn.readTimeout = 5000

                val responseCode = conn.responseCode
                Log.d(TAG, "Models response code: $responseCode")

                if (responseCode == 200) {
                    val response = conn.inputStream.bufferedReader().use { it.readText() }
                    val json = JSONObject(response)

                    val models = mutableListOf<ModelInfo>()

                    // Parse compatible models
                    val compatibleArray = json.optJSONArray("compatible_models") ?: JSONArray()
                    for (i in 0 until compatibleArray.length()) {
                        val m = compatibleArray.getJSONObject(i)
                        val id = m.getString("id")
                        val displayName = m.optString("display_name", id)
                        val isRecommended = m.optBoolean("ciris_recommended", false)
                        val prefix = if (isRecommended) "⭐ " else "✅ "
                        models.add(ModelInfo(id, "$prefix$displayName", true, isRecommended))
                    }

                    // Parse incompatible models
                    val incompatibleArray = json.optJSONArray("incompatible_models") ?: JSONArray()
                    for (i in 0 until incompatibleArray.length()) {
                        val m = incompatibleArray.getJSONObject(i)
                        val id = m.getString("id")
                        val displayName = m.optString("display_name", id)
                        models.add(ModelInfo(id, "⚠️ $displayName", false, false))
                    }

                    withContext(Dispatchers.Main) {
                        currentModels = models
                        updateModelSpinner(models)
                        // Auto-select first recommended or compatible model
                        val recommended = models.indexOfFirst { it.isRecommended }
                        val firstCompatible = models.indexOfFirst { it.isCompatible }
                        val selectIndex = if (recommended >= 0) recommended else if (firstCompatible >= 0) firstCompatible else 0
                        if (selectIndex >= 0 && selectIndex < models.size) {
                            modelSpinner.setSelection(selectIndex)
                            viewModel.setLlmModel(models[selectIndex].id)
                        }
                    }
                } else {
                    Log.w(TAG, "Failed to load models: $responseCode")
                    withContext(Dispatchers.Main) {
                        // Fall back to default models for the provider
                        val defaultModels = getDefaultModels(providerName)
                        currentModels = defaultModels
                        updateModelSpinner(defaultModels)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error loading models: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    // Fall back to default models
                    val defaultModels = getDefaultModels(providerName)
                    currentModels = defaultModels
                    updateModelSpinner(defaultModels)
                }
            } finally {
                isLoadingModels = false
            }
        }
    }

    /**
     * Get default models when backend is not available.
     */
    private fun getDefaultModels(providerName: String): List<ModelInfo> {
        return when (providerName) {
            "OpenAI" -> listOf(
                ModelInfo("gpt-4o", "⭐ GPT-4o (Recommended)", true, true),
                ModelInfo("gpt-4o-mini", "✅ GPT-4o Mini", true, false),
                ModelInfo("gpt-4-turbo", "✅ GPT-4 Turbo", true, false),
                ModelInfo("gpt-3.5-turbo", "⚠️ GPT-3.5 Turbo", false, false)
            )
            "Anthropic" -> listOf(
                ModelInfo("claude-sonnet-4-20250514", "⭐ Claude Sonnet 4 (Recommended)", true, true),
                ModelInfo("claude-3-5-sonnet-20241022", "✅ Claude 3.5 Sonnet", true, false),
                ModelInfo("claude-3-5-haiku-20241022", "✅ Claude 3.5 Haiku", true, false),
                ModelInfo("claude-3-opus-20240229", "✅ Claude 3 Opus", true, false)
            )
            "LocalAI" -> listOf(
                ModelInfo("default", "✅ Default Model", true, true)
            )
            else -> listOf(
                ModelInfo("default", "✅ Default Model", true, true)
            )
        }
    }

    /**
     * Update the model spinner with the given models.
     */
    private fun updateModelSpinner(models: List<ModelInfo>) {
        Log.i(TAG, "updateModelSpinner: Updating with ${models.size} models")
        val displayNames = models.map { it.displayName }.toTypedArray()
        // Use custom spinner layouts with dark text color
        val adapter = ArrayAdapter(requireContext(), R.layout.spinner_item, displayNames)
        adapter.setDropDownViewResource(R.layout.spinner_dropdown_item)
        modelSpinner.adapter = adapter
    }

    /**
     * Validate the LLM configuration by testing the connection.
     */
    private fun validateLLMConnection() {
        val provider = viewModel.llmProvider.value ?: "OpenAI"
        val apiKey = viewModel.llmApiKey.value ?: ""
        val model = viewModel.llmModel.value ?: ""

        Log.i(TAG, "========== validateLLMConnection START ==========")
        Log.i(TAG, "  provider: $provider")
        Log.i(TAG, "  model: $model")
        Log.i(TAG, "  apiKey length: ${apiKey.length}")
        Log.i(TAG, "  apiKey prefix: ${apiKey.take(10)}...")

        // Skip validation for LocalAI (doesn't require API key)
        if (provider == "LocalAI") {
            Log.i(TAG, "LocalAI provider - skipping validation, marking as connected")
            textConnectionStatus.text = getString(R.string.setup_connected)
            textConnectionStatus.setTextColor(requireContext().getColor(R.color.success))
            textConnectionStatus.visibility = View.VISIBLE
            return
        }

        if (apiKey.isEmpty()) {
            Log.w(TAG, "API key is empty - cannot validate")
            Toast.makeText(requireContext(), "API key is required", Toast.LENGTH_SHORT).show()
            return
        }

        // Show testing state
        btnTestConnection.isEnabled = false
        btnTestConnection.text = getString(R.string.setup_testing)
        textConnectionStatus.visibility = View.GONE

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val url = URL("$SERVER_URL/v1/setup/validate-llm")
                Log.i(TAG, "Connecting to: $url")

                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                conn.connectTimeout = 30000  // 30s timeout for LLM validation
                conn.readTimeout = 30000

                val providerId = when (provider) {
                    "OpenAI" -> "openai"
                    "Anthropic" -> "anthropic"
                    "Azure OpenAI" -> "other"
                    "LocalAI" -> "local"
                    else -> "openai"
                }

                val payload = JSONObject().apply {
                    put("provider", providerId)
                    put("api_key", apiKey)
                    if (model.isNotEmpty()) put("model", model)
                }

                Log.i(TAG, "Request payload: provider=$providerId, model=$model, apiKey=<redacted ${apiKey.length} chars>")
                conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }

                val responseCode = conn.responseCode
                Log.i(TAG, "Response code: $responseCode")

                val response = if (responseCode == 200) {
                    conn.inputStream.bufferedReader().use { it.readText() }
                } else {
                    conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "(no error stream)"
                }

                Log.i(TAG, "Response body: $response")

                // The response is wrapped in a SuccessResponse: {"data": {...}}
                val json = JSONObject(response)

                // Check if response is wrapped in "data" field (SuccessResponse)
                val dataJson = if (json.has("data")) {
                    Log.i(TAG, "Response is wrapped in SuccessResponse, extracting data field")
                    json.getJSONObject("data")
                } else {
                    Log.i(TAG, "Response is not wrapped, using directly")
                    json
                }

                val valid = dataJson.optBoolean("valid", false)
                val message = dataJson.optString("message", "")
                val error = dataJson.optString("error", "")

                Log.i(TAG, "Parsed response: valid=$valid, message=$message, error=$error")

                withContext(Dispatchers.Main) {
                    btnTestConnection.isEnabled = true
                    btnTestConnection.text = getString(R.string.setup_test_connection)

                    if (valid) {
                        Log.i(TAG, "Validation SUCCESS")
                        textConnectionStatus.text = getString(R.string.setup_connected)
                        textConnectionStatus.setTextColor(requireContext().getColor(R.color.success))
                        Toast.makeText(requireContext(), message.ifEmpty { "Connection successful!" }, Toast.LENGTH_SHORT).show()
                    } else {
                        Log.w(TAG, "Validation FAILED: $error")
                        textConnectionStatus.text = getString(R.string.setup_connection_failed)
                        textConnectionStatus.setTextColor(requireContext().getColor(R.color.error))
                        Toast.makeText(requireContext(), error.ifEmpty { "Connection failed" }, Toast.LENGTH_LONG).show()
                    }
                    textConnectionStatus.visibility = View.VISIBLE
                }
            } catch (e: Exception) {
                Log.e(TAG, "========== Validation EXCEPTION ==========")
                Log.e(TAG, "Exception type: ${e.javaClass.simpleName}")
                Log.e(TAG, "Exception message: ${e.message}")
                Log.e(TAG, "Stack trace:", e)
                withContext(Dispatchers.Main) {
                    btnTestConnection.isEnabled = true
                    btnTestConnection.text = getString(R.string.setup_test_connection)
                    textConnectionStatus.text = getString(R.string.setup_connection_failed)
                    textConnectionStatus.setTextColor(requireContext().getColor(R.color.error))
                    textConnectionStatus.visibility = View.VISIBLE
                    Toast.makeText(requireContext(), "Error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
            Log.i(TAG, "========== validateLLMConnection END ==========")
        }
    }

    private fun setupClickListeners() {
        // "I have my own AI provider (Advanced)" link
        textAdvancedOption.setOnClickListener {
            Log.i(TAG, "User clicked Advanced option - switching to BYOK mode")
            viewModel.setLlmMode(SetupViewModel.LlmMode.BYOK)
        }

        // "Use Free AI" button in BYOK mode header
        btnUseFreeAi.setOnClickListener {
            Log.i(TAG, "User clicked Use Free AI - switching back to CIRIS_PROXY mode")
            viewModel.setLlmMode(SetupViewModel.LlmMode.CIRIS_PROXY)
        }
    }

    private fun restoreState() {
        Log.d(TAG, "restoreState: Restoring previous selections")

        // Restore provider selection
        val providers = arrayOf("OpenAI", "Anthropic", "Azure OpenAI", "LocalAI")
        viewModel.llmProvider.value?.let { provider ->
            val position = providers.indexOf(provider)
            if (position >= 0) {
                Log.d(TAG, "Restoring provider: $provider at position $position")
                providerSpinner.setSelection(position)
            }
        }

        // Restore API key
        viewModel.llmApiKey.value?.let { key ->
            if (key.isNotEmpty()) {
                Log.d(TAG, "Restoring API key (length=${key.length})")
                apiKeyInput.setText(key)
            }
        }
    }

    private fun updateUIForGoogleAuth(isGoogle: Boolean) {
        Log.i(TAG, "updateUIForGoogleAuth: isGoogle=$isGoogle")

        if (isGoogle) {
            // Google user - show CIRIS proxy option by default
            Log.i(TAG, "Google user detected - showing CIRIS proxy card")
            cardCirisProxy.visibility = View.VISIBLE
            textAdvancedOption.visibility = View.VISIBLE
            descText.text = getString(R.string.setup_llm_desc)

            // If no mode selected yet, default to CIRIS proxy
            if (viewModel.llmMode.value == null) {
                Log.i(TAG, "No mode selected, defaulting to CIRIS_PROXY")
                viewModel.setLlmMode(SetupViewModel.LlmMode.CIRIS_PROXY)
            }
        } else {
            // Non-Google user - force BYOK mode
            Log.i(TAG, "Non-Google user - forcing BYOK mode")
            cardCirisProxy.visibility = View.GONE
            textAdvancedOption.visibility = View.GONE
            viewModel.setLlmMode(SetupViewModel.LlmMode.BYOK)
        }
    }

    private fun updateUIForMode(mode: SetupViewModel.LlmMode?) {
        Log.i(TAG, "updateUIForMode: mode=$mode")

        when (mode) {
            SetupViewModel.LlmMode.CIRIS_PROXY -> {
                Log.i(TAG, "Showing CIRIS Proxy UI")
                // Show CIRIS proxy card, hide BYOK
                cardCirisProxy.visibility = View.VISIBLE
                textAdvancedOption.visibility = View.VISIBLE
                cardByokMode.visibility = View.GONE
                sectionByok.visibility = View.GONE
            }
            SetupViewModel.LlmMode.BYOK -> {
                Log.i(TAG, "Showing BYOK UI")
                // Hide CIRIS proxy card (unless they can switch back)
                val isGoogle = viewModel.isGoogleAuth.value == true
                cardCirisProxy.visibility = View.GONE
                textAdvancedOption.visibility = View.GONE

                // Show "switch back to free AI" banner only for Google users
                cardByokMode.visibility = if (isGoogle) View.VISIBLE else View.GONE
                sectionByok.visibility = View.VISIBLE
            }
            null -> {
                Log.i(TAG, "No mode selected - checking Google auth state")
                val isGoogle = viewModel.isGoogleAuth.value == true
                if (isGoogle) {
                    // Default to showing CIRIS proxy for Google users
                    cardCirisProxy.visibility = View.VISIBLE
                    textAdvancedOption.visibility = View.VISIBLE
                    cardByokMode.visibility = View.GONE
                    sectionByok.visibility = View.GONE
                } else {
                    // Non-Google must use BYOK
                    cardCirisProxy.visibility = View.GONE
                    textAdvancedOption.visibility = View.GONE
                    cardByokMode.visibility = View.GONE
                    sectionByok.visibility = View.VISIBLE
                }
            }
        }
    }
}
