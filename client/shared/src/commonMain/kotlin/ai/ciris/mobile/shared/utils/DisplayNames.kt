package ai.ciris.mobile.shared.utils

/**
 * Utility for converting technical names to human-friendly display names.
 * Mirrors backend SERVICE_NAME_MAPPING from telemetry_service/helpers.py
 */
object DisplayNames {

    // Service name mappings (mirrors backend SERVICE_NAME_MAPPING)
    private val serviceNames = mapOf(
        // Graph services
        "memory_service" to "Memory",
        "memoryservice" to "Memory",
        "localgraphmemoryservice" to "Memory",
        "config_service" to "Configuration",
        "configservice" to "Configuration",
        "graphconfigservice" to "Configuration",
        "telemetry_service" to "Telemetry",
        "telemetryservice" to "Telemetry",
        "audit_service" to "Audit",
        "auditservice" to "Audit",
        "incident_service" to "Incident Management",
        "incidentservice" to "Incident Management",
        "tsdb_consolidation_service" to "Time-Series DB",
        "tsdbconsolidationservice" to "Time-Series DB",
        "consent_service" to "Consent",
        "consentservice" to "Consent",

        // Infrastructure services
        "authentication_service" to "Authentication",
        "authenticationservice" to "Authentication",
        "resource_monitor" to "Resource Monitor",
        "resourcemonitor" to "Resource Monitor",
        "database_maintenance" to "Database",
        "databasemaintenance" to "Database",
        "secrets_service" to "Secrets",
        "secretsservice" to "Secrets",
        "secretstoolservice" to "Secrets Tool",

        // Lifecycle services
        "initialization_service" to "Initialization",
        "initializationservice" to "Initialization",
        "shutdown_service" to "Shutdown",
        "shutdownservice" to "Shutdown",
        "time_service" to "Time",
        "timeservice" to "Time",
        "task_scheduler" to "Task Scheduler",
        "taskscheduler" to "Task Scheduler",

        // Governance services
        "wise_authority" to "Wise Authority",
        "wiseauthority" to "Wise Authority",
        "wiseauthorityservice" to "Wise Authority",
        "adaptive_filter" to "Adaptive Filter",
        "adaptivefilter" to "Adaptive Filter",
        "adaptivefilterservice" to "Adaptive Filter",
        "visibility_service" to "Visibility",
        "visibilityservice" to "Visibility",
        "self_observation" to "Self-Observation",
        "selfobservation" to "Self-Observation",
        "selfobservationservice" to "Self-Observation",

        // Runtime services
        "llm_service" to "LLM",
        "llmservice" to "LLM",
        "runtime_control" to "Runtime Control",
        "runtimecontrol" to "Runtime Control",
        "runtimecontrolservice" to "Runtime Control",

        // Tool services
        "secrets_tool" to "Secrets Tool",
        "secretstool" to "Secrets Tool",
        "coretoolservice" to "Core Tools",
        "apitoolservice" to "API Tools",

        // Adapter-provided services
        "accordmetricsservice" to "Accord Metrics",
        "cirisverifyservice" to "CIRIS Verify",
        "openaicompatibleclient" to "OpenAI Client",

        // CIRIS LLM services
        "ciris_primary" to "CIRIS Primary",
        "cirisprimary" to "CIRIS Primary",
        "ciris_secondary" to "CIRIS Secondary",
        "cirissecondary" to "CIRIS Secondary",
        "ciris" to "CIRIS"
    )

    // Status label mappings
    private val statusLabels = mapOf(
        "closed" to "Healthy",
        "open" to "Error",
        "half_open" to "Recovering",
        "fallback" to "Backup",
        "running" to "Running",
        "stopped" to "Stopped",
        "error" to "Error",
        "initializing" to "Starting",
        "degraded" to "Degraded"
    )

    // Strategy label mappings
    private val strategyLabels = mapOf(
        "fallback" to "Backup",
        "primary" to "Primary",
        "round_robin" to "Load Balanced",
        "random" to "Random",
        "weighted" to "Weighted"
    )

    // Category label mappings
    private val categoryLabels = mapOf(
        "unknown" to "Adapter Services",
        "graph" to "Graph Services",
        "infrastructure" to "Infrastructure",
        "lifecycle" to "Lifecycle",
        "governance" to "Governance",
        "runtime" to "Runtime",
        "tools" to "Tools",
        "adapters" to "Adapters"
    )

    /**
     * Convert a service class name to a human-friendly display name.
     * Examples:
     *   "GraphConfigService" -> "Configuration"
     *   "WiseAuthorityService" -> "Wise Authority"
     *   "OpenAICompatibleClient" -> "OpenAI Client"
     */
    fun humanizeServiceName(className: String): String {
        val normalized = className.lowercase()
            .replace("_", "")
            .trim()

        // Try direct lookup
        serviceNames[normalized]?.let { return it }

        // Fallback: convert PascalCase/snake_case to Title Case
        return className
            .replace("Service", "")
            .replace("_", " ")
            .replace(Regex("([a-z])([A-Z])")) { "${it.groupValues[1]} ${it.groupValues[2]}" }
            .trim()
            .split(" ")
            .joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }
    }

    /**
     * Convert a status string to a human-friendly label.
     * Examples:
     *   "closed" -> "Healthy"
     *   "FALLBACK" -> "Backup"
     */
    fun humanizeStatus(status: String): String {
        return statusLabels[status.lowercase()]
            ?: status.replaceFirstChar { it.uppercase() }
    }

    /**
     * Convert a strategy string to a human-friendly label.
     */
    fun humanizeStrategy(strategy: String): String {
        return strategyLabels[strategy.lowercase()]
            ?: strategy.replaceFirstChar { it.uppercase() }
    }

    /**
     * Convert a category name to a human-friendly label.
     * Specifically handles "UNKNOWN" -> "Adapter Services"
     */
    fun humanizeCategory(category: String): String {
        return categoryLabels[category.lowercase()]
            ?: category.replaceFirstChar { it.uppercase() }
    }

    /**
     * Convert a config key to a human-friendly label.
     * Examples:
     *   "user_agent" -> "User Agent"
     *   "apiKey" -> "API Key"
     */
    fun humanizeConfigKey(key: String): String {
        return key
            .replace("_", " ")
            .replace(Regex("([a-z])([A-Z])")) { "${it.groupValues[1]} ${it.groupValues[2]}" }
            .split(" ")
            .joinToString(" ") { word ->
                when (word.lowercase()) {
                    "api" -> "API"
                    "url" -> "URL"
                    "id" -> "ID"
                    "llm" -> "LLM"
                    "oauth" -> "OAuth"
                    else -> word.replaceFirstChar { it.uppercase() }
                }
            }
    }

    /**
     * Format uptime seconds to a human-readable string.
     * Examples:
     *   3600 -> "1h 0m"
     *   90 -> "1m 30s"
     *   45 -> "45s"
     */
    fun formatUptime(seconds: Float): String {
        val totalSeconds = seconds.toLong()
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val secs = totalSeconds % 60

        return when {
            hours > 0 -> "${hours}h ${minutes}m"
            minutes > 0 -> "${minutes}m ${secs}s"
            else -> "${secs}s"
        }
    }
}
