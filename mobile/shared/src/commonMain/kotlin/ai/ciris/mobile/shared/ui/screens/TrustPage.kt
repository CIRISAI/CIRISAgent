package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.DeviceAttestationCallback
import ai.ciris.mobile.shared.DeviceAttestationResult
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Trust Page - Full-page view of CIRISVerify attestation status
 *
 * Shows detailed attestation information for each of the 5 levels:
 * - Level 1: Binary Loaded
 * - Level 2: Environment
 * - Level 3: Registry Cross-Validation
 * - Level 4: File Integrity
 * - Level 5: Full Trust (Portal Key + Audit)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TrustPage(
    apiClient: CIRISApiClient,
    onNavigateBack: () -> Unit,
    deviceAttestationCallback: DeviceAttestationCallback? = null,
    modifier: Modifier = Modifier
) {
    var verifyStatus by remember { mutableStateOf<VerifyStatusResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val coroutineScope = rememberCoroutineScope()

    // Device attestation state (App Attest on iOS, Play Integrity on Android)
    var deviceAttestationResult by remember { mutableStateOf<DeviceAttestationResult?>(null) }
    var deviceAttestationLoading by remember { mutableStateOf(false) }

    val uriHandler = LocalUriHandler.current
    val clipboardManager = LocalClipboardManager.current

    // Trigger device attestation on mount if callback available
    LaunchedEffect(deviceAttestationCallback) {
        if (deviceAttestationCallback != null && deviceAttestationResult == null) {
            deviceAttestationLoading = true
            deviceAttestationCallback.onDeviceAttestationRequested { result ->
                deviceAttestationResult = result
                deviceAttestationLoading = false
            }
        }
    }

    // Fetch verify status on mount (always full mode from cached attestation)
    LaunchedEffect(Unit) {
        fetchVerifyStatus(
            apiClient = apiClient,
            onSuccess = { verifyStatus = it; loading = false; error = null },
            onError = { error = it; loading = false }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Trust & Security") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = {
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        },
                        enabled = !loading
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Conditional rendering based on state (no early returns!)
            when {
                loading -> {
                    LoadingCard()
                }
                error != null || verifyStatus?.loaded != true -> {
                    ErrorCard(
                        error = error ?: verifyStatus?.error ?: "Unknown error",
                        onRetry = {
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        }
                    )
                }
                else -> {
                    val status = verifyStatus!!

                    // Header card with summary
                    TrustSummaryCard(status = status)

                    // 5 Expandable Tier Cards - consolidated view
                    TierCardsSection(
                        status = status,
                        deviceAttestationResult = deviceAttestationResult,
                        deviceAttestationLoading = deviceAttestationLoading,
                        onCopyDiagnostics = {
                            clipboardManager.setText(AnnotatedString(status.diagnosticInfo ?: "No diagnostics"))
                        }
                    )

                    // Learn more link
                    Text(
                        text = "Learn more about CIRISVerify",
                        fontSize = 14.sp,
                        color = Color(0xFF2563EB),
                        textDecoration = TextDecoration.Underline,
                        modifier = Modifier
                            .clickable { uriHandler.openUri("https://ciris.ai/trust") }
                            .padding(8.dp)
                    )
                }
            }
        }
    }
}

private suspend fun fetchVerifyStatus(
    apiClient: CIRISApiClient,
    onSuccess: (VerifyStatusResponse) -> Unit,
    onError: (String) -> Unit
) {
    try {
        val result = withContext(Dispatchers.IO) {
            // Always use full mode - gets cached attestation from /v1/auth/attestation
            apiClient.getVerifyStatus()
        }
        onSuccess(result)
    } catch (e: Exception) {
        onError(e.message ?: "Failed to fetch verify status")
    }
}

@Composable
private fun LoadingCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF5F5F5))
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            CircularProgressIndicator(color = Color(0xFF059669))
            Text("Running attestation checks...", color = Color(0xFF6B7280))
        }
    }
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFEE2E2))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "Attestation Failed",
                fontWeight = FontWeight.Bold,
                color = Color(0xFFDC2626)
            )
            Text(
                text = error,
                fontSize = 14.sp,
                color = Color(0xFF991B1B)
            )
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDC2626))
            ) {
                Text("Retry")
            }
        }
    }
}

@Composable
private fun TrustSummaryCard(
    status: VerifyStatusResponse
) {
    // Use backend's authoritative level calculation
    val level = status.maxLevel

    // Check if current level has partial passes (for yellow state)
    val sourcesOk = (status.sourcesAgreeing ?: 0) >= 2
    val portalKeyOk = status.registryKeyStatus?.contains("active", ignoreCase = true) == true
    val isPartial = when (level) {
        1 -> status.envOk || status.playIntegrityOk  // Some L2 checks pass
        2 -> sourcesOk || status.fileIntegrityOk  // Some L3/L4 checks pass
        3 -> status.fileIntegrityOk  // L4 passes
        4 -> status.auditOk || portalKeyOk  // Some L5 checks pass
        else -> false
    }

    val bgColor = when {
        level >= 5 -> Color(0xFFD1FAE5)  // Green
        level >= 3 -> Color(0xFFDBEAFE)  // Blue
        isPartial -> Color(0xFFFEF3C7)   // Yellow (partial)
        level >= 1 -> Color(0xFFFEF3C7)  // Yellow
        else -> Color(0xFFF5F5F5)        // Gray
    }
    val textColor = when {
        level >= 5 -> Color(0xFF065F46)
        level >= 3 -> Color(0xFF1E40AF)
        level >= 1 -> Color(0xFF92400E)
        else -> Color(0xFF6B7280)
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Shield with level
            Text(text = "🛡", fontSize = 48.sp)

            Text(
                text = "Attestation Level $level/5",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = textColor
            )

            Text(
                text = when {
                    level >= 5 -> "Full Attestation State - All checks passed"
                    level >= 4 -> "High Attestation - Integrity checks passed"
                    level >= 3 -> "Good Attestation - Registry validation complete"
                    level >= 2 -> "Basic Attestation - Environment validation complete"
                    level >= 1 -> "Minimal Attestation - Binary loaded"
                    status.attestationStatus == "not_attempted" -> "Incomplete - Attestation not started"
                    else -> "Level 0 - No checks passed"
                },
                fontSize = 14.sp,
                color = textColor.copy(alpha = 0.8f)
            )

            // Version badge
            status.version?.let { version ->
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = textColor.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = "CIRISVerify v$version",
                        fontSize = 12.sp,
                        color = textColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Timestamp badge showing when attestation was performed
            status.cachedAt?.let { timestamp ->
                Text(
                    text = "Verify Last Ran: ${formatAttestationTimestamp(timestamp)}",
                    fontSize = 11.sp,
                    color = textColor.copy(alpha = 0.6f)
                )
            }
        }
    }
}

/** Format ISO 8601 timestamp for display with microseconds and UTC */
private fun formatAttestationTimestamp(timestamp: String): String {
    return try {
        // Format: 2026-02-25T15:02:44.666000+00:00 -> 2026-02-25 15:02:44.666000 UTC
        val date = timestamp.substringBefore("T")
        val timeWithMicros = timestamp.substringAfter("T").substringBefore("+").substringBefore("-")
        "$date $timeWithMicros UTC"
    } catch (e: Exception) {
        timestamp.substringBefore("+").replace("T", " ") + " UTC"
    }
}

