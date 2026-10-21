package ai.ciris.mobile

import android.app.Application
import android.content.Context
import android.os.Build
import android.util.Log
import ai.ciris.mobile.shared.platform.ScheduledTaskBroadcastReceiver
import ai.ciris.mobile.shared.platform.ScheduledTaskNotifications
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.verify.CirisVerify
import java.io.File

/**
 * Application class for CIRIS KMP Android app
 * Initializes global components like SecureStorage
 */
class CIRISApplication : Application() {

    private var taskBroadcastReceiver: ScheduledTaskBroadcastReceiver? = null

    override fun onCreate() {
        super.onCreate()

        // CRITICAL: Initialize CirisVerify FIRST to set CIRIS_DATA_DIR env var
        // before any native code runs. This ensures Ed25519 key storage works.
        CirisVerify.setup(this)

        // Initialize SecureStorage with application context
        SecureStorage.setContext(this)

        // Initialize notification channel for scheduled tasks
        ScheduledTaskNotifications.initialize(this)

        // Register broadcast receiver for task events from Python
        taskBroadcastReceiver = ScheduledTaskBroadcastReceiver().also {
            ScheduledTaskBroadcastReceiver.register(this, it)
        }

        // Run migrations for version upgrades (e.g., 1.X -> 2.X)
        MigrationManager.runMigrations(this)

        // Extract bundled llama-server binary for on-device LLM inference
        extractLlamaServerBinary()
    }

    /**
     * Extract the bundled llama-server binary from assets to the app's files directory.
     * Only extracts for ARM64 devices (arm64-v8a ABI).
     */
    private fun extractLlamaServerBinary() {
        val tag = "LlamaServer"

        // Only extract for ARM64 devices
        val supportedAbis = Build.SUPPORTED_ABIS
        if (!supportedAbis.contains("arm64-v8a")) {
            Log.i(tag, "Device ABI not ARM64, skipping llama-server extraction: ${supportedAbis.joinToString()}")
            return
        }

        val binDir = File(filesDir, "bin")
        val targetFile = File(binDir, "llama-server")

        // Skip if already extracted and executable
        if (targetFile.exists() && targetFile.canExecute()) {
            Log.i(tag, "llama-server already extracted at ${targetFile.absolutePath}")
            return
        }

        try {
            // Create bin directory
            if (!binDir.exists()) {
                binDir.mkdirs()
            }

            // Copy from assets
            assets.open("bin/llama-server-arm64").use { input ->
                targetFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }

            // Make executable
            targetFile.setExecutable(true, false)

            Log.i(tag, "Extracted llama-server to ${targetFile.absolutePath} (${targetFile.length()} bytes)")
        } catch (e: Exception) {
            Log.e(tag, "Failed to extract llama-server: ${e.message}", e)
        }
    }

    override fun onTerminate() {
        // Unregister broadcast receiver
        taskBroadcastReceiver?.let {
            try {
                unregisterReceiver(it)
            } catch (e: Exception) {
                Log.w("CIRISApplication", "Failed to unregister receiver: ${e.message}")
            }
        }
        super.onTerminate()
    }
}

/**
 * Handles data migrations between app versions.
 *
 * Key migrations:
 * - 1.X -> 2.X: Fix .env paths (~/ciris -> absolute Android path)
 */
object MigrationManager {
    private const val TAG = "MigrationManager"
    private const val PREFS_NAME = "ciris_migrations"
    private const val KEY_LAST_VERSION = "last_migrated_version"

    // Current major version
    private const val CURRENT_MAJOR_VERSION = 2

    fun runMigrations(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val lastVersion = prefs.getInt(KEY_LAST_VERSION, 0)

        Log.i(TAG, "Checking migrations: lastVersion=$lastVersion, currentMajor=$CURRENT_MAJOR_VERSION")

        // Migration: 1.X -> 2.X - Fix .env paths
        if (lastVersion < 2) {
            migrateEnvPaths(context)
        }

        // Update last migrated version
        prefs.edit().putInt(KEY_LAST_VERSION, CURRENT_MAJOR_VERSION).apply()
    }

    /**
     * Fix .env file paths from ~/ciris to absolute Android paths.
     *
     * In 1.X, the .env file was generated with ~/ciris paths which don't
     * expand on Android. This migration replaces them with absolute paths.
     */
    private fun migrateEnvPaths(context: Context) {
        val cirisHome = File(context.filesDir, "ciris")
        val envFile = File(cirisHome, ".env")

        if (!envFile.exists()) {
            Log.i(TAG, "No .env file to migrate at ${envFile.absolutePath}")
            return
        }

        try {
            var content = envFile.readText()
            val originalContent = content

            // Get the correct absolute path for Android
            val correctDataDir = File(cirisHome, "data").absolutePath

            // Replace ~/ciris/data with the correct absolute path
            // Handle both quoted and unquoted values
            content = content.replace("\"~/ciris/data\"", "\"$correctDataDir\"")
            content = content.replace("=~/ciris/data/", "=$correctDataDir/")
            content = content.replace("=\"~/ciris/data/", "=\"$correctDataDir/")
            content = content.replace("='~/ciris/data/", "='$correctDataDir/")

            // Also handle ~/ciris without /data suffix
            val correctCirisHome = cirisHome.absolutePath
            content = content.replace("\"~/ciris\"", "\"$correctCirisHome\"")
            content = content.replace("=~/ciris\n", "=$correctCirisHome\n")

            if (content != originalContent) {
                // Backup original
                val backupFile = File(cirisHome, ".env.v1.backup")
                envFile.copyTo(backupFile, overwrite = true)
                Log.i(TAG, "Backed up original .env to ${backupFile.absolutePath}")

                // Write fixed content
                envFile.writeText(content)
                Log.i(TAG, "Migrated .env paths: ~/ciris -> $correctCirisHome")
            } else {
                Log.i(TAG, ".env paths already correct, no migration needed")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to migrate .env paths: ${e.message}", e)
        }
    }
}
