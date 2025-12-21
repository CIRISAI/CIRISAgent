"""
CIRIS iOS App - WebView-based GUI with Python Backend

Displays startup checks during initialization, then loads the CIRIS GUI
from the local FastAPI server once the backend is ready.
"""
import sys
import threading
import time
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, CENTER

# Status tracking
STARTUP_LOGS = []
BACKEND_READY = False
BACKEND_ERROR = None


def log(message: str):
    """Log a message to both console and startup logs."""
    print(message)
    STARTUP_LOGS.append(message)


def check_pydantic() -> bool:
    """Verify pydantic loads correctly."""
    log("[1/4] Checking pydantic...")
    try:
        import pydantic
        from pydantic_core import _pydantic_core
        log(f"      Pydantic: {pydantic.VERSION}")
        log(f"      Core: {_pydantic_core.__version__}")
        log("[1/4] OK")
        return True
    except ImportError as e:
        log(f"[1/4] FAILED: {e}")
        return False


def check_fastapi() -> bool:
    """Verify FastAPI loads correctly."""
    log("[2/4] Checking FastAPI...")
    try:
        import fastapi
        log(f"      FastAPI: {fastapi.__version__}")
        log("[2/4] OK")
        return True
    except ImportError as e:
        log(f"[2/4] FAILED: {e}")
        return False


def check_cryptography() -> bool:
    """Verify cryptography loads correctly."""
    log("[3/4] Checking cryptography...")
    try:
        import cryptography
        log(f"      Cryptography: {cryptography.__version__}")
        log("[3/4] OK")
        return True
    except ImportError as e:
        log(f"[3/4] FAILED: {e}")
        return False


def check_ciris_engine() -> bool:
    """Verify CIRIS engine loads correctly."""
    log("[4/4] Checking CIRIS engine...")
    try:
        from ciris_engine.schemas.config.essential import EssentialConfig
        log("      EssentialConfig: OK")
        log("[4/4] OK")
        return True
    except ImportError as e:
        log(f"[4/4] FAILED: {e}")
        return False


class CirisiOS(toga.App):
    def startup(self):
        # Create main box with status display
        self.main_box = toga.Box(style=Pack(direction=COLUMN, padding=10))

        # Title
        self.title_label = toga.Label(
            "CIRIS iOS Runtime",
            style=Pack(padding=(10, 0), font_size=18, font_weight="bold", text_align=CENTER)
        )
        self.main_box.add(self.title_label)

        # Status label
        self.status_label = toga.Label(
            "Starting...",
            style=Pack(padding=(5, 0), text_align=CENTER)
        )
        self.main_box.add(self.status_label)

        # Log display (scrollable text area for startup logs)
        self.log_display = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, padding=10, font_family="monospace")
        )
        self.main_box.add(self.log_display)

        # Create main window
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.main_box
        self.main_window.show()

        # Start checks in background
        threading.Thread(target=self._run_startup, daemon=True).start()

    def _run_startup(self):
        """Run startup checks and start backend."""
        global BACKEND_READY, BACKEND_ERROR

        log("=" * 50)
        log("CIRIS iOS RUNTIME")
        log("=" * 50)
        log(f"Python: {sys.version.split()[0]}")
        log(f"Platform: {sys.platform}")
        log("=" * 50)
        log("")

        self._update_logs()

        # Run checks
        checks = [
            ("Pydantic", check_pydantic),
            ("FastAPI", check_fastapi),
            ("Cryptography", check_cryptography),
            ("CIRIS Engine", check_ciris_engine),
        ]

        all_passed = True
        for name, check_fn in checks:
            self._update_status(f"Checking {name}...")
            if not check_fn():
                all_passed = False
            self._update_logs()
            time.sleep(0.1)  # Brief pause for UI update

        log("")

        if all_passed:
            log("=" * 50)
            log("ALL CHECKS PASSED")
            log("=" * 50)
            log("")
            self._update_logs()
            self._update_status("Starting backend...")

            # Start the backend
            try:
                self._start_backend()
            except Exception as e:
                BACKEND_ERROR = str(e)
                log(f"Backend error: {e}")
                self._update_logs()
                self._update_status(f"Backend error: {e}")
        else:
            log("!" * 50)
            log("SOME CHECKS FAILED")
            log("!" * 50)
            BACKEND_ERROR = "Startup checks failed"
            self._update_logs()
            self._update_status("Startup failed - see logs above")

    def _start_backend(self):
        """Start the CIRIS backend in a thread."""
        global BACKEND_READY

        log("Starting CIRIS backend...")
        self._update_logs()

        try:
            from ciris_ios.ios_main import setup_ios_environment, start_runtime_thread

            # Setup environment
            log("Setting up iOS environment...")
            setup_ios_environment()
            self._update_logs()

            # Start runtime in background thread
            log("Starting runtime thread...")
            self._update_logs()

            runtime_thread = start_runtime_thread()

            # Wait a bit for server to start
            log("Waiting for API server...")
            self._update_logs()
            time.sleep(3)

            # Check if server is responding
            log("Checking API health...")
            self._update_logs()

            import httpx
            try:
                response = httpx.get("http://127.0.0.1:8080/health", timeout=5.0)
                if response.status_code == 200:
                    log("API server is ready!")
                    BACKEND_READY = True
                    self._update_logs()
                    self._update_status("Backend ready - loading GUI...")

                    # Switch to WebView
                    self._switch_to_webview()
                else:
                    log(f"API returned status {response.status_code}")
                    self._update_status("API not ready")
            except Exception as e:
                log(f"API check failed: {e}")
                log("Backend may still be starting...")
                self._update_logs()
                self._update_status("Waiting for backend...")

                # Keep waiting and retry
                for i in range(10):
                    time.sleep(2)
                    try:
                        response = httpx.get("http://127.0.0.1:8080/health", timeout=5.0)
                        if response.status_code == 200:
                            log("API server is ready!")
                            BACKEND_READY = True
                            self._update_logs()
                            self._switch_to_webview()
                            return
                    except Exception:
                        log(f"Retry {i+1}/10...")
                        self._update_logs()

                log("Backend failed to start after retries")
                self._update_status("Backend failed to start")

        except Exception as e:
            log(f"Backend startup error: {e}")
            import traceback
            log(traceback.format_exc())
            self._update_logs()
            self._update_status(f"Error: {e}")

    def _switch_to_webview(self):
        """Switch the UI to show the WebView."""
        def do_switch():
            try:
                # Create WebView pointing to local server
                self.webview = toga.WebView(
                    style=Pack(flex=1),
                    on_webview_load=self._on_webview_load,
                )
                self.webview.url = "http://127.0.0.1:8080"

                # Replace main window content
                self.main_window.content = self.webview
                log("[CIRIS iOS] Switched to WebView")
            except Exception as e:
                log(f"WebView error: {e}")
                self._update_logs()

        # Schedule on main thread
        self.loop.call_soon_threadsafe(do_switch)

    def _on_webview_load(self, widget):
        """Called when WebView finishes loading."""
        log(f"[CIRIS iOS] WebView loaded: {widget.url}")

    def _update_status(self, message: str):
        """Update the status label from any thread."""
        def do_update():
            self.status_label.text = message
        try:
            self.loop.call_soon_threadsafe(do_update)
        except Exception:
            pass

    def _update_logs(self):
        """Update the log display from any thread."""
        def do_update():
            self.log_display.value = "\n".join(STARTUP_LOGS)
        try:
            self.loop.call_soon_threadsafe(do_update)
        except Exception:
            pass


def main():
    return CirisiOS()
