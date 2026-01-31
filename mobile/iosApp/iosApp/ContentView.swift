import SwiftUI
import shared

struct ContentView: View {
    @State private var pythonReady = false
    @State private var initError: String? = nil
    @State private var failedSteps: [StartupStep] = []
    @StateObject private var storeKitManager = StoreKitManager.shared

    var body: some View {
        if pythonReady {
            // Show the Compose UI with Apple Sign-In and StoreKit support once Python is ready
            ComposeViewWithAuthAndStore(storeKitManager: storeKitManager)
                .ignoresSafeArea()
        } else if let error = initError {
            // Show error state with failed steps
            StartupErrorView(message: error, failedSteps: failedSteps) {
                // Retry
                initError = nil
                failedSteps = []
                Task {
                    await initializePython()
                }
            }
        } else {
            // Show loading while initializing Python
            InitializingView(onInitialize: {
                await initializePython()
            })
        }
    }

    private func initializePython() async {
        NSLog("[ContentView] ========================================")
        NSLog("[ContentView] Starting Python initialization...")
        NSLog("[ContentView] ========================================")

        // Step 1: Extract resources on a background thread so UI can update
        NSLog("[ContentView] Starting resource extraction on background thread...")
        let resourcesPath: String? = await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let path = PythonBridge.extractResources()
                continuation.resume(returning: path)
            }
        }

        guard resourcesPath != nil else {
            await MainActor.run {
                initError = "Failed to extract Python resources"
            }
            return
        }
        NSLog("[ContentView] Resources extracted to: \(resourcesPath!)")

        // Step 2: Initialize Python interpreter (quick operation)
        NSLog("[ContentView] Calling PythonBridge.initializePython()...")
        let success = PythonBridge.initializePython()
        NSLog("[ContentView] initializePython returned: %{public}@", success ? "true" : "false")
        if !success {
            initError = "Failed to initialize Python interpreter"
            return
        }

        // Start the CIRIS runtime
        let started = PythonBridge.startRuntime()
        if !started {
            initError = "Failed to start CIRIS runtime"
            return
        }

        // Wait for server to be ready (poll health endpoint AND status file)
        var attempts = 0
        let maxAttempts = 30  // 30 seconds max

        while attempts < maxAttempts {
            try? await Task.sleep(nanoseconds: 1_000_000_000)  // 1 second
            attempts += 1

            // Check startup status file first
            if let status = loadStartupStatus() {
                if let allPassed = status.all_passed {
                    if !allPassed {
                        // Startup checks failed - show error immediately
                        NSLog("[ContentView] Startup checks failed!")
                        await MainActor.run {
                            failedSteps = status.steps.filter { $0.status == "failed" }
                            initError = "Runtime initialization failed"
                        }
                        return
                    }
                }
            }

            // Check health endpoint
            if PythonBridge.checkHealth() {
                NSLog("[ContentView] Server is healthy after \(attempts) seconds")
                await MainActor.run {
                    pythonReady = true
                }
                return
            }

            NSLog("[ContentView] Waiting for server... (\(attempts)/\(maxAttempts))")
        }

        initError = "Server did not become healthy within 30 seconds"
    }

    private func loadStartupStatus() -> StartupStatus? {
        let fileManager = FileManager.default
        guard let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            NSLog("[ContentView] Could not get documents directory")
            return nil
        }

        let statusFile = documentsURL.appendingPathComponent("ciris/startup_status.json")

        if !fileManager.fileExists(atPath: statusFile.path) {
            // Only log occasionally to avoid spam
            return nil
        }

        do {
            let data = try Data(contentsOf: statusFile)
            let status = try JSONDecoder().decode(StartupStatus.self, from: data)
            NSLog("[ContentView] Loaded status: all_passed=%@, current_step=%d",
                  status.all_passed.map { String($0) } ?? "nil",
                  status.current_step)
            return status
        } catch {
            NSLog("[ContentView] Error loading status: %@", error.localizedDescription)
            return nil
        }
    }
}

// MARK: - Status Models

struct StartupStep: Codable, Identifiable {
    let id: Int
    let name: String
    var status: String
    var message: String?
}

