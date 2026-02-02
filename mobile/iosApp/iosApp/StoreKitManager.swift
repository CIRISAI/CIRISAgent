import StoreKit
import Foundation

/// Manager for StoreKit 2 in-app purchases
@MainActor
class StoreKitManager: NSObject, ObservableObject {
    static let shared = StoreKitManager()

    // Product IDs matching CIRISBilling configuration
    static let productIDs: Set<String> = [
        "ai.ciris.mobile.credits_100_v1",
        "ai.ciris.mobile.credits_250_v1",
        "ai.ciris.mobile.credits_600_v1"
    ]

    // Published state
    @Published private(set) var products: [Product] = []
    @Published private(set) var purchasedProductIDs: Set<String> = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    // Transaction listener task
    private var transactionListenerTask: Task<Void, Error>?

    // Callback for purchase verification results
    var onPurchaseVerified: ((Bool, Int, Int, String?) -> Void)?

    // Billing endpoint configuration
    private let billingBaseURL: String

    private override init() {
        // Use environment variable or default to production billing
        self.billingBaseURL = ProcessInfo.processInfo.environment["CIRIS_BILLING_URL"]
            ?? "https://billing.ciris.ai"
        super.init()
    }

    /// Start listening for transactions and load products
    func start() {
        NSLog("[StoreKitManager] Starting...")
        transactionListenerTask = listenForTransactions()

        Task {
            await loadProducts()
        }
    }

    /// Stop listening for transactions
    func stop() {
        NSLog("[StoreKitManager] Stopping...")
        transactionListenerTask?.cancel()
        transactionListenerTask = nil
    }

    /// Load available products from App Store
    func loadProducts() async {
        NSLog("[StoreKitManager] Loading products: \(Self.productIDs)")
        isLoading = true
        errorMessage = nil

        do {
            let storeProducts = try await Product.products(for: Self.productIDs)

            // Sort by price
            products = storeProducts.sorted { $0.price < $1.price }

            NSLog("[StoreKitManager] Loaded \(products.count) products:")
            for product in products {
                NSLog("[StoreKitManager]   - \(product.id): \(product.displayName) @ \(product.displayPrice)")
            }

            isLoading = false
        } catch {
            NSLog("[StoreKitManager] Failed to load products: \(error)")
            errorMessage = "Failed to load products: \(error.localizedDescription)"
            isLoading = false
        }
    }

    /// Purchase a product
    func purchase(_ product: Product, appleIDToken: String) async throws -> PurchaseResult {
        NSLog("[StoreKitManager] Purchasing: \(product.id)")

        do {
            let result = try await product.purchase()

            switch result {
            case .success(let verification):
                NSLog("[StoreKitManager] Purchase succeeded, verifying...")
                let transaction = try checkVerified(verification)

                // Verify with our billing backend
                let verifyResult = await verifyWithBackend(
                    transactionID: String(transaction.id),
                    appleIDToken: appleIDToken
                )

                if verifyResult.success {
                    // Finish the transaction only after successful backend verification
                    await transaction.finish()
                    NSLog("[StoreKitManager] Transaction finished: \(transaction.id)")

                    onPurchaseVerified?(true, verifyResult.creditsAdded, verifyResult.newBalance, nil)
                    return .success(creditsAdded: verifyResult.creditsAdded, newBalance: verifyResult.newBalance)
                } else {
                    NSLog("[StoreKitManager] Backend verification failed: \(verifyResult.error ?? "unknown")")
                    onPurchaseVerified?(false, 0, 0, verifyResult.error)
                    return .failed(error: verifyResult.error ?? "Verification failed")
                }

            case .userCancelled:
                NSLog("[StoreKitManager] Purchase cancelled by user")
                return .cancelled

            case .pending:
                NSLog("[StoreKitManager] Purchase pending (e.g., parental approval)")
                return .pending

            @unknown default:
                NSLog("[StoreKitManager] Unknown purchase result")
                return .failed(error: "Unknown result")
            }
        } catch {
            NSLog("[StoreKitManager] Purchase error: \(error)")
            throw error
        }
    }

    /// Listen for transaction updates (e.g., pending transactions completing)
    private func listenForTransactions() -> Task<Void, Error> {
        return Task.detached { [weak self] in
            NSLog("[StoreKitManager] Starting transaction listener...")

            for await result in Transaction.updates {
                do {
                    let transaction = try await self?.checkVerified(result)

                    if let transaction = transaction {
                        NSLog("[StoreKitManager] Transaction update: \(transaction.id) - \(transaction.productID)")

                        // Note: We don't auto-verify here because we need the Apple ID token
                        // The app should handle pending transactions on next launch
                        await MainActor.run {
                            self?.purchasedProductIDs.insert(transaction.productID)
                        }
                    }
                } catch {
                    NSLog("[StoreKitManager] Transaction verification failed: \(error)")
                }
            }
        }
    }

    /// Verify transaction with StoreKit
    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified(_, let error):
            NSLog("[StoreKitManager] Unverified transaction: \(error)")
            throw StoreError.verificationFailed(error)
        case .verified(let safe):
            return safe
        }
    }

    /// Verify purchase with CIRISBilling backend
    private func verifyWithBackend(transactionID: String, appleIDToken: String) async -> VerifyResult {
        let url = URL(string: "\(billingBaseURL)/v1/user/apple-storekit/verify")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(appleIDToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = ["transaction_id": transactionID]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)

            NSLog("[StoreKitManager] Verifying transaction \(transactionID) with backend...")

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return VerifyResult(success: false, error: "Invalid response")
            }

            NSLog("[StoreKitManager] Backend response: \(httpResponse.statusCode)")

            if httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let success = json["success"] as? Bool ?? false
                    let creditsAdded = json["credits_added"] as? Int ?? 0
                    let newBalance = json["new_balance"] as? Int ?? 0
                    let alreadyProcessed = json["already_processed"] as? Bool ?? false

                    NSLog("[StoreKitManager] Verification success: credits=\(creditsAdded), balance=\(newBalance), already=\(alreadyProcessed)")

                    return VerifyResult(
                        success: success,
                        creditsAdded: creditsAdded,
                        newBalance: newBalance,
                        alreadyProcessed: alreadyProcessed
                    )
                }
            } else {
                let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
                NSLog("[StoreKitManager] Verification failed: \(httpResponse.statusCode) - \(errorBody)")
                return VerifyResult(success: false, error: "Server error: \(httpResponse.statusCode)")
            }
        } catch {
            NSLog("[StoreKitManager] Verification error: \(error)")
            return VerifyResult(success: false, error: error.localizedDescription)
        }

        return VerifyResult(success: false, error: "Unknown error")
    }

    /// Get product info for bridge
    func getProductsInfo() -> [[String: Any]] {
        return products.map { product in
            [
                "id": product.id,
                "displayName": product.displayName,
                "description": product.description,
                "displayPrice": product.displayPrice,
                "price": NSDecimalNumber(decimal: product.price).doubleValue
            ]
        }
    }
}

// MARK: - Types

enum PurchaseResult {
    case success(creditsAdded: Int, newBalance: Int)
    case cancelled
    case pending
    case failed(error: String)
}

enum StoreError: Error {
    case verificationFailed(Error)
    case purchaseFailed(String)
}

struct VerifyResult {
    let success: Bool
    var creditsAdded: Int = 0
    var newBalance: Int = 0
    var alreadyProcessed: Bool = false
    var error: String? = nil
}
