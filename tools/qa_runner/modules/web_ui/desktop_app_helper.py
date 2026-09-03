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

import time
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

    # Seconds to wait after a successful /input before the next one. ZERO ON
    # DESKTOP, non-zero on Android/iOS.
    #
    # KMP TextField binds its value through a StateFlow, and /input answers as
    # soon as the request is POSTED -- the field applies it when it next
    # collects. A StateFlow keeps only the latest value, so back-to-back inputs
    # race that commit and the earlier ones are dropped, every call still
    # reporting success. apps/ios/CLAUDE.md has recorded this for a while as
    # "Text input needs 2-second delay between fields", and login() has slept
    # between fields for exactly this reason.
    #
    # It lives HERE rather than at the call sites because the setup wizard did
    # not know to do it: you_step types username -> password -> confirm
    # back-to-back, the password was the one that vanished, and Android stopped
    # on "Password is required" with btn_next disabled -- every input
    # acknowledged (five-platform runs 33708152999 through the 09-03 nightly).
    # One field on the config fixes every present and future caller.
    input_settle_s: float = 0.0

    # Send each HTTP request in ONE write. The iOS automation server is a
    # hand-rolled POSIX server that does a single recv() into an 8 KB buffer and
    # parses whatever arrived (TestAutomationServer.ios.kt L142-150). httpx
    # writes headers and body separately, so a POST body lands in a second
    # segment the server never reads; it then decodes an empty body and returns
    # the kotlinx error text as the response. Every POST fails, every GET works
    # (five-platform run 33780331440). A workaround for CIRISClient#33 -- one
    # Ktor server in commonMain -- and it goes when that lands.
    one_segment_http: bool = False


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
        transport = _OneSegmentTransport() if self.config.one_segment_http else None
        if transport is not None:
            print("    (one-segment HTTP transport in use: the iOS test server reads one segment -- CIRISClient#33)")
        self._client = httpx.AsyncClient(
            transport=transport,
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
        data = _json(response)
        self._current_screen = data.get("screen", "unknown")
        return self._current_screen

    async def get_elements(self) -> List[ElementInfo]:
        """Get all UI elements currently visible."""
        if not self._client:
            raise RuntimeError("Not connected. Call start() first.")

        response = await self._client.get("/tree")
        data = _json(response)
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
        data = _json(response)
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
        data = _json(response)
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Click '{test_tag}' failed: {error} (response: {data})")
        return True

    async def input_text(
        self,
        test_tag: str,
        text: str,
        clear_first: bool = True,
        timeout: Optional[int] = None,
        verify: bool = True,
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
        data = _json(response)
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Input '{test_tag}' failed: {error} (response: {data})")
        if self.config.input_settle_s:
            await asyncio.sleep(self.config.input_settle_s)
        if verify and not _looks_secret(test_tag):
            await self._verify_input_landed(test_tag, text)
        return True

    async def _verify_input_landed(self, test_tag: str, text: str, budget_s: float = 3.0) -> None:
        """success:true means the request was POSTED, not that the field changed.

        On Android and iOS, /input drops a TextInputRequest onto a StateFlow
        and answers success immediately; the Compose field applies it when it
        next collects. A StateFlow keeps only the latest value, so three
        inputs in quick succession can leave the first two applied to nothing
        -- every call acknowledged, the wizard refusing to advance because a
        required field is empty (five-platform run 33708152999, you_step).
        Desktop applies input synchronously and never shows this.

        So read the field back. The client's tree exposes each element's text;
        wait for it to equal what was typed. A field that exposes no text at
        all is reported as unverifiable rather than failed -- but a field that
        reports a DIFFERENT value is the exact defect this exists to catch.
        """
        deadline = time.monotonic() + budget_s
        seen: Optional[str] = None
        exposes_text = False
        while time.monotonic() < deadline:
            el = await self.get_element(test_tag)
            if el is not None:
                if el.text is None:
                    # STRUCTURAL, NOT SLOW. A client that omits `text` for input
                    # elements will omit it however long we poll, so burning the
                    # whole budget per field buys nothing and costs real time --
                    # three fields in the setup wizard, on the platform that is
                    # already the slowest. Conclude on the first clean read.
                    print(f"    (input '{test_tag}' unverifiable: element exposes no text)")
                    return
                exposes_text = True
                seen = el.text
                if seen == text:
                    return
            await asyncio.sleep(0.1)
        if not exposes_text:
            print(f"    (input '{test_tag}' unverifiable: element never appeared)")
            return
        raise RuntimeError(
            f"Input '{test_tag}' was acknowledged but {budget_s:.0f}s later the field holds "
            f"{seen!r}, not {text!r} — the client reported success for input it never applied"
        )

    async def wait_for_element(self, test_tag: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for an element to appear.

        Args:
            test_tag: The testTag to wait for
            timeout: Timeout in milliseconds (default: config.timeout_ms)

        Returns:
            True if the element appeared.

        Raises:
            RuntimeError: if it did not. THIS NEVER RETURNS FALSE — the
                annotation says ``bool`` because it is always ``True``.

        Every ``if not await wait_for_element(...)`` in this package is therefore
        a DEAD BRANCH, and one of them mattered: the setup wizard's AI step used
        it to detect "this is a node-client build with no AI screen, carry on",
        and instead the run failed on the client that has no such screen. Use
        :meth:`wait_for_optional_element` when absence is a legitimate answer.
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
        data = _json(response)
        if not data.get("success", False):
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Wait for element '{test_tag}' timed out after {timeout_ms}ms: {error}")
        return True

    async def wait_for_optional_element(self, test_tag: str, timeout: Optional[int] = None) -> bool:
        """Wait for an element that MAY legitimately not exist.

        Returns True if it appeared, False if it did not. The distinction that
        :meth:`wait_for_element` cannot express: there, absence is a failure; here
        it is data. Use this only where the caller genuinely handles both — an
        optional wait on a required element hides a real break.
        """
        try:
            return await self.wait_for_element(test_tag, timeout=timeout)
        except RuntimeError:
            return False

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
        data = _json(response)

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

        # The Login screen is a landing page with sign-in-method tiles
        # (btn_google_signin / btn_apple_signin, btn_local_login) and the
        # username/password fields are revealed only after btn_local_login is
        # chosen.
        #
        # This comment used to say the chooser was iOS/Android only and that
        # "Desktop's Login shows input_username directly". That is true of LINUX
        # desktop and FALSE of WINDOWS desktop, where the tree is
        # btn_google_signin / btn_local_login / btn_login_reset_device / ... and
        # carries no input_username until the tile is clicked. The probe below
        # was already platform-agnostic and handled it correctly; the comment
        # was not, and it sent the step-by-step desktop-login flow down a path
        # that assumed the form was always present.
        is_mobile_login = False
        if not await self.is_element_visible("input_username"):
            if await self.is_element_visible("btn_local_login"):
                is_mobile_login = True
                await self.click("btn_local_login")
                # Wait briefly for the local-credentials panel to render
                await self.wait_for_element("input_username", timeout=3000)

        # Input credentials. On iOS/Android, KMP TextField uses a StateFlow
        # for the bound value — text entered via /input doesn't reach the
        # view model synchronously, and back-to-back inputs race the
        # StateFlow commit (documented in apps/ios/CLAUDE.md as
        # "Text input needs 2-second delay between fields"). Insert that
        # delay only on mobile; desktop's Compose state updates are
        # synchronous and don't need it.
        if not await self.input_text("input_username", username):
            return False
        if is_mobile_login:
            await asyncio.sleep(2.0)
        if not await self.input_text("input_password", password):
            return False
        if is_mobile_login:
            await asyncio.sleep(2.0)

        # Click login and wait for Interact screen
        return await self.click_and_wait_for_screen("btn_login_submit", "Interact", timeout_ms=timeout_ms)

    async def navigate_to(self, screen_name: str, timeout_ms: int = 5000) -> bool:
        """
        Navigate to a screen using the EpistemicSidebar (post-2.9.4 nav chrome)
        or the legacy menu for screens not yet migrated.

        Args:
            screen_name: Screen to navigate to (e.g., "Network", "Adapters",
                "Settings")
            timeout_ms: Timeout for navigation

        Returns:
            True if navigation successful
        """
        # Map screen names to:
        #   - EpistemicSidebar nav rows (preferred for post-2.9.4 nav)
        #   - Legacy menu items / direct buttons (fallback)
        # Sidebar tags follow `nav_epistemic_<slug>` where slug = surface id
        # with hyphens normalized to underscores.
        menu_items = {
            # Sidebar-driven (2.9.4 EpistemicSidebar). The federation transport
            # hub is the Global Commons layer in the Commons group (2.9.6 deleted
            # the separate Network/Federation surfaces; this is the canonical name).
            "Global Commons": "nav_epistemic_layer_global_commons",
            # Legacy menu-driven
            "Adapters": "menu_adapters",
            "Settings": "btn_settings",  # Direct button, not in menu
            # Add more as needed
        }

        menu_tag = menu_items.get(screen_name)
        if not menu_tag:
            print(f"Unknown screen: {screen_name}")
            return False

        # Settings has a direct button (pre-sidebar legacy chrome)
        if screen_name == "Settings":
            return await self.click_and_wait_for_screen("btn_settings", "Settings", timeout_ms=timeout_ms)

        # Sidebar-driven navigation — the EpistemicSidebar is always rendered
        # post-login (no toggle). Click the nav row directly, then wait for
        # the destination's root testTag.
        if menu_tag.startswith("nav_epistemic_"):
            # Each surface lives in a collapsible group; the active group is
            # expanded on render and others are collapsed. If the destination
            # row isn't visible yet, expand its group first via the
            # nav_group_<id> header (also a testableClickable).
            screen_groups = {
                # Global Commons lives in the Commons group (id "commons-layers").
                "Global Commons": "nav_group_commons-layers",
            }
            screen_roots = {
                "Global Commons": "screen_network_hub",
            }
            group_tag = screen_groups.get(screen_name)
            root_tag = screen_roots.get(screen_name)

            if not await self.is_element_visible(menu_tag):
                if group_tag is not None and await self.is_element_visible(group_tag):
                    await self.click(group_tag)
                    try:
                        await self.wait_for_element(menu_tag, timeout=2000)
                    except RuntimeError:
                        return False
                else:
                    return False

            if not await self.click(menu_tag):
                return False
            if root_tag is not None:
                try:
                    return await self.wait_for_element(root_tag, timeout=timeout_ms)
                except RuntimeError:
                    return False
            # No known root testTag — fall back to screen-name polling.
            return await self.wait_for_screen(screen_name, timeout=timeout_ms)

        # For legacy menu items, first open menu
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
        data = _json(response)
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
        data = _json(response)
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



def _json(response: "httpx.Response"):
    """Parse a test-server response; tolerate a raw control character, and SAY SO.

    The iOS automation server is a hand-rolled POSIX HTTP server (CIRISClient#33)
    and, the first time it ever answered in CI, every response failed strict
    JSON parsing: "Invalid control character at: line 1 column 77" (run
    33777943107). A driver that dies on that learns nothing -- not which route,
    not which bytes. So: try strict; on a control-character failure, parse with
    strict=False (the same payload, control characters allowed inside strings)
    and print the offending bytes with the position, escaped, so the report
    upstream can quote them. Anything else stays a hard error.
    """
    import json as _json_mod

    try:
        return response.json()
    except ValueError as exc:
        text = response.text
        try:
            data = _json_mod.loads(text, strict=False)
        except ValueError:
            raise exc
        pos = getattr(exc, "pos", None)
        lo = max(0, (pos or 0) - 40)
        window = text[lo:(pos or 0) + 40].encode("unicode_escape").decode("ascii")
        print(
            f"    (test server returned invalid JSON on {response.request.method} "
            f"{response.request.url.path}: {exc}; parsed leniently. bytes around the fault: {window!r})"
        )
        return data


class _OneSegmentTransport(httpx.AsyncBaseTransport):
    """Deliver the whole request -- status line, headers, body -- in one write.

    For a server that does a single recv() and parses what it got. Minimal on
    purpose: HTTP/1.1, Connection: close, read the response to EOF, hand httpx
    the status, headers and body. Nothing else the gate needs.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        body = request.content or b""
        target = url.raw_path.decode("ascii") if isinstance(url.raw_path, (bytes, bytearray)) else str(url.raw_path)
        head = [f"{request.method} {target} HTTP/1.1", f"Host: {url.host}:{url.port or 80}", "Connection: close"]
        for k, v in request.headers.items():
            if k.lower() in ("host", "connection", "content-length", "transfer-encoding"):
                continue
            head.append(f"{k}: {v}")
        head.append(f"Content-Length: {len(body)}")
        wire = ("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + body

        reader, writer = await asyncio.open_connection(url.host, url.port or 80)
        try:
            writer.write(wire)          # ONE write: this is the entire point
            await writer.drain()
            raw = await reader.read(-1)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

        head_end = raw.find(b"\r\n\r\n")
        if head_end < 0:
            raise httpx.TransportError(f"no header terminator in response from {url}")
        head_lines = raw[:head_end].decode("latin-1").split("\r\n")
        try:
            status = int(head_lines[0].split(" ", 2)[1])
        except (IndexError, ValueError) as exc:
            raise httpx.TransportError(f"bad status line {head_lines[0]!r} from {url}") from exc
        headers = []
        for line in head_lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers.append((k.strip(), v.strip()))
        return httpx.Response(status, headers=headers, content=raw[head_end + 4:], request=request)

_SECRET_MARKERS = ("password", "secret", "token", "api_key", "apikey")


def _looks_secret(test_tag: str) -> bool:
    """Masked fields cannot be read back; do not pretend to verify them."""
    t = test_tag.lower()
    return any(m in t for m in _SECRET_MARKERS)


async def describe_test_server(server_url: str = "http://localhost:8091") -> str:
    """Say WHAT the test server answered, for a failure message worth reading.

    `check_desktop_app_running` collapses three very different situations into
    one False — nothing listening, listening but not test mode, and listening but
    answering something unexpected — and the caller then prints a single message
    naming only the second. On Android that produced "the Desktop app is not
    running with test mode enabled" moments after bring-up had reported the test
    server reachable on the same port, which reads as a contradiction and sends
    the reader after the wrong thing entirely.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{server_url}/health")
    except Exception as exc:  # noqa: BLE001
        return f"nothing answered at {server_url}/health ({type(exc).__name__})"
    try:
        data = _json(response)
    except ValueError:
        return f"{server_url}/health returned {response.status_code}, not JSON: {response.text[:120]!r}"
    if data.get("status") != "ok":
        return f"{server_url}/health says status={data.get('status')!r} (payload: {data})"
    if not data.get("testMode", False):
        return (
            f"{server_url}/health is UP but testMode is {data.get('testMode')!r} — the app is "
            f"running WITHOUT test mode (payload: {data})"
        )
    return f"{server_url}/health ok, testMode enabled"


async def attribute_device_failure(server_url: str, backend_url: str) -> str:
    """Which layer died: the automation server, or the whole app process?

    On Android the automation port is reached through an adb forward, and adb
    accepts on the HOST socket before it tries the device. If the device-side
    port is gone, adb accepts and then closes — byte-identical to a live server
    whose request handler died. So the exception seen on :9091 alone cannot
    tell a dead app process from a dead accept loop.

    In run 33704781359 that ambiguity WAS the question. The automation server
    had answered /health with testMode=true seconds earlier, then returned
    RemoteProtocolError, and from the host there was no way to say whether the
    client's accept loop had died or the whole app had been killed — a
    different owner in each case.

    The sibling port settles it. The embedded Python backend is a separate
    listener, on a separate forward, inside the SAME app process:

      backend answers  -> the process is ALIVE; only the automation server
                          stopped. Client-side (the automation surface).
      backend is gone  -> the process itself died; look for an OOM/low-memory
                          kill in logcat, not for an accept-loop bug.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{backend_url}/v1/system/health")
        alive = r.status_code in (200, 401, 403)
        detail = f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        alive = False
        detail = type(exc).__name__

    if alive:
        return (
            f"the app PROCESS IS ALIVE — the embedded backend at {backend_url} still "
            f"answers ({detail}), so only the automation server on {server_url} stopped. "
            "Look at the automation surface, not at a process death."
        )
    return (
        f"the app PROCESS IS GONE — the embedded backend at {backend_url} is also "
        f"unreachable ({detail}), so both listeners died together. Look for a process "
        "kill (OOM / low-memory) in logcat before suspecting the automation server."
    )


async def check_desktop_app_running(server_url: str = "http://localhost:8091") -> bool:
    """Check if the CIRIS Desktop app is running with test mode enabled."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{server_url}/health")
            data = _json(response)
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
                "  cd client && ./gradlew :desktopApp:run\n"
                "\n"
                "Or in a single command:\n"
                "\n"
                "  CIRIS_TEST_MODE=true cd client && ./gradlew :desktopApp:run\n"
            )

    asyncio.get_event_loop().run_until_complete(_check())
