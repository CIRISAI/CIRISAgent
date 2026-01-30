import Foundation
import Compression

/// Swift bridge for Python initialization and runtime management.
/// This provides a clean API that Kotlin/Native can call via cinterop.
@objc public class PythonBridge: NSObject {

    private static var isInitialized = false
    private static var runtimeThread: Thread?
    private static var serverPort: Int = 8080
    private static var extractedResourcesPath: String?

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

    /// Extract Resources.zip if not already extracted
    private static func extractResourcesIfNeeded() -> String? {
        let fm = FileManager.default

        // Get the Documents directory for extraction
        guard let documentsPath = fm.urls(for: .documentDirectory, in: .userDomainMask).first?.path else {
            NSLog("[PythonBridge] ERROR: Could not get Documents directory")
            return nil
        }

        let extractedPath = "\(documentsPath)/PythonResources"

        // Check if already extracted
        if fm.fileExists(atPath: "\(extractedPath)/python/lib") {
            NSLog("[PythonBridge] Resources already extracted at \(extractedPath)")
            extractedResourcesPath = extractedPath
            return extractedPath
        }

        // Find Resources.zip in bundle
        guard let zipPath = Bundle.main.path(forResource: "Resources", ofType: "zip") else {
            NSLog("[PythonBridge] ERROR: Resources.zip not found in bundle")
            return nil
        }

        NSLog("[PythonBridge] Extracting Resources.zip from \(zipPath)...")

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
            NSLog("[PythonBridge] Resources extracted successfully")
            extractedResourcesPath = extractedPath
            return extractedPath
        } catch {
            NSLog("[PythonBridge] ERROR: Failed to extract zip: \(error)")
            return nil
        }
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
            // Run KMP-specific entry point that bypasses Toga
            PythonInit.runModule("ciris_ios.kmp_main")
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
        isInitialized = false
        runtimeThread = nil
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

            // Log progress every 500 files
            if extractedCount % 500 == 0 {
                NSLog("[ZipExtractor] Extracted \(extractedCount) files...")
            }

            // Move to next entry
            offset = dataEnd
        }

        NSLog("[ZipExtractor] Extraction complete: \(extractedCount) files")
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