struct StartupStatus: Codable {
    var steps: [StartupStep]
    var current_step: Int
    var all_passed: Bool?
    var runtime_started: Bool
}

// ExtractionStatus is defined in PythonBridge.swift

// MARK: - Initializing View

struct InitializingView: View {
    let onInitialize: () async -> Void

    @State private var startupStatus: StartupStatus? = nil
    @State private var extractionStatus: ExtractionStatus? = nil
    @State private var statusTimer: Timer? = nil
    @State private var hasStartedInit = false

    let cirisColor = Color(red: 0.255, green: 0.612, blue: 0.627)

    var body: some View {
        ZStack {
            Color(red: 0.1, green: 0.1, blue: 0.18)
                .ignoresSafeArea()

            VStack(spacing: 20) {
                // CIRIS Signet
                Image("CIRISSignet")
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 100, height: 100)

                Text("CIRIS")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundColor(.white)

                // Show extraction or startup status
                if let extraction = extractionStatus, extraction.phase == "extracting" {
                    // Extraction in progress
                    Text("Extracting Resources")
                        .font(.system(size: 14))
                        .foregroundColor(.gray)

                    VStack(spacing: 8) {
                        HStack {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: cirisColor))
                                .scaleEffect(0.8)
                            Text("\(extraction.filesExtracted) files...")
                                .font(.system(size: 14, design: .monospaced))
                                .foregroundColor(cirisColor)
                        }

                        if let currentFile = extraction.currentFile {
                            Text(currentFile)
                                .font(.system(size: 11))
                                .foregroundColor(.gray)
                                .lineLimit(1)
                        }
                    }
                    .padding(.top, 20)

                } else {
                    // Show startup checks
                    Text("Initializing Runtime")
                        .font(.system(size: 14))
                        .foregroundColor(.gray)

                    // Startup Steps
                    VStack(alignment: .leading, spacing: 8) {
                        if let status = startupStatus {
                            ForEach(status.steps) { step in
                                StartupStepRow(step: step, cirisColor: cirisColor)
                            }
                        } else {
                            // Show placeholder while loading status
                            ForEach(1...6, id: \.self) { i in
                                StartupStepRow(
                                    step: StartupStep(id: i, name: stepName(for: i), status: "pending", message: nil),
                                    cirisColor: cirisColor
                                )
                            }
                        }
                    }
                    .padding(.horizontal, 32)
                    .padding(.top, 16)

                    Spacer().frame(height: 20)

                    // Show final status or spinner
                    if let status = startupStatus, let allPassed = status.all_passed {
                        if allPassed {
                            Text("Starting server...")
                                .font(.system(size: 12))
                                .foregroundColor(.gray)
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: cirisColor))
                        } else {
                            Text("Some checks failed")
                                .font(.system(size: 12))
                                .foregroundColor(.red)
                        }
                    } else {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: cirisColor))
                    }
                }
            }
            .padding(.vertical, 40)
        }
        .onAppear {
            // Start polling FIRST, then start initialization
            startStatusPolling()

            // Start initialization on background after a brief delay to let polling begin
            if !hasStartedInit {
                hasStartedInit = true
                Task {
                    // Small delay to ensure UI is ready and polling has started
                    try? await Task.sleep(nanoseconds: 100_000_000)  // 0.1 seconds
                    await onInitialize()
                }
            }
        }
        .onDisappear {
            statusTimer?.invalidate()
        }
    }

    private func stepName(for id: Int) -> String {
        switch id {
        case 1: return "Pydantic"
        case 2: return "FastAPI"
        case 3: return "Cryptography"
        case 4: return "HTTP Client"
        case 5: return "Database"
        case 6: return "CIRIS Engine"
        default: return "Step \(id)"
        }
    }

    private func startStatusPolling() {
        // Poll status files every 0.2 seconds
        statusTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { _ in
            loadAllStatus()
        }
    }

    private func loadAllStatus() {
        let fileManager = FileManager.default
        guard let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return
        }

        let cirisDir = documentsURL.appendingPathComponent("ciris")

        // Load extraction status
        let extractionFile = cirisDir.appendingPathComponent("extraction_status.json")
        if fileManager.fileExists(atPath: extractionFile.path),
           let data = try? Data(contentsOf: extractionFile),
           let status = try? JSONDecoder().decode(ExtractionStatus.self, from: data) {
            DispatchQueue.main.async {
                self.extractionStatus = status
            }
        }

        // Load startup status
        let startupFile = cirisDir.appendingPathComponent("startup_status.json")
        if fileManager.fileExists(atPath: startupFile.path),
           let data = try? Data(contentsOf: startupFile),
           let status = try? JSONDecoder().decode(StartupStatus.self, from: data) {
            DispatchQueue.main.async {
                self.startupStatus = status
            }
        }
    }
}

