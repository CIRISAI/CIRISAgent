"""
Browser Helper for Web UI Testing

Manages Playwright browser lifecycle and provides utility methods for web testing.
Uses Firefox by default for better privacy and compatibility.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = Any
    BrowserContext = Any
    Page = Any


@dataclass
class BrowserConfig:
    """Configuration for browser helper."""

    browser_type: str = "firefox"  # firefox, chromium, webkit
    headless: bool = False  # Show browser window by default for debugging
    viewport_width: int = 1400
    viewport_height: int = 1000
    timeout_ms: int = 30000  # Default timeout for operations
    slow_mo: int = 0  # Slow down operations for debugging (ms)
    screenshot_dir: str = "web_ui_qa_reports"

    # Recording options
    record_video: bool = False
    video_dir: Optional[str] = None


@dataclass
class Screenshot:
    """Screenshot capture result."""

    name: str
    path: str
    timestamp: datetime
    full_page: bool = False


@dataclass
class ElementInfo:
    """Information about a UI element."""

    selector: str
    text: Optional[str] = None
    visible: bool = False
    enabled: bool = False
    tag_name: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)


class BrowserHelper:
    """
    Manages Playwright browser for web UI testing.

    Provides methods for:
    - Browser lifecycle management
    - Page navigation and waiting
    - Element interaction
    - Screenshot capture
    - Form filling
    - Console log capture
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install firefox")

        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._screenshots: List[Screenshot] = []
        self._console_logs: List[Dict[str, Any]] = []
        self._network_logs: List[Dict[str, Any]] = []

        # Ensure screenshot directory exists
        Path(self.config.screenshot_dir).mkdir(parents=True, exist_ok=True)

    @property
    def page(self) -> Optional[Page]:
        """Get the current page."""
        return self._page

    @property
    def screenshots(self) -> List[Screenshot]:
        """Get list of captured screenshots."""
        return self._screenshots.copy()

    @property
    def console_logs(self) -> List[Dict[str, Any]]:
        """Get captured browser console logs."""
        return self._console_logs.copy()

    @property
    def network_logs(self) -> List[Dict[str, Any]]:
        """Get captured network request/response logs."""
        return self._network_logs.copy()

    def get_recent_network_logs(self, count: int = 20, api_only: bool = True) -> List[Dict[str, Any]]:
        """Get recent network logs, optionally filtered to API calls only."""
        logs = self._network_logs[-count:] if count else self._network_logs
        if api_only:
            logs = [l for l in logs if "/v1/" in l.get("url", "")]
        return logs

    def get_recent_console_logs(self, count: int = 20, types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get recent console logs, optionally filtered by type."""
        logs = self._console_logs[-count:] if count else self._console_logs
        if types:
            logs = [l for l in logs if l["type"] in types]
        return logs

    async def start(self) -> "BrowserHelper":
        """Start the browser and create a new page."""
        self._playwright = await async_playwright().start()

        # Select browser type
        browser_launcher = getattr(self._playwright, self.config.browser_type)

        # Launch browser
        self._browser = await browser_launcher.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )

        # Create context with viewport settings
        context_options = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }

        if self.config.record_video and self.config.video_dir:
            context_options["record_video_dir"] = self.config.video_dir

        self._context = await self._browser.new_context(**context_options)
        self._context.set_default_timeout(self.config.timeout_ms)

        # Create page
        self._page = await self._context.new_page()

        # Capture console logs
        self._page.on("console", self._on_console_message)

        # Capture network requests/responses for debugging
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)

        return self

    def _on_console_message(self, msg) -> None:
        """Capture browser console messages."""
        self._console_logs.append(
            {
                "type": msg.type,
                "text": msg.text,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _on_request(self, request) -> None:
        """Capture network requests (for API debugging)."""
        # Only log API requests
        if "/v1/" in request.url:
            self._network_logs.append(
                {
                    "type": "request",
                    "url": request.url,
                    "method": request.method,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    def _on_response(self, response) -> None:
        """Capture network responses (for API debugging)."""
        # Only log API responses
        if "/v1/" in response.url:
            self._network_logs.append(
                {
                    "type": "response",
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    async def stop(self) -> None:
        """Stop the browser and clean up."""
        if self._page:
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def goto(self, url: str, wait_for: str = "networkidle") -> None:
        """Navigate to a URL and wait for load."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        await self._page.goto(url)
        await self._page.wait_for_load_state(wait_for)

    async def screenshot(
        self,
        name: str,
        full_page: bool = False,
        element_selector: Optional[str] = None,
    ) -> Screenshot:
        """
        Capture a screenshot.

        Args:
            name: Name for the screenshot file (without extension)
            full_page: Capture full scrollable page
            element_selector: Capture specific element only

        Returns:
            Screenshot info with path
        """
        if not self._page:
            raise RuntimeError("Browser not started.")

        timestamp = datetime.now()
        filename = f"{name}_{timestamp.strftime('%H%M%S')}.png"
        filepath = str(Path(self.config.screenshot_dir) / filename)

        if element_selector:
            element = self._page.locator(element_selector)
            await element.screenshot(path=filepath)
        else:
            await self._page.screenshot(path=filepath, full_page=full_page)

        shot = Screenshot(
            name=name,
            path=filepath,
            timestamp=timestamp,
            full_page=full_page,
        )
        self._screenshots.append(shot)
        return shot

    async def click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Click an element."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        await locator.click(timeout=timeout)

    async def click_text(self, text: str, exact: bool = False, timeout: Optional[int] = None) -> bool:
        """
        Click an element by its text content.

        Returns:
            True if element found and clicked, False otherwise
        """
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.get_by_text(text, exact=exact)
        if await locator.count() > 0:
            await locator.first.click(timeout=timeout)
            return True
        return False

    async def fill(self, selector: str, value: str, timeout: Optional[int] = None) -> None:
        """Fill an input field."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        await locator.fill(value, timeout=timeout)

    async def fill_input_by_placeholder(self, placeholder: str, value: str) -> bool:
        """
        Fill an input by its placeholder text.

        Returns:
            True if input found and filled, False otherwise
        """
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(f"input[placeholder*='{placeholder}' i]")
        if await locator.count() > 0:
            await locator.first.fill(value)
            return True
        return False

    async def select_option(self, selector: str, value: str) -> None:
        """Select an option from a dropdown."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        await locator.select_option(value)

    async def wait_for_text(self, text: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for text to appear on the page.

        Returns:
            True if text found, False if timeout
        """
        if not self._page:
            raise RuntimeError("Browser not started.")

        try:
            locator = self._page.get_by_text(text)
            await locator.first.wait_for(timeout=timeout or self.config.timeout_ms)
            return True
        except Exception:
            return False

    async def wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for an element matching selector.

        Returns:
            True if found, False if timeout
        """
        if not self._page:
            raise RuntimeError("Browser not started.")

        try:
            await self._page.wait_for_selector(selector, timeout=timeout or self.config.timeout_ms)
            return True
        except Exception:
            return False

    async def get_text(self, selector: str) -> Optional[str]:
        """Get text content of an element."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        if await locator.count() > 0:
            return await locator.first.text_content()
        return None

    async def get_input_value(self, selector: str) -> Optional[str]:
        """Get value of an input field."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        if await locator.count() > 0:
            return await locator.first.input_value()
        return None

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        return await locator.count() > 0 and await locator.first.is_visible()

    async def count_elements(self, selector: str) -> int:
        """Count elements matching selector."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        return await self._page.locator(selector).count()

    async def get_dropdown_options(self, selector: str) -> List[str]:
        """Get all options from a select dropdown."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(f"{selector} option")
        return await locator.all_text_contents()

    async def scroll_down(self, pixels: int = 500) -> None:
        """Scroll the page down."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.evaluate(f"window.scrollBy(0, {pixels})")

    async def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the page."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    async def get_page_content(self) -> str:
        """Get full page HTML content."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        return await self._page.content()

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript expression."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        return await self._page.evaluate(expression)

    async def wait(self, seconds: float) -> None:
        """Wait for a specified number of seconds."""
        await asyncio.sleep(seconds)

    async def press_key(self, selector: str, key: str) -> None:
        """Press a key on an element (e.g., 'Tab', 'Enter')."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        locator = self._page.locator(selector)
        await locator.press(key)


async def check_playwright_installed() -> bool:
    """Check if Playwright and Firefox are installed."""
    if not PLAYWRIGHT_AVAILABLE:
        return False

    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            await browser.close()
            return True
    except Exception:
        return False


def ensure_playwright_installed() -> None:
    """Ensure Playwright and Firefox are installed, install if missing."""
    import subprocess
    import sys

    if not PLAYWRIGHT_AVAILABLE:
        print("Installing Playwright...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        print("Installing Firefox browser...")
        subprocess.check_call(["playwright", "install", "firefox"])
    else:
        # Check if Firefox browser is installed by checking the executable
        # Avoid using asyncio.run() which conflicts with already-running event loops
        try:
            from playwright._impl._driver import compute_driver_executable

            driver_path = compute_driver_executable()
            # If we can compute the driver path, playwright is installed
            # The actual browser check happens when we try to launch
        except Exception:
            print("Installing Firefox browser for Playwright...")
            subprocess.check_call(["playwright", "install", "firefox"])
