package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.*
import platform.Foundation.*

/**
 * iOS implementation of EnvFileUpdater.
 *
 * On iOS, configuration is stored in the Documents/ciris/.env file,
 * similar to Android but with Apple-specific token naming.
 *
 * Uses CIRIS_BILLING_APPLE_ID_TOKEN instead of CIRIS_BILLING_GOOGLE_ID_TOKEN.
 */
actual class EnvFileUpdater {

    companion object {
        private const val TAG = "EnvFileUpdater.ios"
        private const val ENV_FILE_NAME = ".env"
        private const val CONFIG_RELOAD_FILE = ".config_reload"
    }

    private val cirisHome: String? by lazy {
        val documentsPath = NSSearchPathForDirectoriesInDomains(
            NSDocumentDirectory,
            NSUserDomainMask,
            true
        ).firstOrNull() as? String

        documentsPath?.let { "$it/ciris" }
    }

    actual suspend fun updateEnvWithToken(oauthIdToken: String): Result<Boolean> {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot update .env - cirisHome not found")
            return Result.failure(Exception("cirisHome not found"))
        }

        val envPath = "$home/$ENV_FILE_NAME"
        val fileManager = NSFileManager.defaultManager

        if (!fileManager.fileExistsAtPath(envPath)) {
            println("[$TAG] .env file not found at: $envPath")
            return Result.failure(Exception(".env file not found"))
        }

        return try {
            // Read current content
            val content = NSString.stringWithContentsOfFile(envPath, NSUTF8StringEncoding, null)
                ?: throw Exception("Failed to read .env file")

            var newContent = content as String
            println("[$TAG] Read .env file (${newContent.length} bytes)")

            // Check if we're in CIRIS proxy mode
            val isCirisProxyMode = newContent.contains("llm.ciris.ai") ||
                                   newContent.contains("llm.ciris-services.ai")

            var openaiUpdated = false
            if (isCirisProxyMode) {
                // CIRIS proxy mode: Update OPENAI_API_KEY with Apple token
                println("[$TAG] CIRIS proxy mode detected - updating OPENAI_API_KEY")

                val openaiPattern = Regex("""OPENAI_API_KEY=["']?[^"'\n]*["']?""")
                if (openaiPattern.containsMatchIn(newContent)) {
                    newContent = openaiPattern.replace(newContent, """OPENAI_API_KEY="$oauthIdToken"""")
                    openaiUpdated = true
                    println("[$TAG] Updated OPENAI_API_KEY")
                }
            } else {
                println("[$TAG] BYOK mode detected - preserving user's OPENAI_API_KEY")
            }

            // Update CIRIS_BILLING_APPLE_ID_TOKEN for billing
            val billingPattern = Regex("""CIRIS_BILLING_APPLE_ID_TOKEN=["']?[^"'\n]*["']?""")
            var billingUpdated = false

            if (billingPattern.containsMatchIn(newContent)) {
                newContent = billingPattern.replace(newContent, """CIRIS_BILLING_APPLE_ID_TOKEN="$oauthIdToken"""")
                billingUpdated = true
                println("[$TAG] Updated CIRIS_BILLING_APPLE_ID_TOKEN")
            } else {
                // Append if not found
                newContent += "\nCIRIS_BILLING_APPLE_ID_TOKEN=\"$oauthIdToken\"\n"
                billingUpdated = true
                println("[$TAG] Added CIRIS_BILLING_APPLE_ID_TOKEN")
            }

            if (openaiUpdated || billingUpdated) {
                // Write updated content
                val nsContent = newContent as NSString
                val success = nsContent.writeToFile(
                    envPath,
                    atomically = true,
                    encoding = NSUTF8StringEncoding,
                    error = null
                )

                if (success) {
                    println("[$TAG] .env file updated (proxy mode: $isCirisProxyMode)")
                    triggerConfigReload()
                    Result.success(true)
                } else {
                    Result.failure(Exception("Failed to write .env file"))
                }
            } else {
                println("[$TAG] No updates needed for .env file")
                Result.success(false)
            }
        } catch (e: Exception) {
            println("[$TAG] Failed to update .env file: ${e.message}")
            Result.failure(e)
        }
    }

    actual fun triggerConfigReload() {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot write config reload signal - cirisHome not found")
            return
        }

        val reloadPath = "$home/$CONFIG_RELOAD_FILE"

        try {
            val timestamp = NSDate().timeIntervalSince1970.toLong().toString()
            val nsTimestamp = timestamp as NSString
            nsTimestamp.writeToFile(
                reloadPath,
                atomically = true,
                encoding = NSUTF8StringEncoding,
                error = null
            )
            println("[$TAG] Config reload signal written to $reloadPath")
        } catch (e: Exception) {
            println("[$TAG] Failed to write config reload signal: ${e.message}")
        }
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot read .env - cirisHome not found")
            return null
        }

        val envPath = "$home/$ENV_FILE_NAME"
        val fileManager = NSFileManager.defaultManager

        if (!fileManager.fileExistsAtPath(envPath)) {
            println("[$TAG] .env file not found at: $envPath")
            return null
        }

        return try {
            val content = NSString.stringWithContentsOfFile(envPath, NSUTF8StringEncoding, null)
                ?: return null

            val contentStr = content as String
            println("[$TAG] Read .env file for config (${contentStr.length} bytes)")

            // Parse key values
            val values = mutableMapOf<String, String>()
            contentStr.lines().forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isNotEmpty() && !trimmed.startsWith("#") && trimmed.contains("=")) {
                    val parts = trimmed.split("=", limit = 2)
                    if (parts.size == 2) {
                        val key = parts[0].trim()
                        var value = parts[1].trim()
                        // Remove quotes
                        if ((value.startsWith("\"") && value.endsWith("\"")) ||
                            (value.startsWith("'") && value.endsWith("'"))) {
                            value = value.substring(1, value.length - 1)
                        }
                        values[key] = value
                    }
                }
            }

            val baseUrl = values["OPENAI_API_BASE"]
            val model = values["OPENAI_MODEL"]
            val apiKey = values["OPENAI_API_KEY"]

            // Detect provider from base URL
            val provider = when {
                baseUrl == null -> "openai"
                baseUrl.contains("localhost") || baseUrl.contains("127.0.0.1") -> "local"
                baseUrl.contains("llm.ciris") -> "other"  // CIRIS proxy uses "other"
                baseUrl.contains("anthropic") -> "anthropic"
                else -> "other"
            }

            // Check if CIRIS proxy
            val isCirisProxy = baseUrl != null &&
                (baseUrl.contains("llm.ciris.ai") || baseUrl.contains("llm.ciris-services.ai"))

            println("[$TAG] Parsed LLM config: provider=$provider, baseUrl=$baseUrl, model=$model, " +
                    "apiKeySet=${!apiKey.isNullOrEmpty()}, isCirisProxy=$isCirisProxy")

            EnvLlmConfig(
                provider = provider,
                baseUrl = baseUrl,
                model = model,
                apiKeySet = !apiKey.isNullOrEmpty(),
                isCirisProxy = isCirisProxy
            )
        } catch (e: Exception) {
            println("[$TAG] Failed to read .env file: ${e.message}")
            null
        }
    }

    actual suspend fun deleteEnvFile(): Result<Boolean> {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot delete .env - cirisHome not found")
            return Result.failure(Exception("cirisHome not found"))
        }

        val envPath = "$home/$ENV_FILE_NAME"
        val fileManager = NSFileManager.defaultManager

        if (!fileManager.fileExistsAtPath(envPath)) {
            println("[$TAG] .env file doesn't exist, nothing to delete")
            return Result.success(true)
        }

        return try {
            val success = fileManager.removeItemAtPath(envPath, null)
            if (success) {
                println("[$TAG] .env file deleted successfully at: $envPath")
                Result.success(true)
            } else {
                println("[$TAG] Failed to delete .env file")
                Result.failure(Exception("Failed to delete .env file"))
            }
        } catch (e: Exception) {
            println("[$TAG] Exception deleting .env file: ${e.message}")
            Result.failure(e)
        }
    }
}

/**
 * Factory function to create iOS EnvFileUpdater
 */
actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