@Composable
private fun AttestationLevelsCard(status: VerifyStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Attestation Checks",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = "Like a DMV check for AI - each level builds trust",
                fontSize = 12.sp,
                color = Color(0xFF6B7280)
            )

            // Level 1: Binary
            AttestationLevel(
                level = 1,
                title = "Binary Loaded",
                description = "CIRISVerify engine is running and responding",
                passed = status.binaryOk,
                previousFailed = false
            )

            // Level 2: Environment
            AttestationLevel(
                level = 2,
                title = "Environment",
                description = "Platform: ${status.platformOs?.uppercase() ?: "Unknown"} • HW: ${status.hardwareType?.replace("_", " ") ?: "Unknown"}",
                passed = status.envOk,
                previousFailed = !status.binaryOk
            )

            // Level 3: Network
            val networkPassed = listOf(status.dnsUsOk, status.dnsEuOk, status.httpsUsOk || status.httpsEuOk).count { it }
            AttestationLevel(
                level = 3,
                title = "Registry Cross-Validation ($networkPassed/3)",
                description = "HTTPS authoritative, DNS advisory (need 2/3 agreement)",
                passed = networkPassed >= 2,
                previousFailed = !status.binaryOk || !status.envOk,
                extraContent = {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NetworkBadge("US", status.dnsUsOk)
                        NetworkBadge("EU", status.dnsEuOk)
                        NetworkBadge("HTTPS", status.httpsUsOk || status.httpsEuOk)
                    }
                }
            )

            // Level 4: File Integrity
            val anyLowerFailed = !status.binaryOk || !status.envOk || networkPassed < 2
            AttestationLevel(
                level = 4,
                title = "File Integrity",
                description = if (status.filesChecked != null && status.filesChecked > 0) {
                    "Verified ${status.filesPassed ?: 0}/${status.filesChecked} files (${status.attestationMode})"
                } else {
                    "Software matches registry-hosted manifest"
                },
                passed = status.fileIntegrityOk,
                previousFailed = anyLowerFailed
            )

            // Level 5: Full Attestation State
            val anyBelow5Failed = anyLowerFailed || !status.fileIntegrityOk
            AttestationLevel(
                level = 5,
                title = "Full Attestation State",
                description = "Genesis key from CIRISPortal + no tampering detected in audit chain",
                passed = status.registryOk && status.auditOk,
                previousFailed = anyBelow5Failed,
                extraContent = {
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        StatusBadge("Portal Key", status.registryOk)
                        StatusBadge("Audit Trail", status.auditOk)
                    }
                }
            )
        }
    }
}

@Composable
private fun DeviceAttestationCard(
    status: VerifyStatusResponse,
    deviceAttestationResult: DeviceAttestationResult? = null,
    deviceAttestationLoading: Boolean = false
) {
    val isAndroid = status.platformOs?.lowercase() == "android"
    val isIos = status.platformOs?.lowercase() in listOf("ios", "ipados", "macos")

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Device Attestation",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = "Single-party device integrity verification from platform vendor",
                fontSize = 12.sp,
                color = Color(0xFF6B7280)
            )

            when {
                isAndroid -> {
                    // Google Play Integrity - use native result if available
                    val (passed, verdict, verdictItems) = when (deviceAttestationResult) {
                        is DeviceAttestationResult.Success -> Triple(
                            deviceAttestationResult.verified,
                            deviceAttestationResult.verdict,
                            listOf(
                                "Strong Integrity" to deviceAttestationResult.meetsStrongIntegrity,
                                "Device Integrity" to deviceAttestationResult.meetsDeviceIntegrity,
                                "Basic Integrity" to deviceAttestationResult.meetsBasicIntegrity
                            )
                        )
                        is DeviceAttestationResult.Error -> Triple(
                            false,
                            "Error: ${deviceAttestationResult.message}",
                            emptyList()
                        )
                        is DeviceAttestationResult.NotSupported -> Triple(
                            false,
                            "Not supported",
                            emptyList()
                        )
                        null -> Triple(
                            status.playIntegrityOk,
                            status.playIntegrityVerdict ?: if (deviceAttestationLoading) "Checking..." else "Not checked",
                            parsePlayIntegrityVerdict(status.playIntegrityVerdict ?: "")
                        )
                    }

                    val color = when {
                        deviceAttestationLoading -> Color(0xFF6B7280)
                        passed -> Color(0xFF059669)
                        else -> Color(0xFFD97706)
                    }
                    val icon = when {
                        deviceAttestationLoading -> "⋯"
                        passed -> "✓"
                        else -> "○"
                    }

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(color.copy(alpha = 0.05f), RoundedCornerShape(8.dp))
                            .padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = icon,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = color
                            )
                            Text(
                                text = "Google Play Integrity",
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                color = color
                            )
                        }

                        // Verdict badges
                        Column(
                            modifier = Modifier.padding(start = 22.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            verdictItems.forEach { (label, ok) ->
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = if (ok) "●" else "○",
                                        fontSize = 8.sp,
                                        color = if (ok) Color(0xFF059669) else Color(0xFFD97706)
                                    )
                                    Text(
                                        text = label,
                                        fontSize = 12.sp,
                                        color = if (ok) Color(0xFF059669) else Color(0xFF6B7280)
                                    )
                                }
                            }
                        }

                        Text(
                            text = "Validates: genuine app, unmodified device, Google Play Services",
                            fontSize = 11.sp,
                            color = Color(0xFF9CA3AF),
                            modifier = Modifier.padding(start = 22.dp)
                        )
                    }
                }
                isIos -> {
                    // Apple App Attest (placeholder for future)
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xFF6B7280).copy(alpha = 0.05f), RoundedCornerShape(8.dp))
                            .padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = "○",
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF6B7280)
                            )
                            Text(
                                text = "Apple App Attest",
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                color = Color(0xFF6B7280)
                            )
                        }
                        Text(
                            text = "Not yet implemented - coming soon",
                            fontSize = 12.sp,
                            color = Color(0xFF9CA3AF),
                            modifier = Modifier.padding(start = 22.dp)
                        )
                    }
                }
                else -> {
                    // Desktop/other - no device attestation available
                    Text(
                        text = "Device attestation not available on ${status.platformOs ?: "this platform"}",
                        fontSize = 12.sp,
                        color = Color(0xFF9CA3AF)
                    )
                }
            }

            // Disclaimer
            Text(
                text = "Device attestation is independent of software attestation levels above",
                fontSize = 11.sp,
                color = Color(0xFF9CA3AF)
            )
        }
    }
}

/**
 * Parse Play Integrity verdict string into display items
 */
private fun parsePlayIntegrityVerdict(verdict: String): List<Pair<String, Boolean>> {
    return when {
        verdict.contains("MEETS_STRONG_INTEGRITY", ignoreCase = true) -> listOf(
            "App Integrity" to true,
            "Device Integrity" to true,
            "Strong Integrity" to true
        )
        verdict.contains("MEETS_DEVICE_INTEGRITY", ignoreCase = true) -> listOf(
            "App Integrity" to true,
            "Device Integrity" to true,
            "Strong Integrity" to false
        )
        verdict.contains("MEETS_BASIC_INTEGRITY", ignoreCase = true) -> listOf(
            "App Integrity" to true,
            "Device Integrity" to false,
            "Strong Integrity" to false
        )
        verdict == "Not checked" || verdict.isBlank() -> listOf(
            "App Integrity" to false,
            "Device Integrity" to false,
            "Strong Integrity" to false
        )
        else -> listOf(
            "Status" to false
        )
    }
}

@Composable
private fun AttestationLevel(
    level: Int,
    title: String,
    description: String,
    passed: Boolean,
    previousFailed: Boolean,
    extraContent: @Composable (() -> Unit)? = null
) {
    val unverified = previousFailed && passed
    val color = when {
        !passed -> Color(0xFFDC2626)
        unverified -> Color(0xFFD97706)
        else -> Color(0xFF059669)
    }
    val icon = when {
        !passed -> "✗"
        unverified -> "?"
        else -> "✓"
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(color.copy(alpha = 0.05f), RoundedCornerShape(8.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = icon,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = color
            )
            Text(
                text = "Level $level: $title",
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                color = color
            )
        }
        Text(
            text = description,
            fontSize = 12.sp,
            color = Color(0xFF6B7280),
            modifier = Modifier.padding(start = 22.dp)
        )
        extraContent?.let {
            Box(modifier = Modifier.padding(start = 22.dp, top = 4.dp)) {
                it()
            }
        }
    }
}

@Composable
private fun NetworkBadge(label: String, passed: Boolean) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        Text(
            text = if (passed) "●" else "○",
            fontSize = 8.sp,
            color = if (passed) Color(0xFF059669) else Color(0xFFDC2626)
        )
        Text(
            text = label,
            fontSize = 10.sp,
            color = if (passed) Color(0xFF059669) else Color(0xFF6B7280)
        )
    }
}

@Composable
private fun StatusBadge(label: String, passed: Boolean) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(
            text = if (passed) "✓" else "✗",
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            color = if (passed) Color(0xFF059669) else Color(0xFFDC2626)
        )
        Text(
            text = label,
            fontSize = 11.sp,
            color = if (passed) Color(0xFF059669) else Color(0xFFDC2626)
        )
    }
}

@Composable
private fun PlatformInfoCard(status: VerifyStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text("Platform Attestation", fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                status.platformOs?.let {
                    Text("OS: $it", fontSize = 12.sp, color = Color(0xFF6B7280))
                }
                status.platformArch?.let {
                    Text("Arch: $it", fontSize = 12.sp, color = Color(0xFF6B7280))
                }
            }
            status.hardwareType?.let {
                Text("Hardware: ${it.replace("_", " ")}", fontSize = 12.sp, color = Color(0xFF6B7280))
            }
        }
    }
}

