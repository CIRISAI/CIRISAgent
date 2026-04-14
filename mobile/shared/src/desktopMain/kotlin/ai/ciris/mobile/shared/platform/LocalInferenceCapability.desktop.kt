package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Desktop implementation of the local-inference capability probe.
 *
 * Checks system RAM and disk space to determine if the desktop can run
 * llama.cpp with Gemma4. Unlike mobile, desktop doesn't auto-start the
 * server - the wizard offers the user the option to start one.
 */
actual fun probeLocalInferenceCapability(): LocalInferenceCapability {
    val runtime = Runtime.getRuntime()

    // Get total RAM in GB (maxMemory is JVM limit, we need system RAM)
    // Use OS-specific methods to get actual system RAM
    val totalRamGb = getSystemRamGb()

    // Get free disk space on the app data directory
    val homeDir = File(System.getProperty("user.home") ?: "/")
    val freeDiskGb = homeDir.freeSpace.toDouble() / (1024.0 * 1024.0 * 1024.0)

    // Minimum requirements for Gemma4 E2B: 6GB RAM, 3GB disk
    val minRamGb = 6.0
    val minDiskGb = 3.0

    return when {
        totalRamGb < minRamGb -> LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = totalRamGb,
            reason = "System has ${String.format("%.1f", totalRamGb)}GB RAM; need ${minRamGb}GB+ for local inference",
        )
        freeDiskGb < minDiskGb -> LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = totalRamGb,
            reason = "Only ${String.format("%.1f", freeDiskGb)}GB free disk; need ${minDiskGb}GB+ for model",
        )
        else -> LocalInferenceCapability(
            tier = LocalInferenceTier.DESKTOP_CAPABLE,
            totalRamGb = totalRamGb,
            reason = "System can run local llama.cpp inference (${String.format("%.1f", totalRamGb)}GB RAM)",
        )
    }
}

/**
 * Get system RAM in GB using OS-specific methods.
 */
private fun getSystemRamGb(): Double {
    // Try to read from /proc/meminfo on Linux
    try {
        val meminfo = File("/proc/meminfo")
        if (meminfo.exists()) {
            meminfo.readLines().forEach { line ->
                if (line.startsWith("MemTotal:")) {
                    val kb = line.split(Regex("\\s+"))[1].toLongOrNull() ?: 0L
                    return kb.toDouble() / (1024.0 * 1024.0)
                }
            }
        }
    } catch (_: Exception) { }

    // Try using com.sun.management for macOS/Windows
    try {
        val osBean = java.lang.management.ManagementFactory.getOperatingSystemMXBean()
        val method = osBean.javaClass.getMethod("getTotalPhysicalMemorySize")
        method.isAccessible = true
        val bytes = method.invoke(osBean) as Long
        return bytes.toDouble() / (1024.0 * 1024.0 * 1024.0)
    } catch (_: Exception) { }

    // Fallback: use JVM max memory as a rough estimate (will underreport)
    return Runtime.getRuntime().maxMemory().toDouble() / (1024.0 * 1024.0 * 1024.0)
}
