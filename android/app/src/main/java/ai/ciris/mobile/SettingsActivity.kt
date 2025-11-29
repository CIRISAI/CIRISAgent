package ai.ciris.mobile

import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

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
        const val PREFS_NAME = "ciris_settings_secure"
        const val KEY_API_BASE = "openai_api_base"
        const val KEY_API_KEY = "openai_api_key"
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

    private fun getEncryptedSharedPreferences(): SharedPreferences {
        val masterKey = MasterKey.Builder(this)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        return EncryptedSharedPreferences.create(
            this,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private fun loadSettings() {
        val prefs = getEncryptedSharedPreferences()

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
        val prefs = getEncryptedSharedPreferences()
        prefs.edit().apply {
            putString(KEY_API_BASE, apiBase)
            putString(KEY_API_KEY, apiKey)
            apply()
        }

        // Set environment variables for Python runtime (best effort for current process)
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
