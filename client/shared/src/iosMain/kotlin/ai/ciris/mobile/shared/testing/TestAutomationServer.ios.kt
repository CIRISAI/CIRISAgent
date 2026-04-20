@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.testing

import kotlinx.cinterop.*
import kotlinx.coroutines.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import platform.Foundation.NSLog
import platform.posix.*

// Network byte order conversion (big-endian)
private fun htons(value: UShort): UShort {
    return (((value.toInt() and 0xFF) shl 8) or ((value.toInt() shr 8) and 0xFF)).toUShort()
}
private fun htonl(value: UInt): UInt {
    return ((value and 0xFFu) shl 24) or
        ((value and 0xFF00u) shl 8) or
        ((value shr 8) and 0xFF00u) or
        ((value shr 24) and 0xFFu)
}

/**
 * Minimal HTTP server for iOS using POSIX sockets.
 * Provides the same test automation endpoints as the desktop Ktor server.
 * Only starts when CIRIS_TEST_MODE=true.
 */
class IOSTestAutomationServer(private val port: Int = 9091) {

    private var serverSocket: Int = -1
    private var running = false
    private var scope: CoroutineScope? = null

    private val json = Json {
        prettyPrint = true
        isLenient = true
        ignoreUnknownKeys = true
    }

    fun start() {
        if (running) return
        running = true
        scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

        scope?.launch {
            try {
                startServer()
            } catch (e: Exception) {
                NSLog("[TestAutomation.ios] Server error: ${e.message}")
            }
        }
    }

    fun stop() {
        running = false
        if (serverSocket >= 0) {
            close(serverSocket)
            serverSocket = -1
        }
        scope?.cancel()
        scope = null
        NSLog("[TestAutomation.ios] Server stopped")
    }

    private suspend fun startServer() {
        serverSocket = socket(AF_INET, SOCK_STREAM, 0)
        if (serverSocket < 0) {
            NSLog("[TestAutomation.ios] Failed to create socket")
            return
        }

        // Allow port reuse
        memScoped {
            val optval = alloc<IntVar>()
            optval.value = 1
            setsockopt(serverSocket, SOL_SOCKET, SO_REUSEADDR, optval.ptr, sizeOf<IntVar>().toUInt())
        }

        // Bind
        memScoped {
            val addr = alloc<sockaddr_in>()
            addr.sin_family = AF_INET.toUByte()
            addr.sin_port = htons(port.toUShort())
            addr.sin_addr.s_addr = htonl(INADDR_ANY.toUInt())

            if (bind(serverSocket, addr.ptr.reinterpret(), sizeOf<sockaddr_in>().toUInt()) < 0) {
                NSLog("[TestAutomation.ios] Failed to bind to port $port")
                close(serverSocket)
                return
            }
        }

        if (listen(serverSocket, 5) < 0) {
            NSLog("[TestAutomation.ios] Failed to listen")
            close(serverSocket)
            return
        }

        NSLog("[TestAutomation.ios] Server started on http://localhost:$port")

        while (running) {
            val clientSocket = accept(serverSocket, null, null)
            if (clientSocket < 0) {
                if (running) delay(100)
                continue
            }

            // Handle each connection in a coroutine
            scope?.launch {
                try {
                    handleConnection(clientSocket)
                } catch (e: Exception) {
                    NSLog("[TestAutomation.ios] Connection error: ${e.message}")
                } finally {
                    close(clientSocket)
                }
            }
        }
    }

    private suspend fun handleConnection(clientSocket: Int) {
        // Read request
        val buffer = ByteArray(8192)
        val bytesRead = memScoped {
            buffer.usePinned { pinned ->
                recv(clientSocket, pinned.addressOf(0), buffer.size.toULong(), 0).toInt()
            }
        }
        if (bytesRead <= 0) return

        val request = buffer.decodeToString(0, bytesRead)
        val lines = request.split("\r\n")
        if (lines.isEmpty()) return

        // Parse request line
        val parts = lines[0].split(" ")
        if (parts.size < 2) return
        val method = parts[0]
        val path = parts[1].split("?")[0]

        // Parse body (after empty line)
        val bodyStart = request.indexOf("\r\n\r\n")
        val body = if (bodyStart >= 0) request.substring(bodyStart + 4) else ""

        // Route
        val (statusCode, responseBody) = route(method, path, body)

        // Send response
        val response = "HTTP/1.1 $statusCode OK\r\n" +
            "Content-Type: application/json\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n" +
            "Access-Control-Allow-Headers: Content-Type, Authorization\r\n" +
            "Connection: close\r\n" +
            "Content-Length: ${responseBody.encodeToByteArray().size}\r\n" +
            "\r\n" +
            responseBody

        val responseBytes = response.encodeToByteArray()
        memScoped {
            responseBytes.usePinned { pinned ->
                send(clientSocket, pinned.addressOf(0), responseBytes.size.toULong(), 0)
            }
        }
    }

    private suspend fun route(method: String, path: String, body: String): Pair<Int, String> {
        return try {
            when {
                method == "OPTIONS" -> 200 to "{}"
                method == "GET" && path == "/health" ->
                    200 to json.encodeToString(TestAutomationHandler.handleHealth())
                method == "GET" && path == "/tree" ->
                    200 to json.encodeToString(TestAutomationHandler.handleTree())
                method == "GET" && path == "/screen" ->
                    200 to json.encodeToString(TestAutomationHandler.handleScreen())
                method == "POST" && path == "/click" -> {
                    val req = json.decodeFromString<ClickRequest>(body)
                    val resp = TestAutomationHandler.handleClick(req)
                    (if (resp.success) 200 else 404) to json.encodeToString(resp)
                }
                method == "POST" && path == "/input" -> {
                    val req = json.decodeFromString<InputRequest>(body)
                    200 to json.encodeToString(TestAutomationHandler.handleInput(req))
                }
                method == "POST" && path == "/wait" -> {
                    val req = json.decodeFromString<WaitRequest>(body)
                    val resp = TestAutomationHandler.handleWait(req)
                    (if (resp.success) 200 else 404) to json.encodeToString(resp)
                }
                method == "POST" && path == "/scroll" -> {
                    val req = json.decodeFromString<ScrollRequest>(body)
                    200 to json.encodeToString(TestAutomationHandler.handleScroll(req))
                }
                method == "GET" && path.startsWith("/element/") -> {
                    val tag = path.removePrefix("/element/")
                    val elem = TestAutomationHandler.handleGetElement(tag)
                    if (elem != null) 200 to json.encodeToString(elem)
                    else 404 to """{"error":"Element not found"}"""
                }
                else -> 404 to """{"error":"Not found: $method $path"}"""
            }
        } catch (e: Exception) {
            500 to """{"error":"${e.message?.replace("\"", "'")}"}"""
        }
    }

    companion object {
        private var instance: IOSTestAutomationServer? = null

        fun startIfEnabled() {
            val testMode = platform.posix.getenv("CIRIS_TEST_MODE")?.toKString()?.lowercase()
            if (testMode in listOf("true", "1", "yes")) {
                val port = platform.posix.getenv("CIRIS_TEST_PORT")?.toKString()?.toIntOrNull() ?: 9091
                NSLog("[TestAutomation.ios] Test mode enabled, starting server on port $port")
                instance = IOSTestAutomationServer(port).also { it.start() }
            }
        }

        fun stop() {
            instance?.stop()
            instance = null
        }
    }
}
