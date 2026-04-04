package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.getOAuthProviderName
import ai.ciris.mobile.shared.platform.isDesktop
import ai.ciris.mobile.shared.platform.isIOS
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISSignet
import ai.ciris.mobile.shared.ui.components.LanguageSelector
import ai.ciris.mobile.shared.viewmodels.ConnectionStatus
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.graphicsLayer
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Login Screen - Cross-platform login for Android, iOS, and Desktop
 *
 * Shows different options based on platform:
 * - Mobile: OAuth buttons (Google/Apple) + Local Login button
 * - Desktop (first run): Shows setup wizard directly
 * - Desktop (existing user): Shows username/password form
 *
 * Uses dark branded background (#667eea) matching Android exactly.
 */

// Colors from android/app/src/main/res/values/colors.xml
private object LoginColors {
    val Background = Color(0xFF667eea)  // ciris_background
    val Primary = Color(0xFF667eea)     // ciris_primary
    val Accent = Color(0xFF00d4aa)      // ciris_accent
    val White = Color.White
    val Error = SemanticColors.Default.error  // Use semantic error color
}

@Composable
fun LoginScreen(
    onGoogleSignIn: () -> Unit,
    onLocalLogin: () -> Unit,
    onLocalLoginSubmit: (username: String, password: String) -> Unit = { _, _ -> },
    onPrivacyPolicy: () -> Unit = {
        PlatformLogger.i("LoginScreen", "[onPrivacyPolicy] Privacy policy link clicked - opening https://ciris.ai/privacy")
    },
    onServerSettings: () -> Unit = {},
    connectionStatus: ConnectionStatus = ConnectionStatus.DISCONNECTED,
    isLoading: Boolean = false,
    statusMessage: String? = null,
    errorMessage: String? = null,
    showLocalLoginForm: Boolean = false,
    isFirstRun: Boolean = true,
    modifier: Modifier = Modifier
) {
    var marketingOptIn by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var showLoginForm by remember { mutableStateOf(showLocalLoginForm) }
    val focusManager = LocalFocusManager.current

    // For desktop, always show login form (not OAuth buttons)
    val isDesktopMode = isDesktop()

    // Localized strings
    val loginTitle = localizedString("mobile.login_title")
    val loginTagline = localizedString("mobile.login_tagline")
    val providerName = getOAuthProviderName()
    val signinProvider = localizedString("mobile.login_signin_provider", "provider", providerName)
    val localLoginText = localizedString("mobile.login_local")
    val hostedInfo = localizedString("mobile.login_ciris_hosted_info", "provider", providerName)
    val marketingText = localizedString("mobile.login_marketing_optin")
    val privacyText = localizedString("mobile.login_privacy")
    val footerText = localizedString("mobile.login_footer")

    Surface(
        modifier = modifier.fillMaxSize(),
        color = LoginColors.Background
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(start = 24.dp, end = 24.dp, top = 16.dp, bottom = 20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterVertically)
            ) {
                // Language selector - first element, inside Column to avoid overlap
                LanguageSelector(
                    modifier = Modifier.testable("login_language_selector"),
                    compact = false,
                    centered = true
                )

                // CIRIS Signet — slow rotation + gentle pulse for ambient motion
                val infiniteTransition = rememberInfiniteTransition(label = "signet")
                val rotation by infiniteTransition.animateFloat(
                    initialValue = 0f,
                    targetValue = 360f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(durationMillis = 8000, easing = LinearEasing),
                        repeatMode = RepeatMode.Restart
                    ),
                    label = "signet_rotation"
                )
                val scale by infiniteTransition.animateFloat(
                    initialValue = 0.96f,
                    targetValue = 1.04f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(durationMillis = 3000, easing = LinearEasing),
                        repeatMode = RepeatMode.Reverse
                    ),
                    label = "signet_pulse"
                )
                CIRISSignet(
                    tintColor = LoginColors.White,
                    modifier = Modifier
                        .size(56.dp)
                        .graphicsLayer {
                            rotationZ = rotation
                            scaleX = scale
                            scaleY = scale
                        }
                )

                // App name
                Text(
                    text = loginTitle,
                    color = LoginColors.White,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold
                )

                // Tagline — show first-run welcome or returning user tagline
                Text(
                    text = if (isFirstRun) localizedString("mobile.login_first_run_welcome") else loginTagline,
                    color = LoginColors.White.copy(alpha = 0.8f),
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.width(280.dp)
                )

                Spacer(modifier = Modifier.height(16.dp))

                if (isLoading) {
                    // Progress indicator
                    CircularProgressIndicator(
                        color = LoginColors.White,
                        modifier = Modifier.size(48.dp)
                    )

                    if (statusMessage != null) {
                        Text(
                            text = statusMessage,
                            color = LoginColors.White.copy(alpha = 0.9f),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 16.dp)
                        )
                    }
                } else if (isDesktopMode || showLoginForm) {
                    // Desktop mode or Local Login form - show username/password fields
                    LocalLoginForm(
                        username = username,
                        onUsernameChange = { username = it },
                        password = password,
                        onPasswordChange = { password = it },
                        onSubmit = {
                            if (username.isNotBlank() && password.isNotBlank()) {
                                onLocalLoginSubmit(username, password)
                            }
                        },
                        onBack = if (!isDesktopMode) {{ showLoginForm = false }} else null,
                        errorMessage = errorMessage,
                        focusManager = focusManager
                    )
                } else {
                    // Mobile mode - show OAuth buttons
                    Button(
                        onClick = onGoogleSignIn,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = LoginColors.White,
                            contentColor = LoginColors.Primary
                        ),
                        shape = RoundedCornerShape(24.dp),
                        modifier = Modifier
                            .width(280.dp)
                            .height(48.dp)
                            .testableClickable(if (isIOS()) "btn_apple_signin" else "btn_google_signin") { onGoogleSignIn() }
                    ) {
                        Text(
                            text = signinProvider,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // Local Login button (outlined)
                    OutlinedButton(
                        onClick = {
                            if (isFirstRun) {
                                // First run - go to setup wizard for BYOK setup
                                onLocalLogin()
                            } else {
                                // Existing user - show login form
                                showLoginForm = true
                            }
                        },
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = LoginColors.White
                        ),
                        border = ButtonDefaults.outlinedButtonBorder.copy(
                            brush = androidx.compose.ui.graphics.SolidColor(LoginColors.White)
                        ),
                        shape = RoundedCornerShape(24.dp),
                        modifier = Modifier
                            .width(280.dp)
                            .height(48.dp)
                            .testableClickable("btn_local_login") {
                                if (isFirstRun) onLocalLogin() else { showLoginForm = true }
                            }
                    ) {
                        Text(
                            text = localLoginText,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Info text - compact for small screens
                    Text(
                        text = hostedInfo,
                        color = LoginColors.White.copy(alpha = 0.7f),
                        fontSize = 11.sp,
                        textAlign = TextAlign.Center,
                        lineHeight = 15.sp,
                        modifier = Modifier.width(280.dp)
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    // Marketing checkbox - compact layout for small screens
                    Row(
                        modifier = Modifier.width(280.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Checkbox(
                            checked = marketingOptIn,
                            onCheckedChange = { marketingOptIn = it },
                            colors = CheckboxDefaults.colors(
                                checkedColor = LoginColors.White,
                                uncheckedColor = LoginColors.White.copy(alpha = 0.8f),
                                checkmarkColor = LoginColors.Primary
                            ),
                            modifier = Modifier.size(20.dp)
                        )
                        Text(
                            text = marketingText,
                            color = LoginColors.White.copy(alpha = 0.8f),
                            fontSize = 11.sp,
                            lineHeight = 14.sp,
                            modifier = Modifier.padding(start = 8.dp, top = 2.dp)
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    // Privacy link
                    Text(
                        text = privacyText,
                        color = LoginColors.Accent,
                        fontSize = 12.sp,
                        modifier = Modifier
                            .clickable {
                                PlatformLogger.i("LoginScreen", "[PrivacyPolicy] Privacy policy link clicked")
                                onPrivacyPolicy()
                            }
                            .testable("btn_privacy_policy")
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Footer - inside Column so it scrolls with content (no overlap on small screens)
                    Text(
                        text = footerText,
                        color = LoginColors.White.copy(alpha = 0.6f),
                        fontSize = 11.sp
                    )
                }
            }

            // Connection status badge (top-right, desktop only)
            if (isDesktopMode) {
                ConnectionStatusBadge(
                    connectionStatus = connectionStatus,
                    onClick = onServerSettings,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(top = 24.dp, end = 16.dp)
                )
            }
        }
    }
}

/**
 * Local login form with username and password fields.
 * Used for desktop mode and when "Local Login" is clicked on mobile.
 */
@Composable
private fun LocalLoginForm(
    username: String,
    onUsernameChange: (String) -> Unit,
    password: String,
    onPasswordChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onBack: (() -> Unit)?,
    errorMessage: String?,
    focusManager: androidx.compose.ui.focus.FocusManager
) {
    // Localized strings
    val usernameLabel = localizedString("mobile.login_username")
    val passwordLabel = localizedString("mobile.login_password_label")
    val loginText = localizedString("mobile.login_submit")
    val backText = localizedString("mobile.login_back")
    val credentialsHint = localizedString("mobile.login_credentials_hint")

    // Observe text input requests for test automation
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()

    // Handle incoming text input requests
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            when (request.testTag) {
                "input_username" -> {
                    if (request.clearFirst) {
                        onUsernameChange(request.text)
                    } else {
                        onUsernameChange(username + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_password" -> {
                    if (request.clearFirst) {
                        onPasswordChange(request.text)
                    } else {
                        onPasswordChange(password + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
            }
        }
    }

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(280.dp)
    ) {
        // Error message — show user-friendly text, not raw exceptions
        if (errorMessage != null) {
            val displayError = when {
                errorMessage.contains("Invalid credentials", ignoreCase = true) ||
                errorMessage.contains("LoginResponse", ignoreCase = true) ||
                errorMessage.contains("missing at path", ignoreCase = true) ->
                    localizedString("mobile.login_error_invalid_credentials")
                errorMessage.contains("timeout", ignoreCase = true) ||
                errorMessage.contains("connect", ignoreCase = true) ->
                    localizedString("mobile.login_error_connection")
                else -> errorMessage.take(100)
            }
            Text(
                text = displayError,
                color = LoginColors.Error,
                fontSize = 14.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(bottom = 16.dp)
            )
        }

        // Username field
        OutlinedTextField(
            value = username,
            onValueChange = onUsernameChange,
            label = { Text(usernameLabel, color = LoginColors.White.copy(alpha = 0.7f)) },
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = LoginColors.White,
                unfocusedTextColor = LoginColors.White,
                focusedBorderColor = LoginColors.White,
                unfocusedBorderColor = LoginColors.White.copy(alpha = 0.5f),
                cursorColor = LoginColors.White,
                focusedLabelColor = LoginColors.White,
                unfocusedLabelColor = LoginColors.White.copy(alpha = 0.7f)
            ),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Text,
                imeAction = ImeAction.Next
            ),
            keyboardActions = KeyboardActions(
                onNext = { focusManager.moveFocus(FocusDirection.Down) }
            ),
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_username")
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Password field
        OutlinedTextField(
            value = password,
            onValueChange = onPasswordChange,
            label = { Text(passwordLabel, color = LoginColors.White.copy(alpha = 0.7f)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = LoginColors.White,
                unfocusedTextColor = LoginColors.White,
                focusedBorderColor = LoginColors.White,
                unfocusedBorderColor = LoginColors.White.copy(alpha = 0.5f),
                cursorColor = LoginColors.White,
                focusedLabelColor = LoginColors.White,
                unfocusedLabelColor = LoginColors.White.copy(alpha = 0.7f)
            ),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done
            ),
            keyboardActions = KeyboardActions(
                onDone = { onSubmit() }
            ),
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_password")
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Login button - use testableClickable for programmatic click support
        Button(
            onClick = onSubmit,
            enabled = username.isNotBlank() && password.isNotBlank(),
            colors = ButtonDefaults.buttonColors(
                containerColor = LoginColors.White,
                contentColor = LoginColors.Primary,
                disabledContainerColor = LoginColors.White.copy(alpha = 0.5f),
                disabledContentColor = LoginColors.Primary.copy(alpha = 0.5f)
            ),
            shape = RoundedCornerShape(28.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
                .testableClickable("btn_login_submit") { onSubmit() }
        ) {
            Text(
                text = loginText,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium
            )
        }

        // Back button (only on mobile when showing login form)
        if (onBack != null) {
            Spacer(modifier = Modifier.height(12.dp))

            TextButton(
                onClick = onBack,
                modifier = Modifier.testable("btn_login_back")
            ) {
                Text(
                    text = backText,
                    color = LoginColors.White.copy(alpha = 0.8f),
                    fontSize = 14.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Info text
        Text(
            text = credentialsHint,
            color = LoginColors.White.copy(alpha = 0.7f),
            fontSize = 12.sp,
            textAlign = TextAlign.Center
        )
    }
}

/**
 * Connection status badge for the login screen.
 * Shows the current connection status and allows clicking to open server settings.
 */
@Composable
private fun ConnectionStatusBadge(
    connectionStatus: ConnectionStatus,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val statusColor = when (connectionStatus) {
        ConnectionStatus.CONNECTED_LOCAL -> Color(0xFF10B981) // Green
        ConnectionStatus.CONNECTED_REMOTE -> Color(0xFF3B82F6) // Blue
        ConnectionStatus.CONNECTING -> Color(0xFFF59E0B) // Amber
        ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR -> Color(0xFFEF4444) // Red
    }

    val statusText = when (connectionStatus) {
        ConnectionStatus.CONNECTED_LOCAL,
        ConnectionStatus.CONNECTED_REMOTE -> localizedString("mobile.server_status_connected")
        ConnectionStatus.CONNECTING -> localizedString("mobile.server_status_connecting")
        ConnectionStatus.DISCONNECTED,
        ConnectionStatus.ERROR -> localizedString("mobile.server_status_disconnected")
    }

    Surface(
        onClick = onClick,
        modifier = modifier.testable("btn_server_status"),
        shape = RoundedCornerShape(16.dp),
        color = LoginColors.White.copy(alpha = 0.15f)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Status indicator dot
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(statusColor, CircleShape)
            )

            // Status text
            Text(
                text = statusText,
                color = LoginColors.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium
            )
        }
    }
}
