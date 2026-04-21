package ai.ciris.mobile.shared.ui.screens
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable

import ai.ciris.mobile.shared.DeviceAttestationCallback
import ai.ciris.mobile.shared.DeviceAttestationResult
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
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

    // Fetch verify status on mount and poll every 5 seconds while on trust page
    LaunchedEffect(Unit) {
        while (true) {
            fetchVerifyStatus(
                apiClient = apiClient,
                onSuccess = {
                    verifyStatus = it
                    loading = false
                    error = null
                    PlatformLogger.d("TrustPage", "Verify status updated: maxLevel=${it.maxLevel}, levelPending=${it.levelPending}")
                },
                onError = { error = it; loading = false }
            )
            kotlinx.coroutines.delay(5000) // Poll every 5 seconds
        }
    }

    // Only trigger device attestation if level_pending=true (backend needs it)
    // Otherwise use the cached result from the backend
    LaunchedEffect(verifyStatus?.levelPending, deviceAttestationCallback) {
        val needsAttestation = verifyStatus?.levelPending == true
        if (needsAttestation && deviceAttestationCallback != null && deviceAttestationResult == null) {
            PlatformLogger.d("TrustPage", " level_pending=true, triggering device attestation...")
            deviceAttestationLoading = true
            deviceAttestationCallback.onDeviceAttestationRequested { result ->
                deviceAttestationResult = result
                deviceAttestationLoading = false
            }
        } else if (verifyStatus != null && !needsAttestation) {
            PlatformLogger.d("TrustPage", " level_pending=false, using cached attestation (level=${verifyStatus?.maxLevel})")
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_trust_security")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_trust_back") { onNavigateBack() }
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = {
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    refresh = true,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        },
                        modifier = Modifier.testableClickable("btn_trust_refresh") {
                            loading = true
                            coroutineScope.launch {
                                fetchVerifyStatus(
                                    apiClient = apiClient,
                                    refresh = true,
                                    onSuccess = { verifyStatus = it; loading = false; error = null },
                                    onError = { error = it; loading = false }
                                )
                            }
                        },
                        enabled = !loading
                    ) {
                        Icon(CIRISIcons.refresh, contentDescription = "Refresh")
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
                        text = localizedString("mobile.trust_learn_more"),
                        fontSize = 14.sp,
                        color = SemanticColors.Default.info,
                        textDecoration = TextDecoration.Underline,
                        modifier = Modifier
                            .testableClickable("btn_learn_more") { uriHandler.openUri("https://ciris.ai/trust") }
                            .padding(8.dp)
                    )
                }
            }
        }
    }
}

