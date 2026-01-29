package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Consent management screen for GDPR/privacy controls
 * Based on CIRISGUI-Standalone/apps/agui/app/consent/page.tsx
 *
 * Features:
 * - Current consent status display
 * - Consent stream selection (TEMPORARY, PARTNERED, ANONYMOUS)
 * - Impact dashboard for partnered/anonymous users
 * - Consent audit trail
 * - Partnership request flow
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConsentScreen(
    consentData: ConsentScreenData,
    isLoading: Boolean,
    onStreamSelect: (String) -> Unit,
    onRequestPartnership: () -> Unit,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showStreamConfirmDialog by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Consent Management") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    IconButton(onClick = onRefresh, enabled = !isLoading) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        if (isLoading && !consentData.hasConsent) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Current status banner
                item {
                    CurrentConsentBanner(
                        currentStream = consentData.currentStream,
                        expiresAt = consentData.expiresAt,
                        partnershipPending = consentData.partnershipPending
                    )
                }

                // No consent notice
                if (!consentData.hasConsent) {
                    item {
                        NoConsentNotice()
                    }
                }

                // Partnership pending notice
                if (consentData.partnershipPending) {
                    item {
                        PartnershipPendingBanner()
                    }
                }

                // Consent notes
                item {
                    ConsentInfoCard()
                }

                // Stream selection
                item {
                    Text(
                        text = "Choose Your Consent Stream",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(consentData.availableStreams) { stream ->
                    StreamCard(
                        stream = stream,
                        isActive = stream.id == consentData.currentStream,
                        onSelect = {
                            if (stream.id == "partnered") {
                                onRequestPartnership()
                            } else {
                                showStreamConfirmDialog = stream.id
                            }
                        }
                    )
                }

                // Impact dashboard (for partnered/anonymous users)
                if (consentData.currentStream in listOf("partnered", "anonymous") && consentData.impactData != null) {
                    item {
                        ImpactDashboardCard(impact = consentData.impactData)
                    }
                }

                // Audit trail
                if (consentData.auditEntries.isNotEmpty()) {
                    item {
                        Text(
                            text = "Consent History",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    item {
                        AuditTrailCard(entries = consentData.auditEntries)
                    }
                }

                // Privacy notice
                item {
                    Text(
                        text = "You can only view and manage your own consent settings.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 16.dp)
                    )
                }
            }
        }
    }

    // Stream change confirmation dialog
    showStreamConfirmDialog?.let { streamId ->
        val stream = consentData.availableStreams.find { it.id == streamId }
        AlertDialog(
            onDismissRequest = { showStreamConfirmDialog = null },
            title = { Text("Change Consent Stream") },
            text = {
                Text(
                    when (streamId) {
                        "anonymous" -> "Switching to ANONYMOUS will anonymize your data while allowing statistical contributions. Continue?"
                        "temporary" -> "Switching to TEMPORARY will set a 14-day auto-forget period. Continue?"
                        else -> "Are you sure you want to change your consent stream to ${stream?.name ?: streamId}?"
                    }
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onStreamSelect(streamId)
                        showStreamConfirmDialog = null
                    }
                ) {
                    Text("Confirm")
                }
            },
            dismissButton = {
                TextButton(onClick = { showStreamConfirmDialog = null }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
private fun CurrentConsentBanner(
    currentStream: String?,
    expiresAt: String?,
    partnershipPending: Boolean,
    modifier: Modifier = Modifier
) {
    val streamColor = getStreamColor(currentStream)
    val streamIcon = getStreamIcon(currentStream)

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = streamColor.copy(alpha = 0.15f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = streamIcon,
                style = MaterialTheme.typography.headlineMedium
            )

            Spacer(modifier = Modifier.width(16.dp))

            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = (currentStream?.uppercase() ?: "NONE") + " Mode",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = streamColor
                )

                if (currentStream == "temporary" && expiresAt != null) {
                    Text(
                        text = "Expires: $expiresAt",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                if (partnershipPending) {
                    Text(
                        text = "Partnership request pending...",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFFF59E0B)
                    )
                }
            }
        }
    }
}

@Composable
private fun NoConsentNotice(modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFFFEF3C7)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Consent Record Not Yet Created",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF92400E)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Your consent record will be automatically created after your first interaction with CIRIS. This ensures meaningful engagement before establishing a consent relationship.",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFFB45309)
            )
        }
    }
}

@Composable
private fun PartnershipPendingBanner(modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFFDCFCE7)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Partnership Request Pending",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF166534)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Your partnership request is being reviewed. You will be notified when a decision is made.",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF15803D)
            )
        }
    }
}

