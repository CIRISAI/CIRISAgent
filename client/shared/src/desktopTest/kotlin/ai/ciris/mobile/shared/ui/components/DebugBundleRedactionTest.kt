package ai.ciris.mobile.shared.ui.components

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The bundle is built to be handed to someone else. Redaction is therefore not
 * about what we log today — nothing logs a credential today — but about what
 * escapes when somebody later logs one while chasing a bug.
 *
 * Both directions matter equally. A redactor that misses a JWT leaks; a
 * redactor that eats ordinary log lines destroys the only artifact a stranded
 * user can send us. The second half of these tests is the half that keeps the
 * patterns honest.
 */
class DebugBundleRedactionTest {

    private fun redact(s: String) = DebugBundle.redactSecrets(s)

    @Test
    fun `removes jwts`() {
        val jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP"
        val out = redact("[INFO] auth: exchanged $jwt ok")
        assertFalse(out.contains("eyJhbGciOi"), "JWT survived redaction")
        assertTrue(out.contains("[INFO] auth:"), "redaction ate the surrounding line")
    }

    @Test
    fun `removes bearer headers including service tokens`() {
        assertFalse(
            redact("Authorization: Bearer abcdef0123456789abcdef").contains("abcdef0123456789"),
        )
        assertFalse(
            redact("header Bearer service:9f8e7d6c5b4a39281706").contains("9f8e7d6c5b4a"),
        )
    }

    @Test
    fun `removes secret-shaped assignments`() {
        for (line in listOf(
            "api_key=sk-live-abcdef123456",
            "access_token: ghp_AAAABBBBCCCCDDDDEEEE",
            "password = hunter2hunter2",
            """{"client_secret":"s3cr3t-value-here"}""",
        )) {
            val out = redact(line)
            assertTrue(out.contains("<redacted>"), "not redacted: $line -> $out")
        }
        assertFalse(redact("password = hunter2hunter2").contains("hunter2hunter2"))
    }

    @Test
    fun `leaves ordinary diagnostics untouched`() {
        // Every one of these is a line we NEED in a bug report.
        for (line in listOf(
            // The exact lines the Esu report turned on: an auth failure must
            // survive intact, or the bundle loses the one fact worth sending.
            "[ERROR] CIRISApp: token exchange failed: HTTP 401",
            "[ERROR] auth: token exchange failed, no refresh token present",
            "token: expired",
            "[INFO] startup: 22/22 services healthy in 4.2s",
            "client version: 0.5.190",
            "app version: 2.9.41",
            "device: Linux 7.0.0-30-generic amd64",
            "screen: login",
            "[WARN] node: attestation deadline exceeded (20s budget)",
            "GET /v1/system/health -> 200 in 34ms",
        )) {
            assertEquals(line, redact(line), "redactor damaged an ordinary log line")
        }
    }

    @Test
    fun `render passes its whole output through redaction`() {
        val out = DebugBundle.render(
            mapOf("error (full)" to "refresh_token=rt_abcdef0123456789 rejected"),
        )
        assertFalse(out.contains("rt_abcdef0123456789"), "extra map bypassed redaction")
        assertTrue(out.contains("CIRIS debug bundle"))
    }
}