@Composable
private fun FileIntegrityCard(status: VerifyStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text("File Integrity Details", fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("Checked: ${status.filesChecked}", fontSize = 12.sp, color = Color(0xFF6B7280))
                Text("Passed: ${status.filesPassed ?: 0}", fontSize = 12.sp, color = Color(0xFF059669))
                if ((status.filesFailed ?: 0) > 0) {
                    Text("Failed: ${status.filesFailed}", fontSize = 12.sp, color = Color(0xFFDC2626))
                }
            }
            status.integrityFailureReason?.let { reason ->
                // Parse multiple reason segments (separated by ;)
                // Format: "unexpected_files:N|file1,file2;expected_excluded:N|file1,file2"
                val segments = reason.split(";")

                for (segment in segments) {
                    val (displayReason, fileList, isExpected) = when {
                        segment.startsWith("expected_excluded:") -> {
                            val parts = segment.substringAfter("expected_excluded:").split("|", limit = 2)
                            val count = parts[0].toIntOrNull() ?: 0
                            val files = if (parts.size > 1) parts[1] else null
                            Triple("$count expected excluded file(s) (verification wrapper)", files, true)
                        }
                        segment.startsWith("unexpected_files:") -> {
                            val parts = segment.substringAfter("unexpected_files:").split("|", limit = 2)
                            val count = parts[0].toIntOrNull() ?: 0
                            val files = if (parts.size > 1) parts[1] else null
                            Triple("$count unexpected Python file(s) found not in manifest", files, false)
                        }
                        segment == "unexpected" -> Triple("Unexpected files found not in manifest", null, false)
                        segment == "modified" -> Triple("Files have been modified (hash mismatch)", null, false)
                        segment == "missing" -> Triple("Required files are missing", null, false)
                        segment == "manifest" -> Triple("Invalid or tampered manifest", null, false)
                        else -> Triple(segment, null, false)
                    }
                    // Use green for expected excluded, amber for unexpected, red for errors
                    val reasonColor = when {
                        isExpected -> Color(0xFF059669)  // Green - expected/OK
                        segment.startsWith("unexpected") -> Color(0xFFD97706)  // Amber - warning
                        else -> Color(0xFFDC2626)  // Red - error
                    }
                    val label = if (isExpected) "Info" else "Reason"
                    Text("$label: $displayReason", fontSize = 12.sp, color = reasonColor)
                    // Show file list if available
                    fileList?.let { files ->
                        Text("Files: $files", fontSize = 10.sp, color = Color(0xFF6B7280), fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                    }
                }
            }
        }
    }
}

/**
 * 5 Expandable Tier Cards - consolidates all attestation details into collapsible sections
 */
@Composable
private fun TierCardsSection(
    status: VerifyStatusResponse,
    deviceAttestationResult: DeviceAttestationResult?,
    deviceAttestationLoading: Boolean,
    onCopyDiagnostics: () -> Unit
) {
    var expandedTier by remember { mutableStateOf<Int?>(null) }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // L1: Binary & Self-Verification
        // Check if keystore is software-only (no hardware encryption)
        // Key is hardware-backed if: hardware_backed=true AND key_storage_mode contains "HW"
        // attestation_proof.hardware_type refers to Ed25519 signing, not storage encryption
        val hasHardwareStorage = status.hardwareBacked &&
            status.keyStorageMode?.contains("HW", ignoreCase = true) == true
        val isSoftwareKeystore = !hasHardwareStorage
        ExpandableTierCard(
            level = 1,
            title = "Binary Loaded",
            passed = status.binarySelfCheck == "verified",
            checksInfo = buildL1ChecksInfo(status),
            expanded = expandedTier == 1,
            onToggle = { expandedTier = if (expandedTier == 1) null else 1 },
            partial = isSoftwareKeystore  // Yellow if software-backed keystore
        ) {
            L1Content(status)
        }

        // L2: Environment & Device Attestation
        val deviceOk = (deviceAttestationResult as? DeviceAttestationResult.Success)?.verified == true
        ExpandableTierCard(
            level = 2,
            title = "Environment",
            passed = status.hardwareBacked && (deviceOk || status.playIntegrityOk),
            checksInfo = buildL2ChecksInfo(status, deviceAttestationResult),
            expanded = expandedTier == 2,
            onToggle = { expandedTier = if (expandedTier == 2) null else 2 }
        ) {
            L2Content(status, deviceAttestationResult, deviceAttestationLoading)
        }

        // L3: Registry Cross-Validation - requires at least 2/3 sources to agree
        val l3SourcesAgreeing = status.sourcesAgreeing ?: 0
        ExpandableTierCard(
            level = 3,
            title = "Registry Network",
            passed = l3SourcesAgreeing >= 2,
            checksInfo = buildL3ChecksInfo(status),
            expanded = expandedTier == 3,
            onToggle = { expandedTier = if (expandedTier == 3) null else 3 }
        ) {
            L3Content(status)
        }

        // L4: Agent Code Integrity
        ExpandableTierCard(
            level = 4,
            title = "Agent Code Integrity",
            passed = status.fileIntegrityOk,
            checksInfo = buildL4ChecksInfo(status),
            expanded = expandedTier == 4,
            onToggle = { expandedTier = if (expandedTier == 4) null else 4 }
        ) {
            L4Content(status)
        }

        // L5: Full Attestation & Audit
        ExpandableTierCard(
            level = 5,
            title = "Registry & Audit",
            passed = status.auditOk && status.registryKeyStatus?.contains("active", ignoreCase = true) == true,
            checksInfo = buildL5ChecksInfo(status),
            expanded = expandedTier == 5,
            onToggle = { expandedTier = if (expandedTier == 5) null else 5 }
        ) {
            L5Content(status, onCopyDiagnostics)
        }

        // Verify Log (expandable)
        DiagnosticsLogCard(
            diagnostics = status.diagnosticInfo,
            onCopy = onCopyDiagnostics
        )
    }
}

@Composable
private fun ExpandableTierCard(
    level: Int,
    title: String,
    passed: Boolean,
    checksInfo: String,
    expanded: Boolean,
    onToggle: () -> Unit,
    partial: Boolean = false,  // Yellow/warning state (e.g., software-backed keystore)
    content: @Composable ColumnScope.() -> Unit
) {
    val levelColor = when {
        passed && !partial -> Color(0xFF059669)  // Green - fully passed
        partial -> Color(0xFFF59E0B)              // Yellow/amber - partial/warning
        else -> Color(0xFFDC2626)                 // Red - failed
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Column {
            // Header (always visible)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggle() }
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Level badge
                    Text(
                        text = "L$level",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                        modifier = Modifier
                            .background(levelColor, RoundedCornerShape(4.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                    Column {
                        Text(
                            text = title,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 14.sp
                        )
                        Text(
                            text = checksInfo,
                            fontSize = 11.sp,
                            color = Color(0xFF6B7280)
                        )
                    }
                }
                // Expand icon
                Text(
                    text = if (expanded) "▼" else "▶",
                    fontSize = 12.sp,
                    color = Color(0xFF9CA3AF)
                )
            }

            // Expanded content
            if (expanded) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFFF9FAFB))
                        .padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    content = content
                )
            }
        }
    }
}

// Helper functions to build check info strings
private fun buildL1ChecksInfo(status: VerifyStatusResponse): String {
    val binaryOk = status.binarySelfCheck == "verified"
    val funcOk = status.functionSelfCheck == "verified" || status.functionIntegrity == "verified"
    val passed = listOf(binaryOk, funcOk).count { it }
    return "$passed/2 checks • ${if (binaryOk) "Binary ✓" else "Binary ✗"}"
}

private fun buildL2ChecksInfo(status: VerifyStatusResponse, deviceResult: DeviceAttestationResult?): String {
    val isIos = status.platformOs?.lowercase() in listOf("ios", "ipados") ||
        status.hardwareType?.contains("IOS", ignoreCase = true) == true
    val hwOk = status.hardwareBacked
    val playOk = (deviceResult as? DeviceAttestationResult.Success)?.verified == true || status.playIntegrityOk
    val passed = listOf(hwOk, playOk).count { it }
    val attestLabel = if (isIos) "Attest" else "Play"
    return "$passed/2 checks • HW: ${if (hwOk) "✓" else "○"} $attestLabel: ${if (playOk) "✓" else "○"}"
}

