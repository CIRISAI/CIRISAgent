import SwiftUI
import shared

struct ContentView: View {
    @State private var pythonReady = false
    @State private var initError: String? = nil
    @State private var failedSteps: [StartupStep] = []
    @State private var isReconnecting = false
    @State private var reconnectFailed = false
    @State private var reconnectAttempts = 0
    @StateObject private var storeKitManager = StoreKitManager.shared
    @Environment(\.scenePhase) var scenePhase

    var body: some View {
        ZStack {
            if pythonReady {
                // Show the Compose UI with Apple Sign-In and StoreKit support once Python is ready
                ComposeViewWithAuthAndStore(storeKitManager: storeKitManager)
                    .ignoresSafeArea()

                // Overlay while reconnecting or if reconnect failed
                if isReconnecting {
                    ReconnectingOverlay()
                } else if reconnectFailed {
                    RestartRequiredOverlay(
                        retryCount: reconnectAttempts,
                        onRetry: {
                            Task {
                                await checkAndRestartServerIfNeeded()
                            }
                        },
                        onExit: {
                            // Use KMP AppRestarter to terminate app
                            AppRestarter.shared.restartApp()
                        }
                    )
                }
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
        .onChange(of: scenePhase) { newPhase in
            if newPhase == .active && pythonReady {
                // App came to foreground - check if server is still alive
                NSLog("[ContentView] App became active, checking server health...")
                Task {
                    await checkAndRestartServerIfNeeded()
                }
            }
        }
    }

    /// Check if server is alive after app resume and restart if needed
    private func checkAndRestartServerIfNeeded() async {
        // Give iOS a moment to resume all threads before we start checking
        try? await Task.sleep(nanoseconds: 500_000_000)  // 0.5 seconds

        // Quick initial check
        let serverAlive = await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let alive = PythonBridge.checkHealth()
                continuation.resume(returning: alive)
            }
        }

        if serverAlive {
            NSLog("[ContentView] Server is healthy after resume")
            await MainActor.run {
                isReconnecting = false
                reconnectFailed = false
                reconnectAttempts = 0  // Reset on success
            }
            return
        }

        NSLog("[ContentView] Server not responding after resume, waiting for recovery...")

        await MainActor.run {
            isReconnecting = true
            reconnectFailed = false
        }

        // Wait for the server to resume - this calls ensureServerRunning which waits up to 30s
        let success = await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let result = PythonBridge.ensureServerRunning()
                continuation.resume(returning: result)
            }
        }

        await MainActor.run {
            isReconnecting = false
            if success {
                NSLog("[ContentView] Server recovered successfully - refreshing UI")
                reconnectFailed = false
                reconnectAttempts = 0  // Reset on success

                // Force Compose UI to refresh by recreating the view
                // This clears any stale error state in the Kotlin side
                pythonReady = false
            } else {
                reconnectAttempts += 1
                NSLog("[ContentView] Server did not recover (attempt \(reconnectAttempts))")
                reconnectFailed = true
            }
        }

        // If recovery succeeded, re-enable the UI after a brief moment
        if success {
            try? await Task.sleep(nanoseconds: 100_000_000)  // 0.1 seconds
            await MainActor.run {
                pythonReady = true
                NSLog("[ContentView] UI refreshed")
            }
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

/// Runtime status from Python's runtime_status.json
struct RuntimeStatus: Codable {
    var phase: String
    var status: String
    var timestamp: Double?
    var error: String?
    var port: Int?
    var restart_count: Int?

    var phaseEmoji: String {
        switch phase {
        case "EARLY_INIT": return "🔄"
        case "COMPAT_SHIMS": return "🔧"
        case "IOS_MAIN_IMPORT": return "📦"
        case "STARTUP": return "🚀"
        case "ENVIRONMENT": return "🌍"
        case "STARTUP_CHECKS": return "✅"
        case "RUNTIME_INIT": return "⚙️"
        case "SERVICE_INIT": return "🔌"
        case "RUNNING": return "💚"
        case "RESTARTING": return "🔁"
        case "ERROR": return "❌"
        case "STOPPED": return "⏹️"
        default: return "❓"
        }
    }
}

// ExtractionStatus is defined in PythonBridge.swift

// MARK: - Initializing View

struct InitializingView: View {
    let onInitialize: () async -> Void

    @State private var startupStatus: StartupStatus? = nil
    @State private var extractionStatus: ExtractionStatus? = nil
    @State private var runtimeStatus: RuntimeStatus? = nil
    @State private var statusTimer: Timer? = nil
    @State private var hasStartedInit = false
    @State private var showDebugLog = false

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

                    // Runtime status from Python (debug info)
                    if let rs = runtimeStatus {
                        VStack(spacing: 4) {
                            HStack {
                                Text(rs.phaseEmoji)
                                Text(rs.phase)
                                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                                Text("→")
                                    .foregroundColor(.gray)
                                Text(rs.status)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(rs.status == "failed" ? .red : .gray)
                            }

                            if let error = rs.error {
                                Text(error)
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundColor(.red)
                                    .lineLimit(2)
                                    .padding(.horizontal, 16)
                            }
                        }
                        .padding(.top, 12)
                    }

                    // Debug log button
                    Button(action: { showDebugLog = true }) {
                        HStack {
                            Image(systemName: "doc.text.magnifyingglass")
                            Text("View Logs")
                        }
                        .font(.system(size: 12))
                        .foregroundColor(.gray.opacity(0.6))
                    }
                    .padding(.top, 16)
                }
            }
            .padding(.vertical, 40)
        }
        .sheet(isPresented: $showDebugLog) {
            DebugLogView()
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

        // Load runtime status from Python
        let runtimeFile = cirisDir.appendingPathComponent("runtime_status.json")
        if fileManager.fileExists(atPath: runtimeFile.path),
           let data = try? Data(contentsOf: runtimeFile),
           let status = try? JSONDecoder().decode(RuntimeStatus.self, from: data) {
            DispatchQueue.main.async {
                self.runtimeStatus = status
            }
        }
    }
}

