package ai.ciris.mobile.shared.services

import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Persists the user's list of [NodeProfile]s in [SecureStorage].
 *
 * This is the backing store for the first-class **node switcher** on the main
 * page. Profiles (and the session token each holds) are sensitive, so they live
 * only in the encrypted secure store — never in plain prefs. The store keeps the
 * full list under a single key as a JSON array; the active profile is tracked by
 * id under a separate key.
 *
 * Mirrors the storage approach of
 * [ai.ciris.mobile.shared.viewmodels.ServerConnectionViewModel] (JSON-encoded
 * list saved through [SecureStorage.save]) so behaviour and failure handling are
 * consistent across the app.
 */
class NodeProfileStore(
    private val secureStorage: SecureStorage,
) {
    companion object {
        private const val TAG = "NodeProfileStore"
        private const val KEY_PROFILES = "node_profiles"
        private const val KEY_ACTIVE_ID = "active_node_profile_id"
        private const val MAX_PROFILES = 16
    }

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Load all saved node profiles, most-recently-used first. */
    suspend fun loadProfiles(): List<NodeProfile> {
        return try {
            val raw = secureStorage.get(KEY_PROFILES).getOrNull()
            if (raw.isNullOrBlank()) emptyList()
            else json.decodeFromString<List<NodeProfile>>(raw)
                .sortedByDescending { it.lastUsedEpochMs }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "[loadProfiles] Failed: ${e.message}", e)
            emptyList()
        }
    }

    /** Persist the full profile list (capped at [MAX_PROFILES]). */
    private suspend fun saveProfiles(profiles: List<NodeProfile>) {
        try {
            val capped = profiles.sortedByDescending { it.lastUsedEpochMs }.take(MAX_PROFILES)
            secureStorage.save(KEY_PROFILES, json.encodeToString(capped))
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "[saveProfiles] Failed: ${e.message}", e)
        }
    }

    /**
     * Insert or update a profile (keyed by [NodeProfile.id]). Returns the saved
     * list. If a profile with the same id exists it is replaced, preserving any
     * existing token when [profile] carries none.
     */
    suspend fun upsert(profile: NodeProfile): List<NodeProfile> {
        val current = loadProfiles().toMutableList()
        val existingIdx = current.indexOfFirst { it.id == profile.id }
        val merged = if (existingIdx >= 0) {
            val existing = current[existingIdx]
            profile.copy(
                sessionToken = profile.sessionToken ?: existing.sessionToken,
                lastUsedEpochMs = maxOf(profile.lastUsedEpochMs, existing.lastUsedEpochMs),
                // Preserve an existing identity-pin when the incoming profile
                // carries none (e.g. a token-only update must not drop the pin).
                pinnedKeyId = profile.pinnedKeyId ?: existing.pinnedKeyId,
                pinnedPubkeyBase64 = profile.pinnedPubkeyBase64 ?: existing.pinnedPubkeyBase64,
            ).also { current[existingIdx] = it }
        } else {
            current.add(profile)
            profile
        }
        PlatformLogger.i(TAG, "[upsert] ${merged.name} (${merged.baseUrl}) authed=${merged.isAuthenticated}")
        saveProfiles(current)
        return current.sortedByDescending { it.lastUsedEpochMs }
    }

    /** Remove a profile by id. Returns the remaining list. */
    suspend fun remove(id: String): List<NodeProfile> {
        val remaining = loadProfiles().filterNot { it.id == id }
        saveProfiles(remaining)
        if (getActiveProfileId() == id) clearActiveProfileId()
        return remaining
    }

    /**
     * Mark [id] as the active node and bump its lastUsed timestamp.
     * Returns the updated list.
     */
    suspend fun markActive(id: String, nowEpochMs: Long): List<NodeProfile> {
        val updated = loadProfiles().map {
            if (it.id == id) it.copy(lastUsedEpochMs = nowEpochMs) else it
        }
        saveProfiles(updated)
        secureStorage.save(KEY_ACTIVE_ID, id)
        return updated.sortedByDescending { it.lastUsedEpochMs }
    }

    suspend fun getActiveProfileId(): String? =
        secureStorage.get(KEY_ACTIVE_ID).getOrNull()?.takeIf { it.isNotBlank() }

    suspend fun getActiveProfile(): NodeProfile? {
        val id = getActiveProfileId() ?: return null
        return loadProfiles().firstOrNull { it.id == id }
    }

    private suspend fun clearActiveProfileId() {
        secureStorage.delete(KEY_ACTIVE_ID)
    }
}