private fun buildL3ChecksInfo(status: VerifyStatusResponse): String {
    // Registry cross-validation uses 3 sources (DNS US, DNS EU, HTTPS)
    val sources = 3
    val agreement = status.sourcesAgreeing ?: 0
    val icon = when {
        agreement >= 3 -> "✓"
        agreement >= 2 -> "◐"  // Partial (2/3 is still passing)
        else -> "✗"  // Failing (0-1/3)
    }
    return "$agreement/$sources sources • $icon"
}

private fun buildL4ChecksInfo(status: VerifyStatusResponse): String {
    // v0.9.7+: Use unified module_integrity summary when available
    val summary = status.moduleIntegritySummary
    if (summary != null) {
        val totalManifest = summary["total_manifest"] ?: 0
        val verified = summary["verified"] ?: 0
        val failed = summary["failed"] ?: 0
        // Use mobileExcludedCount (server-only files like discord, gui_static)
        val mobileExcluded = status.mobileExcludedCount ?: 0
        val expected = totalManifest - mobileExcluded

        return if (failed > 0) {
            "$verified/$expected • $failed failed"
        } else {
            "$verified/$expected files"
        }
    }

    // Legacy fallback
    val perFile = status.perFileResults ?: emptyMap()
    val manifestTotal = perFile.size.takeIf { it > 0 } ?: (status.filesChecked ?: 0)
    val mobileExcluded = status.mobileExcludedCount ?: 0
    val totalExpected = manifestTotal - mobileExcluded

    // Mobile excluded set for filtering
    val mobileExcludedSet = (status.mobileExcludedList ?: emptyList()).toSet()

    // Filesystem verified files (excluding mobile-excluded)
    val filesystemVerified = perFile.filterValues { it == "passed" }.keys.count { it !in mobileExcludedSet }

    // Chaquopy verified = Python files in manifest marked "missing" (verified via hash, not filesystem)
    val chaquopyCovered = perFile.filterValues { it == "missing" }.keys.count { path ->
        (path.endsWith(".py") || path.endsWith(".pyi")) && path !in mobileExcludedSet
    }

    // Total verified = filesystem (filtered) + Chaquopy
    val totalVerified = filesystemVerified + chaquopyCovered
    val failed = status.filesFailed ?: 0

    return if (failed > 0) {
        "$totalVerified/$totalExpected • $failed failed"
    } else {
        "$totalVerified/$totalExpected files"
    }
}

private fun buildL5ChecksInfo(status: VerifyStatusResponse): String {
    val keyOk = status.registryKeyStatus?.contains("active", ignoreCase = true) == true
    val auditOk = status.auditOk
    val passed = listOf(keyOk, auditOk).count { it }
    return "$passed/2 checks • Key: ${if (keyOk) "✓" else "○"} Audit: ${if (auditOk) "✓" else "○"}"
}

// L1 Content: Binary & Self-Verification
@Composable
private fun L1Content(status: VerifyStatusResponse) {
    // Identity Key - check for hardware-backed storage
    // Ed25519 signing key is wrapped (encrypted) by HW key if: hardware_backed=true AND key_storage_mode contains "HW"
    val hasHardwareStorage = status.hardwareBacked &&
        status.keyStorageMode?.contains("HW", ignoreCase = true) == true
    val isSoftwareOnly = !hasHardwareStorage
    val keyIcon = when {
        isSoftwareOnly -> "⚠️"  // Warning for software-only
        status.hardwareBacked -> "🔐"  // Hardware-backed
        else -> "🔑"  // Unknown/software
    }
    val storageMode = status.keyStorageMode ?: (if (status.hardwareBacked) "Hardware-backed" else "Software")
    val displayValue = if (isSoftwareOnly) {
        "$storageMode (Software-Only)"
    } else {
        storageMode
    }
    DetailRow(
        icon = keyIcon,
        label = "Identity Key (Ed25519)",
        value = displayValue,
        ok = !isSoftwareOnly,
        pending = isSoftwareOnly  // Yellow/warning for software-only
    )
    if (hasHardwareStorage) {
        DetailSubtext("✓ Ed25519 key wrapped by hardware-stored AES key")
    } else if (isSoftwareOnly) {
        DetailSubtext("⚠️ No hardware security module - keys protected by OS only")
    }
    status.ed25519Fingerprint?.let {
        DetailSubtext("Fingerprint: ${it.take(20)}...")
    }

    // Target
    val target = status.targetTriple ?: "${status.platformArch ?: "?"}-${status.platformOs?.lowercase() ?: "?"}"
    DetailRow(icon = "📦", label = "Registry Target", value = target, ok = true)

    // Binary Hash
    val binaryOk = status.binarySelfCheck == "verified"
    DetailRow(
        label = "Binary Hash",
        value = if (binaryOk) "Verified" else (status.binarySelfCheck ?: "Unknown"),
        ok = binaryOk
    )
    status.binaryHash?.let { DetailSubtext("Local: ${it.take(20)}...") }

    // Function Integrity
    val funcStatus = status.functionSelfCheck ?: status.functionIntegrity ?: "not_checked"
    val funcOk = funcStatus == "verified"
    DetailRow(
        label = "Function Integrity",
        value = if (funcOk) "Verified" else funcStatus.replaceFirstChar { it.uppercase() },
        ok = funcOk
    )
    if (status.functionsChecked != null && status.functionsChecked > 0) {
        DetailSubtext("${status.functionsPassed ?: 0}/${status.functionsChecked} functions passed")
    }
    // Show failed functions if available
    val failedFuncs = status.functionsFailedList ?: emptyList()
    if (failedFuncs.isNotEmpty()) {
        Text(
            text = "Failed functions:",
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = Color(0xFFDC2626),
            modifier = Modifier.padding(start = 8.dp, top = 4.dp)
        )
        failedFuncs.take(5).forEach { func ->
            Text(
                text = "  • $func",
                fontSize = 9.sp,
                color = Color(0xFFEF4444),
                modifier = Modifier.padding(start = 12.dp)
            )
        }
        if (failedFuncs.size > 5) {
            Text(
                text = "  ... and ${failedFuncs.size - 5} more",
                fontSize = 9.sp,
                color = Color(0xFFEF4444),
                modifier = Modifier.padding(start = 12.dp)
            )
        }
    }
}

// L2 Content: Environment & Device Attestation
@Composable
private fun L2Content(
    status: VerifyStatusResponse,
    deviceResult: DeviceAttestationResult?,
    loading: Boolean
) {
    // Platform
    DetailRow(
        icon = "📱",
        label = "Platform",
        value = "${status.platformOs ?: "?"} • ${status.platformArch ?: "?"}",
        ok = true
    )

    // Hardware Keystore - check if signing key is encrypted by hardware key
    // HW-AES-256-GCM means Ed25519 key is encrypted by hardware-backed AES key
    val isIosPlatform = status.platformOs?.lowercase() in listOf("ios", "ipados") ||
        status.hardwareType?.contains("IOS", ignoreCase = true) == true
    val hasHwEncryption = status.hardwareBacked &&
        status.keyStorageMode?.contains("HW", ignoreCase = true) == true
    val keystoreLabel = if (isIosPlatform) "Secure Enclave" else "Hardware Keystore"
    val keystoreValue = when {
        hasHwEncryption -> status.keyStorageMode ?: "Hardware-backed"
        isIosPlatform && status.hardwareBacked -> "iOS Secure Enclave (Software Key)"
        status.hardwareBacked -> "Android Keystore (Software)"
        else -> "Software fallback"
    }
    DetailRow(
        label = keystoreLabel,
        value = keystoreValue,
        ok = hasHwEncryption,
        pending = status.hardwareBacked && !hasHwEncryption  // Yellow if Keystore but no HW encryption
    )

    // Device Attestation: App Attest (iOS) / Play Integrity (Android)
    val attestLabel = if (isIosPlatform) "App Attest" else "Play Integrity"
    if (loading) {
        DetailRow(label = attestLabel, value = "Checking...", ok = false, pending = true)
    } else {
        when (deviceResult) {
            is DeviceAttestationResult.Success -> {
                DetailRow(
                    label = attestLabel,
                    value = if (deviceResult.verified) deviceResult.verdict else "Failed",
                    ok = deviceResult.verified
                )
                if (deviceResult.meetsStrongIntegrity) DetailSubtext("• Strong integrity")
                if (deviceResult.meetsDeviceIntegrity) DetailSubtext("• Device integrity")
                if (deviceResult.meetsBasicIntegrity) DetailSubtext("• Basic integrity")
            }
            is DeviceAttestationResult.Error -> {
                DetailRow(label = attestLabel, value = "Error", ok = false)
                DetailSubtext(deviceResult.message.take(80))
            }
            is DeviceAttestationResult.NotSupported -> {
                DetailRow(label = attestLabel, value = "Not supported", ok = false, pending = true)
            }
            null -> {
                DetailRow(
                    label = attestLabel,
                    value = if (status.playIntegrityOk) "Valid" else "Not available",
                    ok = status.playIntegrityOk,
                    pending = !status.playIntegrityOk
                )
            }
        }
    }
}

