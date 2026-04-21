package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.LocalCurrency
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

/**
 * Gas cost estimate for a standard transfer.
 */
@Serializable
data class GasEstimate(
    val gasPriceGwei: String = "0.00",
    val usdcTransferGas: Int = 65000,
    val ethTransferGas: Int = 21000,
    val usdcTransferCostEth: String = "0.000000",
    val usdcTransferCostUsd: String = "0.00",
    val ethPriceUsd: String = "2000"
)

/**
 * Spending progress for session and daily limits.
 */
@Serializable
data class SpendingProgress(
    val sessionSpent: String = "0.00",
    val sessionRemaining: String = "500.00",
    val sessionLimit: String = "500.00",
    val sessionResetMinutes: Int = 60,
    val dailySpent: String = "0.00",
    val dailyRemaining: String = "1000.00",
    val dailyResetHours: Int = 24
)

/**
 * Summary of a recent transaction.
 */
@Serializable
data class TransactionSummary(
    val transactionId: String,
    val type: String,  // "send" or "receive"
    val amount: String,
    val currency: String,
    val recipient: String? = null,
    val sender: String? = null,
    val status: String,  // "pending", "confirmed", "failed"
    val timestamp: String,
    val explorerUrl: String? = null
)

/**
 * Security advisory affecting hardware trust.
 */
@Serializable
data class SecurityAdvisoryData(
    val cve: String? = null,
    val title: String,
    val impact: String,
    val remediation: String? = null
)

/**
 * Wallet status response from API with comprehensive state.
 */
@Serializable
data class WalletStatusResponse(
    // Core wallet info
    val hasWallet: Boolean = false,
    val isInitializing: Boolean = false,  // True while wallet providers are starting up
    val provider: String = "x402",
    val network: String = "base-mainnet",
    val currency: String = "USDC",
    val balance: String = "0.00",
    val ethBalance: String = "0.00",
    val needsGas: Boolean = true,
    val address: String? = null,

    // Paymaster status (ERC-4337 gasless transactions)
    val paymasterEnabled: Boolean = false,
    val paymasterKeyConfigured: Boolean = false,

    // Attestation and limits
    val isReceiveOnly: Boolean = false,
    val attestationLevel: Int = 0,
    val maxTransactionLimit: String = "0.00",
    val dailyLimit: String = "0.00",

    // Hardware trust status
    val hardwareTrustDegraded: Boolean = false,
    val trustDegradationReason: String? = null,
    val securityAdvisories: List<SecurityAdvisoryData> = emptyList(),

    // Spending progress (new)
    val spending: SpendingProgress? = null,

    // Gas estimates (new)
    val gasEstimate: GasEstimate? = null,

    // Recent transactions (new)
    val recentTransactions: List<TransactionSummary> = emptyList()
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

    // Fetch wallet status on mount and poll every 30 seconds for balance updates
    LaunchedEffect(Unit) {
        while (true) {
            fetchWalletStatus(
                apiClient = apiClient,
                onSuccess = {
                    walletStatus = it
                    loading = false
                    error = null
                    PlatformLogger.d("WalletPage", "Wallet status updated: balance=${it.balance}, level=${it.attestationLevel}")
                },
                onError = { error = it; loading = false }
            )
            kotlinx.coroutines.delay(30000) // Poll every 30 seconds for balance updates
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_wallet")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_wallet_back") { onNavigateBack() }
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = localizedString("mobile.common_back"))
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
                        Icon(CIRISIcons.refresh, contentDescription = localizedString("mobile.common_refresh"))
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

                    // Experimental warning card - always show first
                    ExperimentalWarningCard()

                    // Paymaster status card
                    PaymasterStatusCard(
                        paymasterEnabled = status.paymasterEnabled,
                        keyConfigured = status.paymasterKeyConfigured,
                        needsGas = status.needsGas
                    )

                    // Balance card
                    WalletBalanceCard(status = status)

                    // Address card
                    if (status.address != null) {
                        WalletAddressCard(address = status.address, network = status.network)
                    }

                    // Spending progress card (shows session/daily limits usage)
                    if (status.spending != null && !status.isReceiveOnly) {
                        SpendingProgressCard(spending = status.spending)
                    }

                    // Transfer card (only show if not receive-only and has address)
                    if (!status.isReceiveOnly && status.address != null) {
                        WalletTransferCard(
                            apiClient = apiClient,
                            maxAmount = status.maxTransactionLimit,
                            currency = status.currency,
                            onTransferComplete = {
                                // Refresh wallet status after transfer
                                loading = true
                                coroutineScope.launch {
                                    fetchWalletStatus(
                                        apiClient = apiClient,
                                        onSuccess = { walletStatus = it; loading = false; error = null },
                                        onError = { error = it; loading = false }
                                    )
                                }
                            }
                        )
                    }

                    // Limits and attestation card
                    WalletLimitsCard(status = status)

                    // Recent transactions card
                    if (status.recentTransactions.isNotEmpty()) {
                        TransactionHistoryCard(transactions = status.recentTransactions)
                    }

                    // Hardware trust warning with security advisories
                    if (status.hardwareTrustDegraded) {
                        HardwareTrustWarningCard(
                            reason = status.trustDegradationReason,
                            advisories = status.securityAdvisories
                        )
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
            Text(text = localizedString("mobile.wallet_failed"), fontWeight = FontWeight.Bold, color = SemanticColors.Default.error)
            Text(text = error, fontSize = 14.sp, color = SemanticColors.Default.error.copy(alpha = 0.8f))
            Button(onClick = onRetry) {
                Text(localizedString("mobile.common_retry"))
            }
        }
    }
}