@Composable
private fun ConsentInfoCard(modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "About Consent Streams",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "CIRIS offers three consent streams to give you control over your data:",
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                text = "TEMPORARY: Basic interactions with 14-day auto-forget\nPARTNERED: Mutual growth with full personalization\nANONYMOUS: Help others while removing identity",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun StreamCard(
    stream: ConsentStreamInfo,
    isActive: Boolean,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier
) {
    val borderColor = if (isActive) MaterialTheme.colorScheme.primary else Color.Transparent

    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(
                width = if (isActive) 2.dp else 0.dp,
                color = borderColor,
                shape = RoundedCornerShape(12.dp)
            ),
        colors = CardDefaults.cardColors(
            containerColor = if (isActive)
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            else
                MaterialTheme.colorScheme.surface
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = getStreamIcon(stream.id),
                style = MaterialTheme.typography.headlineLarge
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = stream.name,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Text(
                text = stream.description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 8.dp)
            )

            // Benefits list
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier.padding(bottom = 8.dp)
            ) {
                stream.benefits.forEach { benefit ->
                    Text(
                        text = benefit,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            // Duration info
            stream.durationDays?.let { days ->
                Text(
                    text = "Duration: $days days",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (stream.requiresApproval) {
                Text(
                    text = "Requires agent approval",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFFF59E0B)
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            Button(
                onClick = onSelect,
                enabled = !isActive,
                modifier = Modifier.fillMaxWidth(),
                colors = if (isActive) {
                    ButtonDefaults.buttonColors(
                        containerColor = Color.Gray,
                        contentColor = Color.White
                    )
                } else {
                    ButtonDefaults.buttonColors()
                }
            ) {
                Text(
                    when {
                        isActive -> "Current Stream"
                        stream.id == "partnered" -> "Request Partnership"
                        else -> "Switch Stream"
                    }
                )
            }
        }
    }
}

@Composable
private fun ImpactDashboardCard(
    impact: ConsentImpactData,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Your Impact",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Spacer(modifier = Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                ImpactMetric(
                    value = impact.totalInteractions.toString(),
                    label = "Interactions",
                    color = MaterialTheme.colorScheme.primary
                )
                ImpactMetric(
                    value = impact.patternsContributed.toString(),
                    label = "Patterns",
                    color = Color(0xFF10B981)
                )
                ImpactMetric(
                    value = impact.usersHelped.toString(),
                    label = "Users Helped",
                    color = Color(0xFF3B82F6)
                )
                ImpactMetric(
                    value = "${((impact.impactScore * 10).toInt() / 10.0)}",
                    label = "Score",
                    color = Color(0xFF8B5CF6)
                )
            }
        }
    }
}

@Composable
private fun ImpactMetric(
    value: String,
    label: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun AuditTrailCard(
    entries: List<ConsentAuditEntryData>,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            entries.forEach { entry ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "${entry.previousStream} -> ${entry.newStream}",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = entry.reason ?: "No reason provided",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = entry.timestamp,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "by ${entry.initiatedBy}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                if (entry != entries.last()) {
                    HorizontalDivider()
                }
            }
        }
    }
}

// Helper functions
private fun getStreamColor(stream: String?): Color {
    return when (stream?.lowercase()) {
        "temporary" -> Color(0xFFF59E0B) // Yellow
        "partnered" -> Color(0xFF10B981) // Green
        "anonymous" -> Color(0xFF3B82F6) // Blue
        else -> Color.Gray
    }
}

private fun getStreamIcon(stream: String?): String {
    return when (stream?.lowercase()) {
        "temporary" -> "\uD83D\uDEE1\uFE0F" // Shield
        "partnered" -> "\uD83E\uDD1D" // Handshake
        "anonymous" -> "\uD83D\uDC64" // Person silhouette
        else -> "\uD83D\uDCCB" // Clipboard
    }
}

// Data classes

data class ConsentScreenData(
    val hasConsent: Boolean = false,
    val currentStream: String? = null,
    val expiresAt: String? = null,
    val partnershipPending: Boolean = false,
    val availableStreams: List<ConsentStreamInfo> = emptyList(),
    val impactData: ConsentImpactData? = null,
    val auditEntries: List<ConsentAuditEntryData> = emptyList()
)

data class ConsentStreamInfo(
    val id: String,
    val name: String,
    val description: String,
    val durationDays: Int? = null,
    val autoForget: Boolean = false,
    val learningEnabled: Boolean = false,
    val identityRemoved: Boolean = false,
    val requiresApproval: Boolean = false,
    val benefits: List<String> = emptyList()
)

data class ConsentImpactData(
    val totalInteractions: Int = 0,
    val patternsContributed: Int = 0,
    val usersHelped: Int = 0,
    val impactScore: Double = 0.0
)

data class ConsentAuditEntryData(
    val entryId: String,
    val timestamp: String,
    val previousStream: String,
    val newStream: String,
    val initiatedBy: String,
    val reason: String? = null
)
