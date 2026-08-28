package ai.ciris.mobile.shared.platform

import android.content.Context
import android.util.Log
import java.io.File

private const val TAG = "LocalDataWipe"

/**
 * Android wipe: the Python state directory, then the app's own key/value stores.
 *
 * CIRIS_HOME is resolved through EnvFileUpdater's existing accessor rather than
 * rebuilt here — two spellings of that path is how a wipe half-succeeds.
 */
actual fun wipeLocalData(): Boolean {
    // Symmetry with desktop. Always false on a phone today, but the predicate is
    // the feature's one boundary and reading it here keeps that true if the
    // platform set ever changes.
    if (isManagedDeployment()) {
        Log.w(TAG, "refusing: managed deployment")
        return false
    }

    var ok = true

    // 1. The node's state: .env (the CIRIS_CONFIGURED flag the setup check reads),
    //    ciris_engine.db, logs, identity. This is the half that decides whether
    //    the next boot is a first run.
    val home = runCatching { EnvFileUpdater.getCirisHome() }.getOrNull()
    if (home == null) {
        // Not fatal: an unconfigured device may have no home yet, which is the
        // state we are trying to reach anyway.
        Log.w(TAG, "CIRIS_HOME not resolvable — nothing to delete there")
    } else {
        val deleted = runCatching { home.deleteRecursively() }.getOrDefault(false)
        val gone = !home.exists()
        Log.i(TAG, "CIRIS_HOME wipe: path=${home.absolutePath} deleteRecursively=$deleted gone=$gone")
        // deleteRecursively() reports false if ANY child survived, so trust the
        // directory's own existence rather than the return value.
        if (!gone) ok = false
    }

    // 2. Client-side credentials. Without this the app restarts holding a token
    //    for an account the freshly-wiped node no longer knows, which reads as a
    //    login failure rather than a clean first run.
    val ctx = wipeContext
    if (ctx == null) {
        Log.w(TAG, "no Context — shared prefs NOT cleared")
        ok = false
    } else {
        runCatching {
            val prefsDir = File(ctx.applicationInfo.dataDir, "shared_prefs")
            prefsDir.listFiles()?.forEach { f ->
                val name = f.name.removeSuffix(".xml")
                ctx.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit()
                Log.i(TAG, "cleared prefs: $name")
            }
        }.onFailure {
            Log.e(TAG, "prefs clear failed: ${it.message}")
            ok = false
        }
    }

    Log.i(TAG, "wipeLocalData complete, ok=$ok")
    return ok
}

private var wipeContext: Context? = null

fun initLocalDataWipe(context: Context) {
    wipeContext = context.applicationContext
}
