package ai.ciris.mobile.shared.platform

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Reset Device is the most destructive thing this app can do, and it shipped
 * four wrong answers: it deleted an unrelated installed agent, then a whole git
 * checkout including uncommitted work, then anything sharing a directory with a
 * bare `data/`, then the state of a node the client was not even talking to.
 *
 * Every one of those is a statement about what SURVIVES a wipe, which is why
 * these tests assert survival against a populated tree rather than checking
 * that the intended targets are gone.
 */
class LocalDataWipeTest {

    private lateinit var home: File

    @BeforeTest
    fun setUp() {
        home = Files.createTempDirectory("ciris-wipe-test").toFile()
    }

    @AfterTest
    fun tearDown() {
        home.deleteRecursively()
    }

    private fun populate() {
        File(home, ".env").writeText("CIRIS_CONFIGURED=true")
        File(home, "data").mkdirs()
        File(home, "data/ciris_engine.db").writeText("db")
        File(home, "identity").mkdirs()
        File(home, "identity/node.key").writeText("secret")
        File(home, "logs").mkdirs()
        File(home, "config").mkdirs()
        File(home, "config/essential.yaml").writeText("tracked source")

        // Never ours: a wipe that takes these is the bug, not the feature.
        File(home, "my_thesis.txt").writeText("years of work")
        File(home, "src").mkdirs()
        File(home, "src/main.py").writeText("code")
        File(home, ".git").mkdirs()
        File(home, ".git/HEAD").writeText("ref: refs/heads/main")
    }

    @Test
    fun `removes generated state and nothing else`() {
        populate()
        assertTrue(wipeGeneratedState(home, checkout = false))

        assertFalse(File(home, ".env").exists())
        assertFalse(File(home, "data").exists())
        assertFalse(File(home, "identity").exists())
        assertFalse(File(home, "logs").exists())

        assertTrue(File(home, "my_thesis.txt").exists(), "deleted a file it did not write")
        assertTrue(File(home, "src/main.py").exists(), "deleted source that is not node state")
        assertTrue(File(home, ".git/HEAD").exists(), "deleted the repository")
    }

    @Test
    fun `never removes the home directory itself`() {
        populate()
        wipeGeneratedState(home, checkout = false)
        assertTrue(home.exists(), "home directory was removed — bug #2 and #3")
        assertTrue(home.isDirectory)
    }

    @Test
    fun `keeps tracked config in a checkout and removes it otherwise`() {
        populate()
        wipeGeneratedState(home, checkout = true)
        assertTrue(
            File(home, "config/essential.yaml").exists(),
            "deleted tracked source: config/ is node state only outside a checkout",
        )

        tearDown(); setUp(); populate()
        wipeGeneratedState(home, checkout = false)
        assertFalse(File(home, "config").exists(), "kept generated config in a dedicated home")
    }

    @Test
    fun `an empty home succeeds without creating anything`() {
        assertTrue(wipeGeneratedState(home, checkout = false))
        assertTrue(home.listFiles()?.isEmpty() == true)
    }

    @Test
    fun `owns the backend only when it is loopback`() {
        // Unset or blank: the client boots the node itself.
        assertTrue(ownsLocalBackend(null))
        assertTrue(ownsLocalBackend(""))

        assertTrue(ownsLocalBackend("http://localhost:8080"))
        assertTrue(ownsLocalBackend("http://127.0.0.1:8080"))
        assertTrue(ownsLocalBackend("http://127.5.5.5:8080"))
        assertTrue(ownsLocalBackend("http://[::1]:8080"))
        assertTrue(ownsLocalBackend("http://0.0.0.0:8080"))

        // A node on another host keeps its state on its own disk.
        assertFalse(ownsLocalBackend("https://agents.ciris.ai"))
        assertFalse(ownsLocalBackend("http://192.168.1.50:8080"))
        assertFalse(ownsLocalBackend("http://node.local:8080"))
        assertFalse(ownsLocalBackend("garbage"))

        // Hostnames that only LOOK like loopback under a prefix test.
        assertFalse(ownsLocalBackend("http://127.0.0.1.evil.com/"))
        assertFalse(ownsLocalBackend("http://localhost.evil.com/"))
    }
}
