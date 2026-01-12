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