// MARK: - Startup Step Row

struct StartupStepRow: View {
    let step: StartupStep
    let cirisColor: Color

    var body: some View {
        HStack(spacing: 12) {
            // Status icon
            statusIcon
                .frame(width: 20, height: 20)

            // Step name
            Text(step.name)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(textColor)

            Spacer()

            // Version/message if available
            if let message = step.message, step.status == "ok" {
                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(.gray)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch step.status {
        case "ok":
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case "failed":
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        case "running":
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: cirisColor))
                .scaleEffect(0.6)
        default: // pending
            Image(systemName: "circle")
                .foregroundColor(.gray.opacity(0.5))
        }
    }

    private var textColor: Color {
        switch step.status {
        case "ok": return .white
        case "failed": return .red
        case "running": return cirisColor
        default: return .gray
        }
    }
}

// MARK: - Error View

struct ErrorView: View {
    let message: String
    let onRetry: () -> Void

    var body: some View {
        ZStack {
            Color(red: 0.1, green: 0.1, blue: 0.18)
                .ignoresSafeArea()

            VStack(spacing: 24) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 60))
                    .foregroundColor(.red)

                Text("Initialization Error")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(.white)

                Text(message)
                    .font(.system(size: 14))
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                Button(action: onRetry) {
                    Text("Retry")
                        .foregroundColor(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 12)
                        .background(Color(red: 0.255, green: 0.612, blue: 0.627))
                        .cornerRadius(8)
                }
            }
        }
    }
}

// MARK: - Startup Error View

struct StartupErrorView: View {
    let message: String
    let failedSteps: [StartupStep]
    let onRetry: () -> Void

    let cirisColor = Color(red: 0.255, green: 0.612, blue: 0.627)

    var body: some View {
        ZStack {
            Color(red: 0.1, green: 0.1, blue: 0.18)
                .ignoresSafeArea()

            VStack(spacing: 20) {
                // CIRIS Signet (dimmed)
                Image("CIRISSignet")
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 80, height: 80)
                    .opacity(0.5)

                Text("Startup Failed")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(.red)

                Text("The following components failed to load:")
                    .font(.system(size: 14))
                    .foregroundColor(.gray)

                // Failed steps
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(failedSteps) { step in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(.red)
                                Text(step.name)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(.white)
                            }
                            if let msg = step.message {
                                Text(msg)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.gray)
                                    .lineLimit(2)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                    }
                }
                .padding(.horizontal, 24)

                Spacer().frame(height: 10)

                Text("This usually means a native Python module\nis missing from the app bundle.")
                    .font(.system(size: 12))
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)

                Spacer().frame(height: 20)

                Button(action: onRetry) {
                    Text("Retry")
                        .foregroundColor(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 12)
                        .background(cirisColor)
                        .cornerRadius(8)
                }
            }
            .padding(.vertical, 40)
        }
    }
}

// MARK: - Compose Multiplatform Integration

struct ComposeView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController {
        // MainViewController is generated by KMP from shared module
        return Main_iosKt.MainViewController()
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}

/// Compose view with Apple Sign-In integration (legacy, use ComposeViewWithAuthAndStore)
struct ComposeViewWithAuth: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController {
        NSLog("[ComposeViewWithAuth] makeUIViewController called - setting up Apple Sign-In callbacks")

        // Get the key window for presenting the Apple Sign-In sheet
        let scenes = UIApplication.shared.connectedScenes
        let windowScene = scenes.first as? UIWindowScene
        let keyWindow = windowScene?.windows.first { $0.isKeyWindow }

        NSLog("[ComposeViewWithAuth] keyWindow: \(String(describing: keyWindow))")

