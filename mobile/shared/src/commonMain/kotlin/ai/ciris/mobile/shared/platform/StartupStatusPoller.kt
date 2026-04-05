package ai.ciris.mobile.shared.platform

/**
 * Shared startup status polling logic for all platforms.
 *
 * Polls /v1/system/startup-status and emits synthetic console output
 * for services and API startup phases. This replaces duplicated polling
 * logic in each platform's PythonRuntime implementation.
 */
class StartupStatusPoller(
    private val serverUrl: String,
    private val httpFetch: suspend (String) -> String?
) {
    // Track what we've already reported to avoid duplicates
    private var _lastReportedServiceCount = 0
    private val _reportedApiStatuses = mutableSetOf<String>()

    /**
     * Reset tracking state (call when starting a new session)
     */
    fun reset() {
        _lastReportedServiceCount = 0
        _reportedApiStatuses.clear()
    }

    /**
     * Poll startup-status endpoint and emit callback lines for new events.
     *
     * @param callback Function to receive synthetic console lines like:
     *   - "[SERVICE 1/22] TimeService STARTED"
     *   - "[STARTUP] creating_api"
     * @return StartupStatusResult with current counts, or null if poll failed
     */
    suspend fun poll(callback: (String) -> Unit): StartupStatusResult? {
        val body = httpFetch("$serverUrl/v1/system/startup-status") ?: return null

        // Parse services_online and services_total
        val onlineMatch = Regex(""""services_online"\s*:\s*(\d+)""").find(body)
        val totalMatch = Regex(""""services_total"\s*:\s*(\d+)""").find(body)
        val online = onlineMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
        val total = totalMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0

        // Parse service_names array
        val namesMatch = Regex(""""service_names"\s*:\s*\[([^\]]*)\]""").find(body)
        val serviceNames = namesMatch?.groupValues?.get(1)
            ?.split(",")
            ?.map { it.trim().trim('"') }
            ?.filter { it.isNotEmpty() }
            ?: emptyList()

        // Parse api_status_history array for catch-up on missed phases
        val historyMatch = Regex(""""api_status_history"\s*:\s*\[([^\]]*)\]""").find(body)
        val apiStatusHistory = historyMatch?.groupValues?.get(1)
            ?.split(",")
            ?.map { it.trim().trim('"') }
            ?.filter { it.isNotEmpty() }
            ?: emptyList()

        // Parse current phase
        val phaseMatch = Regex(""""phase"\s*:\s*"([^"]*)"""").find(body)
        val phase = phaseMatch?.groupValues?.get(1) ?: ""

        // Emit API status phases we haven't reported yet (in order)
        for (status in apiStatusHistory) {
            if (status.isNotEmpty() && status !in _reportedApiStatuses) {
                callback("[STARTUP] $status")
                _reportedApiStatuses.add(status)
            }
        }

        // Emit service lines for newly started services
        if (online > _lastReportedServiceCount) {
            for (i in (_lastReportedServiceCount + 1)..online) {
                val name = serviceNames.getOrElse(i - 1) { "Service$i" }
                callback("[SERVICE $i/$total] $name STARTED")
            }
            _lastReportedServiceCount = online
        }

        return StartupStatusResult(
            phase = phase,
            servicesOnline = online,
            servicesTotal = total,
            serviceNames = serviceNames,
            apiStatusHistory = apiStatusHistory
        )
    }
}

/**
 * Result from polling startup-status endpoint
 */
data class StartupStatusResult(
    val phase: String,
    val servicesOnline: Int,
    val servicesTotal: Int,
    val serviceNames: List<String>,
    val apiStatusHistory: List<String>
)