@Composable
private fun ExperimentalWarningCard() {
    Card(
        modifier = Modifier.fillMaxWidth().testable("card_wallet_experimental"),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3CD))  // Amber/warning background
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Top
        ) {
            Icon(
                CIRISIcons.warning,
                contentDescription = null,
                modifier = Modifier.size(24.dp),
                tint = Color(0xFF856404)  // Dark amber
            )
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = localizedString("mobile.wallet_experimental_title"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = Color(0xFF856404)  // Dark amber text
                )
                Text(
                    text = localizedString("mobile.wallet_experimental_warning"),
                    fontSize = 13.sp,
                    color = Color(0xFF856404).copy(alpha = 0.9f)
                )
            }
        }
    }
}

@Composable
private fun PaymasterStatusCard(
    paymasterEnabled: Boolean,
    keyConfigured: Boolean,
    needsGas: Boolean
) {
    // Determine status
    val (icon, statusText, bgColor, textColor) = when {
        paymasterEnabled && keyConfigured -> {
            // Gasless transfers enabled
            Quadruple(
                "Gas[v]",
                localizedString("mobile.wallet_paymaster_active"),
                SemanticColors.Default.surfaceSuccess,
                SemanticColors.Default.onSuccess
            )
        }
        paymasterEnabled && !keyConfigured -> {
            // Paymaster enabled but no key - show warning
            Quadruple(
                "Gas[!]",
                localizedString("mobile.wallet_paymaster_key_missing"),
                SemanticColors.Default.surfaceWarning,
                SemanticColors.Default.onWarning
            )
        }
        else -> {
            // Paymaster not enabled - needs ETH for gas
            Quadruple(
                "⛽",
                localizedString("mobile.wallet_paymaster_inactive"),
                Color(0xFFF5F5F5),
                MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }

    Card(
        modifier = Modifier.fillMaxWidth().testable("card_wallet_paymaster"),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = icon,
                fontSize = 18.sp
            )
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                Text(
                    text = statusText,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    color = textColor,
                    modifier = Modifier.testable("txt_paymaster_status")
                )
                if (paymasterEnabled && keyConfigured) {
                    Text(
                        text = localizedString("mobile.wallet_paymaster_key_set"),
                        fontSize = 11.sp,
                        color = textColor.copy(alpha = 0.8f)
                    )
                } else if (needsGas && !keyConfigured) {
                    Text(
                        text = localizedString("mobile.wallet_gas_required"),
                        fontSize = 11.sp,
                        color = textColor.copy(alpha = 0.8f)
                    )
                }
            }
        }
    }
}

