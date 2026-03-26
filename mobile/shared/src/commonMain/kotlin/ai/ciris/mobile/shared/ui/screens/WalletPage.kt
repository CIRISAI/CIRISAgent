package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.background
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

/**
 * Wallet status response from API
 */
@Serializable
data class WalletStatusResponse(
    val hasWallet: Boolean = false,
    val provider: String = "x402",
    val network: String = "base-sepolia",
    val currency: String = "USDC",
    val balance: String = "0.00",
    val address: String? = null,
    val isReceiveOnly: Boolean = false,
    val hardwareTrustDegraded: Boolean = false,
    val trustDegradationReason: String? = null,
    val attestationLevel: Int = 0,
    val maxTransactionLimit: String = "0.00",
    val dailyLimit: String = "0.00"
)

/**
 * Wallet Page - Full-page view of wallet status and balance
 *
 * Shows:
 * - Current balance in USDC
 * - Wallet address (Base L2)
 * - Transaction limits based on attestation level
 * - Hardware trust status
 * - Send/Receive options
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WalletPage(
    apiClient: CIRISApiClient,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var walletStatus by remember { mutableStateOf<WalletStatusResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val coroutineScope = rememberCoroutineScope()

    // Fetch wallet status on mount
    LaunchedEffect(Unit) {
        fetchWalletStatus(
            apiClient = apiClient,
            onSuccess = {
                walletStatus = it
                loading = false
                error = null
            },
            onError = { error = it; loading = false }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Wallet") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_wallet_back") { onNavigateBack() }
                    ) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = {
                            loading = true
                            coroutineScope.launch {
                                fetchWalletStatus(
                                    apiClient = apiClient,
                                    onSuccess = { walletStatus = it; loading = false; error = null },
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
            when {
                loading -> LoadingWalletCard()
                error != null -> WalletErrorCard(error = error!!, onRetry = {
                    loading = true
                    coroutineScope.launch {
                        fetchWalletStatus(
                            apiClient = apiClient,
                            onSuccess = { walletStatus = it; loading = false; error = null },
                            onError = { error = it; loading = false }
                        )
                    }
                })
                walletStatus != null -> {
                    val status = walletStatus!!

                    // Balance card
                    WalletBalanceCard(status = status)

                    // Address card
                    if (status.address != null) {
                        WalletAddressCard(address = status.address, network = status.network)
                    }

                    // Limits card
                    WalletLimitsCard(status = status)

                    // Hardware trust warning
                    if (status.hardwareTrustDegraded) {
                        HardwareTrustWarningCard(reason = status.trustDegradationReason)
                    }
                }
            }
        }
    }
}

@Composable
private fun LoadingWalletCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF5F5F5))
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(40.dp),
            contentAlignment = Alignment.Center
        ) {
            CircularProgressIndicator()
        }
    }
}

@Composable
private fun WalletErrorCard(error: String, onRetry: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceError)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(text = "Failed to load wallet", fontWeight = FontWeight.Bold, color = SemanticColors.Default.error)
            Text(text = error, fontSize = 14.sp, color = SemanticColors.Default.error.copy(alpha = 0.8f))
            Button(onClick = onRetry) {
                Text("Retry")
            }
        }
    }
}

@Composable
private fun WalletBalanceCard(status: WalletStatusResponse) {
    val bgColor = when {
        status.isReceiveOnly -> SemanticColors.Default.surfaceWarning
        status.balance != "0.00" && status.balance != "0" -> SemanticColors.Default.surfaceSuccess
        else -> Color(0xFFF5F5F5)
    }
    val textColor = when {
        status.isReceiveOnly -> SemanticColors.Default.onWarning
        status.balance != "0.00" && status.balance != "0" -> SemanticColors.Default.onSuccess
        else -> SemanticColors.Default.inactive
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Wallet emoji
            Text(text = "💰", fontSize = 48.sp)

            // Balance
            Text(
                text = "${status.balance} ${status.currency}",
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
                color = textColor
            )

            // Provider/Network
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = textColor.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = status.provider.uppercase(),
                        fontSize = 12.sp,
                        color = textColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = textColor.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = status.network,
                        fontSize = 12.sp,
                        color = textColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Receive-only warning
            if (status.isReceiveOnly) {
                Text(
                    text = "Receive Only - Sending disabled due to hardware trust",
                    fontSize = 12.sp,
                    color = textColor.copy(alpha = 0.8f)
                )
            }
        }
    }
}

@Composable
private fun WalletAddressCard(address: String, network: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "Wallet Address",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )
            Text(
                text = address,
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "Network: $network",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}

@Composable
private fun WalletLimitsCard(status: WalletStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Transaction Limits",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )

            // Attestation level
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(text = "Attestation Level", fontSize = 13.sp)
                Text(
                    text = "${status.attestationLevel}/5",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }

            // Max transaction
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(text = "Max Transaction", fontSize = 13.sp)
                Text(
                    text = "$${status.maxTransactionLimit} ${status.currency}",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }

            // Daily limit
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(text = "Daily Limit", fontSize = 13.sp)
                Text(
                    text = "$${status.dailyLimit} ${status.currency}",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }

            // Explanation
            Text(
                text = "Limits increase with higher attestation levels. Complete trust verification to increase limits.",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}

@Composable
private fun HardwareTrustWarningCard(reason: String?) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceWarning)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(text = "Warning", fontSize = 16.sp)
                Text(
                    text = "Hardware Trust Degraded",
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = SemanticColors.Default.onWarning
                )
            }

            Text(
                text = reason ?: "Device security features are compromised. Wallet is in receive-only mode.",
                fontSize = 13.sp,
                color = SemanticColors.Default.onWarning.copy(alpha = 0.9f)
            )

            Text(
                text = "Sending transactions is disabled to protect your funds.",
                fontSize = 12.sp,
                color = SemanticColors.Default.onWarning.copy(alpha = 0.7f)
            )
        }
    }
}

private suspend fun fetchWalletStatus(
    apiClient: CIRISApiClient,
    onSuccess: (WalletStatusResponse) -> Unit,
    onError: (String) -> Unit
) {
    try {
        // For now, return a placeholder status
        // TODO: Add actual wallet API endpoint when backend is ready
        val response = WalletStatusResponse(
            hasWallet = true,
            provider = "x402",
            network = "base-sepolia",
            currency = "USDC",
            balance = "0.00",
            address = null,  // Will be populated when CIRISVerify derives address
            isReceiveOnly = false,
            hardwareTrustDegraded = false,
            attestationLevel = 0,
            maxTransactionLimit = "0.00",
            dailyLimit = "0.00"
        )
        onSuccess(response)
        PlatformLogger.d("WalletPage", "Wallet status fetched (placeholder)")
    } catch (e: Exception) {
        PlatformLogger.e("WalletPage", "Failed to fetch wallet status: ${e.message}")
        onError(e.message ?: "Unknown error")
    }
}
