package ai.ciris.mobile.setup

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Spinner
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import ai.ciris.mobile.R

class SetupLlmFragment : Fragment() {

    private lateinit var viewModel: SetupViewModel
    private lateinit var apiKeyInput: EditText
    private lateinit var providerSpinner: Spinner

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_setup_llm, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        viewModel = ViewModelProvider(requireActivity()).get(SetupViewModel::class.java)

        apiKeyInput = view.findViewById(R.id.edit_api_key)
        providerSpinner = view.findViewById(R.id.spinner_provider)

        // Setup Spinner
        val providers = arrayOf("OpenAI", "Anthropic", "Azure OpenAI", "LocalAI")
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, providers)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        providerSpinner.adapter = adapter

        // Restore state
        viewModel.llmProvider.value?.let {
             val position = providers.indexOf(it)
             if (position >= 0) providerSpinner.setSelection(position)
        }
        apiKeyInput.setText(viewModel.llmApiKey.value)

        // Listeners
        providerSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, position: Int, id: Long) {
                viewModel.setLlmProvider(providers[position])
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
}
