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
            testServer?.stop()
            pythonRuntime.shutdown()
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
