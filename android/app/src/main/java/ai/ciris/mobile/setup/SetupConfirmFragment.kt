package ai.ciris.mobile.setup

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import ai.ciris.mobile.R

/**
 * Confirm/Account Fragment for Setup Wizard (Step 3).
 *
 * For Google OAuth users:
 * - Shows "Google Account Connected" confirmation
 * - Shows setup summary (AI mode, assistant, sign-in method)
 * - No account fields needed (Google handles auth)
 *
 * For non-Google users:
 * - Shows local account creation form (username/password)
 */
class SetupConfirmFragment : Fragment() {

    companion object {
        private const val TAG = "SetupConfirmFragment"
    }

    private lateinit var viewModel: SetupViewModel

    // Views
    private lateinit var titleText: TextView
    private lateinit var descText: TextView
    private lateinit var cardGoogleConnected: LinearLayout
    private lateinit var cardSummary: LinearLayout
    private lateinit var textSummaryAi: TextView
    private lateinit var sectionLocalAccount: LinearLayout
    private lateinit var editUsername: EditText
    private lateinit var editPassword: EditText
    private lateinit var editPasswordConfirm: EditText

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        Log.i(TAG, "onCreateView: Inflating fragment_setup_confirm")
        return inflater.inflate(R.layout.fragment_setup_confirm, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        Log.i(TAG, "onViewCreated: Setting up views")

        viewModel = ViewModelProvider(requireActivity()).get(SetupViewModel::class.java)

        // Find views
        titleText = view.findViewById(R.id.text_title)
        descText = view.findViewById(R.id.text_desc)
        cardGoogleConnected = view.findViewById(R.id.card_google_connected)
        cardSummary = view.findViewById(R.id.card_summary)
        textSummaryAi = view.findViewById(R.id.text_summary_ai)
        sectionLocalAccount = view.findViewById(R.id.section_local_account)
        editUsername = view.findViewById(R.id.edit_username)
        editPassword = view.findViewById(R.id.edit_password)
        editPasswordConfirm = view.findViewById(R.id.edit_password_confirm)

        // Setup text watchers for local account fields
        setupTextWatchers()

        // Observe state changes
        viewModel.isGoogleAuth.observe(viewLifecycleOwner) { isGoogle ->
            Log.i(TAG, "isGoogleAuth changed to: $isGoogle")
            updateUIForAuthMode(isGoogle)
        }

        viewModel.llmMode.observe(viewLifecycleOwner) { mode ->
            Log.i(TAG, "llmMode changed to: $mode")
            updateSummary()
        }

        // Restore state
        restoreState()

        // Log state
        viewModel.logCurrentState()
    }

    private fun setupTextWatchers() {
        editUsername.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setUsername(s.toString())
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        editPassword.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setUserPassword(s.toString())
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })
    }

    private fun restoreState() {
        Log.d(TAG, "restoreState: Restoring previous values")

        viewModel.username.value?.let {
            if (it.isNotEmpty()) {
                Log.d(TAG, "Restoring username: $it")
                editUsername.setText(it)
            }
        }

        viewModel.userPassword.value?.let {
            if (it.isNotEmpty()) {
                Log.d(TAG, "Restoring password (length=${it.length})")
                editPassword.setText(it)
            }
        }
    }

    private fun updateUIForAuthMode(isGoogle: Boolean) {
        Log.i(TAG, "updateUIForAuthMode: isGoogle=$isGoogle")

        if (isGoogle) {
            // Google user - show confirmation and summary, hide account fields
            Log.i(TAG, "Google user - showing confirmation UI")
            titleText.text = getString(R.string.setup_confirm_title)
            descText.text = getString(R.string.setup_confirm_desc)
            cardGoogleConnected.visibility = View.VISIBLE
            cardSummary.visibility = View.VISIBLE
            sectionLocalAccount.visibility = View.GONE
            updateSummary()
        } else {
            // Non-Google user - show account creation form
            Log.i(TAG, "Non-Google user - showing account creation UI")
            titleText.text = getString(R.string.setup_account_title)
            descText.text = getString(R.string.setup_account_desc)
            cardGoogleConnected.visibility = View.GONE
            cardSummary.visibility = View.GONE
            sectionLocalAccount.visibility = View.VISIBLE
        }
    }

    private fun updateSummary() {
        val useCirisProxy = viewModel.useCirisProxy()
        val aiText = if (useCirisProxy) {
            getString(R.string.setup_free_ai_via_google)
        } else {
            getString(R.string.setup_your_own_provider)
        }

        Log.d(TAG, "updateSummary: AI=$aiText, useCirisProxy=$useCirisProxy")
        textSummaryAi.text = getString(R.string.setup_summary_ai, aiText)
    }
}