        let vc = Main_iosKt.MainViewControllerWithAuth(
            onAppleSignInRequested: { callback in
                NSLog("[ComposeViewWithAuth] onAppleSignInRequested LAMBDA INVOKED - about to call AppleSignInHelper.signIn")

                AppleSignInHelper.shared.signIn(presentingWindow: keyWindow) { result in
                    switch result {
                    case .success(let credential):
                        NSLog("[ComposeViewWithAuth] Apple Sign-In success")
                        let bridgeResult = AppleSignInResultBridge.companion.success(
                            idToken: credential.idToken,
                            userId: credential.userId,
                            email: credential.email,
                            displayName: credential.fullName
                        )
                        callback(bridgeResult)

                    case .failure(let error):
                        NSLog("[ComposeViewWithAuth] Apple Sign-In error: \(error.localizedDescription)")
                        if let appleError = error as? AppleSignInHelper.AppleSignInError,
                           appleError == .cancelled {
                            callback(AppleSignInResultBridge.companion.cancelled())
                        } else {
                            callback(AppleSignInResultBridge.companion.error(message: error.localizedDescription))
                        }
                    }
                }
            },
            onSilentSignInRequested: { callback in
                NSLog("[ComposeViewWithAuth] onSilentSignInRequested LAMBDA INVOKED")

                AppleSignInHelper.shared.silentSignIn { result in
                    switch result {
                    case .success(let credential):
                        NSLog("[ComposeViewWithAuth] Silent sign-in success")
                        let bridgeResult = AppleSignInResultBridge.companion.success(
                            idToken: credential.idToken,
                            userId: credential.userId,
                            email: credential.email,
                            displayName: credential.fullName
                        )
                        callback(bridgeResult)

                    case .failure(let error):
                        NSLog("[ComposeViewWithAuth] Silent sign-in not available: \(error.localizedDescription)")
                        // For silent sign-in failures, we return an error to indicate sign-in is required
                        callback(AppleSignInResultBridge.companion.error(message: "4: SIGN_IN_REQUIRED"))
                    }
                }
            }
        )

        NSLog("[ComposeViewWithAuth] MainViewControllerWithAuth returned VC: \(vc)")
        return vc
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {
        NSLog("[ComposeViewWithAuth] updateUIViewController called")
    }
}

/// Compose view with Apple Sign-In and StoreKit integration
struct ComposeViewWithAuthAndStore: UIViewControllerRepresentable {
    @ObservedObject var storeKitManager: StoreKitManager

