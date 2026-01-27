package ai.ciris.mobile.shared.platform

import ai.ciris.mobile.shared.config.CIRISConfig
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Android implementation of EnvFileUpdater.
 *
 * Updates .env file located at /data/user/0/ai.ciris.mobile/files/ciris/.env
 *
 * Logic extracted from:
 * - android/app/src/main/java/ai/ciris/mobile/auth/TokenRefreshManager.kt (lines 240-334)
 */
actual class EnvFileUpdater {

    companion object {
        private const val TAG = "EnvFileUpdater"
        private const val ENV_FILE_NAME = ".env"
        private const val CONFIG_RELOAD_FILE = ".config_reload"

        // CIRIS_HOME is typically at /data/user/0/ai.ciris.mobile/files/ciris
        // We'll find it by looking for common Android data paths
        private val CIRIS_HOME_CANDIDATES = listOf(
            "/data/user/0/ai.ciris.mobile/files/ciris",
            "/data/data/ai.ciris.mobile/files/ciris"
        )

        /**
         * Find the CIRIS_HOME directory
         */
        private fun findCirisHome(): File? {
            for (path in CIRIS_HOME_CANDIDATES) {
                val dir = File(path)
                if (dir.exists() && dir.isDirectory) {
                    Log.d(TAG, "Found CIRIS_HOME at: $path")
                    return dir
                }
            }
            Log.w(TAG, "Could not find CIRIS_HOME in any known location")
            return null
        }
    }

    private val cirisHome: File? = findCirisHome()

    actual suspend fun updateEnvWithToken(googleIdToken: String): Result<Boolean> = withContext(Dispatchers.IO) {
        val envFile = cirisHome?.let { File(it, ENV_FILE_NAME) } ?: run {
            Log.w(TAG, "Cannot update .env - CIRIS_HOME not found")
            return@withContext Result.failure(Exception("CIRIS_HOME not found"))
        }

        if (!envFile.exists()) {
            Log.w(TAG, ".env file not found at: ${envFile.absolutePath}")
            return@withContext Result.failure(Exception(".env file not found"))
        }

        try {
            var content = envFile.readText()
            Log.i(TAG, "Read .env file (${content.length} bytes)")

            // Migrate legacy URLs to new infrastructure if needed
            val (migratedContent, wasMigrated) = CIRISConfig.migrateEnvToNewInfra(content)
            if (wasMigrated) {
                content = migratedContent
                Log.i(TAG, "Migrated legacy URLs to new ciris-services infrastructure")
            }

            // Check if we're in CIRIS proxy mode
            val isCirisProxyMode = CIRISConfig.isCirisProxyUrl(content)

            var openaiUpdated = false
            if (isCirisProxyMode) {
                // CIRIS proxy mode: Update OPENAI_API_KEY with Google token
                Log.i(TAG, "CIRIS proxy mode detected - updating OPENAI_API_KEY")

                val openaiPatterns = listOf(
                    Regex("""OPENAI_API_KEY="[^"]*""""),
                    Regex("""OPENAI_API_KEY='[^']*'"""),
                    Regex("""OPENAI_API_KEY=[^\n]*""")
                )

                for (pattern in openaiPatterns) {
                    if (pattern.containsMatchIn(content)) {
                        content = pattern.replace(content, """OPENAI_API_KEY="$googleIdToken"""")
                        openaiUpdated = true
                        Log.i(TAG, "Updated OPENAI_API_KEY")
                        break
                    }
                }
            } else {
                Log.i(TAG, "BYOK mode detected - preserving user's OPENAI_API_KEY")
            }

            // Always update CIRIS_BILLING_GOOGLE_ID_TOKEN for billing (regardless of BYOK mode)
            val billingPatterns = listOf(
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN="[^"]*""""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN='[^']*'"""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN=[^\n]*""")
            )

            var billingUpdated = false
            for (pattern in billingPatterns) {
                if (pattern.containsMatchIn(content)) {
                    content = pattern.replace(content, """CIRIS_BILLING_GOOGLE_ID_TOKEN="$googleIdToken"""")
                    billingUpdated = true
                    Log.i(TAG, "Updated CIRIS_BILLING_GOOGLE_ID_TOKEN")
                    break
                }
            }

            // If billing token wasn't found, append it
            if (!billingUpdated) {
                content += "\nCIRIS_BILLING_GOOGLE_ID_TOKEN=\"$googleIdToken\"\n"
                billingUpdated = true
                Log.i(TAG, "Added CIRIS_BILLING_GOOGLE_ID_TOKEN")
            }

            if (openaiUpdated || billingUpdated) {
                envFile.writeText(content)
                Log.i(TAG, ".env file updated (proxy mode: $isCirisProxyMode)")

                // Trigger Python to reload config
                triggerConfigReload()

                return@withContext Result.success(true)
            } else {
                Log.w(TAG, "No updates needed for .env file")
                return@withContext Result.success(false)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to update .env file: ${e.message}", e)
            return@withContext Result.failure(e)
        }
    }

    actual fun triggerConfigReload() {
        val reloadFile = cirisHome?.let { File(it, CONFIG_RELOAD_FILE) } ?: run {
            Log.w(TAG, "Cannot write config reload signal - CIRIS_HOME not found")
            return
        }

        try {
            reloadFile.writeText(System.currentTimeMillis().toString())
            Log.i(TAG, "Config reload signal written to ${reloadFile.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to write config reload signal: ${e.message}")
        }
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? = withContext(Dispatchers.IO) {
        val envFile = cirisHome?.let { File(it, ENV_FILE_NAME) } ?: run {
            Log.w(TAG, "Cannot read .env - CIRIS_HOME not found")
            return@withContext null
        }

        if (!envFile.exists()) {
            Log.w(TAG, ".env file not found at: ${envFile.absolutePath}")
            return@withContext null
        }

        try {
            val content = envFile.readText()
            Log.i(TAG, "Read .env file for config (${content.length} bytes)")

            // Parse key values
            val values = mutableMapOf<String, String>()
            content.lines().forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isNotEmpty() && !trimmed.startsWith("#") && trimmed.contains("=")) {
                    val (key, value) = trimmed.split("=", limit = 2)
                    // Remove quotes from value
                    values[key.trim()] = value.trim().removeSurrounding("\"").removeSurrounding("'")
                }
            }

            val baseUrl = values["OPENAI_API_BASE"]
            val model = values["OPENAI_MODEL"]
            val apiKey = values["OPENAI_API_KEY"]

            // Detect provider from base URL
            val provider = when {
                baseUrl == null -> "openai"
                baseUrl.contains("localhost") || baseUrl.contains("127.0.0.1") -> "local"
                CIRISConfig.isCirisProxyUrl(baseUrl) -> "other"  // CIRIS proxy uses "other"
                baseUrl.contains("anthropic") -> "anthropic"
                else -> "other"
            }

            // Check if CIRIS proxy
            val isCirisProxy = baseUrl != null && CIRISConfig.isCirisProxyUrl(baseUrl)

            Log.i(TAG, "Parsed LLM config: provider=$provider, baseUrl=$baseUrl, model=$model, " +
                    "apiKeySet=${!apiKey.isNullOrEmpty()}, isCirisProxy=$isCirisProxy")

            EnvLlmConfig(
                provider = provider,
                baseUrl = baseUrl,
                model = model,
                apiKeySet = !apiKey.isNullOrEmpty(),
                isCirisProxy = isCirisProxy
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read .env file: ${e.message}", e)
            null
        }
    }

    actual suspend fun deleteEnvFile(): Result<Boolean> = withContext(Dispatchers.IO) {
        val envFile = cirisHome?.let { File(it, ENV_FILE_NAME) } ?: run {
            Log.w(TAG, "Cannot delete .env - CIRIS_HOME not found")
            return@withContext Result.failure(Exception("CIRIS_HOME not found"))
        }

        if (!envFile.exists()) {
            Log.i(TAG, ".env file doesn't exist, nothing to delete")
            return@withContext Result.success(true)
        }

        try {
            val deleted = envFile.delete()
            if (deleted) {
                Log.i(TAG, ".env file deleted successfully at: ${envFile.absolutePath}")
                Result.success(true)
            } else {
                Log.e(TAG, "Failed to delete .env file")
                Result.failure(Exception("Failed to delete .env file"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Exception deleting .env file: ${e.message}", e)
            Result.failure(e)
        }
    }
}

/**
 * Factory function to create Android EnvFileUpdater
 */
actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
