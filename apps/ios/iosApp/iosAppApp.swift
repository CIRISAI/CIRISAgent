import SwiftUI

@main
struct iosAppApp: App {
    init() {
        // Catch uncaught Kotlin/Native exceptions that bypass normal error handling.
        // These throw on dispatch queues and kill the process silently — no Python log,
        // no KMP log, no crash report. This handler writes them to a file before death.
        NSSetUncaughtExceptionHandler { exception in
            let msg = """
            === UNCAUGHT KOTLIN/NATIVE EXCEPTION ===
            Time: \(ISO8601DateFormatter().string(from: Date()))
            Name: \(exception.name.rawValue)
            Reason: \(exception.reason ?? "unknown")
            Stack:
            \(exception.callStackSymbols.joined(separator: "\n"))
            """
            NSLog("[CIRIS-CRASH] %@", msg)

            // Write to file so we can pull it after restart
            let logsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("ciris/logs")
            try? FileManager.default.createDirectory(at: logsDir, withIntermediateDirectories: true)
            let crashPath = logsDir.appendingPathComponent("native_crash.log")
            try? msg.write(to: crashPath, atomically: true, encoding: .utf8)
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