// Helper data class for Quadruple since Kotlin doesn't have one
private data class Quadruple<A, B, C, D>(val first: A, val second: B, val third: C, val fourth: D)

@Composable
private fun WalletBalanceCard(status: WalletStatusResponse) {
    // Get currency manager for conversion
    val currencyManager = LocalCurrency.current
    val currentCurrencyInfo by currencyManager?.currentCurrencyInfo?.collectAsState()
        ?: remember { mutableStateOf(null) }

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

    // Convert balance to selected currency
    val usdcAmount = status.balance.toDoubleOrNull() ?: 0.0
    val convertedBalance = currencyManager?.convertFromUsdc(usdcAmount)
    val showConversion = currentCurrencyInfo?.code != "USDC" && currentCurrencyInfo?.code != "USD"

    Card(
        modifier = Modifier.fillMaxWidth().testable("card_wallet_balance"),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        SelectionContainer {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Wallet icon
                Icon(CIRISIcons.wallet, contentDescription = null, modifier = Modifier.size(48.dp), tint = Color.White)

                // Converted Balance (primary, if different currency selected)
                if (showConversion && convertedBalance != null) {
                    Text(
                        text = convertedBalance,
                        fontSize = 32.sp,
                        fontWeight = FontWeight.Bold,
                        color = textColor
                    )
                    // Original USDC balance (secondary)
                    Text(
                        text = "${status.balance} ${status.currency}",
                        fontSize = 16.sp,
                        color = textColor.copy(alpha = 0.7f)
                    )
                } else {
                    // USDC Balance (primary)
                    Text(
                        text = "${status.balance} ${status.currency}",
                        fontSize = 32.sp,
                        fontWeight = FontWeight.Bold,
                        color = textColor
                    )
                }

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
                        text = localizedString("mobile.wallet_receive_only"),
                        fontSize = 12.sp,
                        color = textColor.copy(alpha = 0.8f)
                    )
                }
            }
        }
    }
}

