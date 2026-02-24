import DeviceCheck
import CryptoKit
import Foundation

/// Manages Apple App Attest for hardware-backed device attestation.
/// iOS equivalent of PlayIntegrityManager on Android.
///
/// Flow:
/// 1. Get nonce from backend (which calls CIRISVerify FFI → registry)
/// 2. Generate key via DCAppAttestService
/// 3. Attest key with nonce hash → Apple returns CBOR attestation object
/// 4. Send attestation to backend for verification (CIRISVerify FFI → registry)
class AppAttestManager {

    static let shared = AppAttestManager()

    private let service = DCAppAttestService.shared
    private var keyId: String?

    private init() {
        // Restore saved key ID if available
        keyId = UserDefaults.standard.string(forKey: "ciris_app_attest_key_id")
    }

    /// Check if App Attest is supported on this device.
    var isSupported: Bool {
        return service.isSupported
    }

    /// Perform full App Attest attestation.
    /// Returns a result struct matching the KMP DeviceAttestationResult pattern.
    func attestDevice() async -> AppAttestResult {
        guard isSupported else {
            NSLog("[AppAttest] Not supported on this device")
            return AppAttestResult(verified: false, error: "App Attest not supported")
        }

        NSLog("[AppAttest] Starting attestation flow...")

        // Step 1: Get nonce from backend
        let nonce: String
        do {
            nonce = try await getNonceFromBackend()
            NSLog("[AppAttest] Got nonce: \(nonce.prefix(20))...")
        } catch {
            NSLog("[AppAttest] Failed to get nonce: \(error)")
            return AppAttestResult(verified: false, error: "Failed to get nonce: \(error.localizedDescription)")
        }

        // Step 2: Generate key (or reuse existing)
        let attestKeyId: String
        do {
            attestKeyId = try await generateKeyIfNeeded()
            NSLog("[AppAttest] Using key: \(attestKeyId.prefix(16))...")
        } catch {
            NSLog("[AppAttest] Failed to generate key: \(error)")
            return AppAttestResult(verified: false, error: "Failed to generate key: \(error.localizedDescription)")
        }

        // Step 3: Attest key with nonce hash
        let attestationObject: Data
        do {
            // DCAppAttestService expects SHA256 hash of the challenge
            let nonceData = Data(nonce.utf8)
            let hash = SHA256.hash(data: nonceData)
            let clientDataHash = Data(hash)

            attestationObject = try await service.attestKey(attestKeyId, clientDataHash: clientDataHash)
            NSLog("[AppAttest] Got attestation object: \(attestationObject.count) bytes")
        } catch {
            NSLog("[AppAttest] attestKey failed: \(error)")
            // Key may be compromised, clear it
            keyId = nil
            UserDefaults.standard.removeObject(forKey: "ciris_app_attest_key_id")
            return AppAttestResult(verified: false, error: "attestKey failed: \(error.localizedDescription)")
        }

        // Step 4: Send to backend for verification
        do {
            let result = try await verifyAttestationWithBackend(
                attestationObject: attestationObject,
                keyId: attestKeyId,
                nonce: nonce
            )
            NSLog("[AppAttest] Verification result: verified=\(result.verified)")
            return result
        } catch {
            NSLog("[AppAttest] Backend verification failed: \(error)")
            return AppAttestResult(verified: false, error: "Verification failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Private helpers

    private func generateKeyIfNeeded() async throws -> String {
        if let existing = keyId {
            return existing
        }
        let newKeyId = try await service.generateKey()
        keyId = newKeyId
        UserDefaults.standard.set(newKeyId, forKey: "ciris_app_attest_key_id")
        NSLog("[AppAttest] Generated new key: \(newKeyId.prefix(16))...")
        return newKeyId
    }

    /// Get App Attest nonce from the local Python backend.
    /// Backend calls CIRISVerify FFI → registry GET /v1/integrity/ios/nonce
    private func getNonceFromBackend() async throws -> String {
        let url = URL(string: "http://localhost:8080/v1/setup/app-attest/nonce")!
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.httpMethod = "GET"

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw AppAttestError.backendError("Nonce request failed: HTTP \(statusCode)")
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        // Response format: {"nonce": "...", "expires_at": "..."}
        // Or wrapped: {"data": {"nonce": "...", "expires_at": "..."}}
        let nonceData = (json?["data"] as? [String: Any]) ?? json
        guard let nonce = nonceData?["nonce"] as? String else {
            throw AppAttestError.backendError("No nonce in response")
        }

        return nonce
    }

    /// Verify attestation object with the local Python backend.
    /// Backend calls CIRISVerify FFI → registry POST /v1/integrity/ios/verify
    private func verifyAttestationWithBackend(
        attestationObject: Data,
        keyId: String,
        nonce: String
    ) async throws -> AppAttestResult {
        let url = URL(string: "http://localhost:8080/v1/setup/app-attest/verify")!
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "attestation_object": attestationObject.base64EncodedString(),
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

        // Map to Play Integrity-style verdicts for UI compatibility
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

/// Result of App Attest attestation.
struct AppAttestResult {
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