// L3 Content: Registry Cross-Validation
@Composable
private fun L3Content(status: VerifyStatusResponse) {
    // Registry uses 3 sources: DNS US, DNS EU, HTTPS
    val sources = 3
    val agreement = status.sourcesAgreeing ?: 0
    val isPartial = agreement == 2  // 2/3 is partial but passing

    DetailRow(
        label = "Cross-Validation",
        value = "$agreement/$sources sources agree",
        ok = agreement >= 2,  // 2/3 is passing threshold
        pending = isPartial
    )

    // Show individual source status
    DetailRow(
        label = "DNS (US)",
        value = if (status.dnsUsOk) "✓ Reachable" else "✗ Timeout",
        ok = status.dnsUsOk
    )
    DetailRow(
        label = "DNS (EU)",
        value = if (status.dnsEuOk) "✓ Reachable" else "✗ Timeout",
        ok = status.dnsEuOk
    )
    DetailRow(
        label = "HTTPS",
        value = if (status.httpsUsOk) "✓ Reachable" else "✗ Failed",
        ok = status.httpsUsOk
    )

    DetailRow(
        label = "Registry Status",
        value = when {
            agreement >= 3 -> "All sources agree"
            agreement >= 2 -> "Majority agree ($agreement/3)"
            agreement >= 1 -> "Insufficient ($agreement/3)"
            else -> "Validation pending"
        },
        ok = agreement >= 2,  // 2/3 is passing threshold
        pending = isPartial
    )
}

// L4 Content: Code Integrity
//
// v0.9.7+: Uses unified module_integrity when available (cross-validation of disk/agent/registry)
// Fallback: Legacy deconfliction logic for older CIRISVerify versions
//
// Deconfliction logic (legacy):
// 1. EXPECTED (denominator) = Registry Manifest - Mobile Exclusions
// 2. VERIFIED (numerator) = Filesystem verified + Chaquopy verified (by full path)
// 3. MISSING = Files in expected but not verified by either source
// 4. FAILED = Checksum mismatches reported by CIRISVerify
//
@Composable
private fun L4Content(status: VerifyStatusResponse) {
    // v0.9.7+: Check if unified module_integrity is available
    val summary = status.moduleIntegritySummary
    if (summary != null) {
        L4ContentUnified(status, summary)
        return
    }

    // Legacy fallback for older CIRISVerify versions
    val perFile = status.perFileResults ?: emptyMap()

    // === SOURCE 1: Registry Manifest ===
    val manifestTotal = perFile.size.takeIf { it > 0 } ?: (status.filesChecked ?: 0)
    val mobileExcludedCount = status.mobileExcludedCount ?: 0

    // EXPECTED = Manifest - Mobile Exclusions (denominator)
    val totalExpected = manifestTotal - mobileExcludedCount

    // === SOURCE 2: Chaquopy Hash Verified (Python files) ===
    // These are Python files validated via startup hash, not on filesystem
    val chaquopyVerifiedCount = status.pythonModulesPassed ?: 0

    // === SOURCE 3: Filesystem Verified ===
    // Files physically on disk that passed CIRISVerify check
    val filesystemVerified = perFile.filterValues { it == "passed" }.keys.toList()
    val filesystemVerifiedCount = filesystemVerified.size

    // === MOBILE EXCLUSIONS (from backend) ===
    val mobileExcludedList = status.mobileExcludedList ?: emptyList()
    val mobileExcludedSet = mobileExcludedList.toSet()
    fun isExcluded(path: String) = path in mobileExcludedSet

    // === DECONFLICTED VERIFIED (numerator) ===
    // Python files in manifest that are "missing" from filesystem = covered by chaquopy
    // But exclude mobile-excluded paths from the count
    val missingInManifest = perFile.filterValues { it == "missing" }.keys
    val pythonFilesInManifest = missingInManifest.filter { path ->
        (path.endsWith(".py") || path.endsWith(".pyi")) && !isExcluded(path)
    }
    val chaquopyCoveredFromManifest = pythonFilesInManifest.size

    // Filesystem verified (also exclude mobile-excluded)
    val filesystemVerifiedFiltered = filesystemVerified.filter { !isExcluded(it) }
    val filesystemVerifiedFilteredCount = filesystemVerifiedFiltered.size

    // Total verified = Filesystem (filtered) + Chaquopy (Python files verified via hash)
    val totalVerified = filesystemVerifiedFilteredCount + chaquopyCoveredFromManifest

    // === ACTUALLY UNVERIFIED ===
    // Files in manifest (not excluded) that are NOT verified by either source
    // = Backend's missing count MINUS the Python files we verified via Chaquopy
    val backendMissingCount = status.filesMissingCount ?: 0
    val actuallyUnverifiedCount = maxOf(0, backendMissingCount - chaquopyCoveredFromManifest)

    // Unverified list = non-Python files that are missing (Python files are covered by Chaquopy)
    val actuallyUnverifiedList = status.filesMissingList?.filter { path ->
        !path.endsWith(".py") && !path.endsWith(".pyi")
    } ?: missingInManifest.filter { path ->
        !path.endsWith(".py") && !path.endsWith(".pyi")
    }.toList()

    // === FAILED CHECKSUMS ===
    val failedFiles = perFile.filterValues { it == "failed" }.keys.toList()
    val failedCount = failedFiles.size

    // === UNREADABLE ===
    val unreadableFiles = perFile.filterValues { it == "unreadable" }.keys.toList()

    // === DISPLAY ===
    val integrityOk = failedCount == 0 && unreadableFiles.isEmpty() && actuallyUnverifiedCount == 0

    // Summary header
    DetailRow(
        label = "Code Integrity",
        value = if (integrityOk) "Verified" else "Issues Found",
        ok = integrityOk
    )

    // Main count: Verified / Expected
    DetailSubtext("$totalVerified / $totalExpected verified")

    // Diagnostic breakdown
    Spacer(modifier = Modifier.height(4.dp))
    DetailSubtext("  Manifest: $manifestTotal | Excluded: $mobileExcludedCount | Expected: $totalExpected")
    DetailSubtext("  Filesystem: $filesystemVerifiedCount | Chaquopy (manifest): $chaquopyCoveredFromManifest")
    DetailSubtext("  Missing Python in manifest: ${pythonFilesInManifest.size}")
    val nonPythonMissing = missingInManifest.filter { !it.endsWith(".py") && !it.endsWith(".pyi") }
    DetailSubtext("  Missing non-Python: ${nonPythonMissing.size}")

    // Breakdown
    Spacer(modifier = Modifier.height(8.dp))

    // Collapsible state
    var filesystemExpanded by remember { mutableStateOf(false) }
    var chaquopyExpanded by remember { mutableStateOf(false) }
    var missingExpanded by remember { mutableStateOf(false) }
    var excludedExpanded by remember { mutableStateOf(false) }
    var failedExpanded by remember { mutableStateOf(false) }
    var unexpectedExpanded by remember { mutableStateOf(false) }

    // 1. Filesystem Verified (non-Python files on disk)
    if (filesystemVerifiedCount > 0) {
        CollapsibleFileSection(
            title = "Filesystem Verified",
            count = filesystemVerifiedCount,
            files = filesystemVerified.take(50),
            expanded = filesystemExpanded,
            onToggle = { filesystemExpanded = !filesystemExpanded },
            titleColor = Color(0xFF059669),
            fileColor = Color(0xFF10B981)
        )
    }

    // 2. Chaquopy Hash Verified (Python files from manifest)
    if (chaquopyCoveredFromManifest > 0) {
        CollapsibleFileSection(
            title = "Chaquopy Hash Verified",
            count = chaquopyCoveredFromManifest,
            files = pythonFilesInManifest.take(50),
            expanded = chaquopyExpanded,
            onToggle = { chaquopyExpanded = !chaquopyExpanded },
            titleColor = Color(0xFF059669),
            fileColor = Color(0xFF10B981)
        )
    }

    // Show extra Python modules not in manifest (info only)
    // These are Python modules in chaquopy bundle but not in registry manifest
    // (stdlib, dependencies, etc.)
    val extraChaquopyModules = chaquopyVerifiedCount - chaquopyCoveredFromManifest
    if (extraChaquopyModules > 0) {
        DetailSubtext("  + $extraChaquopyModules extra modules (stdlib/deps, not in manifest)")
    }

    // 3. Actually Unverified (not verified by either filesystem or Chaquopy)
    if (actuallyUnverifiedCount > 0) {
        CollapsibleFileSection(
            title = "Unverified",
            count = actuallyUnverifiedCount,
            files = actuallyUnverifiedList.take(50),
            expanded = missingExpanded,
            onToggle = { missingExpanded = !missingExpanded },
            titleColor = Color(0xFFDC2626),
            fileColor = Color(0xFFEF4444)
        )
    }

    // 4. Failed Checksums (file exists but hash mismatch)
    if (failedCount > 0) {
        CollapsibleFileSection(
            title = "Checksum Mismatch",
            count = failedCount,
            files = failedFiles.take(50),
            expanded = failedExpanded,
            onToggle = { failedExpanded = !failedExpanded },
            titleColor = Color(0xFFDC2626),
            fileColor = Color(0xFFEF4444)
        )
    }

    // 5. Unreadable files
    var unreadableExpanded by remember { mutableStateOf(false) }
    if (unreadableFiles.isNotEmpty()) {
        CollapsibleFileSection(
            title = "Unreadable",
            count = unreadableFiles.size,
            files = unreadableFiles.take(50),
            expanded = unreadableExpanded,
            onToggle = { unreadableExpanded = !unreadableExpanded },
            titleColor = Color(0xFFDC2626),
            fileColor = Color(0xFFEF4444)
        )
    }

    // 6. Mobile Excluded (info - not counted in expected)
    val mobileExcluded = status.mobileExcludedList ?: emptyList()
    if (mobileExcludedCount > 0) {
        CollapsibleFileSection(
            title = "Mobile Excluded",
            count = mobileExcludedCount,
            files = mobileExcluded.take(50),
            expanded = excludedExpanded,
            onToggle = { excludedExpanded = !excludedExpanded },
            titleColor = Color(0xFF6B7280),
            fileColor = Color(0xFF9CA3AF)
        )
    }

    // 7. Unexpected Files (on device but not in manifest)
    val unexpectedFiles = status.filesUnexpectedList ?: emptyList()
    if (unexpectedFiles.isNotEmpty()) {
        CollapsibleFileSection(
            title = "Unexpected Files",
            count = unexpectedFiles.size,
            files = unexpectedFiles.take(50),
            expanded = unexpectedExpanded,
            onToggle = { unexpectedExpanded = !unexpectedExpanded },
            titleColor = Color(0xFFB45309),
            fileColor = Color(0xFF92400E)
        )
    }
}

