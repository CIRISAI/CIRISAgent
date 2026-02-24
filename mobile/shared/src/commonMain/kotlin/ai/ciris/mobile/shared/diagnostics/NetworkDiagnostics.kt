package ai.ciris.mobile.shared.diagnostics

import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.datetime.Clock
import kotlinx.coroutines.*

// Platform-specific logging
expect fun platformLog(tag: String, message: String)

/**
 * Network diagnostics for CIRISVerify registry connectivity.
 *
 * Tests the 3 sources:
 * 1. DNS US: _ciris-verify.us.registry.ciris-services-1.ai TXT via DoH
 * 2. DNS EU: _ciris-verify.eu.registry.ciris-services-1.ai TXT via DoH
 * 3. HTTPS: api.registry.ciris-services-1.ai
 */
object NetworkDiagnostics {

    private const val TAG = "CIRISNetDiag"

    // DNS TXT record queries via DNS-over-HTTPS
    private const val DOH_CLOUDFLARE = "https://1.1.1.1/dns-query"
    private const val DOH_GOOGLE = "https://8.8.8.8/resolve"

    private const val DNS_US_QUERY = "_ciris-verify.us.registry.ciris-services-1.ai"
    private const val DNS_EU_QUERY = "_ciris-verify.eu.registry.ciris-services-1.ai"

    // HTTPS Registry
    private const val HTTPS_REGISTRY = "https://api.registry.ciris-services-1.ai"

    data class DiagResult(
        val name: String,
        val success: Boolean,
        val durationMs: Long,
        val response: String? = null,
        val error: String? = null
    )

    /**
     * Run all diagnostics and log to console.
     * Call this from MainActivity.onCreate() to debug network issues.
     */
    suspend fun runAllDiagnostics(): List<DiagResult> {
        val results = mutableListOf<DiagResult>()

        try {
            log("========== CIRIS Network Diagnostics ==========")
            log("Testing registry connectivity from Android...")
        } catch (e: Exception) {
            log("ERROR initializing diagnostics: ${e.message}")
        }

        // Test 1: DoH via Cloudflare for US
        results.add(testDoH("DoH-Cloudflare-US", DOH_CLOUDFLARE, DNS_US_QUERY))

        // Test 2: DoH via Cloudflare for EU
        results.add(testDoH("DoH-Cloudflare-EU", DOH_CLOUDFLARE, DNS_EU_QUERY))

        // Test 3: DoH via Google for US (alternative)
        results.add(testDoHGoogle("DoH-Google-US", DOH_GOOGLE, DNS_US_QUERY))

        // Test 4: HTTPS Registry health
        results.add(testHttps("HTTPS-Registry-Health", "$HTTPS_REGISTRY/health"))

        // Test 5: HTTPS Registry root (should get 401)
        results.add(testHttps("HTTPS-Registry-Root", HTTPS_REGISTRY))

        // Test 6: Basic internet connectivity
        results.add(testHttps("Internet-Check", "https://httpbin.org/ip"))

        // Summary
        log("========== Results Summary ==========")
        results.forEach { r ->
            val status = if (r.success) "OK" else "FAIL"
            log("[$status] ${r.name}: ${r.durationMs}ms - ${r.error ?: r.response?.take(60) ?: "no response"}")
        }
        log("=====================================")

        return results
    }

    private suspend fun testDoH(name: String, dohUrl: String, query: String): DiagResult {
        log("Testing $name: $query via $dohUrl")
        val start = Clock.System.now().toEpochMilliseconds()

        return try {
            val client = HttpClient()
            val response = withTimeout(10_000) {
                client.get(dohUrl) {
                    parameter("name", query)
                    parameter("type", "TXT")
                    header("Accept", "application/dns-json")
                }
            }
            val duration = Clock.System.now().toEpochMilliseconds() - start
            val body = response.bodyAsText()
            client.close()

            if (response.status.isSuccess()) {
                log("  SUCCESS ($duration ms): ${body.take(100)}...")
                DiagResult(name, true, duration, body)
            } else {
                log("  FAIL ($duration ms): HTTP ${response.status}")
                DiagResult(name, false, duration, error = "HTTP ${response.status}")
            }
        } catch (e: Exception) {
            val duration = Clock.System.now().toEpochMilliseconds() - start
            log("  ERROR ($duration ms): ${e::class.simpleName}: ${e.message}")
            DiagResult(name, false, duration, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    private suspend fun testDoHGoogle(name: String, dohUrl: String, query: String): DiagResult {
        log("Testing $name: $query via Google DoH")
        val start = Clock.System.now().toEpochMilliseconds()

        return try {
            val client = HttpClient()
            val response = withTimeout(10_000) {
                client.get(dohUrl) {
                    parameter("name", query)
                    parameter("type", "TXT")
                }
            }
            val duration = Clock.System.now().toEpochMilliseconds() - start
            val body = response.bodyAsText()
            client.close()

            if (response.status.isSuccess()) {
                log("  SUCCESS ($duration ms): ${body.take(100)}...")
                DiagResult(name, true, duration, body)
            } else {
                log("  FAIL ($duration ms): HTTP ${response.status}")
                DiagResult(name, false, duration, error = "HTTP ${response.status}")
            }
        } catch (e: Exception) {
            val duration = Clock.System.now().toEpochMilliseconds() - start
            log("  ERROR ($duration ms): ${e::class.simpleName}: ${e.message}")
            DiagResult(name, false, duration, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    private suspend fun testHttps(name: String, url: String): DiagResult {
        log("Testing $name: $url")
        val start = Clock.System.now().toEpochMilliseconds()

        return try {
            val client = HttpClient()
            val response = withTimeout(10_000) {
                client.get(url)
            }
            val duration = Clock.System.now().toEpochMilliseconds() - start
            val body = response.bodyAsText()
            client.close()

            // 401 is expected for some endpoints, still counts as "reachable"
            val isReachable = response.status.value in 200..499
            if (isReachable) {
                log("  SUCCESS ($duration ms): HTTP ${response.status} - ${body.take(80)}...")
                DiagResult(name, true, duration, "HTTP ${response.status}: ${body.take(100)}")
            } else {
                log("  FAIL ($duration ms): HTTP ${response.status}")
                DiagResult(name, false, duration, error = "HTTP ${response.status}")
            }
        } catch (e: Exception) {
            val duration = Clock.System.now().toEpochMilliseconds() - start
            log("  ERROR ($duration ms): ${e::class.simpleName}: ${e.message}")
            DiagResult(name, false, duration, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    private fun log(message: String) {
        platformLog(TAG, message)
    }
}
