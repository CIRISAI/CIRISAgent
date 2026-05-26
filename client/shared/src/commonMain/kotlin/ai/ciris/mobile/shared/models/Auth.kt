package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val username: String,
    val password: String
)

@Serializable
data class GoogleAuthRequest(
    val id_token: String,
    val user_id: String? = null
)

@Serializable
data class AuthResponse(
    val access_token: String,
    val token_type: String = "bearer",
    val user: UserInfo
)

@Serializable
data class UserInfo(
    val user_id: String,
    val email: String,
    val name: String? = null,
    val photo_url: String? = null,
    val role: String = "OBSERVER"
)

@Serializable
data class TokenRefreshRequest(
    val refresh_token: String
)

/**
 * Masked identity hint for the founding owner of a personal-install
 * device. Returned by GET /v1/auth/owner-hint and also embedded in the
 * 403 auth_personal_install_observer_blocked detail when a user picks
 * the wrong Google account.
 *
 * Privacy posture matches the server-side rule:
 *   * `masked_email` is always partial (`eri***@gmail.com`) — never
 *     the full address.
 *   * `first_name` only — no surname, no avatar, no external_id.
 *   * `auth_type` lets the client choose the right CTA copy
 *     ("Sign in with Google" vs. "Sign in with username/password").
 *   * `oauth_provider` is null on local-install / password-auth owners.
 *
 * The wrapper response is `{"owner_hint": OwnerHint?}` — the wrapper
 * lets the server distinguish "no setup yet" (200 + null) from "this
 * endpoint isn't available on multi-tenant servers" (404). The client
 * collapses both into Kotlin null.
 */
@Serializable
data class OwnerHint(
    val masked_email: String? = null,
    val first_name: String? = null,
    val auth_type: String? = null,
    val oauth_provider: String? = null
)

@Serializable
data class OwnerHintResponse(
    val owner_hint: OwnerHint? = null
)
