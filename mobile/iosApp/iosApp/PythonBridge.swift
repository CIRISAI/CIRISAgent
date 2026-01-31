import Foundation
import Compression

/// Swift bridge for Python initialization and runtime management.
/// This provides a clean API that Kotlin/Native can call via cinterop.
@objc public class PythonBridge: NSObject {

    private static var isInitialized = false
    private static var runtimeThread: Thread?
    private static var serverPort: Int = 8080
    private static var extractedResourcesPath: String?

    /// Extract resources only (for async UI updates)
    /// Returns the path to extracted resources, or nil on failure
    @objc public static func extractResources() -> String? {
        return extractResourcesIfNeeded()
    }

    /// Initialize the Python interpreter with the app bundle paths
    @objc public static func initializePython() -> Bool {
        if isInitialized {
            NSLog("[PythonBridge] Python already initialized")
            return true
        }

        // First, ensure resources are extracted
        guard let resourcesPath = extractResourcesIfNeeded() else {
            NSLog("[PythonBridge] ERROR: Failed to extract resources")
            return false
        }

        // Set LANG environment variable (required for locale)
        let lang = "\(Locale.current.identifier).UTF-8"
        setenv("LANG", lang, 1)

        NSLog("[PythonBridge] Resources path: \(resourcesPath)")
        NSLog("[PythonBridge] LANG: \(lang)")

        // Initialize Python using C API
        let pythonHome = "\(resourcesPath)/python"
        let appPath = "\(resourcesPath)/app"
        let packagesPath = "\(resourcesPath)/app_packages"

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

        // Determine lib-dynload path
        // On device: use app bundle (code-signed)
        // On simulator: use extracted path (no code signing required)
        var libDynloadPath: String
        #if targetEnvironment(simulator)
        libDynloadPath = "\(pythonHome)/lib/python3.10/lib-dynload"
        NSLog("[PythonBridge] Simulator build - using extracted lib-dynload: \(libDynloadPath)")
        #else
        // On device, use the lib-dynload from the app bundle (code-signed)
        let bundleLibPath = Bundle.main.resourcePath.map { "\($0)/python_lib/lib-dynload" }
        if let bundlePath = bundleLibPath, fm.fileExists(atPath: bundlePath) {
            libDynloadPath = bundlePath
            NSLog("[PythonBridge] Device build - using app bundle lib-dynload: \(libDynloadPath)")
        } else {
            // Fallback to extracted path (will likely fail code signature check)
            libDynloadPath = "\(pythonHome)/lib/python3.10/lib-dynload"
            NSLog("[PythonBridge] WARNING: App bundle lib-dynload not found, falling back to extracted path")
            NSLog("[PythonBridge] This will fail on device due to code signature requirements!")
        }
        #endif

        // Initialize using our Objective-C bridge (which calls Python C API)
        let success = PythonInit.initialize(
            withPythonHome: pythonHome,
            appPath: appPath,
            packagesPath: packagesPath,
            libDynloadPath: libDynloadPath
        )

        if success {
            isInitialized = true
            NSLog("[PythonBridge] Python initialized successfully")
        } else {
            NSLog("[PythonBridge] ERROR: Failed to initialize Python")
        }

        return success
    }

