package ai.ciris.mobile.shared.ui.screens

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
    modifier: Modifier = Modifier
) {
    var verifyStatus by remember { mutableStateOf<VerifyStatusResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var attestationMode by remember { mutableStateOf("partial") }
    val coroutineScope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val clipboardManager = LocalClipboardManager.current

    // Fetch verify status on mount
    LaunchedEffect(Unit) {
        fetchVerifyStatus(
            apiClient = apiClient,
            mode = attestationMode,
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
                                    mode = attestationMode,
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
                                    mode = attestationMode,
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

                    // Mode toggle
                    ModeToggleCard(
                        currentMode = attestationMode,
                        isLoading = loading,
                        onModeChange = { newMode ->
                            attestationMode = newMode
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    mode = newMode,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        },
                        onRun = {
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    mode = attestationMode,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        }
                    )

                    // Attestation levels
                    AttestationLevelsCard(status = status)

                    // Device attestation (Play Integrity / App Attest)
                    DeviceAttestationCard(status = status)

                    // Platform info
                    if (status.platformOs != null || status.platformArch != null) {
                        PlatformInfoCard(status = status)
                    }

                    // File integrity details
                    if (status.filesChecked != null && status.filesChecked > 0) {
                        FileIntegrityCard(status = status)
                    }

                    // Key status warning
                    if (status.keyStatus != "portal_active") {
                        KeyStatusWarningCard(status = status)
                    }

                    // Disclaimer
                    DisclaimerCard()

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

                    // Raw details (expandable)
                    RawDetailsCard(
                        status = status,
                        onCopy = {
                            val text = buildRawDetailsText(status)
                            clipboardManager.setText(AnnotatedString(text))
                        }
                    )
                }
            }
        }
    }
}

private suspend fun fetchVerifyStatus(
    apiClient: CIRISApiClient,
    mode: String,
    onSuccess: (VerifyStatusResponse) -> Unit,
    onError: (String) -> Unit
) {
    try {
        val result = withContext(Dispatchers.IO) {
            apiClient.getVerifyStatus(mode)
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
private fun TrustSummaryCard(status: VerifyStatusResponse) {
    val level = status.maxLevel
    val bgColor = when {
        level >= 5 -> Color(0xFFD1FAE5)
        level >= 3 -> Color(0xFFDBEAFE)
        level >= 1 -> Color(0xFFFEF3C7)
        else -> Color(0xFFF5F5F5)
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
                    else -> "Incomplete - Attestation not started"
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
        }
    }
}

@Composable
private fun ModeToggleCard(
    currentMode: String,
    isLoading: Boolean,
    onModeChange: (String) -> Unit,
    onRun: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Attestation Mode", fontWeight = FontWeight.Medium)

            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                // Partial mode button
                OutlinedButton(
                    onClick = { onModeChange("partial") },
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = if (currentMode == "partial") Color(0xFF2563EB).copy(alpha = 0.1f) else Color.Transparent,
                        contentColor = if (currentMode == "partial") Color(0xFF2563EB) else Color(0xFF6B7280)
                    ),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                    modifier = Modifier.height(32.dp)
                ) {
                    Text("Partial", fontSize = 12.sp)
                }
                // Full mode button
                OutlinedButton(
                    onClick = { onModeChange("full") },
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = if (currentMode == "full") Color(0xFF2563EB).copy(alpha = 0.1f) else Color.Transparent,
                        contentColor = if (currentMode == "full") Color(0xFF2563EB) else Color(0xFF6B7280)
                    ),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                    modifier = Modifier.height(32.dp)
                ) {
                    Text("Full", fontSize = 12.sp)
                }
                // Run button
                Button(
                    onClick = onRun,
                    enabled = !isLoading,
                    contentPadding = PaddingValues(horizontal = 12.dp),
                    modifier = Modifier.height(32.dp)
                ) {
                    Text(if (isLoading) "..." else "Run", fontSize = 12.sp)
                }
            }
        }
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
                    "Verified ${status.filesChecked}/${status.totalFiles ?: "?"} files (${status.attestationMode})"
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
private fun DeviceAttestationCard(status: VerifyStatusResponse) {
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
                    // Google Play Integrity
                    val passed = status.playIntegrityOk
                    val verdict = status.playIntegrityVerdict ?: "Not checked"
                    val color = if (passed) Color(0xFF059669) else Color(0xFFD97706)
                    val icon = if (passed) "✓" else "○"

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
                            val verdictItems = parsePlayIntegrityVerdict(verdict)
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
            status.integrityFailureReason?.let {
                Text("Reason: $it", fontSize = 12.sp, color = Color(0xFFDC2626))
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
                        RawLine("Play Integrity", status.playIntegrityOk)
                        Spacer(modifier = Modifier.height(4.dp))
                        status.playIntegrityVerdict?.let {
                            Text("Play Verdict: $it", fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        }
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
        appendLine("  Play Integrity: ${status.playIntegrityOk}")
        status.playIntegrityVerdict?.let { appendLine("  Play Verdict: $it") }
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
