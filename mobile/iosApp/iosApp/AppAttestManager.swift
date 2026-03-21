import DeviceCheck
import CryptoKit
import Foundation

/// Manages Apple App Attest for hardware-backed device attestation.
/// iOS equivalent of PlayIntegrityManager on Android.
///
/// Results are cached in UserDefaults with a 24h TTL to:
/// - Avoid slamming the registry on crash loops
/// - Skip redundant attestation on normal restarts
/// - Persist across app launches
///
/// Flow (only if cache is stale/missing):
/// 1. Get nonce from backend (CIRISVerify FFI → registry)
/// 2. Generate key via DCAppAttestService
/// 3. Attest key with nonce hash → Apple returns CBOR attestation object
/// 4. Send attestation to backend for verification (CIRISVerify FFI → registry)
/// 5. Cache result in UserDefaults
class AppAttestManager {

    static let shared = AppAttestManager()

    private let service = DCAppAttestService.shared
    private var keyId: String?

    // Cache keys
    private static let cacheResultKey = "ciris_app_attest_result"
    private static let cacheTimestampKey = "ciris_app_attest_timestamp"
    private static let keyIdKey = "ciris_app_attest_key_id"
    private static let cacheTTL: TimeInterval = 24 * 60 * 60  // 24 hours

    /// In-memory cached result for the current session
    private var cachedResult: AppAttestResult?

    /// Serialization: if an attestation is already in-flight, all callers
    /// await the same Task instead of requesting a second nonce.
    private var inFlightTask: Task<AppAttestResult, Never>?

    private static let cachedBuildKey = "ciris_app_attest_build"

    private init() {
        keyId = UserDefaults.standard.string(forKey: Self.keyIdKey)

        // Clear cache when app build changes so new code gets a fresh attestation
        let currentBuild = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? ""
        let cachedBuild = UserDefaults.standard.string(forKey: Self.cachedBuildKey) ?? ""
        if currentBuild != cachedBuild {
            NSLog("[AppAttest] Build changed (\(cachedBuild) → \(currentBuild)), clearing cache + key")
            clearCache()
            // Also clear the attestation key — forces a fresh key generation
            keyId = nil
            UserDefaults.standard.removeObject(forKey: Self.keyIdKey)
            UserDefaults.standard.set(currentBuild, forKey: Self.cachedBuildKey)
        }
    }

    /// Check if App Attest is supported on this device.
    var isSupported: Bool {
        return service.isSupported
    }

    /// Get cached result if available and fresh (< 24h old).
    /// Returns nil if cache is stale or missing.
    func getCachedResult() -> AppAttestResult? {
        // Check in-memory cache first
        if let cached = cachedResult {
            return cached
        }

        // Check persistent cache
        let defaults = UserDefaults.standard
        let timestamp = defaults.double(forKey: Self.cacheTimestampKey)
        guard timestamp > 0 else { return nil }

        let age = Date().timeIntervalSince1970 - timestamp
        guard age < Self.cacheTTL else {
            NSLog("[AppAttest] Cache expired (age=%.0fs, ttl=%.0fs)", age, Self.cacheTTL)
            return nil
        }

        guard let data = defaults.data(forKey: Self.cacheResultKey),
              let result = try? JSONDecoder().decode(AppAttestResult.self, from: data) else {
            return nil
        }

        NSLog("[AppAttest] Using cached result (age=%.0fs): verified=%d", age, result.verified)
        cachedResult = result
        return result
    }

    /// Perform App Attest, using cache if available.
    /// Safe to call concurrently — serializes so only one nonce is in-flight.
    func attestDeviceIfNeeded() async -> AppAttestResult {
        // Return cached result if fresh
        if let cached = getCachedResult() {
            NSLog("[AppAttest] Returning cached result (verified=\(cached.verified))")
            return cached
        }

        // No cache or stale — do full attestation (serialized)
        return await attestDevice()
    }

    /// Perform full App Attest attestation (bypasses cache).
    /// Serialized: if already in-flight, returns the same Task's result
    /// instead of requesting a second nonce (which would cause nonce_expired).
    func attestDevice() async -> AppAttestResult {
        // If another call is already in-flight, piggyback on it
        if let existing = inFlightTask {
            NSLog("[AppAttest] Attestation already in-flight, waiting for existing task...")
            return await existing.value
        }

        let task = Task<AppAttestResult, Never> {
            let result = await performAttestationFlow()
            // Clear in-flight so next call can start fresh
            self.inFlightTask = nil
            return result
        }
        inFlightTask = task
        return await task.value
    }