    /// Extract Resources.zip if not already extracted or if version changed
    private static func extractResourcesIfNeeded() -> String? {
        let fm = FileManager.default
        let startTime = CFAbsoluteTimeGetCurrent()

        NSLog("[PythonBridge] extractResourcesIfNeeded() called")

        // Get the Documents directory for extraction
        guard let documentsPath = fm.urls(for: .documentDirectory, in: .userDomainMask).first?.path else {
            NSLog("[PythonBridge] ERROR: Could not get Documents directory")
            return nil
        }
        NSLog("[PythonBridge] Documents path: \(documentsPath)")

        let extractedPath = "\(documentsPath)/PythonResources"

        // Check if already extracted
        let pythonLibPath = "\(extractedPath)/python/lib"
        let kmpMainPath = "\(extractedPath)/app/ciris_ios/kmp_main.py"
        let versionMarkerPath = "\(extractedPath)/.extraction_version"

        // Get current bundle version to track if we need to re-extract
        let currentVersion = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"
        let currentBuild = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let versionString = "\(currentBuild)-\(currentVersion)"

        // Check for .fwork files as an indicator of new-style extraction
        // Old extractions have .so files, new ones have .fwork files
        let pydanticFworkPath = "\(extractedPath)/app_packages/pydantic_core/_pydantic_core.cpython-310-iphoneos.fwork"
        let pydanticSoPath = "\(extractedPath)/app_packages/pydantic_core/_pydantic_core.cpython-310-iphoneos.so"

        var needsReextract = false

        if fm.fileExists(atPath: pythonLibPath) && fm.fileExists(atPath: kmpMainPath) {
            // Check if this is an old-style extraction (has .so files instead of .fwork)
            if fm.fileExists(atPath: pydanticSoPath) && !fm.fileExists(atPath: pydanticFworkPath) {
                NSLog("[PythonBridge] Old-style extraction detected (.so files instead of .fwork)")
                NSLog("[PythonBridge] Will re-extract to get .fwork files for code signing")
                needsReextract = true
            } else if let existingVersion = try? String(contentsOfFile: versionMarkerPath, encoding: .utf8),
                      existingVersion.trimmingCharacters(in: .whitespacesAndNewlines) == versionString {
                NSLog("[PythonBridge] Resources already extracted at \(extractedPath)")
                NSLog("[PythonBridge] - python/lib exists: YES")
                NSLog("[PythonBridge] - kmp_main.py exists: YES")
                NSLog("[PythonBridge] - Version matches: \(versionString)")
                extractedResourcesPath = extractedPath
                return extractedPath
            } else {
                NSLog("[PythonBridge] Version mismatch or marker missing, will re-extract")
                needsReextract = true
            }
        } else {
            NSLog("[PythonBridge] Need to extract resources:")
            NSLog("[PythonBridge] - python/lib exists: \(fm.fileExists(atPath: pythonLibPath))")
            NSLog("[PythonBridge] - kmp_main.py exists: \(fm.fileExists(atPath: kmpMainPath))")
            needsReextract = true
        }

        guard needsReextract else {
            extractedResourcesPath = extractedPath
            return extractedPath
        }

        // Clear old status files before extraction
        if let cirisDir = fm.urls(for: .documentDirectory, in: .userDomainMask).first?.appendingPathComponent("ciris") {
            try? fm.removeItem(at: cirisDir.appendingPathComponent("extraction_status.json"))
            try? fm.removeItem(at: cirisDir.appendingPathComponent("startup_status.json"))
        }

        // Write initial extraction status
        writeExtractionStatus(ExtractionStatus(phase: "extracting", filesExtracted: 0, totalFiles: nil, currentFile: "Starting..."))

        // Find Resources.zip in bundle
        guard let zipPath = Bundle.main.path(forResource: "Resources", ofType: "zip") else {
            NSLog("[PythonBridge] ERROR: Resources.zip not found in bundle")
            return nil
        }

        // Get zip file size
        if let attrs = try? fm.attributesOfItem(atPath: zipPath),
           let fileSize = attrs[.size] as? Int64 {
            NSLog("[PythonBridge] Resources.zip size: \(fileSize / 1024 / 1024) MB")
        }

        NSLog("[PythonBridge] Extracting Resources.zip from \(zipPath)...")
        NSLog("[PythonBridge] This may take 30-60 seconds on first launch...")

        // Clean up any partial extraction
        try? fm.removeItem(atPath: extractedPath)

        // Create extraction directory
        do {
            try fm.createDirectory(atPath: extractedPath, withIntermediateDirectories: true)
        } catch {
            NSLog("[PythonBridge] ERROR: Failed to create directory: \(error)")
            return nil
        }

        // Extract directly to PythonResources (zip contains app/, python/, app_packages/ at top level)
        let zipURL = URL(fileURLWithPath: zipPath)
        let destinationURL = URL(fileURLWithPath: extractedPath)

        do {
            try ZipExtractor.extract(zipURL: zipURL, to: destinationURL)
            let elapsed = CFAbsoluteTimeGetCurrent() - startTime
            NSLog("[PythonBridge] Resources extracted successfully in \(String(format: "%.1f", elapsed)) seconds")
            extractedResourcesPath = extractedPath

            // Write version marker
            try? versionString.write(toFile: versionMarkerPath, atomically: true, encoding: .utf8)
            NSLog("[PythonBridge] Wrote version marker: \(versionString)")

            // Verify kmp_main.py exists
            if fm.fileExists(atPath: kmpMainPath) {
                NSLog("[PythonBridge] Verified: kmp_main.py exists at \(kmpMainPath)")
            } else {
                NSLog("[PythonBridge] WARNING: kmp_main.py NOT found at \(kmpMainPath)")
                // List what's in ciris_ios directory
                if let contents = try? fm.contentsOfDirectory(atPath: "\(extractedPath)/app/ciris_ios") {
                    NSLog("[PythonBridge] Contents of ciris_ios: \(contents)")
                }
            }

            // Verify .fwork files exist (for device builds)
            if fm.fileExists(atPath: pydanticFworkPath) {
                NSLog("[PythonBridge] Verified: pydantic_core .fwork file exists")
            } else if fm.fileExists(atPath: pydanticSoPath) {
                NSLog("[PythonBridge] WARNING: pydantic_core has .so file instead of .fwork - native extensions may fail on device")
            }

            return extractedPath
        } catch {
            NSLog("[PythonBridge] ERROR: Failed to extract zip: \(error)")
            return nil
        }
    }

