package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A completed browser sign-in, collected by the desktop app that started it.
 *
 * The browser and the app are two processes for one act, so the node parks this
 * against the app's nonce and hands it over exactly once. It carries the
 * identity as well as the bearer on purpose: on first run the wizard derives the
 * federation-ID name from `<provider>-<subject>`, and an app holding only a
 * session would know it was signed in without knowing as whom.
 */
@Serializable
data class OAuthHandoff(
    @SerialName("access_token")
    val accessToken: String,
    @SerialName("token_type")
    val tokenType: String = "Bearer",
    @SerialName("expires_in")
    val expiresIn: Long = 0,
    /** The local certificate this sign-in resolved to (or created). */
    @SerialName("user_id")
    val userId: String = "",
    val role: String = "",
    val provider: String = "",
    /** The provider's stable subject — the fed-ID name is derived from it. */
    @SerialName("external_id")
    val externalId: String = "",
    val email: String? = null,
    /**
     * The provider's raw ID token, when the provider issues one (CIRISServer#434).
     *
     * CIRIS_PROXY sends this AS the LLM api_key, so without it a desktop user who
     * signed in with Google could not select the proxy at all — and was told
     * "Google sign-in is required" while signed in with Google. The node has held
     * it since the code exchange; from ciris-server 0.5.177 it forwards it.
     *
     * Nullable and defaulted on purpose: providers that issue no ID token are a
     * legitimate case, not an error, and an older node simply omits the field.
     */
    @SerialName("id_token")
    val idToken: String? = null,
)

/**
 * The node's terminal error body on the OAuth hand-off endpoint, e.g.
 * `{"reason_id":"auth.oauth.store_unavailable","status":"..."}`. Human message
 * is derived from [reasonId] client-side (the body carries no prose).
 */
@Serializable
data class OAuthHandoffError(
    @SerialName("reason_id")
    val reasonId: String? = null,
    val status: String? = null,
)

/**
 * The outcome of one poll of the desktop OAuth hand-off (#1098 follow-up).
 *
 * Distinguishes a TERMINAL node failure from "still waiting", so a failed
 * sign-in returns to Login with the node's reason instead of spinning to the
 * ~3-minute timeout.
 */
sealed class OAuthHandoffPoll {
    /** 204 — not yet; the human is still in the browser. Keep waiting. */
    object Pending : OAuthHandoffPoll()

    /** The node handed the session over. */
    data class Ready(val handoff: OAuthHandoff) : OAuthHandoffPoll()

    /** The node reported a terminal failure for this flow. Stop and show it. */
    data class Failed(val reasonId: String?, val status: String?) : OAuthHandoffPoll()
}