private suspend fun fetchVerifyStatus(
    apiClient: CIRISApiClient,
    refresh: Boolean = false,
    onSuccess: (VerifyStatusResponse) -> Unit,
    onError: (String) -> Unit
) {
    try {
        if (refresh) {
            // Trigger a fresh attestation run, then poll for the result
            withContext(Dispatchers.Default) { apiClient.getVerifyStatus(refresh = true) }
            // Wait for attestation to complete (typically 2-5s)
            kotlinx.coroutines.delay(3000)
        }
        val result = withContext(Dispatchers.Default) {
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
            CircularProgressIndicator(color = SemanticColors.Default.success)
            Text(localizedString("mobile.trust_running"), color = SemanticColors.Default.inactive)
        }
    }
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceError)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = localizedString("mobile.trust_failed"),
                fontWeight = FontWeight.Bold,
                color = SemanticColors.Default.error
            )
            Text(
                text = error,
                fontSize = 14.sp,
                color = SemanticColors.Default.onError
            )
            Button(
                onClick = onRetry,
                modifier = Modifier.testableClickable("btn_trust_retry") { onRetry() },
                colors = ButtonDefaults.buttonColors(containerColor = SemanticColors.Default.error)
            ) {
                Text(localizedString("mobile.common_retry"))
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
        2 -> sourcesOk || status.moduleIntegrityOk  // Some L3/L4 checks pass
        3 -> status.moduleIntegrityOk  // L4 passes
        4 -> status.auditOk || portalKeyOk  // Some L5 checks pass
        else -> false
    }

    val notAttempted = level == 0 && status.attestationStatus == "not_attempted"
    val bgColor = when {
        level >= 5 -> SemanticColors.Default.surfaceSuccess  // Green - Identity Validated
        level == 4 -> SemanticColors.Default.surfaceWarning  // Amber - Agent Validated
        notAttempted -> Color(0xFFF5F5F5)  // Gray - Not yet started
        else -> SemanticColors.Default.surfaceError          // Red - Issues Detected (L1-3)
    }
    val textColor = when {
        level >= 5 -> SemanticColors.Default.onSuccess  // Green text
        level == 4 -> SemanticColors.Default.onWarning  // Amber text
        notAttempted -> SemanticColors.Default.inactive // Gray text
        else -> SemanticColors.Default.error            // Red text
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
            // Shield with level - trust diamond icon
            Icon(CIRISIcons.diamond, contentDescription = null, modifier = Modifier.size(48.dp), tint = textColor)

            Text(
                text = localizedString("mobile.trust_level").replace("{level}", level.toString()),
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = textColor
            )

            Text(
                text = when {
                    level >= 5 -> "Identity Validated - Full attestation complete"
                    level == 4 -> "Agent Validated - Awaiting identity confirmation"
                    notAttempted -> "Pending - Attestation not yet started"
                    else -> "Issues Detected - Verification incomplete"
                },
                fontSize = 14.sp,
                color = textColor.copy(alpha = 0.8f)
            )

            // Version badges (Agent + CIRISVerify)
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                status.agentVersion?.let { agentVer ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = textColor.copy(alpha = 0.1f)
                    ) {
                        Text(
                            text = localizedString("mobile.trust_agent_ver").replace("{version}", agentVer),
                            fontSize = 12.sp,
                            color = textColor,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
                status.version?.let { version ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = textColor.copy(alpha = 0.1f)
                    ) {
                        Text(
                            text = localizedString("mobile.trust_verify_ver").replace("{version}", version),
                            fontSize = 12.sp,
                            color = textColor,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
            }


            // Timestamp badge showing when attestation was performed
            status.cachedAt?.let { timestamp ->
                Text(
                    text = localizedString("mobile.trust_last_ran").replace("{time}", formatAttestationTimestamp(timestamp)),
                    fontSize = 11.sp,
                    color = textColor.copy(alpha = 0.6f)
                )
            }

            // Expandable level debug info
            LevelDebugExpansion(status = status, textColor = textColor)
        }
    }
}

/**
 * Expandable debug info showing level calculation details
 */
@Composable
private fun LevelDebugExpansion(status: VerifyStatusResponse, textColor: Color) {
    var expanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Tap to expand
        Row(
            modifier = Modifier
                .clickable { expanded = !expanded }
                .padding(4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                if (expanded) CIRISIcons.arrowDown else CIRISIcons.arrowRight,
                contentDescription = null,
                modifier = Modifier.size(10.dp),
                tint = textColor.copy(alpha = 0.6f)
            )
            Text(
                text = localizedString("mobile.trust_level_debug"),
                fontSize = 10.sp,
                color = textColor.copy(alpha = 0.6f)
            )
        }

        AnimatedVisibility(
            visible = expanded,
            enter = expandVertically() + fadeIn(),
            exit = shrinkVertically() + fadeOut()
        ) {
            Surface(
                color = Color.White.copy(alpha = 0.5f),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.padding(top = 8.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    // Description text explaining attestation levels
                    Text(
                        text = localizedString("mobile.trust_level_explain"),
                        fontSize = 9.sp,
                        color = textColor.copy(alpha = 0.7f),
                        modifier = Modifier.padding(bottom = 4.dp)
                    )

                    Divider(color = textColor.copy(alpha = 0.2f), modifier = Modifier.padding(bottom = 4.dp))

                    // L1 checks
                    val l1Pass = status.binarySelfCheck == "verified"
                    LevelDebugRow("L1", l1Pass, "binary=${status.binarySelfCheck}")

                    // L2 checks
                    val l2Pass = status.hardwareBacked && status.hardwareType?.contains("Software", ignoreCase = true) != true
                    LevelDebugRow("L2", l2Pass, "hw=${status.hardwareBacked}, type=${status.hardwareType?.take(10)}")

                    // L3 checks - network key agreement (3 sources)
                    val dnsOk = status.dnsUsOk || status.dnsEuOk
                    val httpsOk = status.httpsUsOk || status.httpsEuOk
                    val l3Sources = listOf(status.registryOk, dnsOk, httpsOk).count { it }
                    val l3Pass = l3Sources >= 2
                    val regIcon = if (status.registryOk) "✓" else "✗"
                    val dnsIcon = if (dnsOk) "✓" else "✗"
                    val httpsIcon = if (httpsOk) "✓" else "✗"
                    LevelDebugRow("L3", l3Pass, "$l3Sources/3: Reg$regIcon DNS$dnsIcon HTTPS$httpsIcon")

                    // L4 checks
                    val l4Pass = status.moduleIntegrityOk
                    LevelDebugRow("L4", l4Pass, "module=${status.moduleIntegrityOk}, file=${status.fileIntegrityOk}")

                    // L5 checks
                    val l5Pass = status.auditOk && status.registryKeyStatus?.contains("active", ignoreCase = true) == true
                    LevelDebugRow("L5", l5Pass, "audit=${status.auditOk}, key=${status.registryKeyStatus?.take(10)}")

                    Divider(color = textColor.copy(alpha = 0.2f), modifier = Modifier.padding(vertical = 4.dp))

                    // Calculated vs reported
                    val calc = when {
                        l5Pass && l4Pass && l3Pass && l2Pass && l1Pass -> 5
                        l4Pass && l3Pass && l2Pass && l1Pass -> 4
                        l3Pass && l2Pass && l1Pass -> 3
                        l2Pass && l1Pass -> 2
                        l1Pass -> 1
                        else -> 0
                    }
                    val match = calc == status.maxLevel
                    Text(
                        text = localizedString("mobile.trust_calc_debug")
                            .replace("{calc}", calc.toString())
                            .replace("{api}", status.maxLevel.toString())
                            .replace("{pending}", status.levelPending.toString()),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                        color = if (match) SemanticColors.Default.success else SemanticColors.Default.error
                    )
                }
            }
        }
    }
}