    /// Start the CIRIS runtime in a background thread
    @objc public static func startRuntime() -> Bool {
        NSLog("[PythonBridge] startRuntime() called")

        guard isInitialized else {
            NSLog("[PythonBridge] ERROR: Python not initialized")
            return false
        }

        if runtimeThread != nil {
            NSLog("[PythonBridge] Runtime already started")
            return true
        }

        NSLog("[PythonBridge] Starting CIRIS runtime in background thread...")
        NSLog("[PythonBridge] Module to run: ciris_ios.kmp_main")

        runtimeThread = Thread {
            NSLog("[PythonBridge] [Thread] CIRIS Runtime thread started")
            NSLog("[PythonBridge] [Thread] Calling PythonInit.runModule('ciris_ios.kmp_main')...")
            // Run KMP-specific entry point that bypasses Toga
            PythonInit.runModule("ciris_ios.kmp_main")
            NSLog("[PythonBridge] [Thread] PythonInit.runModule() returned")
        }
        runtimeThread?.name = "CIRISRuntime"
        runtimeThread?.start()

        NSLog("[PythonBridge] Background thread started, returning true")
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
        isInitialized = false
        runtimeThread = nil
    }
}

/// Extraction status for UI display
struct ExtractionStatus: Codable {
    var phase: String  // "extracting", "complete", "error"
    var filesExtracted: Int
    var totalFiles: Int?
    var currentFile: String?
    var error: String?
}

/// Write extraction status to file for UI to read
func writeExtractionStatus(_ status: ExtractionStatus) {
    let fm = FileManager.default
    guard let documentsURL = fm.urls(for: .documentDirectory, in: .userDomainMask).first else { return }

    let cirisDir = documentsURL.appendingPathComponent("ciris")
    try? fm.createDirectory(at: cirisDir, withIntermediateDirectories: true)

    let statusFile = cirisDir.appendingPathComponent("extraction_status.json")
    if let data = try? JSONEncoder().encode(status) {
        try? data.write(to: statusFile)
    }
}

/// Native Swift ZIP extractor using Compression framework
class ZipExtractor {

    enum ZipError: Error {
        case invalidZipFile
        case unsupportedCompression(Int)
        case decompressionFailed
        case fileCreationFailed(String)
    }

