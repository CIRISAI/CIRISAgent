"""
Mobile infrastructure tests.

Tests for Python runtime, server startup, and service initialization
specific to the Android mobile platform.
"""

import time
from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class MobileTestResult:
    """Result of a mobile test."""

    name: str
    passed: bool
    duration: float
    message: str
    details: Optional[dict] = None


class MobileTestModule:
    """Mobile infrastructure test module."""

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 30.0):
        self.base_url = base_url
        self.timeout = timeout

    def run_all(self) -> List[MobileTestResult]:
        """Run all mobile tests."""
        results = []
        results.append(self.test_server_reachable())
        results.append(self.test_health_endpoint())
        results.append(self.test_services_count())
        results.append(self.test_telemetry_unified())
        return results

    def test_server_reachable(self) -> MobileTestResult:
        """Test that server is reachable."""
        start = time.time()
        try:
            response = requests.get(f"{self.base_url}/v1/system/health", timeout=5)
            return MobileTestResult(
                name="server_reachable",
                passed=response.status_code == 200,
                duration=time.time() - start,
                message=f"HTTP {response.status_code}",
            )
        except Exception as e:
            return MobileTestResult(name="server_reachable", passed=False, duration=time.time() - start, message=str(e))

    def test_health_endpoint(self) -> MobileTestResult:
        """Test health endpoint returns valid JSON."""
        start = time.time()
        try:
            response = requests.get(f"{self.base_url}/v1/system/health", timeout=5)
            data = response.json()

            required_fields = ["healthy", "services_online", "services_total"]
            missing = [f for f in required_fields if f not in data]

            return MobileTestResult(
                name="health_endpoint",
                passed=len(missing) == 0,
                duration=time.time() - start,
                message="Valid response" if not missing else f"Missing: {missing}",
                details=data,
            )
        except Exception as e:
            return MobileTestResult(name="health_endpoint", passed=False, duration=time.time() - start, message=str(e))

    def test_services_count(self) -> MobileTestResult:
        """Test that services are starting up."""
        start = time.time()
        try:
            response = requests.get(f"{self.base_url}/v1/system/health", timeout=5)
            data = response.json()

            services_online = data.get("services_online", 0)
            services_total = data.get("services_total", 22)

            # In first-run mode, expect 10 services
            # In full mode, expect 22 services
            min_expected = 10

            return MobileTestResult(
                name="services_count",
                passed=services_online >= min_expected,
                duration=time.time() - start,
                message=f"{services_online}/{services_total} services online",
                details={"online": services_online, "total": services_total},
            )
        except Exception as e:
            return MobileTestResult(name="services_count", passed=False, duration=time.time() - start, message=str(e))

    def test_telemetry_unified(self) -> MobileTestResult:
        """Test unified telemetry endpoint."""
        start = time.time()
        try:
            # Need auth for telemetry
            # For now, just check endpoint exists
            response = requests.get(f"{self.base_url}/v1/telemetry/unified", timeout=5)

            # 401 is expected without auth, 200 with auth
            passed = response.status_code in [200, 401]

            return MobileTestResult(
                name="telemetry_unified",
                passed=passed,
                duration=time.time() - start,
                message=f"HTTP {response.status_code}",
            )
        except Exception as e:
            return MobileTestResult(
                name="telemetry_unified", passed=False, duration=time.time() - start, message=str(e)
            )