@Composable
private fun LevelDebugRow(level: String, pass: Boolean, details: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = if (pass) "✓" else "✗",
                fontSize = 10.sp,
                color = if (pass) SemanticColors.Default.success else SemanticColors.Default.error
            )
            Text(text = level, fontSize = 10.sp, fontWeight = FontWeight.Medium)
        }
        Text(
            text = details,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
            color = SemanticColors.Default.inactive
        )
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
                text = localizedString("mobile.trust_checks"),
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = localizedString("mobile.trust_checks_desc"),
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
                description = "Platform: ${status.platformOs?.uppercase() ?: "Unknown"} -HW: ${status.hardwareType?.replace("_", " ") ?: "Unknown"}",
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
    // Check platformOs OR hardwareType for platform detection
    // (CIRISVerify may report "linux" instead of "android" - workaround until fixed)
    val isAndroid = status.platformOs?.lowercase() == "android" ||
        status.hardwareType?.contains("Android", ignoreCase = true) == true
    val isIos = status.platformOs?.lowercase() in listOf("ios", "ipados", "macos") ||
        status.hardwareType?.contains("Ios", ignoreCase = true) == true ||
        status.hardwareType?.contains("SecureEnclave", ignoreCase = true) == true

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.trust_device"),
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = localizedString("mobile.trust_device_desc"),
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
                                text = localizedString("mobile.trust_play_integrity"),
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
                            text = localizedString("mobile.trust_play_validates"),
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
                                text = localizedString("mobile.trust_app_attest"),
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                color = Color(0xFF6B7280)
                            )
                        }
                        Text(
                            text = localizedString("mobile.trust_app_attest_soon"),
                            fontSize = 12.sp,
                            color = Color(0xFF9CA3AF),
                            modifier = Modifier.padding(start = 22.dp)
                        )
                    }
                }
                else -> {
                    // Desktop/other - no device attestation available
                    Text(
                        text = localizedString("mobile.trust_device_unavailable").replace("{platform}", status.platformOs ?: "this platform"),
                        fontSize = 12.sp,
                        color = Color(0xFF9CA3AF)
                    )
                }
            }

            // Disclaimer
            Text(
                text = localizedString("mobile.trust_device_independent"),
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
        !passed -> SemanticColors.Default.error
        unverified -> SemanticColors.Default.warning
        else -> SemanticColors.Default.success
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
            color = SemanticColors.Default.inactive,
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
            color = if (passed) SemanticColors.Default.success else SemanticColors.Default.error
        )
        Text(
            text = label,
            fontSize = 10.sp,
            color = if (passed) SemanticColors.Default.success else SemanticColors.Default.inactive
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
            color = if (passed) SemanticColors.Default.success else SemanticColors.Default.error
        )
        Text(
            text = label,
            fontSize = 11.sp,
            color = if (passed) SemanticColors.Default.success else SemanticColors.Default.error
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
            Text(localizedString("mobile.trust_platform"), fontWeight = FontWeight.Bold)
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
            Text(localizedString("mobile.trust_file_integrity"), fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(localizedString("mobile.trust_checked").replace("{count}", status.filesChecked.toString()), fontSize = 12.sp, color = Color(0xFF6B7280))
                Text(localizedString("mobile.trust_passed").replace("{count}", (status.filesPassed ?: 0).toString()), fontSize = 12.sp, color = Color(0xFF059669))
                if ((status.filesFailed ?: 0) > 0) {
                    Text(localizedString("mobile.trust_failed_count").replace("{count}", status.filesFailed.toString()), fontSize = 12.sp, color = Color(0xFFDC2626))
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
        // Key is hardware-backed if: hardware_backed=true AND key_storage_mode is HW/SE/Keychain
        val hasHardwareStorage = status.hardwareBacked && (
            status.keyStorageMode?.contains("HW", ignoreCase = true) == true ||
            status.keyStorageMode?.contains("Secure Enclave", ignoreCase = true) == true ||
            status.keyStorageMode?.contains("Keychain", ignoreCase = true) == true ||
            status.keyStorageMode?.contains("Keystore", ignoreCase = true) == true ||
            status.keyStorageMode?.contains("TPM", ignoreCase = true) == true
        )
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
        // TPM platforms: attestation is implicit when hardware-backed with TPM
        // Mobile platforms: require Play Integrity (Android) or App Attest (iOS)
        val isTpm = status.hardwareType?.contains("TPM", ignoreCase = true) == true ||
            status.attestationProofHardwareType?.contains("TPM", ignoreCase = true) == true
        val deviceOk = (deviceAttestationResult as? DeviceAttestationResult.Success)?.verified == true
        val attestOk = when {
            isTpm -> status.hardwareBacked  // TPM attestation is implicit when hardware-backed
            else -> deviceOk || status.playIntegrityOk
        }
        ExpandableTierCard(
            level = 2,
            title = "Environment",
            passed = status.hardwareBacked && status.hardwareType?.contains("Software", ignoreCase = true) != true && attestOk,
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
            passed = status.moduleIntegrityOk,
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
        passed && !partial -> SemanticColors.Default.success  // Green - fully passed
        partial -> SemanticColors.Default.warning             // Yellow/amber - partial/warning
        else -> SemanticColors.Default.error                  // Red - failed
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
                    .testableClickable("item_tier_$level") { onToggle() }
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
                Icon(
                    if (expanded) CIRISIcons.arrowDown else CIRISIcons.arrowRight,
                    contentDescription = null,
                    modifier = Modifier.size(12.dp),
                    tint = Color(0xFF9CA3AF)
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
    val isIos = status.targetTriple?.contains("apple-ios") == true
    val binLabel = if (isIos) "__TEXT" else "Binary"
    return "$passed/2 checks -$binLabel: ${if (binaryOk) "✓" else "○"} Func: ${if (funcOk) "✓" else "○"}"
}

private fun buildL2ChecksInfo(status: VerifyStatusResponse, deviceResult: DeviceAttestationResult?): String {
    val isIos = status.platformOs?.lowercase() in listOf("ios", "ipados") ||
        status.hardwareType?.contains("Ios", ignoreCase = true) == true
    val isAndroid = status.platformOs?.lowercase() == "android" ||
        status.hardwareType?.contains("Android", ignoreCase = true) == true
    val isMacOs = status.platformOs?.lowercase() == "darwin" ||
        status.hardwareType?.contains("MacOs", ignoreCase = true) == true
    val isTpm = status.hardwareType?.contains("TPM", ignoreCase = true) == true ||
        status.attestationProofHardwareType?.contains("TPM", ignoreCase = true) == true
    val isDesktop = isMacOs || isTpm || status.platformOs?.lowercase() in listOf("linux", "win32", "windows")
    val isSoftwareOnly = status.hardwareType?.contains("Software", ignoreCase = true) == true
    val hwOk = status.hardwareBacked && !isSoftwareOnly

    // Device attestation varies by platform
    val attestOk = when {
        isTpm -> hwOk
        isDesktop -> hwOk  // Desktop SE/TPM attestation is implicit when hardware-backed
        else -> (deviceResult as? DeviceAttestationResult.Success)?.verified == true || status.playIntegrityOk
    }

    val passed = listOf(hwOk, attestOk).count { it }
    val attestLabel = when {
        isTpm -> "TPM"
        isMacOs -> "SE"
        isIos -> "Attest"
        isAndroid -> "Play"
        else -> "Device"
    }
    return "$passed/2 checks -HW: ${if (hwOk) "✓" else "○"} $attestLabel: ${if (attestOk) "✓" else "○"}"
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
    return "$agreement/$sources sources -$icon"
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
            "$verified/$expected -$failed failed"
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
        "$totalVerified/$totalExpected -$failed failed"
    } else {
        "$totalVerified/$totalExpected files"
    }
}

private fun buildL5ChecksInfo(status: VerifyStatusResponse): String {
    val keyOk = status.registryKeyStatus?.contains("active", ignoreCase = true) == true
    val auditOk = status.auditOk
    val passed = listOf(keyOk, auditOk).count { it }
    return "$passed/2 checks -Key: ${if (keyOk) "✓" else "○"} Audit: ${if (auditOk) "✓" else "○"}"
}

// L1 Content: Binary & Self-Verification
@Composable
private fun L1Content(status: VerifyStatusResponse) {
    // Explanation dropdown
    ExplanationDropdown(
        title = "What is Binary Verification?",
        whatItDoes = "Checks that the CIRISVerify security library loaded correctly. Computes a hash of the native binary and validates that critical security functions exist.",
        whyItMatters = "Helps detect tampering with the security library itself. If the verification code is modified, other checks may not be reliable.",
        howItWorks = "The library computes a SHA-256 hash of its own binary at runtime and compares it against the expected hash from the CIRIS Registry. Also checks that exported functions like signing haven't been replaced."
    )

    Spacer(modifier = Modifier.height(8.dp))

    // Identity Key - check for hardware-backed storage
    // Ed25519 signing key is wrapped (encrypted) by HW key if: hardware_backed=true AND key_storage_mode contains "HW"
    val hasHardwareStorage = status.hardwareBacked &&
        status.keyStorageMode?.contains("HW", ignoreCase = true) == true
    val isSoftwareOnly = !hasHardwareStorage
    val keyIconText = when {
        isSoftwareOnly -> null  // Use iconVector instead
        status.hardwareBacked -> "[K]"  // Hardware-backed
        else -> "[k]"  // Unknown/software
    }
    val keyIconVector = if (isSoftwareOnly) CIRISIcons.warning else null
    val storageMode = status.keyStorageMode ?: (if (status.hardwareBacked) "Hardware-backed" else "Software")
    val displayValue = if (isSoftwareOnly) {
        "$storageMode (Software-Only)"
    } else {
        storageMode
    }
    DetailRow(
        icon = keyIconText,
        iconVector = keyIconVector,
        label = "Identity Key (Ed25519)",
        value = displayValue,
        ok = !isSoftwareOnly,
        pending = isSoftwareOnly  // Yellow/warning for software-only
    )
    if (hasHardwareStorage) {
        DetailSubtext("✓ Ed25519 key wrapped by hardware-stored AES key")
    } else if (isSoftwareOnly) {
        DetailSubtext("[!] No hardware security module - keys protected by OS only")
    }
    status.ed25519Fingerprint?.let {
        DetailSubtext("Fingerprint: ${it.take(20)}...")
    }

    // Target
    val target = status.targetTriple ?: "${status.platformArch ?: "?"}-${status.platformOs?.lowercase() ?: "?"}"
    DetailRow(icon = "[P]", label = "Registry Target", value = target, ok = true)

    // Binary self-check (iOS: __TEXT segment hash; other platforms: full binary hash)
    val binaryOk = status.binarySelfCheck == "verified"
    val isIosPlatform = status.targetTriple?.contains("apple-ios") == true
    DetailRow(
        label = if (isIosPlatform) "__TEXT Segment" else "Binary Hash",
        value = if (binaryOk) "Verified" else (status.binarySelfCheck ?: "Unknown"),
        ok = binaryOk
    )
    status.binaryHash?.let { DetailSubtext("Hash: ${it.take(20)}...") }

    // Function Integrity (exported symbol verification)
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
            text = localizedString("mobile.trust_failed_functions"),
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = Color(0xFFDC2626),
            modifier = Modifier.padding(start = 8.dp, top = 4.dp)
        )
        failedFuncs.take(5).forEach { func ->
            Text(
                text = "  -$func",
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
    val isIos = status.platformOs?.lowercase() in listOf("ios", "ipados")
    // Check for TPM platform (Linux/Windows desktop)
    val isTpm = status.hardwareType?.contains("TPM", ignoreCase = true) == true ||
        status.attestationProofHardwareType?.contains("TPM", ignoreCase = true) == true

    // Explanation dropdown - platform-specific content
    val (whatItDoes, whyItMatters, howItWorks) = when {
        isTpm -> Triple(
            "Verifies TPM 2.0 hardware security module presence and generates PCR quotes for platform state attestation.",
            "TPM provides hardware-rooted trust. PCR quotes cryptographically prove the system boot state hasn't been tampered with.",
            "The TPM generates signed quotes of Platform Configuration Registers (PCRs) using its Attestation Key. The Endorsement Key certificate chains to the manufacturer."
        )
        isIos -> Triple(
            "Checks for iOS Secure Enclave and uses Apple App Attest to assess device and app integrity.",
            "Secure Enclave makes key extraction harder. App Attest helps detect modified apps, jailbroken devices, or unofficial installs.",
            "App Attest uses the Secure Enclave to generate attestations verified by Apple. Signing keys are stored in hardware-backed storage."
        )
        else -> Triple(
            "Checks for Android StrongBox/TEE and uses Google Play Integrity to assess device and app integrity.",
            "Hardware security modules make key extraction harder. Play Integrity helps detect modified apps, rooted devices, or unofficial installs.",
            "Play Integrity contacts Google's servers to check device integrity and app authenticity. Signing keys are stored in hardware-backed storage when available."
        )
    }
    ExplanationDropdown(
        title = "What is Environment Verification?",
        whatItDoes = whatItDoes,
        whyItMatters = whyItMatters,
        howItWorks = howItWorks
    )

    Spacer(modifier = Modifier.height(8.dp))

    // Platform
    DetailRow(
        icon = if (isTpm) "[PC]" else "[M]",
        label = "Platform",
        value = "${status.platformOs ?: "?"} -${status.platformArch ?: "?"}",
        ok = true
    )

    // Hardware Security Module - TPM, Secure Enclave, or Android Keystore
    val isIosPlatform = status.platformOs?.lowercase() in listOf("ios", "ipados") ||
        status.hardwareType?.contains("Ios", ignoreCase = true) == true
    val isMacPlatform = status.platformOs?.lowercase() == "darwin" ||
        status.hardwareType?.contains("MacOs", ignoreCase = true) == true
    val isAppleSE = isIosPlatform || isMacPlatform
    val hasHwEncryption = status.hardwareBacked && (
        status.keyStorageMode?.contains("HW", ignoreCase = true) == true ||
        status.keyStorageMode?.contains("Secure Enclave", ignoreCase = true) == true ||
        status.keyStorageMode?.contains("Keychain", ignoreCase = true) == true ||
        status.keyStorageMode?.contains("Keystore", ignoreCase = true) == true ||
        status.keyStorageMode?.contains("TPM", ignoreCase = true) == true
    )
    val keystoreLabel = when {
        isTpm -> "TPM 2.0"
        isAppleSE -> "Secure Enclave"
        else -> "Hardware Keystore"
    }
    val keystoreValue = when {
        isTpm && status.hardwareBacked -> status.hardwareType?.replace("_", " ") ?: "TPM Hardware"
        hasHwEncryption -> status.keyStorageMode ?: "Hardware-backed"
        isAppleSE && status.hardwareBacked -> "Apple SE (ECIES)"
        status.hardwareBacked -> "Hardware-backed (${status.keyStorageMode ?: "unknown"})"
        else -> "Software fallback"
    }
    DetailRow(
        label = keystoreLabel,
        value = keystoreValue,
        ok = status.hardwareBacked && (hasHwEncryption || isTpm || isAppleSE),
        pending = status.hardwareBacked && !hasHwEncryption && !isTpm && !isAppleSE
    )

    // Device/Platform Attestation: TPM Quote (desktop), App Attest (iOS), or Play Integrity (Android)
    if (isTpm) {
        // TPM attestation - PCR quote generated, but NOT verified against manufacturer revocations
        // Full remote attestation would require checking EK cert against TPM manufacturer CRLs
        DetailRow(
            label = "TPM Attestation",
            value = if (status.hardwareBacked) "PCR Quote Available" else "Not available",
            ok = status.hardwareBacked,
            pending = status.hardwareBacked  // Yellow: quote exists but not remotely verified
        )
        if (status.hardwareBacked) {
            DetailSubtext("-AK-signed PCR quote generated")
            DetailSubtext("-EK certificate retrieved")
            DetailSubtext("-Remote verification: not implemented")
        }
    } else if (isMacPlatform) {
        // macOS: App Store distribution provides attestation via codesigning + notarization
        val isAppStoreDistributed = false // TODO: detect via bundle receipt or codesign entitlements
        DetailRow(
            label = "App Store Distribution",
            value = if (isAppStoreDistributed) "Notarized" else "Development build (unsigned)",
            ok = isAppStoreDistributed,
            pending = !isAppStoreDistributed
        )
        if (!isAppStoreDistributed) {
            DetailSubtext("-SE hardware available but entitlements require App Store distribution")
            DetailSubtext("-Install from Mac App Store for full L2 attestation")
        }
    } else {
        // Mobile attestation: App Attest (iOS) / Play Integrity (Android)
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
                    if (deviceResult.meetsStrongIntegrity) DetailSubtext("-Strong integrity")
                    if (deviceResult.meetsDeviceIntegrity) DetailSubtext("-Device integrity")
                    if (deviceResult.meetsBasicIntegrity) DetailSubtext("-Basic integrity")
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
}

// L3 Content: Registry Cross-Validation
@Composable
private fun L3Content(status: VerifyStatusResponse) {
    // Explanation dropdown
    ExplanationDropdown(
        title = "What is Registry Cross-Validation?",
        whatItDoes = "Contacts the CIRIS Registry through 3 independent channels (DNS US, DNS EU, and direct HTTPS) to check that your Steward Key and file hashes are registered.",
        whyItMatters = "Multiple sources reduce single points of failure. If one channel is compromised or unavailable, discrepancies may be detected. At least 2 of 3 sources must agree.",
        howItWorks = "Your Ed25519 public key fingerprint is queried via DNS TXT records in US and EU regions, plus a direct HTTPS API call. Matching responses indicate consistent registry data."
    )

    Spacer(modifier = Modifier.height(8.dp))

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

    // Explanation dropdown (legacy mode)
    ExplanationDropdown(
        title = "What is Code Integrity?",
        whatItDoes = "Compares file hashes against the official CIRIS Registry manifest. Checks Python code, configuration files, and dependencies.",
        whyItMatters = "Helps detect if files have been modified, added, or removed since the official release. Can reveal code injection, backdoors, or unauthorized modifications.",
        howItWorks = "Files are verified through up to 3 sources: (1) Disk - files extracted to filesystem, (2) Agent Cache - Python files loaded by Chaquopy at startup but kept in memory, not on disk, (3) Registry manifest. A file passes if ANY local source matches the registry."
    )

    Spacer(modifier = Modifier.height(8.dp))

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
    // Explanation dropdown
    ExplanationDropdown(
        title = "What is Code Integrity?",
        whatItDoes = "Compares file hashes against the official CIRIS Registry manifest. Checks Python code, configuration files, and dependencies.",
        whyItMatters = "Helps detect if files have been modified, added, or removed since the official release. Can reveal code injection, backdoors, or unauthorized modifications.",
        howItWorks = "Files are verified through up to 3 sources: (1) Disk - files extracted to filesystem, (2) Agent Cache - Python files loaded by Chaquopy at startup but kept in memory, not on disk, (3) Registry manifest. A file passes if ANY local source matches the registry."
    )

    Spacer(modifier = Modifier.height(8.dp))

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
                    .testableClickable("item_disk_agent_mismatch") { diskAgentMismatchExpanded = !diskAgentMismatchExpanded }
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
                    text = "[!] TAMPERING: Disk != Agent Hash (${diskAgentMismatch.size}):",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFDC2626)
                )
            }
            if (diskAgentMismatchExpanded) {
                diskAgentMismatch.keys.take(20).forEach { path ->
                    Text(
                        text = "    -$path",
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
                    .testableClickable("item_registry_mismatch") { registryMismatchExpanded = !registryMismatchExpanded }
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
                        text = "    -$path",
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
    fileColor: Color,
    testTag: String? = null
) {
    // Generate a test tag from title if not provided
    val tag = testTag ?: "item_file_section_${title.lowercase().replace(Regex("[^a-z0-9]+"), "_").take(30)}"
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable(tag) { onToggle() }
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
                text = "  -$file",
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
    // Explanation dropdown
    ExplanationDropdown(
        title = "What is Registry & Audit?",
        whatItDoes = "Checks that YOUR cryptographic identity (Steward Key) is registered and active in the CIRIS Registry, and that security events are being logged to an audit trail.",
        whyItMatters = "The Steward Key identifies YOU as the human operator who purchased this agent through the Portal. This is your identity, not the agent's. The audit trail helps reveal tampering by logging attestation events.",
        howItWorks = "Your Ed25519 Steward Key is registered at purchase. The registry checks if it's active and not revoked. Attestation events are signed with your Steward Key and logged."
    )

    Spacer(modifier = Modifier.height(8.dp))

    // Registry Key
    val keyStatus = status.registryKeyStatus ?: "not_checked"
    val keyOk = keyStatus.contains("active", ignoreCase = true)
    DetailRow(
        label = "Registry Key",
        value = keyStatus.replaceFirstChar { it.uppercase() },
        ok = keyOk,
        pending = keyStatus == "not_checked"
    )

    // Show full fingerprint when registry key check fails or for debugging
    status.ed25519Fingerprint?.let { fingerprint ->
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 18.dp, top = 4.dp, bottom = 4.dp)
                .background(Color(0x10000000), shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp))
                .padding(8.dp)
        ) {
            Text(
                text = "Ed25519 Fingerprint (SHA-256):",
                fontSize = 10.sp,
                color = Color.Gray,
                fontWeight = FontWeight.Medium
            )
            SelectionContainer {
                Text(
                    text = fingerprint,
                    fontSize = 9.sp,
                    fontFamily = FontFamily.Monospace,
                    color = if (keyOk) SemanticColors.Default.success else SemanticColors.Default.error,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
            Text(
                text = "This hash is checked against registry.ciris.ai",
                fontSize = 8.sp,
                color = Color.Gray,
                fontStyle = FontStyle.Italic,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }

    // Show hint when at L4 and registry key not found - user can upgrade to L5
    if (status.maxLevel == 4 && keyStatus.contains("not_found", ignoreCase = true)) {
        Text(
            text = localizedString("mobile.trust_wizard_hint"),
            fontSize = 10.sp,
            color = Color(0xFF2563EB),
            fontStyle = FontStyle.Italic,
            modifier = Modifier.padding(start = 18.dp, top = 2.dp, bottom = 4.dp)
        )
    }

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
            text = localizedString("mobile.trust_copy_diagnostics"),
            fontSize = 11.sp,
            color = Color(0xFF2563EB),
            modifier = Modifier
                .testableClickable("btn_l5_copy_diagnostics") { onCopyDiagnostics() }
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
    icon: String? = null,
    iconVector: ImageVector? = null
) {
    val color = when {
        ok -> SemanticColors.Default.success
        pending -> SemanticColors.Default.warning
        else -> SemanticColors.Default.error
    }
    val statusIcon = when {
        ok -> CIRISIcons.check
        pending -> CIRISIcons.circle
        else -> CIRISIcons.xmark
    }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            when {
                iconVector != null -> Icon(iconVector, contentDescription = null, modifier = Modifier.size(12.dp), tint = Color(0xFF4B5563))
                icon != null -> Text(text = icon, fontSize = 12.sp, color = Color(0xFF4B5563))
            }
            Text(text = label, fontSize = 12.sp, color = Color(0xFF4B5563))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(statusIcon, contentDescription = null, modifier = Modifier.size(11.dp), tint = color)
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

/**
 * Expandable explanation dropdown for each attestation tier.
 * Shows "[i] What is this?" header that expands to show detailed explanation.
 */
@Composable
private fun ExplanationDropdown(
    title: String,
    whatItDoes: String,
    whyItMatters: String,
    howItWorks: String
) {
    var expanded by remember { mutableStateOf(false) }
    // Generate a test tag from title
    val tag = "item_explanation_${title.lowercase().replace(Regex("[^a-z0-9]+"), "_").take(30)}"

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
    ) {
        // Header row - clickable to expand
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable(tag) { expanded = !expanded }
                .background(Color(0xFFF0F9FF), RoundedCornerShape(6.dp))
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(CIRISIcons.info, contentDescription = null, modifier = Modifier.size(12.dp), tint = Color(0xFF0369A1))
                Text(
                    text = title,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color(0xFF0369A1)
                )
            }
            Text(
                text = if (expanded) "▼" else "▶",
                fontSize = 10.sp,
                color = Color(0xFF0369A1)
            )
        }

        // Expanded content
        if (expanded) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color(0xFFF0F9FF).copy(alpha = 0.5f), RoundedCornerShape(bottomStart = 6.dp, bottomEnd = 6.dp))
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // What it does
                Column {
                    Text(
                        text = localizedString("mobile.trust_what_checks"),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF1E40AF)
                    )
                    Text(
                        text = whatItDoes,
                        fontSize = 10.sp,
                        color = Color(0xFF374151),
                        lineHeight = 14.sp
                    )
                }

                // Why it matters
                Column {
                    Text(
                        text = localizedString("mobile.trust_why_matters"),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF1E40AF)
                    )
                    Text(
                        text = whyItMatters,
                        fontSize = 10.sp,
                        color = Color(0xFF374151),
                        lineHeight = 14.sp
                    )
                }

                // How it works
                Column {
                    Text(
                        text = localizedString("mobile.trust_how_works"),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF1E40AF)
                    )
                    Text(
                        text = howItWorks,
                        fontSize = 10.sp,
                        color = Color(0xFF374151),
                        lineHeight = 14.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun VerificationDetailsCard(status: VerifyStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                text = localizedString("mobile.trust_details"),
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
                val keyIconVector = if (status.hardwareBacked) CIRISIcons.keySecure else CIRISIcons.key
                val storageMode = status.keyStorageMode ?: (if (status.hardwareBacked) "Hardware-backed" else "Software")
                CheckRow(
                    label = "Identity Key",
                    value = storageMode,
                    ok = true,
                    iconVector = keyIconVector,
                    detail = status.ed25519Fingerprint?.let { "Fingerprint: ${it.take(16)}..." }
                )

                // Target
                val targetTriple = status.targetTriple ?: "${status.platformArch ?: "unknown"}-${status.platformOs?.lowercase() ?: "unknown"}"
                CheckRow(
                    label = "Registry Target",
                    value = targetTriple,
                    ok = true,
                    iconVector = CIRISIcons.pkg  // package icon
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
    iconVector: ImageVector? = null,
    detail: String? = null
) {
    val color = when {
        ok -> SemanticColors.Default.success
        pending -> SemanticColors.Default.warning
        else -> SemanticColors.Default.error
    }
    val statusIcon = when {
        ok -> CIRISIcons.check
        pending -> CIRISIcons.circle
        else -> CIRISIcons.xmark
    }

    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                when {
                    iconVector != null -> Icon(iconVector, contentDescription = null, modifier = Modifier.size(12.dp), tint = Color(0xFF4B5563))
                    icon != null -> Text(text = icon, fontSize = 12.sp, color = Color(0xFF4B5563))
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
                Icon(statusIcon, contentDescription = null, modifier = Modifier.size(11.dp), tint = color)
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
                    .testableClickable("item_diagnostics_log") { expanded = !expanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(if (expanded) CIRISIcons.arrowDown else CIRISIcons.play, contentDescription = null, modifier = Modifier.size(16.dp))
                    Text(
                        text = "Verify Log",
                        fontWeight = FontWeight.Medium
                    )
                }
                TextButton(
                    onClick = onCopy,
                    modifier = Modifier.testableClickable("btn_copy_diagnostics") { onCopy() },
                    enabled = !diagnostics.isNullOrEmpty()
                ) {
                    Text(localizedString("mobile.common_copy"))
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
                        // Check for null, empty, or literal "null" string
                        val hasContent = !diagnostics.isNullOrEmpty() && diagnostics != "null"
                        if (!hasContent) {
                            Text(
                                text = localizedString("mobile.trust_no_diagnostics"),
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                                color = Color(0xFF9CA3AF)
                            )
                        } else {
                            // Split into lines and display with proper formatting
                            diagnostics!!.lines().forEach { line ->
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
                    text = localizedString("mobile.trust_log_desc"),
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
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceWarning)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = localizedString("mobile.trust_key_inactive"),
                fontWeight = FontWeight.Bold,
                color = SemanticColors.Default.onWarning
            )
            Text(
                text = localizedString("mobile.trust_key_status").replace("{status}", status.keyStatus),
                fontSize = 12.sp,
                color = SemanticColors.Default.warning
            )
            Text(
                text = when (status.keyStatus) {
                    "none" -> "No identity key configured. The identity key is optional and enables validation against the public infrastructure and your audit log."
                    "ephemeral" -> "Using an ephemeral key. To enable full attestation, connect to a CIRISNode to obtain a genesis identity key."
                    "portal_pending" -> "Identity key pending activation. Please complete the device authorization in your browser."
                    else -> "The identity key is not yet active. This is optional and enables additional attestation capabilities."
                },
                fontSize = 12.sp,
                color = SemanticColors.Default.warning
            )
        }
    }
}

@Composable
private fun DisclaimerCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceSuccess)
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = localizedString("mobile.trust_verify_desc"),
                fontSize = 12.sp,
                color = SemanticColors.Default.onSuccess
            )
            Text(
                text = localizedString("mobile.trust_verify_disclaimer"),
                fontSize = 11.sp,
                color = SemanticColors.Default.inactive,
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
                    Text(localizedString("mobile.common_copy"))
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
        color = if (value) SemanticColors.Default.success else SemanticColors.Default.error
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
