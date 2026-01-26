"""
UI Automator Helper for Mobile QA Testing

Provides utilities for interacting with Android UI elements.
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .adb_helper import ADBHelper


@dataclass
class UIElement:
    """Represents a UI element from the hierarchy."""

    resource_id: str
    text: str
    content_desc: str
    class_name: str
    package: str
    bounds: Tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool
    enabled: bool
    focused: bool
    checkable: bool
    checked: bool
    scrollable: bool

    @property
    def center(self) -> Tuple[int, int]:
        """Get center coordinates of the element."""
        return (
            (self.bounds[0] + self.bounds[2]) // 2,
            (self.bounds[1] + self.bounds[3]) // 2,
        )

    @property
    def width(self) -> int:
        """Get element width."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        """Get element height."""
        return self.bounds[3] - self.bounds[1]


class UIAutomator:
    """UI Automator wrapper for element finding and interaction."""

    def __init__(self, adb: ADBHelper):
        """
        Initialize UI Automator.

        Args:
            adb: ADBHelper instance for device communication.
        """
        self.adb = adb
        self._last_hierarchy: Optional[str] = None
        self._last_elements: List[UIElement] = []

    def refresh_hierarchy(self) -> str:
        """Refresh the UI hierarchy dump."""
        self._last_hierarchy = self.adb.dump_ui_hierarchy()
        self._last_elements = self._parse_hierarchy(self._last_hierarchy)
        return self._last_hierarchy

    def _parse_bounds(self, bounds_str: str) -> Tuple[int, int, int, int]:
        """Parse bounds string like '[0,0][1080,1920]' to tuple."""
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if match:
            return (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
            )
        return (0, 0, 0, 0)

    def _parse_hierarchy(self, xml_content: str) -> List[UIElement]:
        """Parse UI hierarchy XML into UIElement list."""
        elements = []

        try:
            root = ET.fromstring(xml_content)
            for node in root.iter("node"):
                element = UIElement(
                    resource_id=node.get("resource-id", ""),
                    text=node.get("text", ""),
                    content_desc=node.get("content-desc", ""),
                    class_name=node.get("class", ""),
                    package=node.get("package", ""),
                    bounds=self._parse_bounds(node.get("bounds", "[0,0][0,0]")),
                    clickable=node.get("clickable", "false") == "true",
                    enabled=node.get("enabled", "true") == "true",
                    focused=node.get("focused", "false") == "true",
                    checkable=node.get("checkable", "false") == "true",
                    checked=node.get("checked", "false") == "true",
                    scrollable=node.get("scrollable", "false") == "true",
                )
                elements.append(element)
        except ET.ParseError as e:
            print(f"Warning: Failed to parse UI hierarchy: {e}")

        return elements

    def get_elements(self, refresh: bool = True) -> List[UIElement]:
        """Get all UI elements."""
        if refresh or not self._last_elements:
            self.refresh_hierarchy()
        return self._last_elements

    def find_by_resource_id(self, resource_id: str, refresh: bool = True) -> Optional[UIElement]:
        """Find element by resource ID."""
        elements = self.get_elements(refresh)
        for element in elements:
            if resource_id in element.resource_id:
                return element
        return None

    def find_by_text(self, text: str, exact: bool = False, refresh: bool = True) -> Optional[UIElement]:
        """Find element by text content."""
        elements = self.get_elements(refresh)
        for element in elements:
            if exact:
                if element.text == text:
                    return element
            else:
                if text.lower() in element.text.lower():
                    return element
        return None

    def find_by_content_desc(self, desc: str, exact: bool = False, refresh: bool = True) -> Optional[UIElement]:
        """Find element by content description."""
        elements = self.get_elements(refresh)
        for element in elements:
            if exact:
                if element.content_desc == desc:
                    return element
            else:
                if desc.lower() in element.content_desc.lower():
                    return element
        return None

    def find_by_class(self, class_name: str, refresh: bool = True) -> List[UIElement]:
        """Find all elements by class name."""
        elements = self.get_elements(refresh)
        return [e for e in elements if class_name in e.class_name]

    def find_clickable(self, refresh: bool = True) -> List[UIElement]:
        """Find all clickable elements."""
        elements = self.get_elements(refresh)
        return [e for e in elements if e.clickable and e.enabled]

    def find_by_predicate(self, predicate: Callable[[UIElement], bool], refresh: bool = True) -> List[UIElement]:
        """Find elements matching a custom predicate."""
        elements = self.get_elements(refresh)
        return [e for e in elements if predicate(e)]

    def click(self, element: UIElement) -> bool:
        """Click on an element."""
        x, y = element.center
        return self.adb.tap(x, y)

    def click_by_text(self, text: str, exact: bool = False) -> bool:
        """Find and click element by text."""
        element = self.find_by_text(text, exact)
        if element:
            return self.click(element)
        return False

    def click_by_resource_id(self, resource_id: str) -> bool:
        """Find and click element by resource ID."""
        element = self.find_by_resource_id(resource_id)
        if element:
            return self.click(element)
        return False

    def click_by_content_desc(self, desc: str, exact: bool = False) -> bool:
        """Find and click element by content description."""
        element = self.find_by_content_desc(desc, exact)
        if element:
            return self.click(element)
        return False

    def set_text(self, element: UIElement, text: str, clear_first: bool = True) -> bool:
        """Set text on an element (typically EditText)."""
        # Click to focus
        if not self.click(element):
            return False
        time.sleep(0.3)

        # Clear existing text if requested
        if clear_first:
            # Select all and delete
            self.adb.press_key("KEYCODE_CTRL_LEFT")
            time.sleep(0.1)
            self.adb.press_key("KEYCODE_A")
            time.sleep(0.1)
            self.adb.press_key("KEYCODE_DEL")
            time.sleep(0.1)

        # Input new text
        return self.adb.input_text(text)

    def set_text_by_resource_id(self, resource_id: str, text: str, clear_first: bool = True) -> bool:
        """Find element by resource ID and set text."""
        element = self.find_by_resource_id(resource_id)
        if element:
            return self.set_text(element, text, clear_first)
        return False

    def wait_for_element(
        self,
        finder: Callable[[], Optional[UIElement]],
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> Optional[UIElement]:
        """Wait for an element to appear."""
        start = time.time()
        while time.time() - start < timeout:
            element = finder()
            if element:
                return element
            time.sleep(poll_interval)
        return None

    def wait_for_text(self, text: str, timeout: float = 10.0, exact: bool = False) -> Optional[UIElement]:
        """Wait for element with specific text to appear."""
        return self.wait_for_element(
            lambda: self.find_by_text(text, exact, refresh=True),
            timeout=timeout,
        )

    def wait_for_resource_id(self, resource_id: str, timeout: float = 10.0) -> Optional[UIElement]:
        """Wait for element with specific resource ID to appear."""
        return self.wait_for_element(
            lambda: self.find_by_resource_id(resource_id, refresh=True),
            timeout=timeout,
        )

    def wait_for_text_gone(self, text: str, timeout: float = 10.0, exact: bool = False) -> bool:
        """Wait for element with specific text to disappear."""
        start = time.time()
        while time.time() - start < timeout:
            element = self.find_by_text(text, exact, refresh=True)
            if not element:
                return True
            time.sleep(0.5)
        return False

    def scroll_down(self, amount: int = 500) -> bool:
        """Scroll down on the screen."""
        width, height = self.adb.get_screen_size()
        center_x = width // 2
        start_y = height // 2 + amount // 2
        end_y = height // 2 - amount // 2
        return self.adb.swipe(center_x, start_y, center_x, end_y, 300)

    def scroll_up(self, amount: int = 500) -> bool:
        """Scroll up on the screen."""
        width, height = self.adb.get_screen_size()
        center_x = width // 2
        start_y = height // 2 - amount // 2
        end_y = height // 2 + amount // 2
        return self.adb.swipe(center_x, start_y, center_x, end_y, 300)

    def scroll_to_text(self, text: str, max_scrolls: int = 10, direction: str = "down") -> Optional[UIElement]:
        """Scroll until text is found."""
        for _ in range(max_scrolls):
            element = self.find_by_text(text)
            if element:
                return element

            if direction == "down":
                self.scroll_down()
            else:
                self.scroll_up()
            time.sleep(0.5)

        return None

    def is_text_visible(self, text: str, exact: bool = False) -> bool:
        """Check if text is visible on screen."""
        return self.find_by_text(text, exact, refresh=True) is not None

    def get_screen_text(self) -> List[str]:
        """Get all visible text on screen."""
        elements = self.get_elements(refresh=True)
        texts = []
        for element in elements:
            if element.text:
                texts.append(element.text)
            if element.content_desc:
                texts.append(element.content_desc)
        return texts

    def dump_screen_info(self) -> dict:
        """Dump current screen information for debugging."""
        elements = self.get_elements(refresh=True)
        return {
            "total_elements": len(elements),
            "clickable_elements": len([e for e in elements if e.clickable]),
            "texts": [e.text for e in elements if e.text],
            "content_descs": [e.content_desc for e in elements if e.content_desc],
            "resource_ids": [e.resource_id for e in elements if e.resource_id],
        }
