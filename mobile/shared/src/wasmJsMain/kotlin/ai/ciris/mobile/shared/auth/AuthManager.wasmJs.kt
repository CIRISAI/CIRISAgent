package ai.ciris.mobile.shared.auth

import kotlinx.browser.localStorage

actual class AuthManager {
    actual suspend fun signInWithApple(): Result<String> = Result.failure(
        UnsupportedOperationException("Apple Sign-In not available on web - use backend OAuth")
    )

    actual suspend fun signInWithGoogle(): Result<String> = Result.failure(
        UnsupportedOperationException("Google Sign-In not available on web - use backend OAuth")
    )

    actual suspend fun signOut(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
    }

    actual fun isSignedIn(): Boolean {
        return localStorage.getItem("ciris_access_token") != null
    }

    actual fun getCurrentUserId(): String? {
        return localStorage.getItem("ciris_user_id")
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
