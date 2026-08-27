package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Desktop wipe target, resolved the way the BACKEND resolves it.
 *
 * Mirrors `ciris_engine.logic.utils.path_resolution.get_ciris_home()`:
 *
 *   /app (CIRIS-Manager-managed)  ->  $CIRIS_HOME  ->  the dev checkout when
 *   running from a source tree  ->  ~/ciris (installed)
 *
 * The dev-checkout case is the one that matters and the one an earlier version
 * of this file omitted. `get_ciris_home()` returns the CURRENT DIRECTORY when it
 * is a git checkout, so a desktop client run from source has its home INSIDE the
 * repo. Resolving to `~/ciris` there would have deleted a completely unrelated
 * installed agent while leaving the active node fully configured — a reset that
 * destroys the wrong data and then reports success.
 *
 * `$CIRIS_DATA_DIR` was also consulted, and is not part of the backend's rule at
 * all: it names a subdirectory, so honouring it would delete `data/` and leave
 * `.env` and `identity/` behind — a half-wipe that still reads as configured.
 */
private fun resolveNodeHome(): File? {
    if (File("/app/agent").isDirectory || File("/app/.ciris_manager").isDirectory) {
        return File("/app")
    }
    System.getenv("CIRIS_HOME")?.takeIf { it.isNotBlank() }?.let { return File(it) }

    // Dev checkout: walk up looking for the repo markers the launcher uses.
    var dir: File? = File(System.getProperty("user.dir", "."))
    repeat(5) {
        val d = dir ?: return@repeat
        if (File(d, "main.py").exists() && File(d, "ciris_engine").isDirectory) return d
        dir = d.parentFile
    }

    return System.getProperty("user.home")?.let { File(it, "ciris") }
}

/**
 * Does this directory actually look like a CIRIS home?
 *
 * The backstop for every resolution mistake, present and future. Recursive
 * deletion of a path derived from environment guesswork is worth exactly one
 * cheap sanity check: if none of these markers are here, we are not looking at a
 * node's home and must not delete it, whatever the resolver said.
 */
private fun looksLikeCirisHome(dir: File): Boolean =
    File(dir, ".env").exists() ||
        File(dir, "identity").isDirectory ||
        File(dir, "data").isDirectory ||
        File(dir, "keys").isDirectory

actual fun wipeLocalData(): Boolean {
    val home = resolveNodeHome() ?: return false
    if (!home.exists()) return true // already absent is the state we want

    if (!looksLikeCirisHome(home)) {
        // Refuse rather than guess. The caller surfaces this to the user instead
        // of restarting into an unchanged node.
        println("[LocalDataWipe] refusing to delete ${home.absolutePath} — no CIRIS home markers")
        return false
    }

    runCatching { home.deleteRecursively() }
    val gone = !home.exists()
    println("[LocalDataWipe] ${home.absolutePath} gone=$gone")
    return gone
}
