import AuthenticationServices
import Foundation

/// Helper class to handle Sign in with Apple authentication
class AppleSignInHelper: NSObject {
    static let shared = AppleSignInHelper()

    private var currentCompletion: ((Result<AppleSignInCredential, Error>) -> Void)?
    private var presentingWindow: UIWindow?

    private override init() {
        super.init()
    }

    /// Credential data from successful Apple Sign-In
    struct AppleSignInCredential {
        let idToken: String
        let userId: String
        let email: String?
        let fullName: String?
    }

    /// Start the interactive Apple Sign-In flow
    func signIn(
        presentingWindow: UIWindow?,
        completion: @escaping (Result<AppleSignInCredential, Error>) -> Void
    ) {
        self.currentCompletion = completion
        self.presentingWindow = presentingWindow

        let provider = ASAuthorizationAppleIDProvider()
        let request = provider.createRequest()
        request.requestedScopes = [.fullName, .email]

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self
        controller.performRequests()

        NSLog("[AppleSignInHelper] Starting Apple Sign-In flow...")
    }

    /// Attempt silent sign-in (check for existing credential)
    func silentSignIn(completion: @escaping (Result<AppleSignInCredential, Error>) -> Void) {
        // Check if we have a stored user ID
        guard let userId = UserDefaults.standard.string(forKey: "appleSignInUserId") else {
            NSLog("[AppleSignInHelper] No stored Apple user ID for silent sign-in")
            completion(.failure(AppleSignInError.noStoredCredential))
            return
        }

        // Verify the credential is still valid
        let provider = ASAuthorizationAppleIDProvider()
        provider.getCredentialState(forUserID: userId) { state, error in
            DispatchQueue.main.async {
                switch state {
                case .authorized:
                    NSLog("[AppleSignInHelper] Silent sign-in: credential is authorized")
                    // Note: We can't get a new ID token without user interaction
                    // The caller should handle this by showing sign-in UI if they need a fresh token
                    completion(.failure(AppleSignInError.requiresInteraction))
                case .revoked:
                    NSLog("[AppleSignInHelper] Silent sign-in: credential was revoked")
                    UserDefaults.standard.removeObject(forKey: "appleSignInUserId")
                    completion(.failure(AppleSignInError.credentialRevoked))
                case .notFound:
                    NSLog("[AppleSignInHelper] Silent sign-in: credential not found")
                    UserDefaults.standard.removeObject(forKey: "appleSignInUserId")
                    completion(.failure(AppleSignInError.noStoredCredential))
                case .transferred:
                    NSLog("[AppleSignInHelper] Silent sign-in: credential transferred")
                    completion(.failure(AppleSignInError.credentialTransferred))
                @unknown default:
                    completion(.failure(AppleSignInError.unknown))
                }
            }
        }
    }

    /// Sign out (clear stored user ID)
    func signOut() {
        UserDefaults.standard.removeObject(forKey: "appleSignInUserId")
        NSLog("[AppleSignInHelper] Signed out, cleared stored user ID")
    }

    enum AppleSignInError: Error, LocalizedError {
        case noStoredCredential
        case credentialRevoked
        case credentialTransferred
        case requiresInteraction
        case noIdentityToken
        case cancelled
        case unknown

        var errorDescription: String? {
            switch self {
            case .noStoredCredential:
                return "No stored Apple credential"
            case .credentialRevoked:
                return "Apple credential was revoked"
            case .credentialTransferred:
                return "Apple credential was transferred"
            case .requiresInteraction:
                return "Sign-in requires user interaction"
            case .noIdentityToken:
                return "No identity token in credential"
            case .cancelled:
                return "Sign-in was cancelled"
            case .unknown:
                return "Unknown error"
            }
        }
    }
}

// MARK: - ASAuthorizationControllerDelegate

extension AppleSignInHelper: ASAuthorizationControllerDelegate {
    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            NSLog("[AppleSignInHelper] Unexpected credential type")
            currentCompletion?(.failure(AppleSignInError.unknown))
            currentCompletion = nil
            return
        }

        guard let identityTokenData = credential.identityToken,
              let idToken = String(data: identityTokenData, encoding: .utf8) else {
            NSLog("[AppleSignInHelper] No identity token in credential")
            currentCompletion?(.failure(AppleSignInError.noIdentityToken))
            currentCompletion = nil
            return
        }

        let userId = credential.user
        let email = credential.email
        let fullName = [credential.fullName?.givenName, credential.fullName?.familyName]
            .compactMap { $0 }
            .joined(separator: " ")
            .nilIfEmpty

        // Store the user ID for future silent sign-in checks
        UserDefaults.standard.set(userId, forKey: "appleSignInUserId")

        NSLog("[AppleSignInHelper] Sign-in successful: userId=\(userId.prefix(8))..., email=\(email ?? "nil")")

        let result = AppleSignInCredential(
            idToken: idToken,
            userId: userId,
            email: email,
            fullName: fullName
        )

        currentCompletion?(.success(result))
        currentCompletion = nil
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        NSLog("[AppleSignInHelper] Sign-in error: \(error.localizedDescription)")

        if let authError = error as? ASAuthorizationError {
            switch authError.code {
            case .canceled:
                currentCompletion?(.failure(AppleSignInError.cancelled))
            case .failed:
                currentCompletion?(.failure(error))
            case .invalidResponse:
                currentCompletion?(.failure(error))
            case .notHandled:
                currentCompletion?(.failure(error))
            case .notInteractive:
                currentCompletion?(.failure(AppleSignInError.requiresInteraction))
            case .unknown:
                currentCompletion?(.failure(AppleSignInError.unknown))
            @unknown default:
                currentCompletion?(.failure(error))
            }
        } else {
            currentCompletion?(.failure(error))
        }

        currentCompletion = nil
    }
}

// MARK: - ASAuthorizationControllerPresentationContextProviding

extension AppleSignInHelper: ASAuthorizationControllerPresentationContextProviding {
    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        // Use the stored window or find the key window
        if let window = presentingWindow {
            return window
        }

        // Fallback: find the key window
        let scenes = UIApplication.shared.connectedScenes
        let windowScene = scenes.first as? UIWindowScene
        return windowScene?.windows.first { $0.isKeyWindow } ?? UIWindow()
    }
}

// MARK: - String Extension

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
