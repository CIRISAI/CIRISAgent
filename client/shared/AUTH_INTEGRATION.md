# Authentication & First-Run Integration Guide

## Overview

This document describes how to integrate the new AuthManager and FirstRunDetector components into your KMP mobile app.

## Components Created

### 1. AuthState.kt
**Location:** `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/models/AuthState.kt`

Defines authentication state models:
- `AuthState` - Sealed class for authentication states (Unauthenticated, Authenticated, Loading, Error)
- `AuthConfig` - Configuration for authentication (auth method, Google data, etc.)
- `TokenData` - Token storage model

**Source:** MainActivity.kt lines 238-270, 1947-1950

### 2. AuthManager (expect/actual)
**Locations:**
- Common: `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/auth/AuthManager.kt`
- Android: `mobile/shared/src/androidMain/kotlin/ai/ciris/mobile/shared/auth/AuthManager.android.kt`

Handles authentication operations:
- Login with username/password
- Login with Google ID token
- Logout
- Token management (save, retrieve, delete)
- Secure storage via EncryptedSharedPreferences

**Source:** MainActivity.kt lines 1025-1120 (encrypted prefs), 1752-1836 (auth methods), 2231-2342 (login), 2569-2637 (logout)

### 3. FirstRunDetector (expect/actual)
**Locations:**
- Common: `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/auth/FirstRunDetector.kt`
- Android: `mobile/shared/src/androidMain/kotlin/ai/ciris/mobile/shared/auth/FirstRunDetector.android.kt`

Detects first-run state:
- Checks for CIRIS_HOME/.env file
- Queries backend /v1/setup/status API
- Determines if setup wizard should be shown

**Source:** MainActivity.kt lines 1665-1750 (first-run logic), 1859-1885 (API check), 2842-2854 (.env check)

## Integration Steps

### Step 1: Initialize in Application.onCreate()

```kotlin
import ai.ciris.mobile.shared.auth.AuthManager
import ai.ciris.mobile.shared.platform.SecureStorage

class CIRISApplication : Application() {
    override fun onCreate() {
        super.onCreate()

        // Set context for secure storage
        SecureStorage.setContext(this)
        AuthManager.setContext(this)
    }
}
```

### Step 2: Use in StartupViewModel

```kotlin
import ai.ciris.mobile.shared.auth.createAuthManager
import ai.ciris.mobile.shared.auth.createFirstRunDetector
import ai.ciris.mobile.shared.auth.detectFirstRunStatus

class StartupViewModel : ViewModel() {
    private val authManager = createAuthManager()
    private val firstRunDetector = createFirstRunDetector()

    init {
        authManager.initialize()
    }

    suspend fun checkStartupState(cirisHomePath: String, serverUrl: String) {
        // Check first-run status
        val firstRunStatus = detectFirstRunStatus(cirisHomePath, serverUrl)

        if (firstRunStatus.setupRequired) {
            // Show setup wizard
            navigateToSetup()
        } else {
            // Check authentication
            if (authManager.isAuthenticated()) {
                // Show main app
                navigateToMain()
            } else {
                // Show login
                navigateToLogin()
            }
        }
    }
}
```

### Step 3: Login Flow

```kotlin
import ai.ciris.mobile.shared.auth.createAuthManager

class LoginViewModel : ViewModel() {
    private val authManager = createAuthManager()

    // Observe auth state
    val authState = authManager.authState.asStateFlow()

    suspend fun loginWithPassword(username: String, password: String, serverUrl: String) {
        authManager.login(username, password, serverUrl).fold(
            onSuccess = { authResponse ->
                // Login successful
                println("Logged in as ${authResponse.user.user_id}")
            },
            onFailure = { error ->
                // Handle error
                println("Login failed: ${error.message}")
            }
        )
    }

    suspend fun loginWithGoogle(idToken: String, userId: String?, serverUrl: String) {
        authManager.loginWithGoogle(idToken, userId, serverUrl).fold(
            onSuccess = { authResponse ->
                // Login successful
                println("Logged in via Google")
            },
            onFailure = { error ->
                // Handle error
                println("Google login failed: ${error.message}")
            }
        )
    }

    suspend fun logout() {
        authManager.logout().fold(
            onSuccess = {
                // Logout successful
                println("Logged out")
            },
            onFailure = { error ->
                println("Logout failed: ${error.message}")
            }
        )
    }
}
```

