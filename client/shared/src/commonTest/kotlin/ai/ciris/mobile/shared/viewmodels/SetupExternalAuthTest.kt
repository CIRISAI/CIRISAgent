package ai.ciris.mobile.shared.viewmodels

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * **An OAuth user is never asked for a password.**
 *
 * `/v1/setup/complete` computes `is_oauth_user = bool(oauth_provider)`. When true
 * it GENERATES a random password for an account that will never use one; when
 * false it refuses:
 *
 * ```
 * HTTP 400 {"detail":"New user password must be at least 8 characters"}
 * ```
 *
 * That refusal is correct for a password account and nonsense to someone who has
 * just signed in with Google — which is exactly what a user hit, mid-wizard, on
 * the BYOK path.
 *
 * The cause was two answers to one question. The CIRIS-proxy branch passed
 * `oauthProvider` straight through; the BYOK branch required
 * `isGoogleAuth && googleUserId != null`. A provider that returns no subject id
 * therefore read as a PASSWORD account on one path and an OAuth account on the
 * other.
 *
 * These pin the derivation itself, so the two branches cannot drift apart again.
 */
class SetupExternalAuthTest {

    @Test
    fun oauth_without_a_subject_id_is_still_oauth() {
        // The reported case: signed in, no subject id came back.
        val s = SetupFormState(isGoogleAuth = true, googleUserId = null, oauthProvider = "google")

        assertTrue(
            s.isExternalAuth,
            "an OAuth sign-in with no subject id read as a PASSWORD account — this is " +
                "the state that produced 'New user password must be at least 8 characters' " +
                "for a user who never set one",
        )
        assertEquals(
            "google",
            s.effectiveOAuthProvider,
            "oauth_provider must still be sent, or the server generates no password and refuses",
        )
    }

    @Test
    fun apple_is_oauth_too() {
        // `isGoogleAuth` is set from `isAuth` for BOTH providers despite the name;
        // a check written against Google alone would take Apple users down the
        // password path.
        val s = SetupFormState(isGoogleAuth = true, googleUserId = "apple-sub-123", oauthProvider = "apple")
        assertTrue(s.isExternalAuth)
        assertEquals("apple", s.effectiveOAuthProvider)
    }

    @Test
    fun ha_addon_is_external_auth_but_not_oauth() {
        val s = SetupFormState(isHAAddonMode = true)
        assertTrue(s.isExternalAuth, "SUPERVISOR_TOKEN is external auth — no password either")
        assertEquals("home_assistant", s.effectiveOAuthProvider)
    }

    @Test
    fun a_genuine_password_account_is_not_external() {
        val s = SetupFormState(isGoogleAuth = false, googleUserId = null)
        assertTrue(!s.isExternalAuth, "a password user must still be required to set one")
        assertNull(
            s.effectiveOAuthProvider,
            "sending an oauth_provider here would make the server generate a random " +
                "password and silently skip the password the user actually chose",
        )
    }
}
