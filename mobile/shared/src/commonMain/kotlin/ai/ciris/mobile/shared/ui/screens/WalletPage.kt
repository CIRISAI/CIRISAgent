package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.LocalCurrency
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.platform.PlatformLogger
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
import androidx.compose.material.icons.filled.Refresh
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
 * Wallet status response from API
 */
@Serializable
data class WalletStatusResponse(
    val hasWallet: Boolean = false,
    val provider: String = "x402",
    val network: String = "base-mainnet",
    val currency: String = "USDC",
    val balance: String = "0.00",
    val ethBalance: String = "0.00",
    val needsGas: Boolean = true,
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
                title = { Text(localizedString("screen_wallet")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_wallet_back") { onNavigateBack() }
                    ) {
                        Icon(Icons.Default.ArrowBack, contentDescription = localizedString("common_back"))
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
                        Icon(Icons.Default.Refresh, contentDescription = localizedString("common_refresh"))
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

                    // Get Gas card (show when ETH balance is too low for transfers)
                    if (status.needsGas && status.address != null && !status.isReceiveOnly) {
                        GetGasCard(walletAddress = status.address)
                    }

                    // Transfer card (only show if not receive-only and has address)
                    if (!status.isReceiveOnly && status.address != null) {
                        WalletTransferCard(
                            apiClient = apiClient,
                            maxAmount = status.maxTransactionLimit,
                            currency = status.currency,
                            needsGas = status.needsGas,
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
            Text(text = localizedString("wallet_failed"), fontWeight = FontWeight.Bold, color = SemanticColors.Default.error)
            Text(text = error, fontSize = 14.sp, color = SemanticColors.Default.error.copy(alpha = 0.8f))
            Button(onClick = onRetry) {
                Text(localizedString("common_retry"))
            }
        }
    }
}

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
        modifier = Modifier.fillMaxWidth(),
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
                // Wallet emoji
                Text(text = "💰", fontSize = 48.sp)

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

                // ETH Balance (for gas)
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "⛽",
                        fontSize = 14.sp
                    )
                    Text(
                        text = "${status.ethBalance} ETH",
                        fontSize = 14.sp,
                        color = if (status.needsGas) SemanticColors.Default.warning else textColor.copy(alpha = 0.7f)
                    )
                    if (status.needsGas) {
                        Text(
                            text = localizedString("wallet_needs_gas"),
                            fontSize = 12.sp,
                            color = SemanticColors.Default.warning
                        )
                    }
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
                        text = localizedString("wallet_receive_only"),
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

    Card(modifier = Modifier.fillMaxWidth()) {
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
                    text = localizedString("wallet_address"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp
                )
                // Copy button
                TextButton(
                    onClick = {
                        clipboardManager.setText(AnnotatedString(address))
                        showCopied = true
                    },
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = if (showCopied) "✓ ${localizedString("common_copy")}!" else "📋 ${localizedString("common_copy")}",
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
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            SelectionContainer {
                Text(
                    text = localizedString("wallet_network", mapOf("network" to network)),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun WalletLimitsCard(status: WalletStatusResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        SelectionContainer {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = localizedString("wallet_limits"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp
                )

                // Attestation level
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(text = localizedString("wallet_attestation"), fontSize = 13.sp)
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
                    Text(text = localizedString("wallet_max_tx"), fontSize = 13.sp)
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
                    Text(text = localizedString("wallet_daily_limit"), fontSize = 13.sp)
                    Text(
                        text = "$${status.dailyLimit} ${status.currency}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium
                    )
                }

                // Explanation
                Text(
                    text = localizedString("wallet_limits_note"),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun HardwareTrustWarningCard(reason: String?) {
    Card(
        modifier = Modifier.fillMaxWidth(),
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
                    Text(text = localizedString("wallet_warning"), fontSize = 16.sp)
                    Text(
                        text = localizedString("wallet_trust_degraded"),
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = SemanticColors.Default.onWarning
                    )
                }

                Text(
                    text = reason ?: localizedString("wallet_receive_only"),
                    fontSize = 13.sp,
                    color = SemanticColors.Default.onWarning.copy(alpha = 0.9f)
                )

                Text(
                    text = localizedString("wallet_sending_disabled"),
                    fontSize = 12.sp,
                    color = SemanticColors.Default.onWarning.copy(alpha = 0.7f)
                )
            }
        }
    }
}

@Composable
private fun GetGasCard(walletAddress: String) {
    val clipboardManager = LocalClipboardManager.current
    var showCopied by remember { mutableStateOf(false) }

    LaunchedEffect(showCopied) {
        if (showCopied) {
            kotlinx.coroutines.delay(2000)
            showCopied = false
        }
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SemanticColors.Default.surfaceWarning.copy(alpha = 0.3f))
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(text = "⛽", fontSize = 20.sp)
                Text(
                    text = localizedString("wallet_gas_required"),
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp
                )
            }

            Text(
                text = localizedString("wallet_gas_note"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
            )

            Text(
                text = localizedString("wallet_gas_how"),
                fontWeight = FontWeight.Medium,
                fontSize = 14.sp
            )

            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = localizedString("wallet_gas_step1"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                )
                Text(
                    text = localizedString("wallet_gas_step2"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                )
                Text(
                    text = localizedString("wallet_gas_step3"),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
                )
            }

            // Copy address button
            OutlinedButton(
                onClick = {
                    clipboardManager.setText(AnnotatedString(walletAddress))
                    showCopied = true
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = if (showCopied) "✓ ${localizedString("wallet_address_copied")}" else "📋 ${localizedString("wallet_copy_address")}",
                    fontSize = 14.sp
                )
            }
        }
    }
}

@Composable
private fun WalletTransferCard(
    apiClient: CIRISApiClient,
    maxAmount: String,
    currency: String,
    needsGas: Boolean = false,
    onTransferComplete: () -> Unit
) {
    var recipientAddress by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var memo by remember { mutableStateOf("") }
    var isTransferring by remember { mutableStateOf(false) }
    var transferError by remember { mutableStateOf<String?>(null) }
    var transferSuccess by remember { mutableStateOf<String?>(null) }
    val coroutineScope = rememberCoroutineScope()

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = localizedString("wallet_send_currency", mapOf("currency" to currency)),
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )

            Text(
                text = localizedString("wallet_transfer_note"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )

            // Recipient address field
            OutlinedTextField(
                value = recipientAddress,
                onValueChange = { recipientAddress = it; transferError = null; transferSuccess = null },
                label = { Text(localizedString("wallet_recipient")) },
                placeholder = { Text("0x...") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                enabled = !isTransferring,
                isError = transferError != null && recipientAddress.isNotEmpty()
            )

            // Amount field
            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it; transferError = null; transferSuccess = null },
                label = { Text(localizedString("wallet_amount", mapOf("currency" to currency))) },
                placeholder = { Text("0.00") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                enabled = !isTransferring,
                supportingText = { Text(localizedString("wallet_max", mapOf("amount" to maxAmount, "currency" to currency))) }
            )

            // Optional memo field
            OutlinedTextField(
                value = memo,
                onValueChange = { memo = it },
                label = { Text(localizedString("wallet_memo")) },
                placeholder = { Text(localizedString("wallet_memo_placeholder")) },
                modifier = Modifier.fillMaxWidth(),
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
            val errorEnterRecipient = localizedString("wallet_enter_recipient")
            val errorInvalidFormat = localizedString("wallet_invalid_format")
            val errorEnterAmount = localizedString("wallet_enter_amount")
            val errorInvalidAmount = localizedString("wallet_invalid_amount")
            val errorTransferFailed = localizedString("wallet_transfer_failed")

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
                                transferSuccess = LocalizationHelper.getString("wallet_transfer_success", mapOf("tx" to txId))
                                // Clear form
                                recipientAddress = ""
                                amount = ""
                                memo = ""
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
                modifier = Modifier.fillMaxWidth(),
                enabled = !isTransferring && recipientAddress.isNotBlank() && amount.isNotBlank()
            ) {
                if (isTransferring) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("wallet_sending"))
                } else {
                    Text(localizedString("wallet_send_currency", mapOf("currency" to currency)))
                }
            }

            // Warning about gas if needed
            if (needsGas) {
                Text(
                    text = "⚠️ ${localizedString("wallet_gas_warning")}",
                    fontSize = 11.sp,
                    color = SemanticColors.Default.error
                )
            }

            // Warning about irreversibility
            Text(
                text = localizedString("wallet_irreversible"),
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
