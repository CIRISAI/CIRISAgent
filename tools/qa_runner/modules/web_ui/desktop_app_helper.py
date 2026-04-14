"""
Desktop App Helper for CIRIS Desktop UI Testing

Communicates with the TestAutomationServer embedded in the CIRIS Desktop app
to interact with UI elements via testTag identifiers.

Replaces browser-based testing with native Compose Desktop automation.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class DesktopAppConfig:
    """Configuration for desktop app helper."""

    # Test automation server URL
    server_url: str = "http://localhost:8091"

    # Timeouts
    timeout_ms: int = 30000  # Default timeout for operations
    poll_interval_ms: int = 100  # Interval for polling operations

    # Screenshot directory (for any screenshots taken)
    screenshot_dir: str = "desktop_app_qa_reports"


@dataclass
class Screenshot:
    """Screenshot capture result."""

    name: str
    path: str
    timestamp: datetime
    full_page: bool = False


@dataclass
class ElementInfo:
    """Information about a UI element from the desktop app."""

    test_tag: str
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    text: Optional[str] = None


class DesktopAppHelper:
    """
    Communicates with the TestAutomationServer in the CIRIS Desktop app.

    Provides methods for:
    - App lifecycle management
    - Element interaction via testTag
    - Screen navigation
    - Waiting for elements
    """

    def __init__(self, config: Optional[DesktopAppConfig] = None):
        self.config = config or DesktopAppConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._screenshots: List[Screenshot] = []
        self._current_screen: str = "unknown"

        # Ensure screenshot directory exists
        Path(self.config.screenshot_dir).mkdir(parents=True, exist_ok=True)

    @property
    def screenshots(self) -> List[Screenshot]:
        """Get list of captured screenshots."""
        return self._screenshots.copy()

    @property
    def current_screen(self) -> str:
        """Get current screen name."""
        return self._current_screen

    async def start(self) -> "DesktopAppHelper":
        """Initialize the HTTP client and verify connection to test server."""
        self._client = httpx.AsyncClient(
            base_url=self.config.server_url,
            timeout=self.config.timeout_ms / 1000.0,
        )

        # Verify connection
        if not await self.is_connected():
            raise RuntimeError(
                f"Cannot connect to desktop app test server at {self.config.server_url}\n"
                "Make sure the desktop app is running with CIRIS_TEST_MODE=true"
            )

        return self

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_connected(self) -> bool:
        """Check if connected to the test automation server."""
        if not self._client:
            return False

        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def get_screen(self) -> str:
        """Get the current screen name."""
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.get("/screen")
        data = response.json()
        self._current_screen = data.get("screen", "unknown")
        return self._current_screen

    async def get_elements(self) -> List[ElementInfo]:
        """Get all UI elements currently visible."""
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.get("/tree")
        data = response.json()
        self._current_screen = data.get("screen", "unknown")

        elements = []
        for elem in data.get("elements", []):
            elements.append(
                ElementInfo(
                    test_tag=elem["testTag"],
                    x=elem["x"],
                    y=elem["y"],
                    width=elem["width"],
                    height=elem["height"],
                    center_x=elem["centerX"],
                    center_y=elem["centerY"],
                    text=elem.get("text"),
                )
            )
        return elements

    async def get_element(self, test_tag: str) -> Optional[ElementInfo]:
        """Get info about a specific element by testTag."""
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.get(f"/element/{test_tag}")
        if response.status_code == 404:
            return None
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"get_element '{test_tag}' failed: {data['error']}")
        return ElementInfo(
            test_tag=data["testTag"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            center_x=data["centerX"],
            center_y=data["centerY"],
            text=data.get("text"),
        )

    async def click(self, test_tag: str, timeout: Optional[int] = None) -> bool:
        """
        Click an element by testTag.

        Returns:
            True if clicked successfully, False if element not found
        """
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        # Wait for element first if timeout specified
        if timeout:
            if not await self.wait_for_element(test_tag, timeout=timeout):
                return False

        response = await self._client.post(
            "/click",
            json={"testTag": test_tag},
        )
        data = response.json()
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Click '{test_tag}' failed: {error} (response: {data})")
        return True

    async def input_text(
        self, test_tag: str, text: str, clear_first: bool = True, timeout: Optional[int] = None
    ) -> bool:
        """
        Input text to an element by testTag.

        Args:
            test_tag: The testTag of the input element
            text: Text to input
            clear_first: Whether to clear existing text first
            timeout: Optional timeout to wait for element

        Returns:
            True if input successful, False if element not found
        """
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        # Wait for element first if timeout specified
        if timeout:
            if not await self.wait_for_element(test_tag, timeout=timeout):
                return False

        response = await self._client.post(
            "/input",
            json={
                "testTag": test_tag,
                "text": text,
                "clearFirst": clear_first,
            },
        )
        data = response.json()
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Input '{test_tag}' failed: {error} (response: {data})")
        return True

    async def wait_for_element(self, test_tag: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for an element to appear.

        Args:
            test_tag: The testTag to wait for
            timeout: Timeout in milliseconds (default: config.timeout_ms)

        Returns:
            True if element found, False if timeout
        """
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        timeout_ms = timeout or self.config.timeout_ms

        response = await self._client.post(
            "/wait",
            json={
                "testTag": test_tag,
                "timeoutMs": timeout_ms,
            },
            timeout=timeout_ms / 1000.0 + 5,  # Add 5s buffer
        )
        data = response.json()
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Wait for element '{test_tag}' timed out after {timeout_ms}ms: {error}")
        return True

    async def act(
        self,
        test_tag: str,
        action: str,
        text: Optional[str] = None,
        clear_first: bool = True,
        wait_ms: int = 500,
        filter_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Combined action + view endpoint. Performs action, waits, returns UI state.

        This is the preferred method for automation as it reduces 3 HTTP calls to 1.

        Args:
            test_tag: Target element's testTag
            action: "click", "input", or "wait"
            text: Text to input (for "input" action)
            clear_first: Clear existing text before input (default: True)
            wait_ms: Milliseconds to wait after action before reading tree (default: 500)
            filter_tags: Optional list of substrings to filter returned elements

        Returns:
            Dict with actionResult, screen, elements, elementCount

        Example:
            result = await helper.act("btn_login_submit", "click", wait_ms=1000)
            print(f"Now on screen: {result['screen']}")

            result = await helper.act(
                "input_skill_md", "input",
                text="---\\nname: My Skill\\n---",
                filter_tags=["skill", "preview"]
            )
        """
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        payload: Dict[str, Any] = {
            "testTag": test_tag,
            "action": action,
            "waitMs": wait_ms,
        }
        if text is not None:
            payload["text"] = text
        payload["clearFirst"] = clear_first
        if filter_tags:
            payload["filterTags"] = filter_tags

        response = await self._client.post("/act", json=payload)
        data = response.json()

        # Update current screen from response
        self._current_screen = data.get("screen", "unknown")

        # Check if action succeeded
        action_result = data.get("actionResult", {})
        if not action_result.get("success", False):
            error = action_result.get("error", "unknown error")
            raise RuntimeError(f"Act '{action}' on '{test_tag}' failed: {error}")

        return data

    async def wait_for_screen(self, screen_name: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for a specific screen to be displayed.

        Args:
            screen_name: The screen name to wait for (e.g., "Interact", "Login")
            timeout: Timeout in milliseconds

        Returns:
            True if screen found, False if timeout
        """
        timeout_ms = timeout or self.config.timeout_ms
        start = datetime.now()

        while True:
            current = await self.get_screen()
            if current == screen_name:
                return True

            elapsed_ms = (datetime.now() - start).total_seconds() * 1000
            if elapsed_ms >= timeout_ms:
                return False

            await asyncio.sleep(self.config.poll_interval_ms / 1000.0)

    async def is_element_visible(self, test_tag: str) -> bool:
        """Check if an element is currently visible."""
        elem = await self.get_element(test_tag)
        return elem is not None

    async def get_element_list(self) -> Dict[str, ElementInfo]:
        """Get all elements as a dict keyed by testTag."""
        elements = await self.get_elements()
        return {e.test_tag: e for e in elements}

    # =========================================================================
    # High-level action methods with built-in polling
    # =========================================================================

    async def click_and_wait_for_screen(self, test_tag: str, expected_screen: str, timeout_ms: int = 5000) -> bool:
        """
        Click an element and wait for screen to change.

        Args:
            test_tag: Element to click
            expected_screen: Screen name to wait for
            timeout_ms: Timeout in milliseconds

        Returns:
            True if screen changed to expected, False on timeout
        """
        if not await self.click(test_tag):
            return False

        return await self.wait_for_screen(expected_screen, timeout=timeout_ms)

    async def click_and_wait_for_element(self, test_tag: str, wait_for_tag: str, timeout_ms: int = 5000) -> bool:
        """
        Click an element and wait for another element to appear.

        Args:
            test_tag: Element to click
            wait_for_tag: Element to wait for after click
            timeout_ms: Timeout in milliseconds

        Returns:
            True if element appeared, False on timeout
        """
        if not await self.click(test_tag):
            return False

        return await self.wait_for_element(wait_for_tag, timeout=timeout_ms)

    async def input_and_verify(self, test_tag: str, text: str, clear_first: bool = True) -> bool:
        """
        Input text and verify the element received it.

        Args:
            test_tag: Element to input text into
            text: Text to input
            clear_first: Whether to clear existing text

        Returns:
            True if input successful
        """
        return await self.input_text(test_tag, text, clear_first=clear_first)

    async def login(
        self,
        username: str = "admin",
        password: str = "qa_test_password_12345",
        timeout_ms: int = 10000,
    ) -> bool:
        """
        Perform login flow and wait for Interact screen.

        Args:
            username: Username to login with
            password: Password to login with
            timeout_ms: Timeout for screen transition

        Returns:
            True if login successful and reached Interact screen
        """
        # Wait for login screen
        if not await self.wait_for_screen("Login", timeout=timeout_ms):
            # Maybe already logged in?
            current = await self.get_screen()
            if current == "Interact":
                return True
            return False

        # Input credentials
        if not await self.input_text("input_username", username):
            return False
        if not await self.input_text("input_password", password):
            return False

        # Click login and wait for Interact screen
        return await self.click_and_wait_for_screen("btn_login_submit", "Interact", timeout_ms=timeout_ms)

    async def navigate_to(self, screen_name: str, timeout_ms: int = 5000) -> bool:
        """
        Navigate to a screen using the menu.

        Args:
            screen_name: Screen to navigate to (e.g., "Adapters", "Settings")
            timeout_ms: Timeout for navigation

        Returns:
            True if navigation successful
        """
        # Map screen names to menu item tags
        menu_items = {
            "Adapters": "menu_adapters",
            "Settings": "btn_settings",  # Direct button, not in menu
            # Add more as needed
        }

        menu_tag = menu_items.get(screen_name)
        if not menu_tag:
            print(f"Unknown screen: {screen_name}")
            return False

        # Settings has a direct button
        if screen_name == "Settings":
            return await self.click_and_wait_for_screen("btn_settings", "Settings", timeout_ms=timeout_ms)

        # For menu items, first open menu
        if not await self.click_and_wait_for_element("btn_menu", menu_tag, timeout_ms=2000):
            return False

        # Click menu item
        return await self.click_and_wait_for_screen(menu_tag, screen_name, timeout_ms=timeout_ms)

    async def attach_file(
        self,
        filename: str,
        media_type: str,
        data_base64: str,
        size_bytes: int,
    ) -> bool:
        """
        Inject a file attachment via test automation (bypasses native file picker).

        Args:
            filename: Display name (e.g., "photo.jpg")
            media_type: MIME type (e.g., "image/jpeg", "application/pdf")
            data_base64: Base64-encoded file content
            size_bytes: File size in bytes

        Returns:
            True if injection successful
        """
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.post(
            "/inject-file",
            json={
                "filename": filename,
                "mediaType": media_type,
                "dataBase64": data_base64,
                "sizeBytes": size_bytes,
            },
        )
        data = response.json()
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"File injection '{filename}' failed: {error} (response: {data})")
        return True

    async def attach_file_from_path(self, file_path: str) -> bool:
        """
        Read a file from disk, base64-encode it, and inject as attachment.

        Args:
            file_path: Path to the file on disk

        Returns:
            True if injection successful
        """
        import base64
        import os

        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {file_path}")
            return False

        size_bytes = path.stat().st_size
        if size_bytes > 10 * 1024 * 1024:
            print(f"File too large: {size_bytes} bytes (max 10MB)")
            return False

        data = path.read_bytes()
        data_base64 = base64.b64encode(data).decode("ascii")

        # Guess MIME type from extension
        ext = path.suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(ext, "application/octet-stream")

        return await self.attach_file(
            filename=path.name,
            media_type=media_type,
            data_base64=data_base64,
            size_bytes=size_bytes,
        )

    async def clear_attachments(self) -> bool:
        """Clear all file attachments via test automation."""
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.post("/clear-attachments")
        data = response.json()
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Clear attachments failed: {error} (response: {data})")
        return True

    async def status(self) -> Dict[str, Any]:
        """
        Get current status: screen and elements.

        Returns:
            Dict with screen name and element list
        """
        elements = await self.get_elements()
        return {
            "screen": self._current_screen,
            "elements": [e.test_tag for e in elements],
            "count": len(elements),
        }

    async def poll_until(
        self,
        condition: callable,
        timeout_ms: int = 5000,
        poll_interval_ms: int = 100,
    ) -> bool:
        """
        Poll until a condition is met.

        Args:
            condition: Async callable that returns True when condition is met
            timeout_ms: Timeout in milliseconds
            poll_interval_ms: Poll interval in milliseconds

        Returns:
            True if condition met, False on timeout
        """
        start = datetime.now()
        while True:
            if await condition():
                return True

            elapsed_ms = (datetime.now() - start).total_seconds() * 1000
            if elapsed_ms >= timeout_ms:
                return False

            await asyncio.sleep(poll_interval_ms / 1000.0)


async def check_desktop_app_running(server_url: str = "http://localhost:8091") -> bool:
    """Check if the CIRIS Desktop app is running with test mode enabled."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{server_url}/health")
            data = response.json()
            return data.get("status") == "ok" and data.get("testMode", False)
    except Exception:
        return False


def ensure_desktop_app_running(server_url: str = "http://localhost:8091") -> None:
    """
    Check if desktop app is running, print instructions if not.

    Raises:
        RuntimeError if desktop app is not running
    """
    import asyncio

    async def _check():
        if not await check_desktop_app_running(server_url):
            raise RuntimeError(
                "\n"
                "❌ CIRIS Desktop app is not running with test mode enabled.\n"
                "\n"
                "To run tests, start the desktop app with test mode:\n"
                "\n"
                "  export CIRIS_TEST_MODE=true\n"
                "  cd mobile && ./gradlew :desktopApp:run\n"
                "\n"
                "Or in a single command:\n"
                "\n"
                "  CIRIS_TEST_MODE=true ./gradlew :desktopApp:run\n"
            )

    asyncio.get_event_loop().run_until_complete(_check())