// v0.9.7+: Unified Module Integrity Display
// Uses pre-calculated cross-validation from CIRISVerify
@Composable
private fun L4ContentUnified(status: VerifyStatusResponse, summary: Map<String, Int>) {
    val totalManifest = summary["total_manifest"] ?: 0
    val verified = summary["verified"] ?: 0
    val failed = summary["failed"] ?: 0
    val missing = summary["missing"] ?: 0
    val excluded = summary["excluded"] ?: 0
    val crossValidated = summary["cross_validated"] ?: 0

    // Mobile excluded comes from status (files like discord, cli adapters not on mobile)
    val mobileExcluded = status.mobileExcludedCount ?: 0

    // Expected = manifest - mobile excluded (not general excluded which is 0)
    val expected = totalManifest - mobileExcluded
    // Remainder = files in manifest, not excluded, but not verified or failed
    val remainder = expected - verified - failed
    val integrityOk = status.moduleIntegrityOk

    // Summary header
    DetailRow(
        label = "Code Integrity",
        value = if (integrityOk) "Verified" else "Issues Found",
        ok = integrityOk
    )

    // Main count: Verified / Expected (excluding mobile-excluded files)
    DetailSubtext("$verified / $expected verified")

    // Diagnostic breakdown
    Spacer(modifier = Modifier.height(4.dp))
    DetailSubtext("  Manifest: $totalManifest | Mobile Excluded: $mobileExcluded | Expected: $expected")
    DetailSubtext("  Cross-validated: $crossValidated (disk = agent = registry)")
    if (failed > 0) {
        DetailSubtext("  Failed: $failed (hash mismatch)")
    }
    if (remainder > 0) {
        DetailSubtext("  Not found: $remainder (in manifest but not on device)")
    }

    // Collapsible state
    var crossValidatedExpanded by remember { mutableStateOf(false) }
    var filesystemExpanded by remember { mutableStateOf(false) }
    var agentExpanded by remember { mutableStateOf(false) }
    var diskAgentMismatchExpanded by remember { mutableStateOf(false) }
    var registryMismatchExpanded by remember { mutableStateOf(false) }
    var notOnDeviceExpanded by remember { mutableStateOf(false) }
    var unexpectedExpanded by remember { mutableStateOf(false) }
    var excludedExpanded by remember { mutableStateOf(false) }

    Spacer(modifier = Modifier.height(8.dp))

    // 1. Cross-validated (STRONGEST: disk == agent == registry)
    val crossValidatedFiles = status.crossValidatedFiles ?: emptyList()
    if (crossValidatedFiles.isNotEmpty() || crossValidated > 0) {
        CollapsibleFileSection(
            title = "✓ Fully Verified (disk = agent = registry)",
            count = crossValidated,
            files = crossValidatedFiles.take(50),
            expanded = crossValidatedExpanded,
            onToggle = { crossValidatedExpanded = !crossValidatedExpanded },
            titleColor = Color(0xFF047857),
            fileColor = Color(0xFF059669)
        )
    }

    // 2. Filesystem Verified (disk == registry, no agent hash provided)
    val filesystemVerifiedFiles = status.filesystemVerifiedFiles ?: emptyList()
    val filesystemVerifiedCount = verified - crossValidated
    if (filesystemVerifiedFiles.isNotEmpty() || filesystemVerifiedCount > 0) {
        CollapsibleFileSection(
            title = "✓ Disk Matches Registry (no agent hash)",
            count = filesystemVerifiedCount,
            files = filesystemVerifiedFiles.take(50),
            expanded = filesystemExpanded,
            onToggle = { filesystemExpanded = !filesystemExpanded },
            titleColor = Color(0xFF059669),
            fileColor = Color(0xFF10B981)
        )
    }

    // 3. Agent/Chaquopy Verified (agent == registry, not on disk)
    val agentVerifiedFiles = status.agentVerifiedFiles ?: emptyList()
    val agentVerifiedCount = summary["agent_only_verified"] ?: agentVerifiedFiles.size
    if (agentVerifiedFiles.isNotEmpty() || agentVerifiedCount > 0) {
        CollapsibleFileSection(
            title = "✓ Agent Hash Matches Registry (not on disk)",
            count = agentVerifiedCount,
            files = agentVerifiedFiles.take(50),
            expanded = agentExpanded,
            onToggle = { agentExpanded = !agentExpanded },
            titleColor = Color(0xFF059669),
            fileColor = Color(0xFF10B981)
        )
    }

    // 4. DISK/AGENT MISMATCH - RED FLAG for tampering!
    val diskAgentMismatch = status.diskAgentMismatch ?: emptyMap()
    if (diskAgentMismatch.isNotEmpty()) {
        Column {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { diskAgentMismatchExpanded = !diskAgentMismatchExpanded }
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (diskAgentMismatchExpanded) "▼" else "▶",
                    fontSize = 10.sp,
                    color = Color(0xFFDC2626)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "⚠️ TAMPERING: Disk ≠ Agent Hash (${diskAgentMismatch.size}):",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFDC2626)
                )
            }
            if (diskAgentMismatchExpanded) {
                diskAgentMismatch.keys.take(20).forEach { path ->
                    Text(
                        text = "    • $path",
                        fontSize = 10.sp,
                        color = Color(0xFFEF4444),
                        fontFamily = FontFamily.Monospace
                    )
                }
                DetailSubtext("    (File changed after startup - possible tampering)")
            }
        }
    }

    // 5. Registry Mismatch (hash doesn't match official registry)
    val registryMismatch = status.registryMismatchFiles ?: emptyMap()
    if (registryMismatch.isNotEmpty()) {
        Column {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { registryMismatchExpanded = !registryMismatchExpanded }
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (registryMismatchExpanded) "▼" else "▶",
                    fontSize = 10.sp,
                    color = Color(0xFFDC2626)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "✗ Hash ≠ Registry (modified files) (${registryMismatch.size}):",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFDC2626)
                )
            }
            if (registryMismatchExpanded) {
                registryMismatch.keys.take(20).forEach { path ->
                    Text(
                        text = "    • $path",
                        fontSize = 10.sp,
                        color = Color(0xFFEF4444),
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }
    }

    // 6. In Manifest but Not on Device (files expected but missing)
    val filesMissingList = status.filesMissingList ?: emptyList()
    if (remainder > 0 || filesMissingList.isNotEmpty()) {
        CollapsibleFileSection(
            title = "? In Manifest but Not on Device",
            count = remainder,
            files = filesMissingList.take(50),
            expanded = notOnDeviceExpanded,
            onToggle = { notOnDeviceExpanded = !notOnDeviceExpanded },
            titleColor = Color(0xFFD97706),  // Orange/amber
            fileColor = Color(0xFFF59E0B)
        )
    }

    // 7. On Device but Not in Manifest (unexpected files)
    val filesUnexpectedList = status.filesUnexpectedList ?: emptyList()
    if (filesUnexpectedList.isNotEmpty()) {
        CollapsibleFileSection(
            title = "? On Device but Not in Manifest",
            count = filesUnexpectedList.size,
            files = filesUnexpectedList.take(50),
            expanded = unexpectedExpanded,
            onToggle = { unexpectedExpanded = !unexpectedExpanded },
            titleColor = Color(0xFFD97706),  // Orange/amber
            fileColor = Color(0xFFF59E0B)
        )
    }

    // 8. Mobile Excluded (server-only files not bundled in APK)
    val mobileExcludedCount = status.mobileExcludedCount ?: excluded
    val mobileExcludedList = status.mobileExcludedList ?: emptyList()
    if (mobileExcludedCount > 0) {
        CollapsibleFileSection(
            title = "— Server-Only (not bundled in mobile)",
            count = mobileExcludedCount,
            files = mobileExcludedList.take(50),
            expanded = excludedExpanded,
            onToggle = { excludedExpanded = !excludedExpanded },
            titleColor = Color(0xFF6B7280),
            fileColor = Color(0xFF9CA3AF)
        )
    }
}

