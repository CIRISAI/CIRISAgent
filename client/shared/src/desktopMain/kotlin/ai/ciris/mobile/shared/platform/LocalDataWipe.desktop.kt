package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Generated state a node writes into its home. Everything here is recreated on
 * the next boot; nothing here is authored by a human.
 *
 * This list is what makes a checkout-mode reset safe. It is deliberately an
 * ALLOW-LIST: an unknown directory is left alone, because the cost of missing
 * one is a stale file and the cost of guessing wrong is someone's source tree.
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
 * Entries from [GENERATED_STATE] that are TRACKED SOURCE in a checkout and must
 * never be deleted there.
 *
 * `config/` is generated state in a dedicated home and repository source in a
 * checkout — it holds `config/essential.yaml` and
 * `config/environment_variables.md`. The same name means two different things
 * depending on where the home is, which is exactly the kind of ambiguity that
 * turns a reset into data loss.
 *
 * A dedicated home is still wiped whole, so nothing is missed there; this
 * exclusion applies only to the selective checkout path.
 */
private val TRACKED_IN_CHECKOUT = setOf("config")

/**
 * Desktop wipe target, resolved the way the BACKEND resolves it.
 *
 * Mirrors `ciris_engine.logic.utils.path_resolution.get_ciris_home()`:
 *   /app (managed) -> $CIRIS_HOME -> the dev checkout -> ~/ciris (installed)
 */
private fun resolveNodeHome(): File? {
    // Kept so the resolver still MIRRORS get_ciris_home() exactly; wipeLocalData
    // refuses on managed before it ever gets here.
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

private fun looksLikeCirisHome(dir: File): Boolean =
    GENERATED_STATE.any { File(dir, it).exists() }

/**
 * Erase local node state.
 *
 * TWO MODES, and the distinction is the whole safety story.
 *
 * When the home is a DEDICATED directory (`$CIRIS_HOME`, `~/ciris`, `/app`),
 * the directory itself is state and is removed whole.
 *
 * When the home is a SOURCE CHECKOUT — which `get_ciris_home()` returns for a
 * desktop client launched from a repo — the directory is NOT ours to delete. It
 * holds tracked source and uncommitted work, and a previous revision of this
 * file would have recursively deleted all of it: the checkout has `.env` and
 * `data/`, so the marker check waved it through. Deleting a developer's
 * repository is a far worse outcome than the stale-config bug this function
 * exists to fix.
 *
 * So a checkout is wiped ENTRY BY ENTRY from [GENERATED_STATE], and never as a
 * whole. `.git` is the discriminator, and it is also checked directly as a
 * belt: no path containing a `.git` directory is ever recursively deleted,
 * regardless of how it was resolved.
 */
actual fun wipeLocalData(): Boolean {
    // Managed deployments are not ours to wipe. `/app` belongs to CIRIS-Manager,
    // the operator owns its lifecycle, and the person in front of this UI is not
    // necessarily the person entitled to destroy it. Refusing is reported to the
    // user rather than silently doing nothing.
    if (isManagedDeployment()) {
        println("[LocalDataWipe] refusing: CIRIS-Manager-managed deployment (/app)")
        return false
    }

    val home = resolveNodeHome() ?: return false
    if (!home.exists()) return true

    if (!looksLikeCirisHome(home)) {
        println("[LocalDataWipe] refusing ${home.absolutePath} — no CIRIS state markers")
        return false
    }

    val isCheckout = File(home, ".git").exists() ||
        (File(home, "main.py").exists() && File(home, "ciris_engine").isDirectory)

    if (isCheckout) {
        // Selective: only what the node generated.
        var ok = true
        for (name in GENERATED_STATE) {
            if (name in TRACKED_IN_CHECKOUT) {
                println("[LocalDataWipe] skipping $name — tracked source in a checkout")
                continue
            }
            val f = File(home, name)
            if (!f.exists()) continue
            runCatching { if (f.isDirectory) f.deleteRecursively() else f.delete() }
            if (f.exists()) {
                println("[LocalDataWipe] could not remove ${f.absolutePath}")
                ok = false
            }
        }
        println("[LocalDataWipe] checkout mode: wiped generated state under ${home.absolutePath}, ok=$ok")
        return ok
    }

    runCatching { home.deleteRecursively() }
    val gone = !home.exists()
    println("[LocalDataWipe] dedicated home ${home.absolutePath} gone=$gone")
    return gone
}
