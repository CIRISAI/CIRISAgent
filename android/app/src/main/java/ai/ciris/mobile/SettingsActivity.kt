package ai.ciris.mobile

import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Settings activity for configuring the remote LLM endpoint.
 *
 * Users can configure their own OpenAI-compatible endpoint:
 * - OpenAI: https://api.openai.com/v1
 * - Local LLM: http://192.168.1.100:8080/v1
 * - Together.ai: https://api.together.xyz/v1
 * - Any other OpenAI-compatible endpoint
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var apiBaseInput: EditText
    private lateinit var apiKeyInput: EditText
    private lateinit var saveButton: Button

    companion object {
        private const val PREFS_NAME = "ciris_settings"
        private const val KEY_API_BASE = "openai_api_base"
        private const val KEY_API_KEY = "openai_api_key"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        apiBaseInput = findViewById(R.id.apiBaseInput)
        apiKeyInput = findViewById(R.id.apiKeyInput)
        saveButton = findViewById(R.id.saveButton)

        // Load saved settings
        loadSettings()

        saveButton.setOnClickListener {
            saveSettings()
        }
    }

    private fun loadSettings() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        apiBaseInput.setText(
            prefs.getString(KEY_API_BASE, "https://api.openai.com/v1")
        )

        apiKeyInput.setText(
            prefs.getString(KEY_API_KEY, "")
        )
    }

    private fun saveSettings() {
        val apiBase = apiBaseInput.text.toString().trim()
        val apiKey = apiKeyInput.text.toString().trim()

        if (apiBase.isEmpty()) {
            Toast.makeText(this, "API Base URL is required", Toast.LENGTH_SHORT).show()
            return
        }

        if (apiKey.isEmpty()) {
            Toast.makeText(this, "API Key is required", Toast.LENGTH_SHORT).show()
            return
        }

        // Save to SharedPreferences
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString(KEY_API_BASE, apiBase)
            putString(KEY_API_KEY, apiKey)
            apply()
        }

        // Set environment variables for Python runtime
        System.setProperty("OPENAI_API_BASE", apiBase)
        System.setProperty("OPENAI_API_KEY", apiKey)

        Toast.makeText(
            this,
            "Settings saved. Restart app to apply changes.",
            Toast.LENGTH_LONG
        ).show()

        finish()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
