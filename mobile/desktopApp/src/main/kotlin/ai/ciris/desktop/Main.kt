package ai.ciris.desktop

import ai.ciris.desktop.testing.TestAutomationServer
import ai.ciris.mobile.shared.CIRISApp
import ai.ciris.mobile.shared.localization.LocalizationResourceLoader
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.createEnvFileUpdater
import ai.ciris.mobile.shared.platform.createPythonRuntime
import ai.ciris.mobile.shared.platform.createSecureStorage
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import androidx.compose.ui.res.painterResource
import java.awt.event.ComponentAdapter
import java.awt.event.ComponentEvent
import java.io.File

fun main() {
    // Set macOS application name (menu bar + dock)
    System.setProperty("apple.awt.application.name", "CIRIS Agent")

    // Robust crash guards — we have zero ANRs in prod on both app stores
    // and desktop should match. A single unhandled exception in a
    // coroutine / Compose callback / AWT event should NEVER wedge the UI
    // or kill the JVM silently.
    //
    // 1) JVM-wide fallback: anything that escapes every catch block
    //    ends up here. Log it; do not let the thread die quietly.
    Thread.setDefaultUncaughtExceptionHandler { thread, error ->
        System.err.println(
            "[DesktopCrashGuard] UNCAUGHT on ${thread.name}: ${error::class.qualifiedName}: ${error.message}"
        )
        error.printStackTrace(System.err)
    }
    // 2) AWT EDT-specific handler (Swing dispatches exceptions through
    //    sun.awt.exception.handler when set as a system property). If the
    //    EDT hits a fatal error we still want the app to keep running.
    System.setProperty(
        "sun.awt.exception.handler",
        "ai.ciris.desktop.AwtExceptionHandler"
    )

    // Set macOS Dock icon. painterResource("icon.png") on the Window
    // only controls the title-bar icon — the Dock, Cmd-Tab switcher,
    // and app-bundle representation need the JVM's AWT Taskbar API.
    // Without this, raw `java -jar …` launches show the default Java
    // coffee-cup icon in the Dock. Works on macOS Big Sur+.
    runCatching {
        val iconStream = object {}.javaClass.classLoader.getResourceAsStream("icon.png")
        if (iconStream != null) {
            val image = javax.imageio.ImageIO.read(iconStream)
            if (image != null && java.awt.Taskbar.isTaskbarSupported()) {
                val taskbar = java.awt.Taskbar.getTaskbar()
                if (taskbar.isSupported(java.awt.Taskbar.Feature.ICON_IMAGE)) {
                    taskbar.iconImage = image
                }
            }
        }
    }.onFailure { e ->
        println("[Desktop] Could not set Dock icon: ${e.message}")
    }

    // Initialize localization directory for development
    // Try to find the localization directory relative to the project root
    val localizationPaths = listOf(
        File("localization"),                                      // Current dir
        File("../localization"),                                   // Parent
        File("../../localization"),                                // Grandparent (from mobile)
        File("../../../localization"),                             // From mobile/desktopApp
        File(System.getProperty("user.dir"), "localization"),      // Working dir
        File(System.getProperty("user.home"), "CIRISAgent/localization"),  // Home
    )
    for (path in localizationPaths) {
        if (path.exists() && path.isDirectory) {
            println("[Desktop] Found localization directory: ${path.absolutePath}")
            LocalizationResourceLoader.init(path)
            break
        }
    }

    // Create the runtime early so we can shut it down on exit
    val pythonRuntime = createPythonRuntime()

    // Register JVM shutdown hook to kill server process if we launched one
    Runtime.getRuntime().addShutdownHook(Thread {
        pythonRuntime.shutdown()
    })

    application {
    val windowState = rememberWindowState(width = 1200.dp, height = 800.dp)

    // Start test automation server if enabled
    val testServer = if (TestAutomationServer.isTestModeEnabled()) {
        val port = System.getenv("CIRIS_TEST_PORT")?.toIntOrNull() ?: 9091
        println("[Desktop] Test mode enabled - starting automation server on port $port")
        val server = TestAutomationServer.getInstance(port)

        // Configure shared module TestAutomation to delegate to our server
        TestAutomation.configure(
            onRegister = { tag, x, y, w, h, text -> server.registerElement(tag, x, y, w, h, text) },
            onUnregister = { tag -> server.unregisterElement(tag) },
            onSetScreen = { screen -> server.currentScreen = screen },
            onClear = { server.clearElements() },
            isEnabled = { true }
        )

        server.also { it.start() }
    } else {
        null
    }

    Window(
        onCloseRequest = {
            // Quit immediately — do NOT block the UI thread waiting
            // for Ktor's grace period or the Python subprocess to
            // tear down. Shutdown work is already registered via the
            // JVM shutdown hook (see addShutdownHook above) and runs
            // on exit.
            //
            // BUT: exitApplication() alone isn't enough to kill the
            // JVM if there are stuck non-daemon threads (Ktor test
            // server accept loop, Python subprocess watchers, etc.).
            // The JVM would keep living invisibly. Force-exit on a
            // short watchdog so the app ALWAYS dies when the user
            // clicks the red close button.
            Thread {
                runCatching { testServer?.stop() }
            }.also { it.isDaemon = true }.start()
            exitApplication()
            Thread {
                try { Thread.sleep(1500) } catch (_: InterruptedException) {}
                // If we're still alive 1.5 s later, force-exit. This
                // runs the JVM shutdown hooks (pythonRuntime.shutdown)
                // on the way out, so the Python subprocess still gets
                // cleaned up correctly.
                System.exit(0)
            }.also { it.isDaemon = true }.start()
        },
        title = "CIRIS Agent",
        state = windowState,
        icon = painterResource("icon.png"),
    ) {
        var accessToken by remember { mutableStateOf("") }

        // Track window position for test automation (screen-absolute coordinates)
        LaunchedEffect(Unit) {
            testServer?.let { server ->
                // Get initial position and set AWT window ref for screenshots
                val frame = window
                server.updateWindowPosition(frame.x, frame.y)
                server.awtWindow = frame

                // Track position changes
                frame.addComponentListener(object : ComponentAdapter() {
                    override fun componentMoved(e: ComponentEvent) {
                        server.updateWindowPosition(frame.x, frame.y)
                    }
                })
            }
        }

        MaterialTheme {
            Surface(
                modifier = Modifier.fillMaxSize(),
                color = MaterialTheme.colorScheme.background
            ) {
                CIRISApp(
                    accessToken = accessToken,
                    baseUrl = System.getenv("CIRIS_API_URL") ?: "http://localhost:8080",
                    pythonRuntime = pythonRuntime,
                    secureStorage = createSecureStorage(),
                    envFileUpdater = createEnvFileUpdater(),
                    googleSignInCallback = null,  // Not supported on desktop
                    purchaseLauncher = null,  // Not supported on desktop
                    deviceAttestationCallback = null,  // Not supported on desktop
                    onTokenUpdated = { newToken ->
                        accessToken = newToken
                    }
                )
            }
        }
    }
}
}