@Composable
private fun CollapsibleFileSection(
    title: String,
    count: Int,
    files: List<String>,
    expanded: Boolean,
    onToggle: () -> Unit,
    titleColor: Color,
    fileColor: Color
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onToggle() }
            .padding(start = 8.dp, top = 6.dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = if (expanded) "▼" else "▶",
            fontSize = 10.sp,
            color = titleColor
        )
        Spacer(modifier = Modifier.width(4.dp))
        Text(
            text = "$title ($count):",
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = titleColor
        )
    }

    if (expanded && files.isNotEmpty()) {
        files.forEach { file ->
            Text(
                text = "  • $file",
                fontSize = 9.sp,
                color = fileColor,
                modifier = Modifier.padding(start = 20.dp)
            )
        }
        if (count > files.size) {
            Text(
                text = "  ... and ${count - files.size} more (not fetched)",
                fontSize = 9.sp,
                color = fileColor.copy(alpha = 0.7f),
                modifier = Modifier.padding(start = 20.dp)
            )
        }
    }
}

// L5 Content: Registry & Audit
@Composable
private fun L5Content(status: VerifyStatusResponse, onCopyDiagnostics: () -> Unit) {
    // Registry Key
    val keyStatus = status.registryKeyStatus ?: "not_checked"
    val keyOk = keyStatus.contains("active", ignoreCase = true)
    DetailRow(
        label = "Registry Key",
        value = keyStatus.replaceFirstChar { it.uppercase() },
        ok = keyOk,
        pending = keyStatus == "not_checked"
    )

    // Audit Trail
    DetailRow(
        label = "Audit Trail",
        value = if (status.auditOk) "Verified" else "Pending",
        ok = status.auditOk,
        pending = !status.auditOk
    )

    // Copy diagnostics button
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
        horizontalArrangement = Arrangement.End
    ) {
        Text(
            text = "Copy Diagnostics",
            fontSize = 11.sp,
            color = Color(0xFF2563EB),
            modifier = Modifier
                .clickable { onCopyDiagnostics() }
                .padding(4.dp)
        )
    }
}

@Composable
private fun DetailRow(
    label: String,
    value: String,
    ok: Boolean,
    pending: Boolean = false,
    icon: String? = null
) {
    val color = when {
        ok -> Color(0xFF059669)
        pending -> Color(0xFFD97706)
        else -> Color(0xFFDC2626)
    }
    val statusIcon = when {
        ok -> "✓"
        pending -> "○"
        else -> "✗"
    }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (icon != null) Text(text = icon, fontSize = 12.sp)
            Text(text = label, fontSize = 12.sp, color = Color(0xFF4B5563))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(text = statusIcon, fontSize = 11.sp, color = color)
            Text(
                text = value,
                fontSize = 11.sp,
                color = color,
                fontFamily = if (value.length > 20) FontFamily.Monospace else FontFamily.Default
            )
        }
    }
}

@Composable
private fun DetailSubtext(text: String) {
    Text(
        text = text,
        fontSize = 10.sp,
        fontFamily = FontFamily.Monospace,
        color = Color(0xFF9CA3AF),
        modifier = Modifier.padding(start = 18.dp)
    )
}

@Composable
private fun VerificationDetailsCard(status: VerifyStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                text = "Verification Details",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            // === LEVEL 1: Self-Verification (Local Only) ===
            TierSection(
                level = 1,
                title = "Self-Verification",
                badge = "Local"
            ) {
                // Identity Key
                val keyIcon = if (status.hardwareBacked) "🔐" else "🔑"
                val storageMode = status.keyStorageMode ?: (if (status.hardwareBacked) "Hardware-backed" else "Software")
                CheckRow(
                    label = "Identity Key",
                    value = storageMode,
                    ok = true,
                    icon = keyIcon,
                    detail = status.ed25519Fingerprint?.let { "Fingerprint: ${it.take(16)}..." }
                )

                // Target
                val targetTriple = status.targetTriple ?: "${status.platformArch ?: "unknown"}-${status.platformOs?.lowercase() ?: "unknown"}"
                CheckRow(
                    label = "Registry Target",
                    value = targetTriple,
                    ok = true,
                    icon = "📦"
                )

                // Binary Self-Check
                val binaryStatus = status.binarySelfCheck ?: "not_checked"
                val binaryOk = binaryStatus == "verified"
                CheckRow(
                    label = "Binary Hash",
                    value = binaryStatus.replaceFirstChar { it.uppercase() },
                    ok = binaryOk,
                    pending = binaryStatus.contains("unavailable"),
                    detail = status.binaryHash?.let { "Local: ${it.take(16)}..." }
                )

                // Function Self-Check
                val funcStatus = status.functionSelfCheck ?: status.functionIntegrity ?: "not_checked"
                val funcOk = funcStatus == "verified"
                val funcDetail = if (status.functionsChecked != null && status.functionsChecked > 0) {
                    "${status.functionsPassed ?: 0}/${status.functionsChecked} functions"
                } else null
                CheckRow(
                    label = "Function Integrity",
                    value = funcStatus.replaceFirstChar { it.uppercase() },
                    ok = funcOk,
                    pending = funcStatus.contains("unavailable") || funcStatus.contains("not_found"),
                    detail = funcDetail
                )
            }

            // === LEVEL 4: Agent Code Integrity (Recursive - needs registry manifest) ===
            TierSection(
                level = 4,
                title = "Agent Code Integrity",
                badge = ""
            ) {
                // File Integrity
                val fileOk = status.fileIntegrityOk
                val fileDetail = if (status.filesChecked != null && status.filesChecked > 0) {
                    "${status.filesPassed ?: 0}/${status.filesChecked} files"
                } else null
                CheckRow(
                    label = "File Manifest",
                    value = if (fileOk) "Verified" else (status.integrityFailureReason?.take(30) ?: "Failed"),
                    ok = fileOk,
                    detail = fileDetail
                )

                // Python Integrity (mobile only)
                if (status.pythonModulesChecked != null && status.pythonModulesChecked > 0) {
                    val pyOk = status.pythonIntegrityOk && status.pythonHashValid
                    CheckRow(
                        label = "Python Modules",
                        value = if (pyOk) "Verified" else "Hash mismatch",
                        ok = pyOk,
                        detail = "${status.pythonModulesPassed ?: 0}/${status.pythonModulesChecked} modules, hash: ${status.pythonTotalHash?.take(12) ?: "N/A"}..."
                    )
                }
            }

            // === LEVEL 5: Registry & Audit (Recursive - network verification) ===
            TierSection(
                level = 5,
                title = "Registry & Audit",
                badge = "Recursive"
            ) {
                // Registry Key Status
                val regStatus = status.registryKeyStatus ?: "not_checked"
                val regOk = regStatus.contains("active", ignoreCase = true)
                CheckRow(
                    label = "Registry Key",
                    value = regStatus.replaceFirstChar { it.uppercase() },
                    ok = regOk,
                    pending = regStatus == "not_checked"
                )

                // Audit Trail
                CheckRow(
                    label = "Audit Trail",
                    value = if (status.auditOk) "Verified" else "Pending",
                    ok = status.auditOk,
                    pending = !status.auditOk
                )
            }
        }
    }
}

