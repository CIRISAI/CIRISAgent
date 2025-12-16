package ai.ciris.mobile.setup

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import ai.ciris.mobile.R

/**
 * Welcome Fragment for Setup Wizard (Step 1).
 *
 * Shows context-aware welcome message:
 * - Google OAuth users: "You're ready to go!" with free AI messaging
 * - Non-Google users: "Quick Setup Required" with BYOK instructions
 */
class SetupWelcomeFragment : Fragment() {

    companion object {
        private const val TAG = "SetupWelcomeFragment"
    }

    private lateinit var viewModel: SetupViewModel

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        Log.i(TAG, "onCreateView: Inflating welcome fragment")
        return inflater.inflate(R.layout.fragment_setup_welcome, container, false)
    }

    private var detailsExpanded = false

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        Log.i(TAG, "onViewCreated: Setting up welcome view")

        viewModel = ViewModelProvider(requireActivity()).get(SetupViewModel::class.java)

        val cardGoogleReady = view.findViewById<LinearLayout>(R.id.card_google_ready)
        val cardSetupRequired = view.findViewById<LinearLayout>(R.id.card_setup_required)
        val textHowItWorks = view.findViewById<TextView>(R.id.text_how_it_works)
        val detailsToggle = view.findViewById<TextView>(R.id.details_toggle)
        val detailsContent = view.findViewById<TextView>(R.id.details_content)

        // Setup expandable details
        detailsToggle.setOnClickListener {
            detailsExpanded = !detailsExpanded
            if (detailsExpanded) {
                detailsToggle.text = getString(R.string.setup_details_collapse)
                detailsContent.visibility = View.VISIBLE
            } else {
                detailsToggle.text = getString(R.string.setup_details_expand)
                detailsContent.visibility = View.GONE
            }
        }

        // Observe Google auth state to show appropriate messaging
        viewModel.isGoogleAuth.observe(viewLifecycleOwner) { isGoogle ->
            Log.i(TAG, "isGoogleAuth changed: $isGoogle")

            if (isGoogle) {
                Log.i(TAG, "Google user - showing 'ready to go' message")
                cardGoogleReady.visibility = View.VISIBLE
                cardSetupRequired.visibility = View.GONE
            } else {
                Log.i(TAG, "Non-Google user - showing 'setup required' message")
                cardGoogleReady.visibility = View.GONE
                cardSetupRequired.visibility = View.VISIBLE
            }
        }
    }
}
