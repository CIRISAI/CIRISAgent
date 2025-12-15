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
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import ai.ciris.mobile.R

/**
 * LLM Configuration Fragment for Setup Wizard.
 *
 * For Google OAuth users:
 * - Shows "Free AI Access Ready" card with CIRIS proxy option
 * - Advanced link to switch to BYOK mode
 *
 * For non-Google users:
 * - Shows BYOK provider selection directly
 */
class SetupLlmFragment : Fragment() {

    companion object {
        private const val TAG = "SetupLlmFragment"
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

        // Setup provider spinner
        setupProviderSpinner()

        // Setup click listeners
        setupClickListeners()

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
        Log.d(TAG, "setupProviderSpinner: Setting up provider dropdown")
        val providers = arrayOf("OpenAI", "Anthropic", "Azure OpenAI", "LocalAI")
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, providers)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        providerSpinner.adapter = adapter

        providerSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, position: Int, id: Long) {
                val provider = providers[position]
                Log.d(TAG, "Provider selected: $provider")
                viewModel.setLlmProvider(provider)
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }

        apiKeyInput.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setLlmApiKey(s.toString())
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })
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