// MARK: - Debug Log View

struct DebugLogView: View {
    @Environment(\.dismiss) var dismiss
    @State private var logContent: String = "Loading..."
    @State private var selectedLog: String = "runtime"
    @State private var autoRefresh = true
    @State private var refreshTimer: Timer?

    let logTypes = ["runtime", "errors", "swift"]
    let cirisColor = Color(red: 0.255, green: 0.612, blue: 0.627)

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Log type picker
                Picker("Log Type", selection: $selectedLog) {
                    Text("Runtime").tag("runtime")
                    Text("Errors").tag("errors")
                    Text("Swift").tag("swift")
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding()
                .onChange(of: selectedLog) { _ in
                    loadLog()
                }

                // Log content
                ScrollView {
                    ScrollViewReader { proxy in
                        Text(logContent)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                            .id("logBottom")
                    }
                }
                .background(Color.black)

                // Auto-refresh toggle
                HStack {
                    Toggle("Auto-refresh", isOn: $autoRefresh)
                        .font(.system(size: 12))
                        .foregroundColor(.gray)

                    Spacer()

                    Button("Refresh") {
                        loadLog()
                    }
                    .font(.system(size: 12))
                    .foregroundColor(cirisColor)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color(red: 0.12, green: 0.12, blue: 0.18))
            }
            .background(Color(red: 0.1, green: 0.1, blue: 0.18))
            .navigationTitle("Debug Logs")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .onAppear {
            loadLog()
            startAutoRefresh()
        }
        .onDisappear {
            refreshTimer?.invalidate()
        }
        .onChange(of: autoRefresh) { enabled in
            if enabled {
                startAutoRefresh()
            } else {
                refreshTimer?.invalidate()
            }
        }
    }

    private func startAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            if autoRefresh {
                loadLog()
            }
        }
    }

    private func loadLog() {
        let fileManager = FileManager.default
        guard let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            logContent = "Could not access documents directory"
            return
        }

        let logsDir = documentsURL.appendingPathComponent("ciris/logs")

        let logFile: URL
        switch selectedLog {
        case "errors":
            logFile = logsDir.appendingPathComponent("kmp_errors.log")
        case "swift":
            logFile = logsDir.appendingPathComponent("swift_bridge.log")
        default:
            logFile = logsDir.appendingPathComponent("kmp_runtime.log")
        }

        if !fileManager.fileExists(atPath: logFile.path) {
            // Try python_error.log as fallback
            let errorLog = documentsURL.appendingPathComponent("python_error.log")
            if fileManager.fileExists(atPath: errorLog.path),
               let content = try? String(contentsOf: errorLog, encoding: .utf8) {
                logContent = "=== Python Error Log ===\n\n" + content
                return
            }

            logContent = "No log file found at:\n\(logFile.path)\n\nLog directory contents:\n"

            if fileManager.fileExists(atPath: logsDir.path),
               let files = try? fileManager.contentsOfDirectory(atPath: logsDir.path) {
                logContent += files.joined(separator: "\n")
            } else {
                logContent += "(logs directory does not exist)"

                // Show ciris directory contents instead
                let cirisDir = documentsURL.appendingPathComponent("ciris")
                if let files = try? fileManager.contentsOfDirectory(atPath: cirisDir.path) {
                    logContent += "\n\nciris/ directory:\n" + files.joined(separator: "\n")
                }
            }
            return
        }

        do {
            let content = try String(contentsOf: logFile, encoding: .utf8)
            // Get last 200 lines
            let lines = content.components(separatedBy: .newlines)
            let lastLines = lines.suffix(200)
            logContent = lastLines.joined(separator: "\n")
        } catch {
            logContent = "Error reading log: \(error.localizedDescription)"
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

// MARK: - Reconnecting Overlay

struct ReconnectingOverlay: View {
    let cirisColor = Color(red: 0.255, green: 0.612, blue: 0.627)
    @State private var dots = ""
    @State private var timer: Timer?

    var body: some View {
        ZStack {
            // Semi-transparent background
            Color.black.opacity(0.7)
                .ignoresSafeArea()

            VStack(spacing: 16) {
                ProgressView()
                    .progressViewStyle(CircularProgressViewStyle(tint: cirisColor))
                    .scaleEffect(1.5)

                Text("Resuming\(dots)")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.white)
                    .frame(width: 150)

                Text("Please wait...")
                    .font(.system(size: 14))
                    .foregroundColor(.gray)
            }
            .padding(32)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color(red: 0.12, green: 0.12, blue: 0.18))
            )
        }
        .onAppear {
            // Animate dots
            timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
                if dots.count >= 3 {
                    dots = ""
                } else {
                    dots += "."
                }
            }
        }
        .onDisappear {
            timer?.invalidate()
        }
    }
}