    /// The actual attestation flow — called only once at a time via serialization.
    private func performAttestationFlow() async -> AppAttestResult {
        guard isSupported else {
            NSLog("[AppAttest] Not supported on this device")
            let result = AppAttestResult(verified: false, error: "App Attest not supported")
            cacheResult(result)
            return result
        }

        NSLog("[AppAttest] Starting attestation flow...")

        // Step 1: Get nonce from backend
        let nonce: String
        do {
            nonce = try await getNonceFromBackend()
            NSLog("[AppAttest] Got nonce: \(nonce.prefix(20))...")
        } catch {
            NSLog("[AppAttest] Failed to get nonce: \(error)")
            let result = AppAttestResult(verified: false, error: "Failed to get nonce: \(error.localizedDescription)")
            cacheResult(result)
            return result
        }

        // Step 2: Generate key (or reuse existing)
        let attestKeyId: String
        do {
            attestKeyId = try await generateKeyIfNeeded()
            NSLog("[AppAttest] Using key: \(attestKeyId.prefix(16))...")
        } catch {
            NSLog("[AppAttest] Failed to generate key: \(error)")
            let result = AppAttestResult(verified: false, error: "Failed to generate key: \(error.localizedDescription)")
            cacheResult(result)
            return result
        }

        // Step 3: Attest key with nonce hash
        let attestationObject: Data
        do {
            let nonceData = Data(nonce.utf8)
            let hash = SHA256.hash(data: nonceData)
            let clientDataHash = Data(hash)

            attestationObject = try await service.attestKey(attestKeyId, clientDataHash: clientDataHash)
            NSLog("[AppAttest] Got attestation object: \(attestationObject.count) bytes")
        } catch {
            NSLog("[AppAttest] attestKey failed: \(error)")
            // Key may be compromised, clear it
            keyId = nil
            UserDefaults.standard.removeObject(forKey: Self.keyIdKey)
            let result = AppAttestResult(verified: false, error: "attestKey failed: \(error.localizedDescription)")
            cacheResult(result)
            return result
        }

        // Step 4: Send to backend for verification
        do {
            let result = try await verifyAttestationWithBackend(
                attestationObject: attestationObject,
                keyId: attestKeyId,
                nonce: nonce
            )
            NSLog("[AppAttest] Verification result: verified=\(result.verified)")
            cacheResult(result)
            return result
        } catch {
            NSLog("[AppAttest] Backend verification failed: \(error)")
            let result = AppAttestResult(verified: false, error: "Verification failed: \(error.localizedDescription)")
            cacheResult(result)
            return result
        }
    }

    // MARK: - Cache

    private func cacheResult(_ result: AppAttestResult) {
        cachedResult = result
        // Only persist successful results for 24h.
        // Failed results stay in memory for this session only — next
        // launch will retry (prevents 24h lockout on transient errors).
        guard result.verified else {
            NSLog("[AppAttest] Not persisting failed result (memory-only): \(result.error ?? "unknown")")
            return
        }
        let defaults = UserDefaults.standard
        if let data = try? JSONEncoder().encode(result) {
            defaults.set(data, forKey: Self.cacheResultKey)
            defaults.set(Date().timeIntervalSince1970, forKey: Self.cacheTimestampKey)
            NSLog("[AppAttest] Cached successful result to UserDefaults")
        }
    }

    /// Clear cached result (e.g., on logout or manual refresh).
    func clearCache() {
        cachedResult = nil
        let defaults = UserDefaults.standard
        defaults.removeObject(forKey: Self.cacheResultKey)
        defaults.removeObject(forKey: Self.cacheTimestampKey)
        NSLog("[AppAttest] Cache cleared")
    }

    // MARK: - Private helpers

    private func generateKeyIfNeeded() async throws -> String {
        if let existing = keyId {
            return existing
        }
        let newKeyId = try await service.generateKey()
        keyId = newKeyId
        UserDefaults.standard.set(newKeyId, forKey: Self.keyIdKey)
        NSLog("[AppAttest] Generated new key: \(newKeyId.prefix(16))...")
        return newKeyId
    }

    /// Get App Attest nonce from the local Python backend.
    private func getNonceFromBackend() async throws -> String {
        let url = URL(string: "http://127.0.0.1:8080/v1/setup/app-attest/nonce")!
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.httpMethod = "GET"

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw AppAttestError.backendError("Nonce request failed: HTTP \(statusCode)")
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let nonceData = (json?["data"] as? [String: Any]) ?? json
        guard let nonce = nonceData?["nonce"] as? String else {
            throw AppAttestError.backendError("No nonce in response")
        }

        return nonce
    }

    /// Verify attestation object with the local Python backend.
    private func verifyAttestationWithBackend(
        attestationObject: Data,
        keyId: String,
        nonce: String
    ) async throws -> AppAttestResult {
        let url = URL(string: "http://127.0.0.1:8080/v1/setup/app-attest/verify")!
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "attestation": attestationObject.base64EncodedString(),
            "key_id": keyId,
            "nonce": nonce
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw AppAttestError.backendError("Verify request failed: HTTP \(statusCode)")
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let resultData = (json?["data"] as? [String: Any]) ?? json

        let verified = resultData?["verified"] as? Bool ?? false
        let error = resultData?["error"] as? String

        let deviceEnv = resultData?["device_environment"] as? [String: Any]
        let isGenuine = deviceEnv?["is_genuine_device"] as? Bool ?? false
        let isUnmodified = deviceEnv?["is_unmodified_app"] as? Bool ?? false

        let verdict: String
        if verified && isGenuine && isUnmodified {
            verdict = "MEETS_STRONG_INTEGRITY"
        } else if verified && isGenuine {
            verdict = "MEETS_DEVICE_INTEGRITY"
        } else if verified {
            verdict = "MEETS_BASIC_INTEGRITY"
        } else {
            verdict = error ?? "VERIFICATION_FAILED"
        }

        return AppAttestResult(
            verified: verified,
            verdict: verdict,
            isGenuineDevice: isGenuine,
            isUnmodifiedApp: isUnmodified,
            error: error
        )
    }
}

/// Result of App Attest attestation. Codable for UserDefaults persistence.
struct AppAttestResult: Codable {
    let verified: Bool
    var verdict: String = ""
    var isGenuineDevice: Bool = false
    var isUnmodifiedApp: Bool = false
    var error: String? = nil
}

enum AppAttestError: LocalizedError {
    case backendError(String)
    case notSupported

    var errorDescription: String? {
        switch self {
        case .backendError(let msg): return msg
        case .notSupported: return "App Attest not supported"
        }
    }
}
