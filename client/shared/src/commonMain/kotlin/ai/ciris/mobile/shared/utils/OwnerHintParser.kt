package ai.ciris.mobile.shared.utils

import ai.ciris.mobile.shared.models.OwnerHint
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Extract a 2.9.2 `owner_hint` payload from the error message text we
 * raise when the server returns 403
 * `auth_personal_install_observer_blocked`.
 *
 * Why string parsing instead of structured error capture: the existing
 * generated API client surfaces server errors as `Exception(message)`
 * with the body baked into the message string — there is no typed
 * error envelope we can deserialize. Rather than refactor the API
 * layer for this single recovery path, we look for the embedded JSON
 * object and lift the `owner_hint` field out.
 *
 * Expected shapes (both produced by the FastAPI HTTPException
 * serialiser at auth.py:_reject_observer_on_personal_install):
 *   `Token exchange failed (403): {"detail":{"code":"...","owner_hint":{...}}}`
 *   `... {"detail":{"code":"...","message":"...","owner_hint":{...}}}`
 *
 * Returns null when:
 *   * the error text doesn't contain `owner_hint`, OR
 *   * the JSON fragment is unparseable (server returned a different
 *     shape, the error was wrapped, etc.).
 *
 * Never throws — callers fall back to the previously-loaded hint (or
 * a generic recovery card) on parse failure.
 */
fun parseOwnerHintFromErrorBody(errorBody: String?): OwnerHint? {
    if (errorBody.isNullOrBlank() || !errorBody.contains("owner_hint")) return null

    return try {
        val jsonStart = errorBody.indexOf('{')
        if (jsonStart < 0) return null
        // Find the matching closing brace for the outermost JSON object
        // by depth-counting — handles nested objects like detail.owner_hint
        // without pulling in a regex.
        val payload = extractJsonObject(errorBody, jsonStart) ?: return null

        val parser = Json { ignoreUnknownKeys = true; isLenient = true }
        val root = parser.parseToJsonElement(payload).jsonObject

        // The detail field is the FastAPI envelope. Some clients re-wrap
        // it — try both `detail.owner_hint` and a top-level `owner_hint`.
        val ownerHintNode = (root["detail"] as? JsonObject)?.get("owner_hint")
            ?: root["owner_hint"]

        val hintObj = ownerHintNode as? JsonObject ?: return null

        OwnerHint(
            masked_email = (hintObj["masked_email"] as? JsonPrimitive)?.contentOrNull(),
            first_name = (hintObj["first_name"] as? JsonPrimitive)?.contentOrNull(),
            auth_type = (hintObj["auth_type"] as? JsonPrimitive)?.contentOrNull(),
            oauth_provider = (hintObj["oauth_provider"] as? JsonPrimitive)?.contentOrNull(),
        )
    } catch (e: Throwable) {
        null
    }
}

/**
 * Extract the JSON object that starts at `startIdx` (must be a `{`).
 * Returns null if the braces don't balance — e.g. the message text
 * embedded the prefix `{` of a JSON object but was truncated.
 */
private fun extractJsonObject(source: String, startIdx: Int): String? {
    var depth = 0
    var inString = false
    var escape = false
    for (i in startIdx until source.length) {
        val ch = source[i]
        if (escape) {
            escape = false
            continue
        }
        if (ch == '\\') {
            escape = true
            continue
        }
        if (ch == '"') {
            inString = !inString
            continue
        }
        if (inString) continue
        when (ch) {
            '{' -> depth++
            '}' -> {
                depth--
                if (depth == 0) {
                    return source.substring(startIdx, i + 1)
                }
            }
        }
    }
    return null
}

/** JSON null-safe content extractor — mirrors the kotlinx-serialization helper. */
private fun JsonPrimitive.contentOrNull(): String? {
    return if (this.isString) {
        this.content
    } else {
        // Numbers / bools / unquoted null — owner_hint fields are all strings,
        // so a non-string primitive means the server contract changed.
        if (this.content == "null") null else this.content
    }
}