// MARK: - Restart Required Overlay

struct RestartRequiredOverlay: View {
    let cirisColor = Color(red: 0.255, green: 0.612, blue: 0.627)
    let retryCount: Int
    let onRetry: () -> Void
    let onExit: () -> Void

    var body: some View {
        ZStack {
            // Semi-transparent background
            Color.black.opacity(0.85)
                .ignoresSafeArea()

            VStack(spacing: 20) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 48))
                    .foregroundColor(.orange)

                Text("Connection Lost")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.white)

                Text("The server stopped while the app was sleeping.")
                    .font(.system(size: 14))
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)

                // Show both buttons - user can choose
                HStack(spacing: 16) {
                    Button(action: onRetry) {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Try Again")
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(cirisColor)
                        .cornerRadius(8)
                    }

                    Button(action: onExit) {
                        HStack {
                            Image(systemName: "arrow.uturn.left")
                            Text("Restart App")
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(Color.orange)
                        .cornerRadius(8)
                    }
                }
                .padding(.top, 8)

                if retryCount > 0 {
                    Text("Retry attempts: \(retryCount)")
                        .font(.system(size: 11))
                        .foregroundColor(.gray.opacity(0.6))
                }
            }
            .padding(32)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color(red: 0.12, green: 0.12, blue: 0.18))
            )
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
