package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Login Screen - EXACTLY matches android/app/.../auth/LoginActivity.kt
 *
 * Shows two login options:
 * - Sign in with Google: Required for CIRIS hosted LLM services, also supports BYOK
 * - Local Login: Offline mode with user-provided API key (BYOK only)
 *
 * Uses dark branded background (#667eea) matching Android exactly.
 */

// Colors from android/app/src/main/res/values/colors.xml
private object LoginColors {
    val Background = Color(0xFF667eea)  // ciris_background
    val Primary = Color(0xFF667eea)     // ciris_primary
    val Accent = Color(0xFF00d4aa)      // ciris_accent
    val White = Color.White
}

@Composable
fun LoginScreen(
    onGoogleSignIn: () -> Unit,
    onLocalLogin: () -> Unit,
    isLoading: Boolean = false,
    statusMessage: String? = null,
    modifier: Modifier = Modifier
) {
    var marketingOptIn by remember { mutableStateOf(false) }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = LoginColors.Background
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                // Logo "C"
                Text(
                    text = "C",
                    color = LoginColors.White,
                    fontSize = 96.sp,
                    fontWeight = FontWeight.Light
                )

                // App name
                Text(
                    text = "CIRIS Agent",
                    color = LoginColors.White,
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(top = 8.dp)
                )

                // Tagline
                Text(
                    text = "Your AI companion",
                    color = LoginColors.White.copy(alpha = 0.8f),
                    fontSize = 16.sp,
                    modifier = Modifier.padding(top = 4.dp)
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
                } else {
                    // Sign in with Google button (white, rounded)
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
                    ) {
                        Text(
                            text = "Sign in with Google",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Local Login button (outlined)
                    OutlinedButton(
                        onClick = onLocalLogin,
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
                    ) {
                        Text(
                            text = "Local Login",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Info text
                    Text(
                        text = "CIRIS hosted LLM services require Google login.\nBring your own API key works with either option.",
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
                            text = "Send me product updates and announcements",
                            color = LoginColors.White.copy(alpha = 0.8f),
                            fontSize = 12.sp,
                            modifier = Modifier.padding(start = 4.dp)
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    // Privacy link
                    Text(
                        text = "View Privacy Policy",
                        color = LoginColors.Accent,
                        fontSize = 12.sp,
                        modifier = Modifier.clickable {
                            // TODO: Open privacy policy
                        }
                    )
                }
            }

            // Footer
            Text(
                text = "Powered by CIRIS AI",
                color = LoginColors.White.copy(alpha = 0.6f),
                fontSize = 12.sp,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 24.dp)
            )
        }
    }
}
