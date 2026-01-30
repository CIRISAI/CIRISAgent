import Foundation

/// Swift bridge for Python initialization and runtime management.
/// This provides a clean API that Kotlin/Native can call via cinterop.
@objc public class PythonBridge: NSObject {

    private static var isInitialized = false
    private static var runtimeThread: Thread?
    private static var serverPort: Int = 8080

    /// Initialize the Python interpreter with the app bundle paths
    @objc public static func initializePython() -> Bool {
        if isInitialized {
            NSLog("[PythonBridge] Python already initialized")
            return true
        }

        guard let resourcePath = Bundle.main.resourcePath else {
            NSLog("[PythonBridge] ERROR: Could not get resource path")
            return false
        }

        // Set LANG environment variable (required for locale)
        let lang = "\(Locale.current.identifier).UTF-8"
        setenv("LANG", lang, 1)

        NSLog("[PythonBridge] Resource path: \(resourcePath)")
        NSLog("[PythonBridge] LANG: \(lang)")

        // Initialize Python using C API
        let pythonHome = "\(resourcePath)/Resources/python"
        let appPath = "\(resourcePath)/Resources/app"
        let packagesPath = "\(resourcePath)/Resources/app_packages"

        // Verify paths exist
        let fm = FileManager.default
        guard fm.fileExists(atPath: "\(pythonHome)/lib") else {
            NSLog("[PythonBridge] ERROR: Python stdlib not found at \(pythonHome)/lib")
            return false
        }

        guard fm.fileExists(atPath: appPath) else {
            NSLog("[PythonBridge] ERROR: App code not found at \(appPath)")
            return false
        }

        NSLog("[PythonBridge] Python home: \(pythonHome)")
        NSLog("[PythonBridge] App path: \(appPath)")
        NSLog("[PythonBridge] Packages path: \(packagesPath)")

        // Initialize using our Objective-C bridge (which calls Python C API)
        let success = PythonInit.initialize(
            withPythonHome: pythonHome,
            appPath: appPath,
            packagesPath: packagesPath
        )

        if success {
            isInitialized = true
            NSLog("[PythonBridge] Python initialized successfully")
        } else {
            NSLog("[PythonBridge] ERROR: Failed to initialize Python")
        }

        return success
    }

    /// Start the CIRIS runtime in a background thread
    @objc public static func startRuntime() -> Bool {
        guard isInitialized else {
            NSLog("[PythonBridge] ERROR: Python not initialized")
            return false
        }

        if runtimeThread != nil {
            NSLog("[PythonBridge] Runtime already started")
            return true
        }

        NSLog("[PythonBridge] Starting CIRIS runtime...")

        runtimeThread = Thread {
            PythonInit.runModule("ciris_ios")
        }
        runtimeThread?.name = "CIRISRuntime"
        runtimeThread?.start()

        return true
    }

    /// Check if Python is initialized
    @objc public static func isPythonInitialized() -> Bool {
        return isInitialized
    }

    /// Check if the runtime is running
    @objc public static func isRuntimeRunning() -> Bool {
        return runtimeThread?.isExecuting ?? false
    }

    /// Get the server port
    @objc public static func getServerPort() -> Int {
        return serverPort
    }

    /// Check server health
    @objc public static func checkHealth() -> Bool {
        let url = URL(string: "http://localhost:\(serverPort)/v1/system/health")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 2.0

        let semaphore = DispatchSemaphore(value: 0)
        var isHealthy = false

        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            if let httpResponse = response as? HTTPURLResponse {
                isHealthy = httpResponse.statusCode == 200
            }
            semaphore.signal()
        }
        task.resume()
        _ = semaphore.wait(timeout: .now() + 3.0)

        return isHealthy
    }

    /// Shutdown the Python runtime
    @objc public static func shutdown() {
        NSLog("[PythonBridge] Shutting down Python runtime...")
        // Note: Python finalization should be handled carefully
        // to avoid crashes. For now, we just mark as not initialized.
        isInitialized = false
        runtimeThread = nil
    }
}