@Composable
private fun WalletAddressCard(address: String, network: String) {
    val clipboardManager = LocalClipboardManager.current
    var showCopied by remember { mutableStateOf(false) }

    // Reset "Copied!" message after 2 seconds
    LaunchedEffect(showCopied) {
        if (showCopied) {
            kotlinx.coroutines.delay(2000)
            showCopied = false
        }
    }

    Card(modifier = Modifier.fillMaxWidth().testable("card_wallet_address")) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString("mobile.wallet_address"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp
                )
                // Copy button
                TextButton(
                    onClick = {
                        clipboardManager.setText(AnnotatedString(address))
                        showCopied = true
                    },
                    modifier = Modifier.testable("btn_copy_address"),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = if (showCopied) "[v] ${localizedString("mobile.common_copy")}!" else "[>] ${localizedString("mobile.common_copy")}",
                        fontSize = 12.sp
                    )
                }
            }
            // Selectable address text
            SelectionContainer {
                Text(
                    text = address,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("txt_wallet_address")
                )
            }
            SelectionContainer {
                Text(
                    text = localizedString("mobile.wallet_network", mapOf("network" to network)),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun WalletLimitsCard(status: WalletStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth().testable("card_wallet_limits")) {
        SelectionContainer {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = localizedString("mobile.wallet_limits"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp
                )

                // Attestation level
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(text = localizedString("mobile.wallet_attestation"), fontSize = 13.sp)
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
                    Text(text = localizedString("mobile.wallet_max_tx"), fontSize = 13.sp)
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
                    Text(text = localizedString("mobile.wallet_daily_limit"), fontSize = 13.sp)
                    Text(
                        text = "$${status.dailyLimit} ${status.currency}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium
                    )
                }

                // Explanation
                Text(
                    text = localizedString("mobile.wallet_limits_note"),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun HardwareTrustWarningCard(
    reason: String?,
    advisories: List<SecurityAdvisoryData> = emptyList()
) {
    Card(
        modifier = Modifier.fillMaxWidth().testable("card_trust_warning"),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceWarning)
    ) {
        SelectionContainer {
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
                    Text(text = localizedString("mobile.wallet_warning"), fontSize = 16.sp)
                    Text(
                        text = localizedString("mobile.wallet_trust_degraded"),
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = SemanticColors.Default.onWarning
                    )
                }

                Text(
                    text = reason ?: localizedString("mobile.wallet_receive_only"),
                    fontSize = 13.sp,
                    color = SemanticColors.Default.onWarning.copy(alpha = 0.9f)
                )

                // Security advisories
                if (advisories.isNotEmpty()) {
                    HorizontalDivider(
                        modifier = Modifier.padding(vertical = 4.dp),
                        color = SemanticColors.Default.onWarning.copy(alpha = 0.3f)
                    )
                    Text(
                        text = "Security Advisories:",
                        fontWeight = FontWeight.Medium,
                        fontSize = 12.sp,
                        color = SemanticColors.Default.onWarning
                    )
                    advisories.forEach { advisory ->
                        Column(
                            modifier = Modifier.padding(start = 8.dp, top = 4.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp)
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(text = "•", fontSize = 12.sp, color = SemanticColors.Default.onWarning)
                                Text(
                                    text = advisory.title,
                                    fontWeight = FontWeight.Medium,
                                    fontSize = 11.sp,
                                    color = SemanticColors.Default.onWarning
                                )
                                if (advisory.cve != null) {
                                    Surface(
                                        shape = RoundedCornerShape(4.dp),
                                        color = SemanticColors.Default.error.copy(alpha = 0.2f)
                                    ) {
                                        Text(
                                            text = advisory.cve,
                                            fontSize = 9.sp,
                                            color = SemanticColors.Default.error,
                                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                        )
                                    }
                                }
                            }
                            Text(
                                text = advisory.impact,
                                fontSize = 10.sp,
                                color = SemanticColors.Default.onWarning.copy(alpha = 0.8f)
                            )
                            if (advisory.remediation != null) {
                                Text(
                                    text = "Fix: ${advisory.remediation}",
                                    fontSize = 10.sp,
                                    fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
                                    color = SemanticColors.Default.onWarning.copy(alpha = 0.7f)
                                )
                            }
                        }
                    }
                }

                Text(
                    text = localizedString("mobile.wallet_sending_disabled"),
                    fontSize = 12.sp,
                    color = SemanticColors.Default.onWarning.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun SpendingProgressCard(spending: SpendingProgress) {
    Card(modifier = Modifier.fillMaxWidth().testable("card_spending_progress")) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Spending Progress",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )

            // Session spending
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(text = "Session", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        text = "$${spending.sessionSpent} / $${spending.sessionLimit}",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
                val sessionProgress = try {
                    spending.sessionSpent.toFloat() / spending.sessionLimit.toFloat()
                } catch (e: Exception) { 0f }
                LinearProgressIndicator(
                    progress = { sessionProgress.coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = if (sessionProgress > 0.8f) SemanticColors.Default.warning else SemanticColors.Default.success,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant
                )
                Text(
                    text = "Resets in ${spending.sessionResetMinutes} min",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }

            // Daily spending
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(text = "Daily", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        text = "$${spending.dailySpent} / $${spending.dailyRemaining.toDoubleOrNull()?.let { spending.dailySpent.toDoubleOrNull()?.plus(it)?.toString() } ?: spending.dailyRemaining}",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
                val dailyLimit = (spending.dailySpent.toDoubleOrNull() ?: 0.0) + (spending.dailyRemaining.toDoubleOrNull() ?: 1000.0)
                val dailyProgress = try {
                    (spending.dailySpent.toDoubleOrNull() ?: 0.0) / dailyLimit
                } catch (e: Exception) { 0.0 }
                LinearProgressIndicator(
                    progress = { dailyProgress.toFloat().coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = if (dailyProgress > 0.8) SemanticColors.Default.warning else SemanticColors.Default.success,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant
                )
                Text(
                    text = "Resets in ${spending.dailyResetHours} hours",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun TransactionHistoryCard(transactions: List<TransactionSummary>) {
    Card(modifier = Modifier.fillMaxWidth().testable("card_transaction_history")) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Recent Transactions",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )

            transactions.forEach { tx ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Direction icon (ASCII for WASM/Skia)
                        Text(
                            text = if (tx.type == "send") "->" else "<-",
                            fontSize = 16.sp
                        )
                        Column {
                            Text(
                                text = if (tx.type == "send") "Sent" else "Received",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Text(
                                text = tx.recipient?.take(10)?.plus("...") ?: tx.sender?.take(10)?.plus("...") ?: "",
                                fontSize = 10.sp,
                                fontFamily = FontFamily.Monospace,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                            )
                        }
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = "${if (tx.type == "send") "-" else "+"}${tx.amount} ${tx.currency}",
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            color = if (tx.type == "send") SemanticColors.Default.error else SemanticColors.Default.success
                        )
                        // Status badge
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = when (tx.status) {
                                "confirmed" -> SemanticColors.Default.success.copy(alpha = 0.2f)
                                "pending" -> SemanticColors.Default.warning.copy(alpha = 0.2f)
                                else -> SemanticColors.Default.error.copy(alpha = 0.2f)
                            }
                        ) {
                            Text(
                                text = tx.status,
                                fontSize = 9.sp,
                                color = when (tx.status) {
                                    "confirmed" -> SemanticColors.Default.success
                                    "pending" -> SemanticColors.Default.warning
                                    else -> SemanticColors.Default.error
                                },
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
                if (tx != transactions.last()) {
                    HorizontalDivider(
                        modifier = Modifier.padding(vertical = 4.dp),
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f)
                    )
                }
            }
        }
    }
}

@Composable
private fun WalletTransferCard(
    apiClient: CIRISApiClient,
    maxAmount: String,
    currency: String,
    onTransferComplete: () -> Unit
) {
    var recipientAddress by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var memo by remember { mutableStateOf("") }
    var isTransferring by remember { mutableStateOf(false) }
    var transferError by remember { mutableStateOf<String?>(null) }
    var transferSuccess by remember { mutableStateOf<String?>(null) }

    // Address validation state
    var addressValidation by remember { mutableStateOf<ai.ciris.mobile.shared.api.AddressValidationResult?>(null) }
    var isValidatingAddress by remember { mutableStateOf(false) }

    // Duplicate check state
    var duplicateCheck by remember { mutableStateOf<ai.ciris.mobile.shared.api.DuplicateCheckResult?>(null) }
    var showDuplicateWarning by remember { mutableStateOf(false) }

    val coroutineScope = rememberCoroutineScope()

    // Validate address when it changes (debounced)
    LaunchedEffect(recipientAddress) {
        if (recipientAddress.length == 42 && recipientAddress.startsWith("0x")) {
            kotlinx.coroutines.delay(300) // Debounce
            isValidatingAddress = true
            try {
                addressValidation = apiClient.validateAddress(recipientAddress)
            } catch (e: Exception) {
                PlatformLogger.e("WalletTransfer", "Address validation failed: ${e.message}")
            } finally {
                isValidatingAddress = false
            }
        } else {
            addressValidation = null
        }
    }

    // Check for duplicate when amount changes (if address is valid)
    LaunchedEffect(amount, recipientAddress) {
        if (recipientAddress.length == 42 && amount.isNotBlank()) {
            val amountValue = amount.toDoubleOrNull()
            if (amountValue != null && amountValue > 0) {
                kotlinx.coroutines.delay(500) // Debounce
                try {
                    duplicateCheck = apiClient.checkDuplicateTransaction(recipientAddress, amount, currency)
                } catch (e: Exception) {
                    PlatformLogger.e("WalletTransfer", "Duplicate check failed: ${e.message}")
                }
            }
        } else {
            duplicateCheck = null
        }
    }

    Card(modifier = Modifier.fillMaxWidth().testable("card_wallet_transfer")) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("mobile.wallet_send_currency", mapOf("currency" to currency)),
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = localizedString("mobile.wallet_transfer_note"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )

            // Recipient address field with validation feedback
            OutlinedTextField(
                value = recipientAddress,
                onValueChange = { recipientAddress = it; transferError = null; transferSuccess = null },
                label = { Text(localizedString("mobile.wallet_recipient")) },
                placeholder = { Text("0x...") },
                modifier = Modifier.fillMaxWidth().testable("input_recipient_address"),
                singleLine = true,
                enabled = !isTransferring,
                isError = addressValidation?.let { !it.valid || !it.checksumValid } ?: false,
                trailingIcon = {
                    when {
                        isValidatingAddress -> CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                        addressValidation?.valid == true && addressValidation?.checksumValid == true -> Icon(CIRISIcons.check, contentDescription = "Valid", tint = SemanticColors.Default.success, modifier = Modifier.size(20.dp))
                        addressValidation?.valid == true && addressValidation?.checksumValid == false -> Icon(CIRISIcons.warning, contentDescription = "Warning", tint = SemanticColors.Default.warning, modifier = Modifier.size(20.dp))
                        addressValidation?.valid == false -> Icon(CIRISIcons.close, contentDescription = "Invalid", tint = SemanticColors.Default.error, modifier = Modifier.size(20.dp))
                        else -> {}
                    }
                },
                supportingText = {
                    Column {
                        // Show validation status
                        when {
                            addressValidation?.isZeroAddress == true -> {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(CIRISIcons.warning, contentDescription = null, tint = SemanticColors.Default.error, modifier = Modifier.size(12.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("Zero address - funds will be burned!", color = SemanticColors.Default.error, fontSize = 10.sp)
                                }
                            }
                            addressValidation?.checksumValid == false && addressValidation?.computedChecksum != null -> {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(CIRISIcons.warning, contentDescription = null, tint = SemanticColors.Default.warning, modifier = Modifier.size(12.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("Invalid checksum. Use: ${addressValidation?.computedChecksum}", color = SemanticColors.Default.warning, fontSize = 10.sp)
                                }
                            }
                            addressValidation?.error != null -> {
                                Text(addressValidation?.error ?: "", color = SemanticColors.Default.error, fontSize = 10.sp)
                            }
                            addressValidation?.checksumValid == true -> {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(CIRISIcons.check, contentDescription = null, tint = SemanticColors.Default.success, modifier = Modifier.size(12.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("Valid EIP-55 checksum", color = SemanticColors.Default.success, fontSize = 10.sp)
                                }
                            }
                        }
                    }
                }
            )

            // Amount field
            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it; transferError = null; transferSuccess = null },
                label = { Text(localizedString("mobile.wallet_amount", mapOf("currency" to currency))) },
                placeholder = { Text("0.00") },
                modifier = Modifier.fillMaxWidth().testable("input_transfer_amount"),
                singleLine = true,
                enabled = !isTransferring,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                supportingText = { Text(localizedString("mobile.wallet_max", mapOf("amount" to maxAmount, "currency" to currency))) }
            )

            // Duplicate transaction warning
            if (duplicateCheck?.isDuplicate == true) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceWarning)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(CIRISIcons.warning, contentDescription = "Warning", modifier = Modifier.size(20.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Possible Duplicate",
                                fontWeight = FontWeight.Medium,
                                fontSize = 13.sp,
                                color = SemanticColors.Default.onWarning
                            )
                            Text(
                                text = duplicateCheck?.warning ?: "You sent this amount to this address recently.",
                                fontSize = 11.sp,
                                color = SemanticColors.Default.onWarning.copy(alpha = 0.8f)
                            )
                        }
                    }
                }
            }

            // Optional memo field
            OutlinedTextField(
                value = memo,
                onValueChange = { memo = it },
                label = { Text(localizedString("mobile.wallet_memo")) },
                placeholder = { Text(localizedString("mobile.wallet_memo_placeholder")) },
                modifier = Modifier.fillMaxWidth().testable("input_transfer_memo"),
                singleLine = true,
                enabled = !isTransferring
            )

            // Error message
            if (transferError != null) {
                Text(
                    text = transferError!!,
                    color = SemanticColors.Default.error,
                    fontSize = 12.sp
                )
            }

            // Success message
            if (transferSuccess != null) {
                Text(
                    text = transferSuccess!!,
                    color = SemanticColors.Default.success,
                    fontSize = 12.sp
                )
            }

            // Pre-capture localized strings for use in onClick lambda
            val errorEnterRecipient = localizedString("mobile.wallet_enter_recipient")
            val errorInvalidFormat = localizedString("mobile.wallet_invalid_format")
            val errorEnterAmount = localizedString("mobile.wallet_enter_amount")
            val errorInvalidAmount = localizedString("mobile.wallet_invalid_amount")
            val errorTransferFailed = localizedString("mobile.wallet_transfer_failed")

            // Send button
            Button(
                onClick = {
                    // Validate inputs
                    if (recipientAddress.isBlank()) {
                        transferError = errorEnterRecipient
                        return@Button
                    }
                    if (!recipientAddress.startsWith("0x") || recipientAddress.length != 42) {
                        transferError = errorInvalidFormat
                        return@Button
                    }
                    // Block if address is zero address
                    if (addressValidation?.isZeroAddress == true) {
                        transferError = "Cannot send to zero address - funds would be burned"
                        return@Button
                    }
                    if (amount.isBlank()) {
                        transferError = errorEnterAmount
                        return@Button
                    }
                    val amountValue = amount.toDoubleOrNull()
                    if (amountValue == null || amountValue <= 0) {
                        transferError = errorInvalidAmount
                        return@Button
                    }

                    // Execute transfer
                    isTransferring = true
                    transferError = null
                    transferSuccess = null

                    coroutineScope.launch {
                        try {
                            val result = apiClient.transferUsdc(
                                recipient = recipientAddress,
                                amount = amount,
                                memo = memo.ifBlank { null }
                            )

                            if (result.success) {
                                val txId = result.txHash ?: result.transactionId ?: ""
                                transferSuccess = LocalizationHelper.getString("mobile.wallet_transfer_success", mapOf("tx" to txId))
                                // Clear form
                                recipientAddress = ""
                                amount = ""
                                memo = ""
                                addressValidation = null
                                duplicateCheck = null
                                onTransferComplete()
                            } else {
                                transferError = result.error ?: errorTransferFailed
                            }
                        } catch (e: Exception) {
                            transferError = e.message ?: errorTransferFailed
                        } finally {
                            isTransferring = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().testable("btn_send_transfer"),
                enabled = !isTransferring && recipientAddress.isNotBlank() && amount.isNotBlank()
            ) {
                if (isTransferring) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("mobile.wallet_sending"))
                } else {
                    Text(localizedString("mobile.wallet_send_currency", mapOf("currency" to currency)))
                }
            }

            // Warning about irreversibility
            Text(
                text = localizedString("mobile.wallet_irreversible"),
                fontSize = 11.sp,
                color = SemanticColors.Default.warning
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
        val response = apiClient.getWalletStatus()
        onSuccess(response)
        PlatformLogger.d("WalletPage", "Wallet status fetched: address=${response.address}, balance=${response.balance}")
    } catch (e: Exception) {
        PlatformLogger.e("WalletPage", "Failed to fetch wallet status: ${e.message}")
        onError(e.message ?: "Unknown error")
    }
}
