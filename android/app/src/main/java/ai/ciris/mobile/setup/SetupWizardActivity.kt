package ai.ciris.mobile.setup

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import androidx.viewpager2.widget.ViewPager2
import ai.ciris.mobile.MainActivity
import ai.ciris.mobile.R
import ai.ciris.mobile.auth.GoogleSignInHelper
import ai.ciris.mobile.config.CIRISConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Setup Wizard Activity - 3-step native Kotlin wizard.
 *
 * Steps:
 * 1. Welcome - Introduction
 * 2. LLM - AI configuration (CIRIS proxy for Google users, BYOK for others)
 * 3. Confirm - Summary (Google) or account creation (non-Google)
 *
 * Key features:
 * - Admin password is auto-generated (users don't need to set it)
 * - Google OAuth users get free CIRIS AI (via proxy)
 * - Non-Google users must provide their own API key (BYOK)
 */
class SetupWizardActivity : AppCompatActivity() {

    private lateinit var viewPager: ViewPager2
    private lateinit var btnNext: Button
    private lateinit var btnBack: Button
    private lateinit var viewModel: SetupViewModel
    private val indicators = ArrayList<TextView>()
    private var googleSignInHelper: GoogleSignInHelper? = null

    companion object {
        private const val TAG = "SetupWizard"
        private const val SERVER_URL = "http://localhost:8080"
        private const val STEP_COUNT = 3
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(TAG, "onCreate: Starting setup wizard")
        setContentView(R.layout.activity_setup_wizard)

        viewModel = ViewModelProvider(this).get(SetupViewModel::class.java)

        viewPager = findViewById(R.id.viewPager)
        btnNext = findViewById(R.id.btn_next)
        btnBack = findViewById(R.id.btn_back)

        // Only 3 step indicators now
        indicators.add(findViewById(R.id.step1_indicator))
        indicators.add(findViewById(R.id.step2_indicator))
        indicators.add(findViewById(R.id.step3_indicator))

        // Detect Google OAuth state
        detectGoogleAuthState()

        val pagerAdapter = SetupPagerAdapter(this)
        viewPager.adapter = pagerAdapter
        viewPager.isUserInputEnabled = false // Disable swipe

        btnNext.setOnClickListener {
            val current = viewPager.currentItem
            Log.i(TAG, "Next button clicked, current step: $current")
            if (validateStep(current)) {
                if (current < STEP_COUNT - 1) {
                    Log.i(TAG, "Moving to step ${current + 1}")
                    viewPager.currentItem = current + 1
                } else {
                    Log.i(TAG, "Last step - submitting setup")
                    submitSetup()
                }
            }
        }

        btnBack.setOnClickListener {
            val current = viewPager.currentItem
            if (current > 0) {
                Log.i(TAG, "Back button clicked, moving to step ${current - 1}")
                viewPager.currentItem = current - 1
            }
        }

        viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                Log.i(TAG, "Page selected: $position")
                updateUI(position)
            }
        })

        updateUI(0)
        viewModel.logCurrentState()
    }

    /**
     * Detect if user is signed in with Google OAuth.
     * This determines whether CIRIS proxy option is available.
     *
     * Priority order:
     * 1. Intent extras from MainActivity (most reliable - fresh from LoginActivity)
     * 2. GoogleSignInHelper (fallback - may be stale)
     */
    private fun detectGoogleAuthState() {
        Log.i(TAG, "detectGoogleAuthState: Checking for Google sign-in")

        try {
            // First check Intent extras from MainActivity - this is the most reliable source
            // because it comes directly from LoginActivity's successful Google sign-in
            val authMethod = intent.getStringExtra("auth_method")
            val intentIdToken = intent.getStringExtra("google_id_token")
            val intentUserId = intent.getStringExtra("google_user_id")
            val intentEmail = intent.getStringExtra("user_email")
            val intentName = intent.getStringExtra("user_name")

            Log.i(TAG, "Intent extras: authMethod=$authMethod, hasToken=${intentIdToken != null}, email=$intentEmail")

            if (authMethod == "google" && !intentIdToken.isNullOrEmpty()) {
                Log.i(TAG, "User signed in with Google (from Intent) - enabling CIRIS proxy option")
                viewModel.setGoogleAuthState(
                    isAuth = true,
                    idToken = intentIdToken,
                    email = intentEmail,
                    userId = intentUserId
                )
                return
            }

            // Fallback: Check GoogleSignInHelper (may not have fresh account)
            googleSignInHelper = GoogleSignInHelper(this)

            val isSignedIn = googleSignInHelper?.isSignedIn() == true
            val idToken = googleSignInHelper?.getIdToken()
            val email = googleSignInHelper?.getUserEmail()
            val userId = googleSignInHelper?.getGoogleUserId()

            Log.i(TAG, "GoogleSignInHelper state: signedIn=$isSignedIn, hasToken=${idToken != null}, email=$email")

            if (isSignedIn && idToken != null) {
                Log.i(TAG, "User is signed in with Google (from Helper) - enabling CIRIS proxy option")
                viewModel.setGoogleAuthState(
                    isAuth = true,
                    idToken = idToken,
                    email = email,
                    userId = userId
                )
            } else {
                Log.i(TAG, "User is not signed in with Google - BYOK only")
                viewModel.setGoogleAuthState(
                    isAuth = false,
                    idToken = null,
                    email = null,
                    userId = null
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking Google auth state: ${e.message}", e)
            viewModel.setGoogleAuthState(false, null, null, null)
        }
    }

    private fun updateUI(position: Int) {
        Log.d(TAG, "updateUI: position=$position")

        // Update buttons
        if (position == 0) {
            btnBack.visibility = View.GONE
            btnNext.text = getString(R.string.setup_continue)
        } else {
            btnBack.visibility = View.VISIBLE
            if (position == STEP_COUNT - 1) {
                btnNext.text = getString(R.string.setup_finish)
            } else {
                btnNext.text = getString(R.string.setup_next)
            }
        }

        // Update indicators (only 3 now)
        val activeDrawable = getDrawable(R.drawable.bg_step_active)
        val inactiveDrawable = getDrawable(R.drawable.bg_step_inactive)
        val activeColor = getColor(R.color.white)
        val inactiveColor = getColor(R.color.gray_medium)

        for (i in indicators.indices) {
            if (i <= position) {
                indicators[i].background = activeDrawable
                indicators[i].setTextColor(activeColor)
            } else {
                indicators[i].background = inactiveDrawable
                indicators[i].setTextColor(inactiveColor)
            }
        }
    }

    private fun validateStep(position: Int): Boolean {
        Log.i(TAG, "validateStep: position=$position")
        viewModel.logCurrentState()

        when (position) {
            0 -> {
                // Welcome step - always valid
                Log.d(TAG, "Welcome step validation: PASS")
                return true
            }
            1 -> {
                // LLM step
                val mode = viewModel.llmMode.value
                Log.i(TAG, "LLM step validation: mode=$mode")

                if (mode == SetupViewModel.LlmMode.CIRIS_PROXY) {
                    // CIRIS proxy mode - just need Google auth (already validated)
                    val hasToken = viewModel.googleIdToken.value != null
                    Log.i(TAG, "CIRIS proxy mode: hasToken=$hasToken")
                    if (!hasToken) {
                        Toast.makeText(this, "Google sign-in required for free AI", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    return true
                } else {
                    // BYOK mode - need API key
                    val apiKey = viewModel.llmApiKey.value
                    val provider = viewModel.llmProvider.value
                    Log.i(TAG, "BYOK mode: provider=$provider, apiKeyLength=${apiKey?.length ?: 0}")

                    if (provider == "LocalAI") {
                        // LocalAI might not need API key
                        Log.d(TAG, "LocalAI provider - API key optional")
                        return true
                    }

                    if (apiKey.isNullOrEmpty()) {
                        Log.w(TAG, "API key is required for $provider")
                        Toast.makeText(this, "API Key is required", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    return true
                }
            }
            2 -> {
                // Confirm step
                val isGoogle = viewModel.isGoogleAuth.value == true
                Log.i(TAG, "Confirm step validation: isGoogle=$isGoogle")

                if (isGoogle) {
                    // Google user - no additional validation needed
                    Log.d(TAG, "Google user - no account fields needed")
                    return true
                } else {
                    // Non-Google user - validate username/password
                    val username = viewModel.username.value
                    val password = viewModel.userPassword.value

                    Log.i(TAG, "Validating local account: username=$username, passwordLength=${password?.length ?: 0}")

                    if (username.isNullOrEmpty()) {
                        Toast.makeText(this, "Username is required", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    if (password.isNullOrEmpty()) {
                        Toast.makeText(this, "Password is required", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    if (password.length < 8) {
                        Toast.makeText(this, "Password must be at least 8 characters", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    return true
                }
            }
        }
        return true
    }

    private fun submitSetup() {
        Log.i(TAG, "========== submitSetup called ==========")
        viewModel.logCurrentState()

        btnNext.isEnabled = false
        btnNext.text = "Setting up..."

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val payload = buildSetupPayload()
                Log.i(TAG, "Setup payload: $payload")

                val url = URL("$SERVER_URL/v1/setup/complete")
                Log.i(TAG, "Submitting to: $url")

                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true

                conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }

                val responseCode = conn.responseCode
                Log.i(TAG, "Setup response code: $responseCode")

                if (responseCode == 200) {
                    val response = conn.inputStream.bufferedReader().use { it.readText() }
                    Log.i(TAG, "Setup response: $response")

                    withContext(Dispatchers.Main) {
                        Log.i(TAG, "Setup complete - navigating to MainActivity")
                        Toast.makeText(this@SetupWizardActivity, "Setup Complete!", Toast.LENGTH_SHORT).show()

                        val intent = Intent(this@SetupWizardActivity, MainActivity::class.java)
                        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                        intent.putExtra("show_setup", false)
                        startActivity(intent)
                        finish()
                    }
                } else {
                    val error = conn.errorStream?.bufferedReader()?.use { it.readText() }
                    Log.e(TAG, "Setup failed: $responseCode - $error")
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@SetupWizardActivity, "Setup failed: $error", Toast.LENGTH_LONG).show()
                        btnNext.isEnabled = true
                        btnNext.text = getString(R.string.setup_finish)
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Setup exception", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@SetupWizardActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                    btnNext.isEnabled = true
                    btnNext.text = getString(R.string.setup_finish)
                }
            }
        }
    }

    /**
     * Build the JSON payload for setup completion.
     * Handles both CIRIS proxy and BYOK modes.
     */
    private fun buildSetupPayload(): JSONObject {
        Log.i(TAG, "buildSetupPayload: Building setup request")

        val payload = JSONObject()
        val useCirisProxy = viewModel.useCirisProxy()
        val isGoogle = viewModel.isGoogleAuth.value == true

        Log.i(TAG, "  useCirisProxy=$useCirisProxy, isGoogle=$isGoogle")

        if (useCirisProxy) {
            // CIRIS Proxy mode - use Google ID token with CIRIS hosted proxy
            Log.i(TAG, "  Configuring CIRIS proxy mode")

            val googleIdToken = viewModel.googleIdToken.value ?: ""
            val googleUserId = viewModel.googleUserId.value ?: ""

            Log.i(TAG, "  googleIdToken.length=${googleIdToken.length}, googleUserId=$googleUserId")

            // Use "other" provider so backend writes OPENAI_API_BASE to .env
            payload.put("llm_provider", "other")
            payload.put("llm_api_key", googleIdToken)  // Use actual JWT
            payload.put("llm_base_url", CIRISConfig.CIRIS_LLM_PROXY_URL)
            payload.put("llm_model", "default")

            // Configure European backup
            payload.put("backup_llm_api_key", googleIdToken)
            payload.put("backup_llm_base_url", CIRISConfig.CIRIS_LLM_PROXY_URL_EU)
            payload.put("backup_llm_model", "default")

            Log.i(TAG, "  LLM proxy URLs: primary=${CIRISConfig.CIRIS_LLM_PROXY_URL}, backup=${CIRISConfig.CIRIS_LLM_PROXY_URL_EU}")

        } else {
            // BYOK mode - use user-provided API key
            Log.i(TAG, "  Configuring BYOK mode")

            val providerName = viewModel.llmProvider.value ?: "OpenAI"
            val providerId = when (providerName) {
                "OpenAI" -> "openai"
                "Anthropic" -> "anthropic"
                "Azure OpenAI" -> "other"
                "LocalAI" -> "local"
                else -> "openai"
            }

            var apiKey = viewModel.llmApiKey.value ?: ""
            if (apiKey.isEmpty() && providerId == "local") {
                apiKey = "local"
            }

            Log.i(TAG, "  provider=$providerId, apiKey.length=${apiKey.length}")

            payload.put("llm_provider", providerId)
            payload.put("llm_api_key", apiKey)

            // Optional base URL for custom providers
            val baseUrl = viewModel.llmBaseUrl.value
            if (!baseUrl.isNullOrEmpty()) {
                payload.put("llm_base_url", baseUrl)
            }

            val model = viewModel.llmModel.value
            if (!model.isNullOrEmpty()) {
                payload.put("llm_model", model)
            }
        }

        // Auto-generate admin password (users never see this)
        val adminPassword = viewModel.generateAdminPassword()
        payload.put("system_admin_password", adminPassword)
        Log.i(TAG, "  Generated admin password (32 chars)")

        // User account configuration
        if (isGoogle) {
            // Google OAuth user - use Google account info
            val googleEmail = viewModel.googleEmail.value ?: "google_user"
            val googleUserId = viewModel.googleUserId.value

            Log.i(TAG, "  Google user: email=$googleEmail, userId=$googleUserId")

            payload.put("admin_username", "oauth_google_user")
            payload.put("admin_password", null as String?)  // Optional for OAuth
            payload.put("oauth_provider", "google")
            payload.put("oauth_external_id", googleUserId)
            payload.put("oauth_email", googleEmail)
        } else {
            // Local user account
            val username = viewModel.username.value ?: "admin"
            val password = viewModel.userPassword.value

            Log.i(TAG, "  Local user: username=$username")

            payload.put("admin_username", username)
            payload.put("admin_password", password)
        }

        // Required fields with defaults
        payload.put("template_id", "ally")  // Force Ally template for Android
        val adapters = JSONArray()
        adapters.put("api")
        payload.put("enabled_adapters", adapters)
        payload.put("agent_port", 8080)

        Log.i(TAG, "  template=ally, adapters=[api], port=8080")

        return payload
    }
}
