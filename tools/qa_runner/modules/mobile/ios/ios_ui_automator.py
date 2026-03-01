"""
iOS UI Automator — UIAutomator-compatible interface for iOS simulator.

Uses xcrun simctl for interaction and macOS Vision framework for text detection.
Provides the same API surface as the Android UIAutomator so existing test cases
can run on iOS with minimal changes.
"""

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..device_helper import UIElement
from .vision_helper import TextRegion, VisionHelper
from .xcrun_helper import XCRunHelper


def _region_to_element(region: TextRegion) -> UIElement:
    """Convert a VisionHelper TextRegion to a UIElement."""
    return UIElement(
        text=region.text,
        bounds=(region.x, region.y, region.x + region.width, region.y + region.height),
        clickable=True,
        enabled=True,
    )


class iOSUIAutomator:
    """
    iOS equivalent of Android UIAutomator.

    Uses screenshot + Vision OCR for element discovery and xcrun simctl for interaction.
    Provides the same high-level methods as UIAutomator:
    - wait_for_text, is_text_visible, click_by_text, find_by_text
    - get_screen_text, dump_screen_info, refresh_hierarchy
    """

    def __init__(self, xcrun: XCRunHelper):
        self.xcrun = xcrun
        self.vision = VisionHelper()
        self._screenshot_dir = Path(tempfile.mkdtemp(prefix="ciris_ios_ui_"))
        self._screenshot_counter = 0
        self._cached_regions: List[TextRegion] = []
        self._cache_valid = False

    def _take_screenshot(self) -> str:
        """Take a screenshot and return its path."""
        self._screenshot_counter += 1
        path = str(self._screenshot_dir / f"screen_{self._screenshot_counter}.png")
        self.xcrun.screenshot(path)
        return path

    def refresh_hierarchy(self) -> None:
        """Refresh the cached UI state by taking a new screenshot and running OCR."""
        path = self._take_screenshot()
        self._cached_regions = self.vision.recognize_text(path)
        self._cache_valid = True

    def _ensure_fresh(self) -> None:
        """Ensure we have a fresh OCR scan."""
        if not self._cache_valid:
            self.refresh_hierarchy()

    # ========== Text Finding ==========

    def find_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find a UI element by its text content."""
        self._ensure_fresh()
        text_lower = text.lower()
        for region in self._cached_regions:
            if exact:
                if region.text == text:
                    return _region_to_element(region)
            else:
                if text_lower in region.text.lower():
                    return _region_to_element(region)
        return None

    def find_by_content_desc(self, desc: str, exact: bool = False) -> Optional[UIElement]:
        """Find by content description — falls back to text search on iOS."""
        return self.find_by_text(desc, exact=exact)

    def find_by_resource_id(self, resource_id: str) -> Optional[UIElement]:
        """Find by resource ID — not supported on iOS, returns None."""
        return None

    def find_by_class(self, class_name: str) -> List[UIElement]:
        """Find by class name — not supported via OCR, returns empty list."""
        return []

    def find_clickable(self) -> List[UIElement]:
        """Find all clickable elements — returns all detected text regions."""
        self._ensure_fresh()
        return [_region_to_element(r) for r in self._cached_regions]

    def is_text_visible(self, text: str, exact: bool = False) -> bool:
        """Check if text is currently visible on screen."""
        self._ensure_fresh()
        text_lower = text.lower()
        for region in self._cached_regions:
            if exact:
                if region.text == text:
                    return True
            else:
                if text_lower in region.text.lower():
                    return True
        return False

    def wait_for_text(self, text: str, timeout: float = 30.0, interval: float = 1.0) -> Optional[UIElement]:
        """Wait for text to appear on screen."""
        start = time.time()
        while time.time() - start < timeout:
            self._cache_valid = False  # Force fresh screenshot
            element = self.find_by_text(text)
            if element:
                return element
            time.sleep(interval)
        return None

    def get_screen_text(self) -> List[str]:
        """Get all visible text on screen."""
        self._ensure_fresh()
        return [r.text for r in self._cached_regions]

    def dump_screen_info(self) -> Dict:
        """Dump screen state for debugging."""
        self._ensure_fresh()
        return {
            "texts": [r.text for r in self._cached_regions],
            "regions": len(self._cached_regions),
        }

    # ========== Click Operations ==========

    def click(self, element: UIElement) -> bool:
        """Click on a UI element."""
        cx, cy = element.center
        return self.xcrun.tap(cx, cy)

    def click_by_text(self, text: str, exact: bool = False) -> bool:
        """Find text and click it."""
        element = self.find_by_text(text, exact=exact)
        if element:
            return self.click(element)
        return False

    def click_by_resource_id(self, resource_id: str) -> bool:
        """Click by resource ID — not supported on iOS."""
        return False

    def click_by_content_desc(self, desc: str) -> bool:
        """Click by content description — falls back to text click."""
        return self.click_by_text(desc)

    # ========== Text Input ==========

    def set_text(self, element: UIElement, text: str) -> bool:
        """Set text on an element (tap + clear + type)."""
        # Tap the element first
        self.click(element)
        time.sleep(0.3)
        # Select all and delete existing text
        # On iOS simulator, Cmd+A then Delete
        self.xcrun.input_text(text)
        return True

    # ========== Google Lens (Android-only, no-ops on iOS) ==========

    def is_google_lens_open(self) -> bool:
        """Google Lens detection — not applicable on iOS."""
        return False

    def dismiss_google_lens(self) -> None:
        """Google Lens dismissal — not applicable on iOS."""
        pass

    # ========== Utility ==========

    def get_elements(self, refresh: bool = True) -> List[UIElement]:
        """Get all detected elements."""
        if refresh:
            self._cache_valid = False
        self._ensure_fresh()
        return [_region_to_element(r) for r in self._cached_regions]
