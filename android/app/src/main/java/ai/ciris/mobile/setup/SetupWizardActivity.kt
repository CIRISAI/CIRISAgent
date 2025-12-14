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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class SetupWizardActivity : AppCompatActivity() {

    private lateinit var viewPager: ViewPager2
    private lateinit var btnNext: Button
    private lateinit var btnBack: Button
    private lateinit var viewModel: SetupViewModel
    private val indicators = ArrayList<TextView>()

    companion object {
        private const val TAG = "SetupWizard"
        private const val SERVER_URL = "http://localhost:8080"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup_wizard)

        viewModel = ViewModelProvider(this).get(SetupViewModel::class.java)

        viewPager = findViewById(R.id.viewPager)
        btnNext = findViewById(R.id.btn_next)
        btnBack = findViewById(R.id.btn_back)

        indicators.add(findViewById(R.id.step1_indicator))
        indicators.add(findViewById(R.id.step2_indicator))
        indicators.add(findViewById(R.id.step3_indicator))
        indicators.add(findViewById(R.id.step4_indicator))

        val pagerAdapter = SetupPagerAdapter(this)
        viewPager.adapter = pagerAdapter
        viewPager.isUserInputEnabled = false // Disable swipe

        btnNext.setOnClickListener {
            val current = viewPager.currentItem
            if (validateStep(current)) {
                if (current < 3) {
                    viewPager.currentItem = current + 1
                } else {
                    submitSetup()
                }
            }
        }

        btnBack.setOnClickListener {
            val current = viewPager.currentItem
            if (current > 0) {
                viewPager.currentItem = current - 1
            }
        }

        viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                updateUI(position)
            }
        })

        updateUI(0)
    }

    private fun updateUI(position: Int) {
        // Update buttons
        if (position == 0) {
            btnBack.visibility = View.GONE
            btnNext.text = getString(R.string.setup_continue)
        } else {
            btnBack.visibility = View.VISIBLE
            if (position == 3) {
                btnNext.text = getString(R.string.setup_finish)
            } else {
                btnNext.text = getString(R.string.setup_next)
            }
        }

        // Update indicators
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
        when (position) {
            0 -> return true
            1 -> {
                val apiKey = viewModel.llmApiKey.value
                val provider = viewModel.llmProvider.value
                // LocalAI might not need API key in some cases, but wizard logic usually requires it or "local"
                if ((provider == "OpenAI" || provider == "Anthropic") && apiKey.isNullOrEmpty()) {
                    Toast.makeText(this, "API Key is required", Toast.LENGTH_SHORT).show()
                    return false
                }
                return true
            }
            2 -> {
                val pwd = viewModel.adminPassword.value
                val confirm = viewModel.adminPasswordConfirm.value
                if (pwd.isNullOrEmpty()) {
                    Toast.makeText(this, "Admin password is required", Toast.LENGTH_SHORT).show()
                    return false
                }
                if (pwd != confirm) {
                    Toast.makeText(this, "Passwords do not match", Toast.LENGTH_SHORT).show()
                    return false
                }
                if (pwd!!.length < 8) {
                    Toast.makeText(this, "Password must be at least 8 characters", Toast.LENGTH_SHORT).show()
                    return false
                }
                return true
            }
            3 -> {
                val username = viewModel.username.value
                val pwd = viewModel.userPassword.value
                if (username.isNullOrEmpty()) {
                    Toast.makeText(this, "Username is required", Toast.LENGTH_SHORT).show()
                    return false
                }
                if (pwd.isNullOrEmpty()) {
                    Toast.makeText(this, "Password is required", Toast.LENGTH_SHORT).show()
                    return false
                }
                if (pwd!!.length < 8) {
                    Toast.makeText(this, "Password must be at least 8 characters", Toast.LENGTH_SHORT).show()
                    return false
                }
                return true
            }
        }
        return true
    }

    private fun submitSetup() {
        btnNext.isEnabled = false
        btnNext.text = "Setting up..."

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                // Prepare JSON payload
                val payload = JSONObject()

                // Map provider name to ID
                val providerName = viewModel.llmProvider.value ?: "OpenAI"
                val providerId = when (providerName) {
                    "OpenAI" -> "openai"
                    "Anthropic" -> "anthropic"
                    "Azure OpenAI" -> "other"
                    "LocalAI" -> "local"
                    else -> "openai"
                }
                payload.put("llm_provider", providerId)

                var apiKey = viewModel.llmApiKey.value
                if (apiKey.isNullOrEmpty()) {
                    if (providerId == "local") apiKey = "local"
                    else apiKey = "sk-placeholder" // Should not happen due to validation
                }
                payload.put("llm_api_key", apiKey)

                // System admin password (Step 3)
                payload.put("system_admin_password", viewModel.adminPassword.value)

                // New User Account (Step 4)
                payload.put("admin_username", viewModel.username.value)
                payload.put("admin_password", viewModel.userPassword.value)

                val email = viewModel.email.value
                if (!email.isNullOrEmpty()) {
                     payload.put("oauth_email", email)
                }

                // Required fields with defaults
                payload.put("template_id", "general")
                val adapters = JSONArray()
                adapters.put("api")
                payload.put("enabled_adapters", adapters)
                payload.put("agent_port", 8080)

                Log.i(TAG, "Submitting setup: $payload")

                val url = URL("$SERVER_URL/v1/setup/complete")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true

                conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }

                val responseCode = conn.responseCode
                Log.i(TAG, "Setup response code: $responseCode")

                if (responseCode == 200) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@SetupWizardActivity, "Setup Complete!", Toast.LENGTH_SHORT).show()

                        // Restart MainActivity to reload state
                        val intent = Intent(this@SetupWizardActivity, MainActivity::class.java)
                        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                        intent.putExtra("show_setup", false)
                        startActivity(intent)
                        finish()
                    }
                } else {
                    val error = conn.errorStream?.bufferedReader()?.use { it.readText() }
                    Log.e(TAG, "Setup failed: $error")
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
}
