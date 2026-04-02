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
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
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
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically)
            ) {
                // CIRIS Signet
                CIRISSignet(
                    tintColor = LoginColors.White,
                    modifier = Modifier.size(100.dp)
                )

                // App name
                Text(
                    text = loginTitle,
                    color = LoginColors.White,
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(top = 8.dp)
                )

                // Tagline — show first-run welcome or returning user tagline
                Text(
                    text = if (isFirstRun) localizedString("mobile.login_first_run_welcome") else loginTagline,
                    color = LoginColors.White.copy(alpha = 0.8f),
                    fontSize = 16.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(top = 4.dp).width(280.dp)
                )

                Spacer(modifier = Modifier.height(48.dp))

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
                        shape = RoundedCornerShape(28.dp),
                        modifier = Modifier
                            .width(280.dp)
                            .height(56.dp)
                            .testable(if (isIOS()) "btn_apple_signin" else "btn_google_signin")
                    ) {
                        Text(
                            text = signinProvider,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

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
                        shape = RoundedCornerShape(28.dp),
                        modifier = Modifier
                            .width(280.dp)
                            .height(56.dp)
                            .testable("btn_local_login")
                    ) {
                        Text(
                            text = localLoginText,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Info text
                    Text(
                        text = hostedInfo,
                        color = LoginColors.White.copy(alpha = 0.7f),
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center,
                        lineHeight = 18.sp,
                        modifier = Modifier.width(280.dp)
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Marketing checkbox
                    Row(
                        modifier = Modifier.width(280.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = marketingOptIn,
                            onCheckedChange = { marketingOptIn = it },
                            colors = CheckboxDefaults.colors(
                                checkedColor = LoginColors.White,
                                uncheckedColor = LoginColors.White.copy(alpha = 0.8f),
                                checkmarkColor = LoginColors.Primary
                            )
                        )
                        Text(
                            text = marketingText,
                            color = LoginColors.White.copy(alpha = 0.8f),
                            fontSize = 12.sp,
                            modifier = Modifier.padding(start = 4.dp)
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
                }
            }

            // Footer
            Text(
                text = footerText,
                color = LoginColors.White.copy(alpha = 0.6f),
                fontSize = 12.sp,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 24.dp)
            )

            // Language selector - prominent, centered at top (rendered last for z-order)
            // This changes BOTH the interface AND agent reasoning language
            LanguageSelector(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 24.dp)
                    .testable("login_language_selector"),
                compact = false,
                centered = true
            )
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
        // Error message
        if (errorMessage != null) {
            Text(
                text = errorMessage,
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
