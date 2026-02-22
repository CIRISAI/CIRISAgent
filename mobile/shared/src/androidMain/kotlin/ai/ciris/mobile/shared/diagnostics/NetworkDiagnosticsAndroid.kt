package ai.ciris.mobile.shared.diagnostics

import android.util.Log
import kotlinx.coroutines.*
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android-specific network diagnostics using HttpURLConnection.
 * This avoids Ktor engine issues and uses standard Android networking.
 */
object NetworkDiagnosticsAndroid {

    private const val TAG = "CIRISNetDiag"

    // DNS TXT record queries via DNS-over-HTTPS
    private const val DOH_CLOUDFLARE_US = "https://1.1.1.1/dns-query?name=_ciris-verify.us.registry.ciris-services-1.ai&type=TXT"
    private const val DOH_CLOUDFLARE_EU = "https://1.1.1.1/dns-query?name=_ciris-verify.eu.registry.ciris-services-1.ai&type=TXT"
    private const val DOH_GOOGLE_US = "https://8.8.8.8/resolve?name=_ciris-verify.us.registry.ciris-services-1.ai&type=TXT"

    // HTTPS Registry
    private const val HTTPS_REGISTRY_HEALTH = "https://api.registry.ciris-services-1.ai/health"
    private const val HTTPS_HTTPBIN = "https://httpbin.org/ip"

    data class DiagResult(
        val name: String,
        val success: Boolean,
        val durationMs: Long,
        val response: String? = null,
        val error: String? = null
    )

    /**
     * Run all diagnostics. Call from MainActivity in Dispatchers.IO.
     */
    suspend fun runAllDiagnostics(): List<DiagResult> = withContext(Dispatchers.IO) {
        val results = mutableListOf<DiagResult>()

        log("========== CIRIS Network Diagnostics ==========")
        log("Testing registry connectivity from Android...")

        // Test 1: Internet connectivity first
        results.add(testUrl("Internet-Check", HTTPS_HTTPBIN))

        // Test 2: DoH via Cloudflare for US
        results.add(testDoH("DoH-Cloudflare-US", DOH_CLOUDFLARE_US))

        // Test 3: DoH via Cloudflare for EU
        results.add(testDoH("DoH-Cloudflare-EU", DOH_CLOUDFLARE_EU))

        // Test 4: DoH via Google for US
        results.add(testDoH("DoH-Google-US", DOH_GOOGLE_US))

        // Test 5: HTTPS Registry health
        results.add(testUrl("HTTPS-Registry-Health", HTTPS_REGISTRY_HEALTH))

        // Summary
        log("========== Results Summary ==========")
        results.forEach { r ->
            val status = if (r.success) "OK" else "FAIL"
            log("[$status] ${r.name}: ${r.durationMs}ms - ${r.error ?: r.response?.take(80) ?: "no response"}")
        }
        log("=====================================")

        results
    }

    private fun testDoH(name: String, url: String): DiagResult {
        log("Testing $name...")
        val start = System.currentTimeMillis()

        return try {
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000
            connection.setRequestProperty("Accept", "application/dns-json")

            val responseCode = connection.responseCode
            val duration = System.currentTimeMillis() - start

            if (responseCode == 200) {
                val body = connection.inputStream.bufferedReader().readText()
                connection.disconnect()
                log("  OK ($duration ms): ${body.take(100)}...")
                DiagResult(name, true, duration, body.take(200))
            } else {
                connection.disconnect()
                log("  FAIL ($duration ms): HTTP $responseCode")
                DiagResult(name, false, duration, error = "HTTP $responseCode")
            }
        } catch (e: Exception) {
            val duration = System.currentTimeMillis() - start
            log("  ERROR ($duration ms): ${e::class.simpleName}: ${e.message}")
            DiagResult(name, false, duration, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    private fun testUrl(name: String, url: String): DiagResult {
        log("Testing $name: $url")
        val start = System.currentTimeMillis()

        return try {
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000

            val responseCode = connection.responseCode
            val duration = System.currentTimeMillis() - start

            // 401/404 still means reachable
            if (responseCode in 200..499) {
                val body = try {
                    connection.inputStream.bufferedReader().readText()
                } catch (e: Exception) {
                    "(no body)"
                }
                connection.disconnect()
                log("  OK ($duration ms): HTTP $responseCode - ${body.take(80)}...")
                DiagResult(name, true, duration, "HTTP $responseCode: ${body.take(100)}")
            } else {
                connection.disconnect()
                log("  FAIL ($duration ms): HTTP $responseCode")
                DiagResult(name, false, duration, error = "HTTP $responseCode")
            }
        } catch (e: Exception) {
            val duration = System.currentTimeMillis() - start
            log("  ERROR ($duration ms): ${e::class.simpleName}: ${e.message}")
            DiagResult(name, false, duration, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    private fun log(message: String) {
        Log.i(TAG, message)
    }
}
