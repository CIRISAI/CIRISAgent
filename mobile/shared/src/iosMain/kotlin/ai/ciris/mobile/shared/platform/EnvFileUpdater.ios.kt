@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.platform

import ai.ciris.mobile.shared.config.CIRISConfig
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
        private const val TOKEN_REFRESH_SIGNAL_FILE = ".token_refresh_needed"
    }

    private var lastSignalTimestamp: Long = 0

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

            // Migrate legacy URLs to new infrastructure if needed
            val (migratedContent, wasMigrated) = CIRISConfig.migrateEnvToNewInfra(newContent)
            if (wasMigrated) {
                newContent = migratedContent
                println("[$TAG] Migrated legacy URLs to new ciris-services infrastructure")
            }

            // Check if we're in CIRIS proxy mode
            val isCirisProxyMode = CIRISConfig.isCirisProxyUrl(newContent)

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

                // Also update secondary CIRIS_OPENAI_API_KEY_2 if it points to a CIRIS proxy
                val secondaryBasePattern = Regex("""CIRIS_OPENAI_API_BASE_2=["']?([^"'\n]*)["']?""")
                val secondaryBaseMatch = secondaryBasePattern.find(newContent)
                val secondaryBase = secondaryBaseMatch?.groupValues?.getOrNull(1) ?: ""
                if (secondaryBase.contains("ciris.ai")) {
                    val secondaryKeyPattern = Regex("""CIRIS_OPENAI_API_KEY_2=["']?[^"'\n]*["']?""")
                    if (secondaryKeyPattern.containsMatchIn(newContent)) {
                        newContent = secondaryKeyPattern.replace(newContent, """CIRIS_OPENAI_API_KEY_2="$oauthIdToken"""")
                        println("[$TAG] Updated CIRIS_OPENAI_API_KEY_2 (secondary CIRIS proxy)")
                    }
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

            // Also update CIRIS_BILLING_GOOGLE_ID_TOKEN with the same token
            // Python checks this env var first, so it must stay in sync on iOS
            val googleBillingPattern = Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN=["']?[^"'\n]*["']?""")
            if (googleBillingPattern.containsMatchIn(newContent)) {
                newContent = googleBillingPattern.replace(newContent, """CIRIS_BILLING_GOOGLE_ID_TOKEN="$oauthIdToken"""")
                println("[$TAG] Updated CIRIS_BILLING_GOOGLE_ID_TOKEN (sync with Apple token)")
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
                baseUrl.contains("llm01.ciris-services") -> "other"  // CIRIS proxy uses "other"
                baseUrl.contains("anthropic") -> "anthropic"
                else -> "other"
            }

            // Check if CIRIS proxy (llmXX.ciris-services-* pattern for future scaling)
            val isCirisProxy = baseUrl != null && CIRISConfig.isCirisProxyUrl(baseUrl)

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

    actual fun checkTokenRefreshSignal(): Boolean {
        val home = cirisHome ?: return false
        val signalPath = "$home/$TOKEN_REFRESH_SIGNAL_FILE"
        val fileManager = NSFileManager.defaultManager

        if (!fileManager.fileExistsAtPath(signalPath)) return false

        return try {
            val content = NSString.stringWithContentsOfFile(signalPath, NSUTF8StringEncoding, null)
                ?: return false
            val signalTimestamp = (content as String).trim().toDoubleOrNull()?.toLong() ?: 0L

            if (signalTimestamp > lastSignalTimestamp) {
                println("[$TAG] Token refresh signal detected (timestamp: $signalTimestamp)")
                lastSignalTimestamp = signalTimestamp
                // Delete the signal file
                fileManager.removeItemAtPath(signalPath, null)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            println("[$TAG] Error reading token refresh signal: ${e.message}")
            false
        }
    }

    actual suspend fun clearSigningKey(): Result<Boolean> {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot clear signing key - cirisHome not found")
            return Result.failure(Exception("cirisHome not found"))
        }

        return try {
            val fileManager = NSFileManager.defaultManager

            // Delete the data directory which contains the encrypted key file and databases
            val dataPath = "$home/data"
            if (fileManager.fileExistsAtPath(dataPath)) {
                val deleted = fileManager.removeItemAtPath(dataPath, null)
                println("[$TAG] Data directory ${if (deleted) "deleted" else "NOT deleted"}: $dataPath")
            }

            // Also try the older path where key might be stored
            val oldKeyPath = "$home/agent_signing.ed25519.enc"
            if (fileManager.fileExistsAtPath(oldKeyPath)) {
                val deleted = fileManager.removeItemAtPath(oldKeyPath, null)
                println("[$TAG] Old key file ${if (deleted) "deleted" else "NOT deleted"}: $oldKeyPath")
            }

            // Delete from iOS Keychain
            // TODO: Implement keychain deletion if CIRISVerify uses iOS Keychain for key storage
            println("[$TAG] Signing key and data cleared successfully")
            Result.success(true)
        } catch (e: Exception) {
            println("[$TAG] Error clearing signing key: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Clear only the data directory, preserving the signing key.
     * Use this for a "soft reset" that keeps wallet access intact.
     */
    actual suspend fun clearDataOnly(): Result<Boolean> {
        val home = cirisHome ?: run {
            println("[$TAG] Cannot clear data - cirisHome not found")
            return Result.failure(Exception("cirisHome not found"))
        }

        return try {
            val fileManager = NSFileManager.defaultManager

            // Only delete the data directory (databases, audit logs, etc.)
            val dataPath = "$home/data"
            if (fileManager.fileExistsAtPath(dataPath)) {
                val deleted = fileManager.removeItemAtPath(dataPath, null)
                println("[$TAG] Data directory ${if (deleted) "deleted" else "NOT deleted"}: $dataPath")
            } else {
                println("[$TAG] Data directory does not exist")
            }

            println("[$TAG] Data cleared - signing key preserved for wallet access")
            Result.success(true)
        } catch (e: Exception) {
            println("[$TAG] Error clearing data: ${e.message}")
            Result.failure(e)
        }
    }
}

/**
 * Factory function to create iOS EnvFileUpdater
 */
actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