    /// Extract a ZIP file to destination directory
    static func extract(zipURL: URL, to destinationURL: URL) throws {
        let fm = FileManager.default
        let data = try Data(contentsOf: zipURL)

        var offset = 0
        var extractedCount = 0

        while offset < data.count - 4 {
            // Look for local file header signature (0x04034b50)
            let signature = data.subdata(in: offset..<offset+4).withUnsafeBytes { $0.load(as: UInt32.self) }

            if signature != 0x04034b50 {
                // Not a local file header, might be central directory
                break
            }

            // Parse local file header
            let compressionMethod = data.subdata(in: offset+8..<offset+10).withUnsafeBytes { $0.load(as: UInt16.self) }
            let compressedSize = data.subdata(in: offset+18..<offset+22).withUnsafeBytes { $0.load(as: UInt32.self) }
            let uncompressedSize = data.subdata(in: offset+22..<offset+26).withUnsafeBytes { $0.load(as: UInt32.self) }
            let fileNameLength = data.subdata(in: offset+26..<offset+28).withUnsafeBytes { $0.load(as: UInt16.self) }
            let extraFieldLength = data.subdata(in: offset+28..<offset+30).withUnsafeBytes { $0.load(as: UInt16.self) }

            // Extract filename
            let fileNameStart = offset + 30
            let fileNameEnd = fileNameStart + Int(fileNameLength)
            guard fileNameEnd <= data.count else { throw ZipError.invalidZipFile }

            let fileNameData = data.subdata(in: fileNameStart..<fileNameEnd)
            guard let fileName = String(data: fileNameData, encoding: .utf8) else {
                throw ZipError.invalidZipFile
            }

            // Calculate data offset
            let dataStart = fileNameEnd + Int(extraFieldLength)
            let dataEnd = dataStart + Int(compressedSize)
            guard dataEnd <= data.count else { throw ZipError.invalidZipFile }

            let filePath = destinationURL.appendingPathComponent(fileName).path

            // Check if this is a directory
            if fileName.hasSuffix("/") {
                try fm.createDirectory(atPath: filePath, withIntermediateDirectories: true)
            } else {
                // Ensure parent directory exists
                let parentPath = (filePath as NSString).deletingLastPathComponent
                if !fm.fileExists(atPath: parentPath) {
                    try fm.createDirectory(atPath: parentPath, withIntermediateDirectories: true)
                }

                // Extract file data
                let compressedData = data.subdata(in: dataStart..<dataEnd)

                let fileData: Data
                if compressionMethod == 0 {
                    // Stored (no compression)
                    fileData = compressedData
                } else if compressionMethod == 8 {
                    // Deflate compression
                    fileData = try decompress(compressedData, expectedSize: Int(uncompressedSize))
                } else {
                    throw ZipError.unsupportedCompression(Int(compressionMethod))
                }

                // Write file
                if !fm.createFile(atPath: filePath, contents: fileData) {
                    throw ZipError.fileCreationFailed(filePath)
                }
            }

            extractedCount += 1

            // Log and write progress every 100 files
            if extractedCount % 100 == 0 {
                NSLog("[ZipExtractor] Progress: \(extractedCount) files extracted...")
                writeExtractionStatus(ExtractionStatus(
                    phase: "extracting",
                    filesExtracted: extractedCount,
                    totalFiles: nil,
                    currentFile: fileName.components(separatedBy: "/").last
                ))
            }

            // Move to next entry
            offset = dataEnd
        }

        NSLog("[ZipExtractor] Extraction complete: \(extractedCount) total files")
        writeExtractionStatus(ExtractionStatus(
            phase: "complete",
            filesExtracted: extractedCount,
            totalFiles: extractedCount
        ))
    }

    /// Decompress deflate-compressed data
    private static func decompress(_ compressedData: Data, expectedSize: Int) throws -> Data {
        // Use Compression framework for deflate decompression
        // Note: ZIP uses raw deflate (no zlib header), so we use COMPRESSION_ZLIB with skip

        let destinationBuffer = UnsafeMutablePointer<UInt8>.allocate(capacity: expectedSize)
        defer { destinationBuffer.deallocate() }

        let decompressedSize = compressedData.withUnsafeBytes { sourcePtr -> Int in
            guard let baseAddress = sourcePtr.baseAddress else { return 0 }

            // Try raw deflate first
            let result = compression_decode_buffer(
                destinationBuffer, expectedSize,
                baseAddress.assumingMemoryBound(to: UInt8.self), compressedData.count,
                nil,
                COMPRESSION_ZLIB
            )
            return result
        }

        if decompressedSize == 0 || decompressedSize != expectedSize {
            throw ZipError.decompressionFailed
        }

        return Data(bytes: destinationBuffer, count: decompressedSize)
    }
}