@Composable
private fun TierSection(
    level: Int,
    title: String,
    badge: String,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "L$level",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    modifier = Modifier
                        .background(Color(0xFF6366F1), RoundedCornerShape(4.dp))
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                )
                Text(
                    text = title,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    color = Color(0xFF374151)
                )
            }
            Text(
                text = badge,
                fontSize = 10.sp,
                color = Color(0xFF6B7280),
                modifier = Modifier
                    .background(Color(0xFFE5E7EB), RoundedCornerShape(4.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp)
            )
        }
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xFFF9FAFB), RoundedCornerShape(8.dp))
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content
        )
    }
}

@Composable
private fun CheckRow(
    label: String,
    value: String,
    ok: Boolean,
    pending: Boolean = false,
    icon: String? = null,
    detail: String? = null
) {
    val color = when {
        ok -> Color(0xFF059669)
        pending -> Color(0xFFD97706)
        else -> Color(0xFFDC2626)
    }
    val statusIcon = when {
        ok -> "✓"
        pending -> "○"
        else -> "✗"
    }

    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (icon != null) {
                    Text(text = icon, fontSize = 12.sp)
                }
                Text(
                    text = label,
                    fontSize = 12.sp,
                    color = Color(0xFF4B5563)
                )
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(text = statusIcon, fontSize = 11.sp, color = color)
                Text(
                    text = value,
                    fontSize = 11.sp,
                    color = color,
                    fontFamily = if (value.contains("-") || value.length > 20) FontFamily.Monospace else FontFamily.Default
                )
            }
        }
        detail?.let {
            Text(
                text = it,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                color = Color(0xFF9CA3AF),
                modifier = Modifier.padding(start = if (icon != null) 18.dp else 0.dp)
            )
        }
    }
}

@Composable
private fun DiagnosticsLogCard(
    diagnostics: String?,
    onCopy: () -> Unit
) {
    var expanded by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(text = "📋", fontSize = 16.sp)
                    Text(
                        text = if (expanded) "▼ Verify Log" else "▶ Verify Log",
                        fontWeight = FontWeight.Medium
                    )
                }
                TextButton(onClick = onCopy, enabled = !diagnostics.isNullOrEmpty()) {
                    Text("Copy")
                }
            }

            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    color = Color(0xFF1F2937),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp)
                    ) {
                        if (diagnostics.isNullOrEmpty()) {
                            Text(
                                text = "No diagnostics available",
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                                color = Color(0xFF9CA3AF)
                            )
                        } else {
                            // Split into lines and display with proper formatting
                            diagnostics.lines().forEach { line ->
                                val color = when {
                                    line.startsWith("===") -> Color(0xFF60A5FA) // Section headers
                                    line.contains("PASS") || line.contains("✓") -> Color(0xFF34D399)
                                    line.contains("FAIL") || line.contains("✗") -> Color(0xFFF87171)
                                    line.contains("WARN") || line.contains("○") -> Color(0xFFFBBF24)
                                    line.contains(":") -> Color(0xFFE5E7EB) // Key-value lines
                                    else -> Color(0xFF9CA3AF)
                                }
                                Text(
                                    text = line,
                                    fontSize = 10.sp,
                                    fontFamily = FontFamily.Monospace,
                                    color = color
                                )
                            }
                        }
                    }
                }
                Text(
                    text = "This log shows the full CIRISVerify attestation output",
                    fontSize = 10.sp,
                    color = Color(0xFF9CA3AF),
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }
    }
}

@Composable
private fun KeyStatusWarningCard(status: VerifyStatusResponse) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFEF3C7))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "Identity Key Not Active",
                fontWeight = FontWeight.Bold,
                color = Color(0xFF92400E)
            )
            Text(
                text = "Key status: ${status.keyStatus}",
                fontSize = 12.sp,
                color = Color(0xFFD97706)
            )
            Text(
                text = when (status.keyStatus) {
                    "none" -> "No identity key configured. The identity key is optional and enables validation against the public infrastructure and your audit log."
                    "ephemeral" -> "Using an ephemeral key. To enable full attestation, connect to a CIRISNode to obtain a genesis identity key."
                    "portal_pending" -> "Identity key pending activation. Please complete the device authorization in your browser."
                    else -> "The identity key is not yet active. This is optional and enables additional attestation capabilities."
                },
                fontSize = 12.sp,
                color = Color(0xFFD97706)
            )
        }
    }
}

@Composable
private fun DisclaimerCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF0FDF4))
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "CIRISVerify provides cryptographic attestation of agent identity for the Coherence Ratchet and CIRIS Scoring.",
                fontSize = 12.sp,
                color = Color(0xFF047857)
            )
            Text(
                text = "CIRISVerify provides cryptographic attestation under defined threat models and does not guarantee absolute security.",
                fontSize = 11.sp,
                color = Color(0xFF6B7280),
                fontWeight = FontWeight.Normal
            )
        }
    }
}

@Composable
private fun RawDetailsCard(
    status: VerifyStatusResponse,
    onCopy: () -> Unit
) {
    var expanded by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (expanded) "▼ Raw Details" else "▶ Raw Details",
                    fontWeight = FontWeight.Medium
                )
                TextButton(onClick = onCopy) {
                    Text("Copy")
                }
            }

            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    color = Color(0xFFF5F5F5),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        RawLine("Binary", status.binaryOk)
                        RawLine("Env", status.envOk)
                        RawLine("DNS US", status.dnsUsOk)
                        RawLine("DNS EU", status.dnsEuOk)
                        RawLine("HTTPS US", status.httpsUsOk)
                        RawLine("HTTPS EU", status.httpsEuOk)
                        RawLine("File Integrity", status.fileIntegrityOk)
                        RawLine("Registry", status.registryOk)
                        RawLine("Audit", status.auditOk)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Platform: ${status.platformOs ?: "?"} / ${status.platformArch ?: "?"}", fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        Text("Hardware: ${status.hardwareType ?: "?"}", fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        Text("Key Status: ${status.keyStatus}", fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        status.keyId?.let { Text("Key ID: $it", fontSize = 10.sp, fontFamily = FontFamily.Monospace) }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Files: ${status.filesChecked ?: 0}/${status.totalFiles ?: 0}", fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                    }
                }
            }
        }
    }
}

@Composable
private fun RawLine(label: String, value: Boolean) {
    Text(
        text = "$label: $value",
        fontSize = 10.sp,
        fontFamily = FontFamily.Monospace,
        color = if (value) Color(0xFF059669) else Color(0xFFDC2626)
    )
}

private fun buildRawDetailsText(status: VerifyStatusResponse): String {
    return buildString {
        appendLine("CIRISVerify Status")
        appendLine("==================")
        appendLine("Max Level: ${status.maxLevel}/5")
        appendLine("Version: ${status.version ?: "unknown"}")
        appendLine()
        appendLine("Checks:")
        appendLine("  Binary: ${status.binaryOk}")
        appendLine("  Env: ${status.envOk}")
        appendLine("  DNS US: ${status.dnsUsOk}")
        appendLine("  DNS EU: ${status.dnsEuOk}")
        appendLine("  HTTPS US: ${status.httpsUsOk}")
        appendLine("  HTTPS EU: ${status.httpsEuOk}")
        appendLine("  File Integrity: ${status.fileIntegrityOk}")
        appendLine("  Registry: ${status.registryOk}")
        appendLine("  Audit: ${status.auditOk}")
        appendLine()
        appendLine("Platform: ${status.platformOs ?: "?"} / ${status.platformArch ?: "?"}")
        appendLine("Hardware: ${status.hardwareType ?: "?"}")
        appendLine("Key Status: ${status.keyStatus}")
        status.keyId?.let { appendLine("Key ID: $it") }
        appendLine()
        appendLine("Files: ${status.filesChecked ?: 0}/${status.totalFiles ?: 0}")
        status.integrityFailureReason?.let { appendLine("Failure: $it") }
    }
}
