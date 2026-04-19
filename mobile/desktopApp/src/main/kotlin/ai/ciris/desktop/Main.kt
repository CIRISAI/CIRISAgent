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
            // on exit. Blocking here for 3+ seconds is what made the
            // macOS red close button feel broken — users had to use
            // the File > Quit menu to get out.
            Thread {
                runCatching { testServer?.stop() }
            }.also { it.isDaemon = true }.start()
            exitApplication()
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
