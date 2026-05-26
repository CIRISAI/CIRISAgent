package ai.ciris.mobile.shared.utils

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Tests for the 2.9.2 personal-install observer-block error-body
 * parser. The parser is the bridge between the server's structured
 * 403 detail and the client's structured recovery UI — if it fails to
 * extract the owner_hint, the user sees the generic "wrong account"
 * card instead of "this device is set up for Eric (eri***@gmail.com)".
 *
 * Every shape the FastAPI HTTPException serialiser produces is pinned
 * here. New shapes (e.g. a wrapped or i18n-translated error envelope)
 * should add a case rather than relax an existing assertion.
 */
class OwnerHintParserTest {

    @Test
    fun returns_null_for_empty_body() {
        assertNull(parseOwnerHintFromErrorBody(null))
        assertNull(parseOwnerHintFromErrorBody(""))
        assertNull(parseOwnerHintFromErrorBody("   "))
    }

    @Test
    fun returns_null_when_owner_hint_key_absent() {
        // Generic 500 from the server — no owner_hint anywhere.
        val body = "Token exchange failed (500): {\"detail\":\"internal server error\"}"
        assertNull(parseOwnerHintFromErrorBody(body))
    }

    @Test
    fun parses_full_personal_install_403_payload() {
        // The shape we actually see in production after the 2.9.2
        // server change ships. detail.owner_hint nested under
        // FastAPI's HTTPException envelope.
        val body = """Token exchange failed (403): {"detail":{"code":"auth_personal_install_observer_blocked","message":"This is a personal CIRIS installation.","owner_hint":{"masked_email":"eri***@gmail.com","first_name":"Eric","auth_type":"oauth","oauth_provider":"google"}}}"""
        val hint = parseOwnerHintFromErrorBody(body)
        assertEquals("eri***@gmail.com", hint?.masked_email)
        assertEquals("Eric", hint?.first_name)
        assertEquals("oauth", hint?.auth_type)
        assertEquals("google", hint?.oauth_provider)
    }

    @Test
    fun parses_payload_with_only_some_fields_set() {
        // Local-login owner — no email, no provider. The card still
        // needs to render with the first name so this must not return
        // null.
        val body = """{"detail":{"code":"auth_personal_install_observer_blocked","owner_hint":{"first_name":"admin","auth_type":"password","masked_email":null,"oauth_provider":null}}}"""
        val hint = parseOwnerHintFromErrorBody(body)
        assertNull(hint?.masked_email)
        assertEquals("admin", hint?.first_name)
        assertEquals("password", hint?.auth_type)
        assertNull(hint?.oauth_provider)
    }

    @Test
    fun parses_top_level_owner_hint_without_envelope() {
        // Some intermediate clients re-wrap errors and drop the
        // `detail` envelope — accept the top-level shape too.
        val body = """{"owner_hint":{"first_name":"Eric","masked_email":"eri***@gmail.com"}}"""
        val hint = parseOwnerHintFromErrorBody(body)
        assertEquals("Eric", hint?.first_name)
        assertEquals("eri***@gmail.com", hint?.masked_email)
    }

    @Test
    fun returns_null_on_unbalanced_json() {
        // Server error truncated mid-payload — never throw, just return
        // null so the recovery card falls back to a generic body.
        val body = """Token exchange failed (403): {"detail":{"code":"auth_personal_install_observer_blocked","owner_hint":{"first_name":"Eric"""
        assertNull(parseOwnerHintFromErrorBody(body))
    }

    @Test
    fun returns_null_on_garbage_json() {
        val body = "owner_hint = not actually json"
        assertNull(parseOwnerHintFromErrorBody(body))
    }

    @Test
    fun handles_strings_with_escaped_braces() {
        // Make sure brace counting respects strings — a `{` inside a
        // quoted message value should not break the depth tracking.
        val body = """{"detail":{"message":"unexpected {token}","owner_hint":{"first_name":"Eric"}}}"""
        val hint = parseOwnerHintFromErrorBody(body)
        assertEquals("Eric", hint?.first_name)
    }
}
