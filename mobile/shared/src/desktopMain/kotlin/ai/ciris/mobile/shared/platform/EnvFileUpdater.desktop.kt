package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Desktop EnvFileUpdater implementation.
 * Reads/writes .env files in the CIRIS home directory.
 */
actual class EnvFileUpdater {
    private val cirisHome: File by lazy {
        val home = System.getenv("CIRIS_HOME")
            ?: "${System.getProperty("user.home")}/.ciris"
        File(home).also { it.mkdirs() }
    }

    private val envFile: File get() = File(cirisHome, ".env")
    private val configReloadFile: File get() = File(cirisHome, ".config_reload")

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

        val baseUrl = envVars["OPENAI_API_BASE"]
        val apiKey = envVars["OPENAI_API_KEY"]
        val model = envVars["OPENAI_MODEL"]

        // Detect provider from base URL
        val provider = when {
            baseUrl?.contains("anthropic") == true -> "anthropic"
            baseUrl?.contains("openai") == true -> "openai"
            baseUrl?.contains("localhost") == true -> "local"
            baseUrl?.contains("ciris") == true -> "ciris"
            else -> "other"
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
}

actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
