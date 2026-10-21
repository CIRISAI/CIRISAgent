"""
Verify Trust Page Tests for CIRIS Mobile App.

Validates that the Trust and Security page displays correct CIRISVerify
attestation information including:
- Key storage mode (hardware vs software)
- Ed25519 fingerprint
- Binary self-check status
- Function self-check status
- File integrity counts
- Play Integrity status
- Registry key status
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .adb_helper import ADBHelper
from .test_cases import CIRISAppConfig, TestReport, TestResult
from .ui_automator import UIAutomator


@dataclass
class VerifyTrustExpectations:
    """Expected values for trust page validation."""

    # Key attestation
    hardware_backed: bool = True
    key_storage_contains: str = "HW-AES"  # Should contain this for hardware-backed
    fingerprint_length: int = 64  # SHA-256 hex is 64 chars

    # Platform
    target_triple_contains: str = "android"

    # File integrity (should have non-zero counts on Android)
    min_files_checked: int = 50
    min_files_total: int = 100

    # Self-verification (may fail due to registry manifest bug, but should show status)
    binary_self_check_not_null: bool = True
    function_self_check_not_null: bool = True


class VerifyTrustTests:
    """Test suite for Trust and Security page verification."""

    def __init__(
        self,
        adb: ADBHelper,
        ui: UIAutomator,
        device_id: Optional[str] = None,
        expectations: Optional[VerifyTrustExpectations] = None,
    ):
        self.adb = adb
        self.ui = ui
        self.device_id = device_id
        self.expectations = expectations or VerifyTrustExpectations()
        self.package = CIRISAppConfig.PACKAGE

    def run_all(self) -> List[TestReport]:
        """Run all verify trust tests."""
        reports = []

        # Navigate to trust page first
        nav_report = self._navigate_to_trust_page()
        reports.append(nav_report)
        if nav_report.result != TestResult.PASSED:
            return reports

        # Wait for page to load
        time.sleep(3)

        # Run validation tests
        reports.append(self._test_key_storage_display())
        reports.append(self._test_fingerprint_display())
        reports.append(self._test_target_triple_display())
        reports.append(self._test_file_integrity_counts())
        reports.append(self._test_binary_self_check())
        reports.append(self._test_function_self_check())
        reports.append(self._test_play_integrity_display())
        reports.append(self._test_raw_details_expansion())

        return reports

    def _navigate_to_trust_page(self) -> TestReport:
        """Navigate to the Trust and Security page."""
        start = time.time()
        try:
            # Try clicking hamburger menu
            if self.ui.click_by_content_desc("Open navigation drawer"):
                time.sleep(1)
            elif self.ui.click_by_content_desc("Menu"):
                time.sleep(1)
            else:
                # Try finding overflow menu
                self.ui.click_by_content_desc("More options")
                time.sleep(1)

            # Click Trust and Security
            if self.ui.click_by_text("Trust and Security"):
                time.sleep(2)
                return TestReport(
                    name="navigate_to_trust",
                    result=TestResult.PASSED,
                    duration=time.time() - start,
                    message="Successfully navigated to Trust and Security page",
                )

            # Alternative: Try via Settings
            if self.ui.click_by_text("Settings"):
                time.sleep(1)
                if self.ui.click_by_text("Trust and Security"):
                    time.sleep(2)
                    return TestReport(
                        name="navigate_to_trust",
                        result=TestResult.PASSED,
                        duration=time.time() - start,
                        message="Navigated via Settings -> Trust and Security",
                    )

            return TestReport(
                name="navigate_to_trust",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Could not find Trust and Security menu item",
            )
        except Exception as e:
            return TestReport(
                name="navigate_to_trust",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Navigation error: {e}",
            )

    def _get_screen_text(self) -> str:
        """Get all text from current screen via UI dump."""
        try:
            dump = self.ui.dump_ui()
            # Extract all text content
            texts = re.findall(r'text="([^"]*)"', dump)
            return "\n".join(texts)
        except Exception:
            return ""

    def _test_key_storage_display(self) -> TestReport:
        """Test that key storage mode is displayed correctly."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Check for hardware-backed indicator
            if self.expectations.hardware_backed:
                # Should show HW-AES or ANDROID_KEYSTORE or Hardware
                if any(x in screen_text.upper() for x in ["HW-AES", "ANDROID_KEYSTORE", "HARDWARE", "HARDWARE-BACKED"]):
                    return TestReport(
                        name="key_storage_display",
                        result=TestResult.PASSED,
                        duration=time.time() - start,
                        message="Hardware-backed key storage displayed correctly",
                    )
                # Check if showing SOFTWARE when should be hardware
                if "SOFTWARE" in screen_text.upper() and "HARDWARE" not in screen_text.upper():
                    return TestReport(
                        name="key_storage_display",
                        result=TestResult.FAILED,
                        duration=time.time() - start,
                        message="Shows SOFTWARE but expected HARDWARE-backed storage",
                    )
            return TestReport(
                name="key_storage_display",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message=f"Key storage indicator not found in screen",
            )
        except Exception as e:
            return TestReport(
                name="key_storage_display",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking key storage: {e}",
            )

    def _test_fingerprint_display(self) -> TestReport:
        """Test that Ed25519 fingerprint is displayed."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for hex fingerprint pattern (64 hex chars)
            fingerprint_pattern = r"[a-f0-9]{64}"
            matches = re.findall(fingerprint_pattern, screen_text.lower())

            if matches:
                return TestReport(
                    name="fingerprint_display",
                    result=TestResult.PASSED,
                    duration=time.time() - start,
                    message=f"Found fingerprint: {matches[0][:16]}...",
                )

            # Check for truncated fingerprint (with ...)
            truncated_pattern = r"[a-f0-9]{16,}\.\.\.?"
            truncated = re.findall(truncated_pattern, screen_text.lower())
            if truncated:
                return TestReport(
                    name="fingerprint_display",
                    result=TestResult.PASSED,
                    duration=time.time() - start,
                    message=f"Found truncated fingerprint: {truncated[0]}",
                )

            return TestReport(
                name="fingerprint_display",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="No Ed25519 fingerprint found on screen",
            )
        except Exception as e:
            return TestReport(
                name="fingerprint_display",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking fingerprint: {e}",
            )

    def _test_target_triple_display(self) -> TestReport:
        """Test that target triple (platform) is displayed."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for android target triple
            if "aarch64-linux-android" in screen_text.lower() or "android" in screen_text.lower():
                return TestReport(
                    name="target_triple_display",
                    result=TestResult.PASSED,
                    duration=time.time() - start,
                    message="Target triple/platform displayed correctly",
                )

            return TestReport(
                name="target_triple_display",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Target triple not found on screen",
            )
        except Exception as e:
            return TestReport(
                name="target_triple_display",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking target triple: {e}",
            )

    def _test_file_integrity_counts(self) -> TestReport:
        """Test that file integrity counts are displayed and non-zero."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for file count patterns like "102/925" or "Files: 102/925"
            count_pattern = r"(\d+)\s*/\s*(\d+)"
            matches = re.findall(count_pattern, screen_text)

            for checked, total in matches:
                checked_int = int(checked)
                total_int = int(total)
                if (
                    checked_int >= self.expectations.min_files_checked
                    and total_int >= self.expectations.min_files_total
                ):
                    return TestReport(
                        name="file_integrity_counts",
                        result=TestResult.PASSED,
                        duration=time.time() - start,
                        message=f"File counts displayed: {checked_int}/{total_int}",
                    )

            # Check for 0/0 which indicates parsing issue
            if "0/0" in screen_text or "0 / 0" in screen_text:
                return TestReport(
                    name="file_integrity_counts",
                    result=TestResult.FAILED,
                    duration=time.time() - start,
                    message="File counts show 0/0 - parsing issue in API client",
                )

            return TestReport(
                name="file_integrity_counts",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="File integrity counts not found or too low",
            )
        except Exception as e:
            return TestReport(
                name="file_integrity_counts",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking file counts: {e}",
            )

    def _test_binary_self_check(self) -> TestReport:
        """Test that binary self-check status is displayed."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for binary check status
            binary_statuses = ["verified", "mismatch", "not_found", "unavailable", "not_checked"]
            found_status = None
            for status in binary_statuses:
                if status.lower() in screen_text.lower():
                    found_status = status
                    break

            if found_status:
                is_pass = found_status != "null" and self.expectations.binary_self_check_not_null
                return TestReport(
                    name="binary_self_check",
                    result=TestResult.PASSED if is_pass else TestResult.FAILED,
                    duration=time.time() - start,
                    message=f"Binary self-check status: {found_status}",
                )

            # Check for null/None display
            if "null" in screen_text.lower() or "none" in screen_text.lower():
                return TestReport(
                    name="binary_self_check",
                    result=TestResult.FAILED,
                    duration=time.time() - start,
                    message="Binary self-check shows null/None - extraction issue",
                )

            return TestReport(
                name="binary_self_check",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Binary self-check status not found",
            )
        except Exception as e:
            return TestReport(
                name="binary_self_check",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking binary self-check: {e}",
            )

    def _test_function_self_check(self) -> TestReport:
        """Test that function self-check status is displayed."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for function check status
            func_statuses = ["verified", "no_manifest", "not_checked", "failed"]
            found_status = None
            for status in func_statuses:
                if status.lower().replace("_", " ") in screen_text.lower() or status.lower() in screen_text.lower():
                    found_status = status
                    break

            if found_status:
                return TestReport(
                    name="function_self_check",
                    result=TestResult.PASSED,
                    duration=time.time() - start,
                    message=f"Function self-check status: {found_status}",
                )

            # Check for null/None display
            if "null" in screen_text.lower() and "function" in screen_text.lower():
                return TestReport(
                    name="function_self_check",
                    result=TestResult.FAILED,
                    duration=time.time() - start,
                    message="Function self-check shows null - extraction issue",
                )

            return TestReport(
                name="function_self_check",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Function self-check status not found",
            )
        except Exception as e:
            return TestReport(
                name="function_self_check",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking function self-check: {e}",
            )

    def _test_play_integrity_display(self) -> TestReport:
        """Test that Play Integrity status is displayed."""
        start = time.time()
        try:
            screen_text = self._get_screen_text()

            # Look for Play Integrity indicators
            play_indicators = [
                "play integrity",
                "device integrity",
                "device attestation",
                "google play",
                "strong integrity",
                "basic integrity",
            ]

            for indicator in play_indicators:
                if indicator.lower() in screen_text.lower():
                    # Check if showing passed/verified
                    has_pass = any(x in screen_text.lower() for x in ["passed", "verified", "true", "✓"])
                    return TestReport(
                        name="play_integrity_display",
                        result=TestResult.PASSED,
                        duration=time.time() - start,
                        message=f"Play Integrity displayed (passed={has_pass})",
                    )

            return TestReport(
                name="play_integrity_display",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Play Integrity status not found on screen",
            )
        except Exception as e:
            return TestReport(
                name="play_integrity_display",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error checking Play Integrity: {e}",
            )

    def _test_raw_details_expansion(self) -> TestReport:
        """Test that raw details can be expanded and shows data."""
        start = time.time()
        try:
            # Try to click "Raw Details" to expand
            if self.ui.click_by_text("Raw Details"):
                time.sleep(1)
                screen_text = self._get_screen_text()

                # Check for expected raw detail fields
                expected_fields = ["binary", "env", "dns", "https", "registry", "audit"]
                found_fields = sum(1 for f in expected_fields if f.lower() in screen_text.lower())

                if found_fields >= 3:
                    return TestReport(
                        name="raw_details_expansion",
                        result=TestResult.PASSED,
                        duration=time.time() - start,
                        message=f"Raw details expanded, found {found_fields}/{len(expected_fields)} fields",
                    )

            return TestReport(
                name="raw_details_expansion",
                result=TestResult.FAILED,
                duration=time.time() - start,
                message="Could not expand raw details or fields missing",
            )
        except Exception as e:
            return TestReport(
                name="raw_details_expansion",
                result=TestResult.ERROR,
                duration=time.time() - start,
                message=f"Error expanding raw details: {e}",
            )


def run_verify_trust_tests(device_id: Optional[str] = None, verbose: bool = False) -> Tuple[bool, List[TestReport]]:
    """
    Run verify trust page tests.

    Args:
        device_id: Optional ADB device ID
        verbose: Enable verbose output

    Returns:
        Tuple of (all_passed, reports)
    """
    adb = ADBHelper(device_id=device_id)
    ui = UIAutomator(adb)

    tests = VerifyTrustTests(adb, ui, device_id)
    reports = tests.run_all()

    all_passed = all(r.result == TestResult.PASSED for r in reports)
    return all_passed, reports