### Step 4: Access Token for API Calls

```kotlin
import ai.ciris.mobile.shared.auth.createAuthManager

class ApiClient {
    private val authManager = createAuthManager()

    suspend fun makeAuthenticatedRequest(endpoint: String): Result<String> {
        val token = authManager.getAccessToken()
        if (token == null) {
            return Result.failure(Exception("Not authenticated"))
        }

        // Use token in Authorization header
        // Authorization: Bearer {token}
        return makeHttpRequest(endpoint, token)
    }
}
```

## API Endpoints Used

The AuthManager integrates with these CIRIS API endpoints:

- `POST /v1/auth/login` - Username/password authentication
- `POST /v1/auth/native/google` - Google ID token exchange
- `POST /v1/auth/logout` - Logout
- `POST /v1/auth/refresh` - Token refresh (not yet implemented)
- `GET /v1/setup/status` - Check setup status (FirstRunDetector)

## Security Notes

### Token Storage
- Tokens are stored using EncryptedSharedPreferences (Android)
- AES-256 encryption for token data
- Tokens never stored in plain text
- Memory fallback only if context unavailable

### Context Management
- AuthManager requires Android context for secure storage
- Set context once in Application.onCreate()
- Don't tie to Activity lifecycle (use ApplicationContext)

### Token Lifecycle
- Tokens persist across app restarts
- Logout clears all stored tokens
- No automatic token refresh yet (requires backend support)

## Migration from MainActivity

The following MainActivity logic has been extracted to shared components:

| MainActivity Code | New Component | Status |
|------------------|---------------|--------|
| Lines 238-270: Auth state classes | `AuthState.kt` | ✅ Complete |
| Lines 1025-1120: Encrypted prefs | `AuthManager.android.kt` | ✅ Complete |
| Lines 1752-1836: Token methods | `AuthManager.kt` | ✅ Complete |
| Lines 2307-2343: Local login | `AuthManager.login()` | ✅ Complete |
| Lines 1903-1964: Google token exchange | `AuthManager.loginWithGoogle()` | ✅ Complete |
| Lines 2569-2637: Logout | `AuthManager.logout()` | ✅ Complete |
| Lines 1859-1885: Setup status API | `FirstRunDetector.checkSetupStatusFromApi()` | ✅ Complete |
| Lines 2842-2854: .env file check | `FirstRunDetector.envFileExists()` | ✅ Complete |

## Next Steps

1. **StartupViewModel Integration** - Use FirstRunDetector to determine app flow
2. **LoginScreen Integration** - Use AuthManager for authentication
3. **API Client Integration** - Use AuthManager.getAccessToken() for authenticated requests
4. **Token Refresh** - Implement when backend adds refresh token endpoint
5. **iOS Implementation** - Create iOS actual implementations (AuthManager.ios.kt, FirstRunDetector.ios.kt)

## Testing

### Unit Tests
```kotlin
class AuthManagerTest {
    @Test
    fun `test login success`() = runTest {
        val authManager = createAuthManager()
        val result = authManager.login("admin", "password", "http://localhost:8000")
        assertTrue(result.isSuccess)
    }
}
```

### Integration Points
- StartupViewModel needs to check first-run state
- SetupScreen needs to complete first-run (creates .env)
- Main app needs to check auth state before API calls

## File References

All source code references point to specific line numbers in:
`/home/emoore/CIRISAgent/android/app/src/main/java/ai/ciris/mobile/MainActivity.kt`

This ensures traceability back to the original working implementation.