    func makeUIViewController(context: Context) -> UIViewController {
        NSLog("[ComposeViewWithAuthAndStore] makeUIViewController called - setting up Apple Sign-In and StoreKit callbacks")

        // Start StoreKit manager
        storeKitManager.start()

        // Get the key window for presenting the Apple Sign-In sheet
        let scenes = UIApplication.shared.connectedScenes
        let windowScene = scenes.first as? UIWindowScene
        let keyWindow = windowScene?.windows.first { $0.isKeyWindow }

        NSLog("[ComposeViewWithAuthAndStore] keyWindow: \(String(describing: keyWindow))")

        let vc = Main_iosKt.MainViewControllerWithAuthAndStore(
            // Apple Sign-In callbacks
            onAppleSignInRequested: { callback in
                NSLog("[ComposeViewWithAuthAndStore] onAppleSignInRequested LAMBDA INVOKED")

                AppleSignInHelper.shared.signIn(presentingWindow: keyWindow) { result in
                    switch result {
                    case .success(let credential):
                        NSLog("[ComposeViewWithAuthAndStore] Apple Sign-In success")
                        let bridgeResult = AppleSignInResultBridge.companion.success(
                            idToken: credential.idToken,
                            userId: credential.userId,
                            email: credential.email,
                            displayName: credential.fullName
                        )
                        callback(bridgeResult)

                    case .failure(let error):
                        NSLog("[ComposeViewWithAuthAndStore] Apple Sign-In error: \(error.localizedDescription)")
                        if let appleError = error as? AppleSignInHelper.AppleSignInError,
                           appleError == .cancelled {
                            callback(AppleSignInResultBridge.companion.cancelled())
                        } else {
                            callback(AppleSignInResultBridge.companion.error(message: error.localizedDescription))
                        }
                    }
                }
            },
            onSilentSignInRequested: { callback in
                NSLog("[ComposeViewWithAuthAndStore] onSilentSignInRequested LAMBDA INVOKED")

                AppleSignInHelper.shared.silentSignIn { result in
                    switch result {
                    case .success(let credential):
                        NSLog("[ComposeViewWithAuthAndStore] Silent sign-in success")
                        let bridgeResult = AppleSignInResultBridge.companion.success(
                            idToken: credential.idToken,
                            userId: credential.userId,
                            email: credential.email,
                            displayName: credential.fullName
                        )
                        callback(bridgeResult)

                    case .failure(let error):
                        NSLog("[ComposeViewWithAuthAndStore] Silent sign-in not available: \(error.localizedDescription)")
                        callback(AppleSignInResultBridge.companion.error(message: "4: SIGN_IN_REQUIRED"))
                    }
                }
            },

            // StoreKit callbacks
            onLoadProducts: { callback in
                NSLog("[ComposeViewWithAuthAndStore] onLoadProducts LAMBDA INVOKED")

                Task { @MainActor in
                    // Ensure products are loaded
                    if self.storeKitManager.products.isEmpty {
                        await self.storeKitManager.loadProducts()
                    }

                    // Convert to bridge products
                    let bridgeProducts = self.storeKitManager.products.map { product in
                        StoreKitProductBridge.companion.create(
                            id: product.id,
                            displayName: product.displayName,
                            description: product.description,
                            displayPrice: product.displayPrice,
                            price: NSDecimalNumber(decimal: product.price).doubleValue
                        )
                    }

                    NSLog("[ComposeViewWithAuthAndStore] Returning \(bridgeProducts.count) products to Kotlin")
                    callback(bridgeProducts)
                }
            },
            onPurchase: { productId, appleIDToken, callback in
                NSLog("[ComposeViewWithAuthAndStore] onPurchase LAMBDA INVOKED for \(productId)")

                Task { @MainActor in
                    // Find the product
                    guard let product = self.storeKitManager.products.first(where: { $0.id == productId }) else {
                        NSLog("[ComposeViewWithAuthAndStore] Product not found: \(productId)")
                        callback(StoreKitPurchaseResultBridge.companion.failed(error: "Product not found"))
                        return
                    }

                    do {
                        let result = try await self.storeKitManager.purchase(product, appleIDToken: appleIDToken)

                        switch result {
                        case .success(let creditsAdded, let newBalance):
                            NSLog("[ComposeViewWithAuthAndStore] Purchase success: +\(creditsAdded) credits, balance: \(newBalance)")
                            callback(StoreKitPurchaseResultBridge.companion.success(
                                creditsAdded: Int32(creditsAdded),
                                newBalance: Int32(newBalance)
                            ))

                        case .cancelled:
                            NSLog("[ComposeViewWithAuthAndStore] Purchase cancelled")
                            callback(StoreKitPurchaseResultBridge.companion.cancelled())

                        case .pending:
                            NSLog("[ComposeViewWithAuthAndStore] Purchase pending")
                            callback(StoreKitPurchaseResultBridge.companion.pending())

                        case .failed(let error):
                            NSLog("[ComposeViewWithAuthAndStore] Purchase failed: \(error)")
                            callback(StoreKitPurchaseResultBridge.companion.failed(error: error))
                        }
                    } catch {
                        NSLog("[ComposeViewWithAuthAndStore] Purchase error: \(error)")
                        callback(StoreKitPurchaseResultBridge.companion.failed(error: error.localizedDescription))
                    }
                }
            },
            isStoreLoading: {
                // Kotlin expects KotlinBoolean, Swift Bool auto-bridges
                return KotlinBoolean(bool: self.storeKitManager.isLoading)
            },
            getStoreError: {
                return self.storeKitManager.errorMessage
            }
        )

        NSLog("[ComposeViewWithAuthAndStore] MainViewControllerWithAuthAndStore returned VC: \(vc)")
        return vc
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {
        NSLog("[ComposeViewWithAuthAndStore] updateUIViewController called")
    }
}

#Preview {
    ContentView()
}
