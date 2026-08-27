package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The buffer is written from several threads at once and read when things have
 * already gone wrong.
 *
 * On desktop the node's stdout reader logs from `Dispatchers.IO` while view
 * models log from their own scopes. That is not an exotic case: it is what a
 * failing startup looks like, which is the only time anyone downloads a debug
 * bundle. A buffer that silently drops entries under concurrency would omit
 * exactly the errors it exists to capture, and the loss would be invisible —
 * the bundle still arrives, just missing the line that explains the failure.
 *
 * These live in `desktopTest`, not `commonTest`, deliberately: they need real
 * parallelism. On a single-threaded target `Dispatchers.Default` interleaves
 * without ever overlapping, so a read-modify-write bug passes.
 */
class DebugLogBufferConcurrencyTest {

    @BeforeTest
    fun reset() = DebugLogBuffer.clear()

    @Test
    fun `concurrent adds lose no entries and never repeat an id`() = runBlocking {
        // Under the buffer cap, so every add must survive: any shortfall is a
        // lost update rather than intended trimming.
        val writers = 16
        val perWriter = 10
        val total = writers * perWriter

        (0 until writers).map { w ->
            async(Dispatchers.Default) {
                repeat(perWriter) { i -> DebugLogBuffer.add("INFO", "w$w", "msg-$i") }
            }
        }.awaitAll()

        val entries = DebugLogBuffer.entries.value
        assertEquals(total, entries.size, "lost entries under concurrent add")

        val ids = entries.map { it.id }
        assertEquals(ids.size, ids.toSet().size, "duplicate ids under concurrent add")
        assertEquals(ids.sorted(), ids, "ids not monotonic in list order")
    }

    @Test
    fun `concurrent error adds count every error`() = runBlocking {
        val writers = 16
        val perWriter = 8

        (0 until writers).map { w ->
            async(Dispatchers.Default) {
                repeat(perWriter) { i -> DebugLogBuffer.add("ERROR", "w$w", "boom-$i") }
            }
        }.awaitAll()

        assertEquals(
            writers * perWriter,
            DebugLogBuffer.errorCount.value,
            "lost increments: errorCount read-modify-write is not atomic",
        )
        assertTrue(DebugLogBuffer.latestError.value?.startsWith("[w") == true)
    }

    @Test
    fun `buffer trims to the cap and keeps the newest`() = runBlocking {
        // Single-threaded: this asserts the trim policy, not the race.
        repeat(250) { i -> DebugLogBuffer.add("INFO", "t", "m$i") }

        val entries = DebugLogBuffer.entries.value
        assertEquals(200, entries.size, "buffer did not trim to MAX_ENTRIES")
        assertEquals("m249", entries.last().message, "trim dropped the newest, not the oldest")
        assertEquals("m50", entries.first().message)
    }
}
