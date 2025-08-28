#!/usr/bin/env python3
"""
Production route validation script for CIRISManager.

This script validates all nginx routes including:
- Health checks
- Manager UI and API
- Agent GUI routes (client-side routing)
- Agent API routes
- Documentation endpoints
- OAuth callbacks

Usage:
    python validate_prod_routes.py [--host HOST] [--agent AGENT] [--verbose]

Examples:
    python validate_prod_routes.py
    python validate_prod_routes.py --host https://agents.ciris.ai --agent datum
    python validate_prod_routes.py --host http://localhost --agent test-agent --verbose
"""

import argparse
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"


class RouteValidator:
    def __init__(self, host: str, verbose: bool = False):
        self.host = host.rstrip("/")
        self.verbose = verbose
        self.client = httpx.Client(base_url=self.host, verify=True, timeout=10.0)

    def __enter__(self) -> "RouteValidator":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.client.close()

    def log(self, message: str, level: str = "INFO") -> None:
        """Log a message with color coding."""
        if level == "DEBUG" and not self.verbose:
            return

        color = {
            "DEBUG": CYAN,
            "INFO": "",
            "SUCCESS": GREEN,
            "WARNING": YELLOW,
            "ERROR": RED,
            "HEADER": BLUE + BOLD,
        }.get(level, "")

        print(f"{color}{message}{RESET}")

    def test_route(
        self,
        path: str,
        expected_status: int,
        description: str,
        check_content: Optional[str] = None,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Test a single route with verbose output."""

        url = f"{path}"
        self.log(f"\nTesting: {description}", "DEBUG")
        self.log(f"  URL: {self.host}{url}", "DEBUG")
        self.log(f"  Method: {method}", "DEBUG")
        self.log(f"  Expected Status: {expected_status}", "DEBUG")

        try:
            # Make request
            start_time = datetime.now()
            if method == "GET":
                response = self.client.get(url, follow_redirects=False, headers=headers)
            elif method == "POST":
                response = self.client.post(url, json=json_body, follow_redirects=False, headers=headers)
            else:
                response = self.client.request(method, url, follow_redirects=False, headers=headers)

            elapsed = (datetime.now() - start_time).total_seconds()

            # Log response details
            self.log(f"  Response Status: {response.status_code}", "DEBUG")
            self.log(f"  Response Time: {elapsed:.3f}s", "DEBUG")
            self.log("  Response Headers:", "DEBUG")
            for header, value in response.headers.items():
                if header.lower() in ["server", "content-type", "location", "x-powered-by"]:
                    self.log(f"    {header}: {value}", "DEBUG")

            # Check status code
            status_ok = response.status_code == expected_status

            # Check content if specified
            content_ok = True
            content_msg = ""
            if check_content and status_ok:
                if check_content in response.text:
                    content_ok = True
                    content_msg = " (contains expected content)"
                    self.log(f"  Content Check: PASS - Found '{check_content[:50]}'", "DEBUG")
                else:
                    content_ok = False
                    content_msg = f" (missing expected content: '{check_content}')"
                    self.log(f"  Content Check: FAIL - Expected '{check_content[:50]}'", "DEBUG")
                    self.log(f"  Actual content (first 200 chars): {response.text[:200]}", "DEBUG")

            # Determine result
            if status_ok and content_ok:
                result_msg = f"{GREEN}✓{RESET} {description}: {response.status_code}{content_msg} ({elapsed:.3f}s)"
                return True, result_msg
            elif not status_ok:
                result_msg = f"{RED}✗{RESET} {description}: Expected {expected_status}, got {response.status_code} ({elapsed:.3f}s)"
                if self.verbose and response.text:
                    self.log(f"  Response body (first 200 chars): {response.text[:200]}", "DEBUG")
                return False, result_msg
            else:
                result_msg = f"{RED}✗{RESET} {description}: {response.status_code}{content_msg} ({elapsed:.3f}s)"
                return False, result_msg

        except httpx.TimeoutException:
            return False, f"{RED}✗{RESET} {description}: Request timed out after 10s"
        except Exception as e:
            self.log(f"  Exception: {type(e).__name__}: {str(e)}", "ERROR")
            return False, f"{RED}✗{RESET} {description}: {str(e)}"

    def validate_agent_routes(self, agent_id: str) -> Tuple[int, int, int]:
        """Validate all routes for a specific agent."""
        self.log(f"\n{MAGENTA}{'='*70}{RESET}", "HEADER")
        self.log(f"Validating routes for agent: {BOLD}{agent_id}{RESET}", "HEADER")
        self.log(f"{MAGENTA}{'='*70}{RESET}", "HEADER")

        routes = [
            # Agent API routes
            (
                f"/api/{agent_id}/v1/agent/status",
                401,
                f"[{agent_id}] API status endpoint",
                None,
                "GET",
            ),
            (
                f"/api/{agent_id}/v1/agent/identity",
                401,
                f"[{agent_id}] API identity endpoint",
                None,
                "GET",
            ),
            (
                f"/api/{agent_id}/v1/system/health",
                200,
                f"[{agent_id}] API health check",
                "healthy",
                "GET",
            ),
            # Documentation routes (should work after fix)
            (f"/api/{agent_id}/docs", 200, f"[{agent_id}] Swagger UI", "<title>", "GET"),
            (f"/api/{agent_id}/redoc", 200, f"[{agent_id}] ReDoc UI", "<title>", "GET"),
            (
                f"/api/{agent_id}/openapi.json",
                200,
                f"[{agent_id}] OpenAPI spec",
                '"openapi"',
                "GET",
            ),
            # OAuth callback routes
            (
                f"/v1/auth/oauth/{agent_id}/google/callback",
                422,
                f"[{agent_id}] Google OAuth callback",
                None,
                "GET",
            ),
            (
                f"/v1/auth/oauth/{agent_id}/github/callback",
                422,
                f"[{agent_id}] GitHub OAuth callback",
                None,
                "GET",
            ),
            # Note: Agent GUI uses client-side routing - /agent/{id} paths are handled by React router
            # The nginx location ~ ^/agent/([^/]+) proxies to agent_gui which serves the React app
        ]

        passed = 0
        failed = 0
        warnings = 0

        for path, expected_status, description, check_content, method in routes:
            success, message = self.test_route(path, expected_status, description, check_content, method)
            print(message)

            if success:
                passed += 1
            else:
                # Check if it's a known issue
                if any(x in path for x in ["docs", "redoc", "openapi"]):
                    warnings += 1
                    self.log(
                        f"  {YELLOW}→ Known issue: Documentation routes pending fix deployment{RESET}",
                        "WARNING",
                    )
                elif "/agent/" in path and "client-side" in description:
                    warnings += 1
                    self.log(
                        f"  {YELLOW}→ Note: Agent GUI uses client-side routing from root{RESET}",
                        "WARNING",
                    )
                else:
                    failed += 1

        return passed, failed, warnings

    def validate_manager_routes(self) -> Tuple[int, int, int]:
        """Validate all manager routes."""
        self.log(f"\n{MAGENTA}{'='*70}{RESET}", "HEADER")
        self.log("Validating Manager routes", "HEADER")
        self.log(f"{MAGENTA}{'='*70}{RESET}", "HEADER")

        routes = [
            # Health check
            ("/health", 200, "Nginx health check", "healthy", "GET"),
            # Manager UI and API
            ("/manager/", 303, "Manager UI (should redirect to auth)", None, "GET"),
            ("/manager/v1/status", 200, "Manager API status", '"status"', "GET"),
            ("/manager/v1/agents", 200, "Manager API agents list", '"agents"', "GET"),
            ("/manager/v1/templates", 200, "Manager API templates", '"templates"', "GET"),
            ("/manager/v1/health", 200, "Manager API health", '"status"', "GET"),
            # Manager OAuth
            ("/manager/v1/oauth/login", 307, "Manager OAuth login redirect", None, "GET"),
            # Root GUI
            ("/", 200, "Root (Agent GUI)", "<!DOCTYPE html>", "GET"),
            # Non-existent routes return 404 (not GUI - this is intentional)
            ("/this-route-does-not-exist", 404, "Non-existent route returns 404", None, "GET"),
        ]

        passed = 0
        failed = 0
        warnings = 0

        for path, expected_status, description, check_content, method in routes:
            success, message = self.test_route(path, expected_status, description, check_content, method)
            print(message)

            if success:
                passed += 1
            else:
                failed += 1

        return passed, failed, warnings

    def run_full_validation(self, agent_ids: List[str]) -> bool:
        """Run complete validation for all agents."""
        self.log(f"\n{BLUE}{BOLD}CIRISManager Production Route Validation{RESET}", "HEADER")
        self.log(f"{BLUE}Host: {self.host}{RESET}", "HEADER")
        self.log(f"{BLUE}Time: {datetime.now()}{RESET}", "HEADER")
        self.log(f"{BLUE}Agents to test: {', '.join(agent_ids)}{RESET}", "HEADER")

        total_passed = 0
        total_failed = 0
        total_warnings = 0

        # Test manager routes
        passed, failed, warnings = self.validate_manager_routes()
        total_passed += passed
        total_failed += failed
        total_warnings += warnings

        # Test each agent
        for agent_id in agent_ids:
            passed, failed, warnings = self.validate_agent_routes(agent_id)
            total_passed += passed
            total_failed += failed
            total_warnings += warnings

        # Summary
        self.log(f"\n{MAGENTA}{'='*70}{RESET}", "HEADER")
        self.log(f"{BOLD}VALIDATION SUMMARY{RESET}", "HEADER")
        self.log(f"{MAGENTA}{'='*70}{RESET}", "HEADER")

        print(f"Results: {GREEN}{total_passed} passed{RESET}, ", end="")
        if total_failed > 0:
            print(f"{RED}{total_failed} failed{RESET}, ", end="")
        else:
            print("0 failed, ", end="")
        if total_warnings > 0:
            print(f"{YELLOW}{total_warnings} warnings{RESET}")
        else:
            print("0 warnings")

        if total_failed > 0:
            self.log(f"\n{RED}{BOLD}❌ VALIDATION FAILED{RESET}", "ERROR")
            self.log("Some routes are not working correctly!", "ERROR")
            return False
        elif total_warnings > 0:
            self.log(f"\n{YELLOW}{BOLD}⚠️  VALIDATION PASSED WITH WARNINGS{RESET}", "WARNING")
            self.log("Known issues exist but core functionality works", "WARNING")
            return True
        else:
            self.log(f"\n{GREEN}{BOLD}✅ ALL ROUTES VALIDATED SUCCESSFULLY!{RESET}", "SUCCESS")
            return True


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate CIRISManager production routes")
    parser.add_argument(
        "--host",
        default="https://agents.ciris.ai",
        help="Host to test (default: https://agents.ciris.ai)",
    )
    parser.add_argument(
        "--agent",
        action="append",
        dest="agents",
        help="Agent ID to test (can be specified multiple times)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Default to testing datum if no agents specified
    if not args.agents:
        args.agents = ["datum"]

    # Run validation
    with RouteValidator(args.host, args.verbose) as validator:
        success = validator.run_full_validation(args.agents)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
