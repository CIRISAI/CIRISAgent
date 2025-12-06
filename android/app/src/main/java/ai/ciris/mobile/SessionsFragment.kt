package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
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
 * SessionsFragment - Cognitive Session Management UI
 *
 * Allows users to initiate and monitor DREAM, PLAY, and SOLITUDE
 * cognitive sessions. Shows current state and provides controls
 * for state transitions.
 */
class SessionsFragment : Fragment() {

    private lateinit var loadingIndicator: ProgressBar
    private lateinit var refreshButton: ImageButton
    private lateinit var currentStateBanner: View
    private lateinit var currentStateDot: View
    private lateinit var currentStateText: TextView
    private lateinit var dreamStatusDot: View
    private lateinit var dreamBadge: TextView
    private lateinit var initiateDreamButton: Button
    private lateinit var playStatusDot: View
    private lateinit var playBadge: TextView
    private lateinit var initiatePlayButton: Button
    private lateinit var solitudeStatusDot: View
    private lateinit var solitudeBadge: TextView
    private lateinit var initiateSolitudeButton: Button
    private lateinit var returnToWorkButton: Button

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private var accessToken: String? = null
    private var pollingJob: Job? = null
    private var currentState: String = "WORK"

    companion object {
        private const val TAG = "SessionsFragment"
        private const val BASE_URL = "http://localhost:8080"
        private const val POLL_INTERVAL_MS = 3000L
        private const val ARG_ACCESS_TOKEN = "access_token"

        fun newInstance(accessToken: String?): SessionsFragment {
            return SessionsFragment().apply {
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
        return inflater.inflate(R.layout.fragment_sessions, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        accessToken = arguments?.getString(ARG_ACCESS_TOKEN)
        Log.i(TAG, "SessionsFragment started, hasToken=${accessToken != null}")

        // Bind views
        loadingIndicator = view.findViewById(R.id.loadingIndicator)
        refreshButton = view.findViewById(R.id.refreshButton)
        currentStateBanner = view.findViewById(R.id.currentStateBanner)
        currentStateDot = view.findViewById(R.id.currentStateDot)
        currentStateText = view.findViewById(R.id.currentStateText)
        dreamStatusDot = view.findViewById(R.id.dreamStatusDot)
        dreamBadge = view.findViewById(R.id.dreamBadge)
        initiateDreamButton = view.findViewById(R.id.initiateDreamButton)
        playStatusDot = view.findViewById(R.id.playStatusDot)
        playBadge = view.findViewById(R.id.playBadge)
        initiatePlayButton = view.findViewById(R.id.initiatePlayButton)
        solitudeStatusDot = view.findViewById(R.id.solitudeStatusDot)
        solitudeBadge = view.findViewById(R.id.solitudeBadge)
        initiateSolitudeButton = view.findViewById(R.id.initiateSolitudeButton)
        returnToWorkButton = view.findViewById(R.id.returnToWorkButton)

        // Setup click listeners
        refreshButton.setOnClickListener { fetchProcessorStates() }
        initiateDreamButton.setOnClickListener { initiateSession("DREAM") }
        initiatePlayButton.setOnClickListener { initiateSession("PLAY") }
        initiateSolitudeButton.setOnClickListener { initiateSession("SOLITUDE") }
        returnToWorkButton.setOnClickListener { initiateSession("WORK") }

        // Initial fetch
        fetchProcessorStates()
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
                fetchProcessorStatesInternal()
            }
        }
    }

    private fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    private fun fetchProcessorStates() {
        loadingIndicator.visibility = View.VISIBLE
        CoroutineScope(Dispatchers.IO).launch {
            fetchProcessorStatesInternal()
            withContext(Dispatchers.Main) {
                loadingIndicator.visibility = View.GONE
            }
        }
    }

    private suspend fun fetchProcessorStatesInternal() {
        try {
            val request = Request.Builder()
                .url("$BASE_URL/v1/system/processors")
                .apply {
                    accessToken?.let { addHeader("Authorization", "Bearer $it") }
                }
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: return

            if (response.isSuccessful) {
                val statesResponse = gson.fromJson(body, ProcessorStatesResponse::class.java)
                withContext(Dispatchers.Main) {
                    updateUI(statesResponse.data)
                }
            } else {
                Log.w(TAG, "Failed to fetch processor states: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching processor states", e)
        }
    }

    private fun updateUI(states: List<ProcessorStateInfo>?) {
        if (states == null) return

        // Find active state
        val activeState = states.find { it.isActive }
        currentState = activeState?.name ?: "UNKNOWN"
        currentStateText.text = currentState

        // Update banner color based on state
        val bannerColor = when (currentState) {
            "WORK" -> "#EFF6FF"
            "DREAM" -> "#F3E8FF"
            "PLAY" -> "#FEF3C7"
            "SOLITUDE" -> "#E0F2FE"
            else -> "#F3F4F6"
        }
        currentStateBanner.setBackgroundColor(android.graphics.Color.parseColor(bannerColor))

        // Update state indicators
        updateStateIndicator(dreamStatusDot, dreamBadge, initiateDreamButton, currentState == "DREAM")
        updateStateIndicator(playStatusDot, playBadge, initiatePlayButton, currentState == "PLAY")
        updateStateIndicator(solitudeStatusDot, solitudeBadge, initiateSolitudeButton, currentState == "SOLITUDE")

        // Show/hide return to work button
        returnToWorkButton.visibility = if (currentState != "WORK" && currentState != "WAKEUP" && currentState != "SHUTDOWN") {
            View.VISIBLE
        } else {
            View.GONE
        }
    }

    private fun updateStateIndicator(dot: View, badge: TextView, button: Button, isActive: Boolean) {
        if (isActive) {
            dot.setBackgroundResource(R.drawable.status_dot_green)
            badge.visibility = View.VISIBLE
            badge.text = "ACTIVE"
            button.isEnabled = false
            button.alpha = 0.5f
        } else {
            dot.setBackgroundResource(R.drawable.status_dot_inactive)
            badge.visibility = View.GONE
            button.isEnabled = currentState == "WORK"  // Can only initiate from WORK state
            button.alpha = if (currentState == "WORK") 1.0f else 0.5f
        }
    }

    private fun initiateSession(targetState: String) {
        val title = if (targetState == "WORK") "Return to Work" else "Initiate $targetState Session"
        val message = when (targetState) {
            "DREAM" -> "Initiate a DREAM session for deep introspection and memory consolidation?"
            "PLAY" -> "Initiate a PLAY session for creative exploration and experimentation?"
            "SOLITUDE" -> "Initiate a SOLITUDE session for quiet reflection and planning?"
            "WORK" -> "Return to normal WORK state?"
            else -> "Change cognitive state to $targetState?"
        }

        AlertDialog.Builder(requireContext())
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("Confirm") { _, _ ->
                performStateTransition(targetState)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performStateTransition(targetState: String) {
        loadingIndicator.visibility = View.VISIBLE

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Use the dedicated state transition API endpoint
                val transitionBody = mapOf(
                    "target_state" to targetState,
                    "reason" to "Requested via Android Sessions UI"
                )

                val request = Request.Builder()
                    .url("$BASE_URL/v1/system/state/transition")
                    .post(gson.toJson(transitionBody).toRequestBody("application/json".toMediaType()))
                    .apply {
                        accessToken?.let { addHeader("Authorization", "Bearer $it") }
                    }
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                withContext(Dispatchers.Main) {
                    loadingIndicator.visibility = View.GONE

                    if (response.isSuccessful && body != null) {
                        val transitionResponse = gson.fromJson(body, StateTransitionResponse::class.java)
                        if (transitionResponse.data?.success == true) {
                            Toast.makeText(
                                context,
                                "Transitioned to ${transitionResponse.data.currentState}",
                                Toast.LENGTH_SHORT
                            ).show()
                            // Refresh state immediately
                            fetchProcessorStates()
                        } else {
                            Toast.makeText(
                                context,
                                transitionResponse.data?.message ?: "Transition not initiated",
                                Toast.LENGTH_SHORT
                            ).show()
                        }
                    } else {
                        val errorMsg = when (response.code) {
                            400 -> "Invalid state requested"
                            401 -> "Authentication required"
                            503 -> "State transition not supported"
                            else -> "Failed to request state transition (${response.code})"
                        }
                        Toast.makeText(context, errorMsg, Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error requesting state transition", e)
                withContext(Dispatchers.Main) {
                    loadingIndicator.visibility = View.GONE
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}

// Data classes
data class ProcessorStatesResponse(
    val success: Boolean,
    val data: List<ProcessorStateInfo>?
)

data class ProcessorStateInfo(
    val name: String,
    @SerializedName("is_active") val isActive: Boolean,
    val description: String,
    val capabilities: List<String>
)

data class StateTransitionResponse(
    val success: Boolean,
    val data: StateTransitionData?
)

data class StateTransitionData(
    val success: Boolean,
    @SerializedName("current_state") val currentState: String?,
    @SerializedName("previous_state") val previousState: String?,
    val message: String?
)
