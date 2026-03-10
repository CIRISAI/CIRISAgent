package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Desktop EnvFileUpdater implementation.
 * Reads/writes .env files in the CIRIS home directory.
 */
actual class EnvFileUpdater {
    private val cirisHome: File by lazy {
        val home = System.getenv("CIRIS_HOME")
            ?: "${System.getProperty("user.home")}/ciris"  // ~/ciris not ~/.ciris
        File(home).also { it.mkdirs() }
    }

    private val envFile: File get() = File(cirisHome, ".env")
    private val configReloadFile: File get() = File(cirisHome, ".config_reload")
    private val tokenRefreshSignalFile: File get() = File(cirisHome, ".token_refresh_needed")
    private var lastSignalTimestamp: Long = 0

    actual suspend fun updateEnvWithToken(oauthIdToken: String): Result<Boolean> = runCatching {
        val envContent = if (envFile.exists()) envFile.readText() else ""
        val lines = envContent.lines().toMutableList()

        // Update or add CIRIS_BILLING_OAUTH_TOKEN
        val tokenKey = "CIRIS_BILLING_OAUTH_TOKEN"
        val tokenLine = "$tokenKey=$oauthIdToken"

        val existingIndex = lines.indexOfFirst { it.startsWith("$tokenKey=") }
        if (existingIndex >= 0) {
            lines[existingIndex] = tokenLine
        } else {
            lines.add(tokenLine)
        }

        envFile.writeText(lines.joinToString("\n"))
        triggerConfigReload()
        true
    }

    actual fun triggerConfigReload() {
        configReloadFile.writeText(System.currentTimeMillis().toString())
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? {
        if (!envFile.exists()) return null

        val envVars = mutableMapOf<String, String>()
        envFile.readLines().forEach { line ->
            val trimmed = line.trim()
            if (trimmed.isNotEmpty() && !trimmed.startsWith("#") && trimmed.contains("=")) {
                val (key, value) = trimmed.split("=", limit = 2)
                envVars[key.trim()] = value.trim().removeSurrounding("\"")
            }
        }

        // Read provider from .env or runtime environment variables
        val explicitProvider = envVars["CIRIS_LLM_PROVIDER"]
            ?: envVars["LLM_PROVIDER"]
            ?: System.getenv("CIRIS_LLM_PROVIDER")
            ?: System.getenv("LLM_PROVIDER")

        // Check for mock LLM (env var or .env)
        val isMockLlm = envVars["CIRIS_MOCK_LLM"]?.lowercase() in listOf("true", "1", "yes", "on")
            || System.getenv("CIRIS_MOCK_LLM")?.lowercase() in listOf("true", "1", "yes", "on")

        // Check for API keys (prefer provider-specific, fall back to OPENAI_API_KEY for compatibility)
        val anthropicKey = envVars["ANTHROPIC_API_KEY"]
        val openaiKey = envVars["OPENAI_API_KEY"]
        val apiKey = anthropicKey ?: openaiKey

        // Base URL (check provider-specific first)
        val baseUrl = envVars["ANTHROPIC_BASE_URL"]
            ?: envVars["OPENAI_API_BASE"]
            ?: envVars["OPENAI_BASE_URL"]

        // Model (OPENAI_MODEL is used for all providers in CIRIS)
        val model = envVars["OPENAI_MODEL"]

        // Determine provider: mock > explicit > detected from key > detected from URL
        val provider = when {
            isMockLlm -> "mockllm"
            explicitProvider != null -> explicitProvider
            !anthropicKey.isNullOrEmpty() -> "anthropic"
            baseUrl?.contains("anthropic") == true -> "anthropic"
            baseUrl?.contains("openai") == true -> "openai"
            baseUrl?.contains("localhost") == true -> "local"
            baseUrl?.contains("ciris") == true -> "ciris"
            else -> "openai" // default
        }

        val isCirisProxy = baseUrl?.contains("ciris") == true ||
            baseUrl?.contains("proxy") == true

        return EnvLlmConfig(
            provider = provider,
            baseUrl = baseUrl,
            model = model,
            apiKeySet = !apiKey.isNullOrEmpty(),
            isCirisProxy = isCirisProxy
        )
    }

    actual suspend fun deleteEnvFile(): Result<Boolean> = runCatching {
        if (envFile.exists()) {
            envFile.delete()
        }
        true
    }

    actual fun checkTokenRefreshSignal(): Boolean {
        if (!tokenRefreshSignalFile.exists()) return false

        return try {
            val signalContent = tokenRefreshSignalFile.readText().trim()
            val signalTimestamp = signalContent.toDoubleOrNull()?.toLong() ?: 0L

            if (signalTimestamp > lastSignalTimestamp) {
                lastSignalTimestamp = signalTimestamp
                tokenRefreshSignalFile.delete()
                true
            } else {
                false
            }
        } catch (_: Exception) {
            false
        }
    }

    actual suspend fun clearSigningKey(): Result<Boolean> = runCatching {
        // Delete the data directory which contains the encrypted key file and databases
        val dataDir = File(cirisHome, "data")
        if (dataDir.exists()) {
            val deleted = dataDir.deleteRecursively()
            println("[EnvFileUpdater.desktop] Data directory ${if (deleted) "deleted" else "NOT deleted"}: ${dataDir.absolutePath}")
        }

        // Also try the older path where key might be stored
        val oldKeyFile = File(cirisHome, "agent_signing.ed25519.enc")
        if (oldKeyFile.exists()) {
            val deleted = oldKeyFile.delete()
            println("[EnvFileUpdater.desktop] Old key file ${if (deleted) "deleted" else "NOT deleted"}: ${oldKeyFile.absolutePath}")
        }

        // Desktop doesn't use hardware keystore, so no keystore deletion needed
        println("[EnvFileUpdater.desktop] Signing key and data cleared successfully")
        true
    }
}

actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
