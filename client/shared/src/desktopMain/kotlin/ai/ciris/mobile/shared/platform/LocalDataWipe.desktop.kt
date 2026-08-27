package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Generated state a node writes into its home. Everything here is recreated on
 * the next boot; nothing here is authored by a human.
 *
 * Deliberately an ALLOW-LIST. The cost of missing an entry is a stale file; the
 * cost of guessing wrong is someone else's data.
 */
private val GENERATED_STATE = listOf(
    ".env",
    "ceg",
    "claim_pin",
    "config",
    "data",
    "data_archive",
    "identity",
    "keys",
    "logs",
    "secrets",
    "startup_python_hashes.json",
)

/**
 * Entries that are TRACKED SOURCE in a checkout and must not be deleted there.
 *
 * `config/` is generated state in a dedicated home and repository source in a
 * checkout — it holds `config/essential.yaml` and
 * `config/environment_variables.md`. One name, two meanings, decided by where
 * the home happens to be.
 */
private val TRACKED_IN_CHECKOUT = setOf("config")

/**
 * The node home, resolved the way the BACKEND resolves it.
 *
 * Mirrors `ciris_engine.logic.utils.path_resolution.get_ciris_home()`:
 *   /app (managed) -> $CIRIS_HOME -> the dev checkout -> ~/ciris (installed)
 */
private fun resolveNodeHome(): File? {
    if (isManagedDeployment()) return File("/app")
    System.getenv("CIRIS_HOME")?.takeIf { it.isNotBlank() }?.let { return File(it) }

    var dir: File? = File(System.getProperty("user.dir", "."))
    repeat(5) {
        val d = dir ?: return@repeat
        if (File(d, "main.py").exists() && File(d, "ciris_engine").isDirectory) return d
        dir = d.parentFile
    }

    return System.getProperty("user.home")?.let { File(it, "ciris") }
}

/** A source checkout, where `config/` is tracked source rather than node state. */
private fun isSourceCheckout(home: File): Boolean =
    File(home, ".git").exists() ||
        (File(home, "main.py").exists() && File(home, "ciris_engine").isDirectory)

/**
 * Erase local node state.
 *
 * ONE PATH: the home directory itself is NEVER deleted, anywhere.
 *
 * This function had two modes — dedicated homes removed whole, checkouts wiped
 * entry by entry — and that distinction was wrong three revisions running. Each
 * time, a guard was added to make whole-directory deletion safe, and each time
 * the guard admitted something it should not have:
 *
 *   1. resolved `~/ciris` while the backend's home was a source checkout, so it
 *      deleted an unrelated installed agent and left the live node configured;
 *   2. resolved the checkout correctly and then recursively deleted it — the
 *      whole repository, tracked source and uncommitted work, because a
 *      configured checkout has `.env` and `data/` and the marker check passed;
 *   3. treated a bare `data/` or `logs/` as proof of ownership, so a
 *      `CIRIS_HOME` pointed at `$HOME` or any shared directory would take
 *      everything in it with it.
 *
 * The mode bought nothing that justified that. Removing only what the node
 * generates reaches the identical end state — no `.env`, so the next boot is a
 * genuine first run — and leaves no input, resolved or misresolved, that can
 * make this delete something it does not recognise. What survives is an empty
 * directory and any file we never wrote, which is exactly what should survive.
 */
actual fun wipeLocalData(): Boolean {
    // Managed deployments are not ours to wipe: `/app` belongs to CIRIS-Manager,
    // and the person at this UI is not necessarily entitled to destroy it.
    if (isManagedDeployment()) {
        println("[LocalDataWipe] refusing: CIRIS-Manager-managed deployment (/app)")
        return false
    }

    val home = resolveNodeHome() ?: return false
    if (!home.exists()) return true

    val checkout = isSourceCheckout(home)
    var ok = true
    var removed = 0

    for (name in GENERATED_STATE) {
        if (checkout && name in TRACKED_IN_CHECKOUT) {
            println("[LocalDataWipe] skipping $name — tracked source in a checkout")
            continue
        }
        val f = File(home, name)
        if (!f.exists()) continue
        runCatching { if (f.isDirectory) f.deleteRecursively() else f.delete() }
        if (f.exists()) {
            println("[LocalDataWipe] could not remove ${f.absolutePath}")
            ok = false
        } else {
            removed++
        }
    }

    println("[LocalDataWipe] ${home.absolutePath}: removed $removed generated entries, ok=$ok")
    return ok
}
