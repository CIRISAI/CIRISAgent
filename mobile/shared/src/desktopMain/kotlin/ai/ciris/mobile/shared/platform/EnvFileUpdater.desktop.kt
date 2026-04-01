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
        // Delete primary .env location (~/ciris/.env or CIRIS_HOME/.env)
        if (envFile.exists()) {
            envFile.delete()
            println("[EnvFileUpdater.desktop] Deleted: ${envFile.absolutePath}")
        }
        // Also delete legacy .env in CWD and CWD/ciris/ (Python first_run checks both)
        val cwd = File(System.getProperty("user.dir") ?: ".")
        val legacyEnv = File(cwd, ".env")
        if (legacyEnv.exists()) {
            legacyEnv.delete()
            println("[EnvFileUpdater.desktop] Deleted legacy: ${legacyEnv.absolutePath}")
        }
        val cirisSubdirEnv = File(cwd, "ciris/.env")
        if (cirisSubdirEnv.exists()) {
            cirisSubdirEnv.delete()
            println("[EnvFileUpdater.desktop] Deleted ciris subdir: ${cirisSubdirEnv.absolutePath}")
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

    /**
     * Clear only the data directory, preserving the signing key.
     * Use this for a "soft reset" that keeps wallet access intact.
     */
    actual suspend fun clearDataOnly(): Result<Boolean> = runCatching {
        // Clear data directories in all possible locations
        // Python dev mode uses CWD/data/, production uses ~/ciris/data/
        val dataDirs = mutableListOf<File>()

        // Primary: cirisHome/data (~/ciris/data or CIRIS_HOME/data)
        dataDirs.add(File(cirisHome, "data"))

        // Dev mode: Python uses git repo root as CIRIS_HOME
        // Walk up from CWD to find the repo root (contains .git)
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        while (dir != null) {
            if (File(dir, ".git").exists()) {
                val repoData = File(dir, "data")
                if (repoData != dataDirs[0]) {
                    dataDirs.add(repoData)
                    println("[EnvFileUpdater.desktop] Dev mode: found repo root at ${dir.absolutePath}")
                }
                break
            }
            dir = dir.parentFile
        }

        // Also check for legacy root-level databases in repo root
        if (dir != null) {
            val repoRoot = dir
            val legacyDbs = listOf("ciris_engine.db", "ciris_audit.db", "secrets.db", "audit.db")
            for (dbName in legacyDbs) {
                val legacyDb = File(repoRoot, dbName)
                if (legacyDb.exists()) {
                    val deleted = legacyDb.delete()
                    println("[EnvFileUpdater.desktop] Legacy DB ${if (deleted) "deleted" else "NOT deleted"}: ${legacyDb.absolutePath}")
                }
                for (suffix in listOf("-wal", "-shm")) {
                    val walFile = File(repoRoot, "$dbName$suffix")
                    if (walFile.exists()) walFile.delete()
                }
            }
        }

        // Files to preserve during soft reset (signing keys for wallet access)
        val preservePatterns = listOf("agent_signing", "agent_manifest")

        for (dataDir in dataDirs) {
            if (dataDir.exists()) {
                // Selectively delete: preserve signing key files, delete everything else
                var deletedCount = 0
                var preservedCount = 0
                dataDir.listFiles()?.forEach { file ->
                    val shouldPreserve = preservePatterns.any { file.name.startsWith(it) }
                    if (shouldPreserve) {
                        preservedCount++
                        println("[EnvFileUpdater.desktop] Preserved: ${file.name}")
                    } else if (file.isDirectory) {
                        file.deleteRecursively()
                        deletedCount++
                    } else {
                        file.delete()
                        deletedCount++
                    }
                }
                println("[EnvFileUpdater.desktop] Data directory cleaned: ${dataDir.absolutePath} (deleted=$deletedCount, preserved=$preservedCount)")
            } else {
                println("[EnvFileUpdater.desktop] Data directory does not exist: ${dataDir.absolutePath}")
            }
        }

        println("[EnvFileUpdater.desktop] Data cleared - signing key preserved for wallet access")
        true
    }
}

actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
