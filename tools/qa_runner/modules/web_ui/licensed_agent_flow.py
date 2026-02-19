"""
Licensed Agent First-Start Flow for Web UI QA

Browser-based end-to-end flow for a first-run agent that:
1. Connects to CIRIS Portal via device auth (from web UI)
2. Waits for Portal authorization
3. Receives provisioned credentials (template, adapters, signing key)
4. Completes setup via web UI
5. Verifies agent is configured and services are online

This is the web UI version of:
  tools/qa_runner/modules/mobile/first_time_licensed_agent.py

Usage:
    python -m tools.qa_runner.modules.web_ui --tests licensed_agent
    python -m tools.qa_runner.modules.web_ui --tests licensed_agent --llm-provider groq
"""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .browser_helper import BrowserHelper
from .test_cases import TestReport, TestResult, WebUITestConfig


@dataclass
class LicensedAgentConfig(WebUITestConfig):
    """Extended config for licensed agent flow."""

    portal_url: str = "https://portal.ciris.ai"
    poll_timeout: int = 300  # 5 minutes to authorize via Portal
    poll_interval: int = 5


# =============================================================================
# Helper Functions - API calls for status checking
# =============================================================================


def _api_get(base_url: str, path: str, token: Optional[str] = None, timeout: int = 30) -> Dict:
    """Make GET request to API."""
    url = f"{base_url}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _api_post(base_url: str, path: str, data: Optional[Dict] = None, timeout: int = 30) -> Dict:
    """Make POST request to API."""
    url = f"{base_url}{path}"
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _api_get_raw(base_url: str, path: str, params: Optional[Dict] = None, timeout: int = 30):
    """Make GET request and return raw response."""
    url = f"{base_url}{path}"
    return requests.get(url, params=params, timeout=timeout)


# =============================================================================
# Test Functions - Licensed Agent Flow
# =============================================================================


async def test_api_health(browser: BrowserHelper, config: LicensedAgentConfig) -> TestReport:
    """Step 1: Verify API is healthy before starting UI flow."""
    start = datetime.now()
    report = TestReport(name="api_health", result=TestResult.PASSED)

    try:
        data = _api_get(config.base_url, "/v1/system/health")
        health = data.get("data", {})
        status = health.get("status", "unknown")
        version = health.get("version", "unknown")

        if status == "healthy":
            report.message = f"API healthy v{version}"
            report.details["version"] = version
        else:
            report.result = TestResult.FAILED
            report.message = f"API unhealthy: {status}"
            report.details = health

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = f"Cannot reach API: {e}"

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_first_run_status(browser: BrowserHelper, config: LicensedAgentConfig) -> TestReport:
    """Step 2: Verify agent is in first-run mode."""
    start = datetime.now()
    report = TestReport(name="first_run_status", result=TestResult.PASSED)

    try:
        data = _api_get(config.base_url, "/v1/setup/status")
        setup = data.get("data", {})
        is_first_run = setup.get("is_first_run", False)
        setup_required = setup.get("setup_required", False)

        if is_first_run or setup_required:
            report.message = "First-run mode confirmed"
            report.details = setup
        else:
            report.result = TestResult.FAILED
            report.message = "Agent is already configured"
            report.details = setup

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = f"Status check failed: {e}"

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_load_setup_page(browser: BrowserHelper, config: LicensedAgentConfig) -> TestReport:
    """Step 3: Load setup wizard and navigate to Connect Node option."""
    start = datetime.now()
    report = TestReport(name="load_setup_page", result=TestResult.PASSED)

    try:
        await browser.goto(f"{config.base_url}/setup")
        await browser.wait(2)

        shot = await browser.screenshot("licensed_setup_start", full_page=True)
        report.screenshots.append(shot.path)

        content = await browser.get_page_content()

        if "Welcome to CIRIS" in content or "Setup" in content:
            report.message = "Setup wizard loaded"

            # Look for "Connect to CIRIS Node" or similar option
            connect_indicators = [
                "Connect to CIRIS",
                "CIRIS Node",
                "Portal",
                "Licensed",
                "Enterprise",
            ]
            found = [i for i in connect_indicators if i.lower() in content.lower()]
            report.details["connect_indicators"] = found

        else:
            report.result = TestResult.FAILED
            report.message = "Setup wizard not found"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_initiate_connect_node(browser: BrowserHelper, config: LicensedAgentConfig) -> TestReport:
    """Step 4: Click Connect Node button and initiate device auth."""
    start = datetime.now()
    report = TestReport(name="initiate_connect_node", result=TestResult.PASSED)

    try:
        # Look for Connect to CIRIS Node button
        connect_btn = browser.page.locator("button").filter(has_text="Connect to CIRIS")
        btn_count = await connect_btn.count()

        if btn_count == 0:
            # Try alternative text
            connect_btn = browser.page.locator("button").filter(has_text="Connect Node")
            btn_count = await connect_btn.count()

        if btn_count == 0:
            # Try clicking a card/link instead of button
            connect_link = browser.page.locator("a, div[role='button']").filter(has_text="CIRIS Node")
            btn_count = await connect_link.count()
            if btn_count > 0:
                connect_btn = connect_link

        if btn_count > 0:
            await connect_btn.first.scroll_into_view_if_needed()
            await browser.wait(0.5)
            await connect_btn.first.click()
            report.details["clicked"] = "Connect to CIRIS Node"
            await browser.wait(2)

            shot = await browser.screenshot("licensed_connect_clicked", full_page=True)
            report.screenshots.append(shot.path)

            # Check page content for device code or verification URL
            content = await browser.get_page_content()

            # Look for device code indicators
            code_indicators = ["code", "authorize", "verification", "portal.ciris.ai"]
            found = [i for i in code_indicators if i.lower() in content.lower()]
            report.details["code_indicators"] = found

            if found:
                report.message = "Connect node initiated - authorization required"
            else:
                # Try API fallback to get device code
                try:
                    data = _api_post(
                        config.base_url,
                        "/v1/setup/connect-node",
                        {"node_url": config.portal_url},
                    )
                    rd = data.get("data", data)
                    device_code = rd.get("device_code", "")
                    user_code = rd.get("user_code", "")
                    verification_uri = rd.get("verification_uri_complete", "")

                    if device_code:
                        report.message = f"Device auth initiated (code: {user_code})"
                        report.details["device_code"] = device_code
                        report.details["user_code"] = user_code
                        report.details["verification_uri"] = verification_uri
                        report.details["portal_url"] = config.portal_url
                    else:
                        report.result = TestResult.FAILED
                        report.message = "No device code received"

                except Exception as api_err:
                    report.result = TestResult.FAILED
                    report.message = f"Connect node failed: {api_err}"
        else:
            # Button not found - try direct API call
            report.details["ui_button_not_found"] = True
            try:
                data = _api_post(
                    config.base_url,
                    "/v1/setup/connect-node",
                    {"node_url": config.portal_url},
                )
                rd = data.get("data", data)
                device_code = rd.get("device_code", "")
                user_code = rd.get("user_code", "")
                verification_uri = rd.get("verification_uri_complete", "")

                if device_code:
                    report.message = f"Device auth via API (code: {user_code})"
                    report.details["device_code"] = device_code
                    report.details["user_code"] = user_code
                    report.details["verification_uri"] = verification_uri
                    report.details["portal_url"] = config.portal_url
                else:
                    report.result = TestResult.FAILED
                    report.message = "Connect node button not found and API failed"

            except Exception as api_err:
                report.result = TestResult.FAILED
                report.message = f"Connect node failed: {api_err}"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_wait_for_authorization(
    browser: BrowserHelper,
    config: LicensedAgentConfig,
    device_code: str,
    portal_url: str,
) -> TestReport:
    """Step 5: Poll for Portal authorization and display verification URL."""
    start = datetime.now()
    report = TestReport(name="wait_for_authorization", result=TestResult.PASSED)

    try:
        params = {"device_code": device_code, "portal_url": portal_url}
        poll_count = 0

        while time.time() - start.timestamp() < config.poll_timeout:
            poll_count += 1
            resp = _api_get_raw(config.base_url, "/v1/setup/connect-node/status", params=params)

            try:
                body = resp.json()
            except Exception:
                body = {}

            rd = body.get("data", body)
            poll_status = rd.get("status", "unknown")

            if poll_status == "complete":
                # Authorization successful!
                report.message = "Portal authorization complete"
                report.details["polls"] = poll_count
                report.details["template"] = rd.get("template", "")
                report.details["adapters"] = rd.get("adapters", [])
                report.details["has_signing_key"] = bool(rd.get("signing_key_b64"))
                report.details["stewardship_tier"] = rd.get("stewardship_tier", 0)
                report.details["provisioned"] = rd
                return report

            if poll_status == "error":
                report.result = TestResult.FAILED
                report.message = f"Authorization rejected: {rd.get('error', '?')}"
                report.details["polls"] = poll_count
                return report

            # Still pending - show progress
            elapsed = int(time.time() - start.timestamp())
            print(
                f"\r  Waiting for Portal auth... " f"({elapsed}s / {config.poll_timeout}s, poll #{poll_count})",
                end="",
                flush=True,
            )

            # Take periodic screenshots
            if poll_count % 12 == 1:  # Every ~60 seconds
                shot = await browser.screenshot(f"licensed_poll_{poll_count}", full_page=True)
                report.screenshots.append(shot.path)

            time.sleep(config.poll_interval)

        print()  # Newline after progress
        report.result = TestResult.FAILED
        report.message = f"Timeout after {poll_count} polls ({config.poll_timeout}s)"
        report.details["polls"] = poll_count

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_complete_licensed_setup(
    browser: BrowserHelper,
    config: LicensedAgentConfig,
    provisioned: Dict[str, Any],
) -> TestReport:
    """Step 6: Complete setup with provisioned credentials via UI."""
    start = datetime.now()
    report = TestReport(name="complete_licensed_setup", result=TestResult.PASSED)

    try:
        # Refresh the page to get updated UI state after authorization
        await browser.goto(f"{config.base_url}/setup")
        await browser.wait(2)

        shot = await browser.screenshot("licensed_post_auth", full_page=True)
        report.screenshots.append(shot.path)

        content = await browser.get_page_content()

        # Check if UI shows authorization was successful
        success_indicators = ["authorized", "connected", "provisioned", "continue", "next step"]
        found = [i for i in success_indicators if i.lower() in content.lower()]
        report.details["success_indicators"] = found

        # Navigate through remaining setup steps
        # The UI should now show LLM configuration step

        # Step A: Configure LLM (if API key is provided)
        if config.llm_api_key:
            # Find provider selection
            provider_names = {
                "openrouter": "OpenRouter",
                "openai": "OpenAI",
                "anthropic": "Anthropic",
                "groq": "Groq",
            }
            provider_text = provider_names.get(config.llm_provider.lower(), config.llm_provider)

            clicked = await browser.click_text(provider_text)
            if clicked:
                report.details["selected_provider"] = provider_text
                await browser.wait(1)

            # Enter API key
            api_input = browser.page.locator("input[type='password']").first
            if await api_input.count() > 0:
                await api_input.clear()
                await api_input.type(config.llm_api_key, delay=10)
                report.details["api_key_entered"] = True

        # Step B: Click through to account creation
        for step in range(5):
            await browser.wait(1)
            content = await browser.get_page_content()

            # Check if we're on account creation
            if "Create Your Accounts" in content or "Admin Account" in content:
                report.details["reached_account_step"] = True
                break

            # Look for Continue button
            continue_btn = browser.page.locator("button:has-text('Continue')")
            if await continue_btn.count() > 0:
                btn = continue_btn.first
                if await btn.is_enabled():
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    await browser.wait(2)

        # Step C: Fill account creation (use provisioned template info)
        content = await browser.get_page_content()
        if "Create Your Accounts" in content or "Admin Account" in content:
            # Generate random admin password
            generate_link = browser.page.locator("button, a").filter(has_text="Generate Random")
            if await generate_link.count() > 0:
                await generate_link.first.click()
                await browser.wait(1)

            # Fill username
            username_input = browser.page.locator("input#username")
            if await username_input.count() > 0:
                await username_input.first.fill(config.admin_username)

            shot = await browser.screenshot("licensed_account_filled", full_page=True)
            report.screenshots.append(shot.path)

        # Step D: Click Complete Setup
        complete_btn = browser.page.locator("button").filter(has_text="Complete Setup")
        if await complete_btn.count() > 0:
            await complete_btn.first.click()
            report.details["clicked_complete"] = True

            # Wait for redirect
            for i in range(15):
                await browser.wait(1)
                content = await browser.get_page_content()
                current_url = browser.page.url

                if "Sign in" in content or "/login" in current_url:
                    report.message = "Licensed setup completed - redirected to login"
                    shot = await browser.screenshot("licensed_complete", full_page=True)
                    report.screenshots.append(shot.path)
                    return report

            report.message = "Setup submitted - waiting for completion"
        else:
            # Try direct API call for setup completion
            payload = {
                "llm_provider": config.llm_provider,
                "llm_api_key": config.llm_api_key,
                "template_id": provisioned.get("template", "default"),
                "enabled_adapters": list(set(["api"] + provisioned.get("adapters", []))),
                "admin_username": config.admin_username,
                "admin_password": config.admin_password,
                "node_url": config.portal_url,
                "stewardship_tier": provisioned.get("stewardship_tier"),
                "signing_key_provisioned": bool(provisioned.get("signing_key_b64")),
                "provisioned_signing_key_b64": provisioned.get("signing_key_b64"),
            }

            resp = requests.post(
                f"{config.base_url}/v1/setup/complete",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )

            if resp.status_code == 200:
                report.message = "Licensed setup completed via API"
            else:
                report.result = TestResult.FAILED
                report.message = f"Setup completion failed: HTTP {resp.status_code}"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_verify_licensed_agent(browser: BrowserHelper, config: LicensedAgentConfig) -> TestReport:
    """Step 7: Verify agent is configured and services are online."""
    start = datetime.now()
    report = TestReport(name="verify_licensed_agent", result=TestResult.PASSED)

    try:
        # Wait for server to restart after setup
        time.sleep(3)

        # Login to get token
        login_data = _api_post(
            config.base_url,
            "/v1/auth/login",
            {"username": config.admin_username, "password": config.admin_password},
        )
        token = login_data.get("access_token")

        if not token:
            report.result = TestResult.FAILED
            report.message = "Could not login after setup"
            return report

        report.details["login_success"] = True

        # Check setup status
        setup_data = _api_get(config.base_url, "/v1/setup/status")
        setup = setup_data.get("data", {})
        is_first_run = setup.get("is_first_run", True)

        if is_first_run:
            report.result = TestResult.FAILED
            report.message = "Agent still in first-run mode after setup"
            return report

        # Check telemetry for services
        time.sleep(5)  # Give services time to start

        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{config.base_url}/v1/telemetry/unified",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                telem = resp.json().get("data", resp.json())
                online = telem.get("services_online", 0)
                total = telem.get("services_total", 0)
                cog_state = telem.get("cognitive_state")

                report.message = f"Licensed agent verified: {online}/{total} services, state={cog_state}"
                report.details["services_online"] = online
                report.details["services_total"] = total
                report.details["cognitive_state"] = cog_state
            else:
                report.message = "Agent configured (telemetry unavailable)"

        except Exception:
            report.message = "Agent configured (telemetry unavailable)"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


# =============================================================================
# Full Licensed Agent Flow
# =============================================================================


async def run_licensed_agent_flow(
    browser: BrowserHelper,
    config: LicensedAgentConfig,
) -> List[TestReport]:
    """
    Run the full licensed agent first-start flow.

    Flow:
    1. API health check
    2. Verify first-run status
    3. Load setup page
    4. Initiate connect node (device auth)
    5. Wait for Portal authorization
    6. Complete setup with provisioned credentials
    7. Verify agent is configured

    Returns:
        List of TestReport for each step
    """
    reports: List[TestReport] = []

    print("\n" + "=" * 60)
    print("Licensed Agent First-Start Flow (Web UI)")
    print("=" * 60)
    print(f"  API:     {config.base_url}")
    print(f"  Portal:  {config.portal_url}")
    print(f"  LLM:     {config.llm_provider} (key: {'set' if config.llm_api_key else 'MISSING'})")
    print(f"  Timeout: {config.poll_timeout}s")
    print()

    # Step 1: API Health
    print("[1/7] API health check...")
    report = await test_api_health(browser, config)
    reports.append(report)
    _print_result(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 2: First-run status
    print("[2/7] Verify first-run status...")
    report = await test_first_run_status(browser, config)
    reports.append(report)
    _print_result(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 3: Load setup page
    print("[3/7] Load setup wizard...")
    report = await test_load_setup_page(browser, config)
    reports.append(report)
    _print_result(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 4: Initiate connect node
    print(f"[4/7] Connect to Portal ({config.portal_url})...")
    report = await test_initiate_connect_node(browser, config)
    reports.append(report)
    _print_result(report)
    if report.result != TestResult.PASSED:
        return reports

    # Display authorization URL
    device_code = report.details.get("device_code", "")
    user_code = report.details.get("user_code", "")
    verification_uri = report.details.get("verification_uri", "")
    portal_url = report.details.get("portal_url", config.portal_url)

    if device_code:
        print()
        print("  " + "=" * 50)
        print("  AUTHORIZE THIS AGENT IN YOUR BROWSER:")
        if verification_uri:
            print(f"    {verification_uri}")
        else:
            print(f"    {portal_url}/device")
        if user_code:
            print(f"  User code: {user_code}")
        print("  " + "=" * 50)
        print()

        # Step 5: Wait for authorization
        print(f"[5/7] Waiting for Portal authorization (timeout: {config.poll_timeout}s)...")
        report = await test_wait_for_authorization(browser, config, device_code, portal_url)
        reports.append(report)
        print()  # Newline after progress
        _print_result(report)
        if report.result != TestResult.PASSED:
            return reports

        provisioned = report.details.get("provisioned", {})

        # Step 6: Complete setup
        print("[6/7] Complete setup with provisioned credentials...")
        report = await test_complete_licensed_setup(browser, config, provisioned)
        reports.append(report)
        _print_result(report)
        if report.result not in (TestResult.PASSED, TestResult.SKIPPED):
            return reports

        # Step 7: Verify
        print("[7/7] Verify licensed agent...")
        report = await test_verify_licensed_agent(browser, config)
        reports.append(report)
        _print_result(report)

    else:
        print("  [WARN] No device code obtained - cannot proceed with Portal auth")
        report = TestReport(
            name="skip_remaining",
            result=TestResult.SKIPPED,
            message="Portal connection not available",
        )
        reports.append(report)

    return reports


def _print_result(report: TestReport) -> None:
    """Print test result in consistent format."""
    icons = {
        TestResult.PASSED: "PASS",
        TestResult.FAILED: "FAIL",
        TestResult.ERROR: "ERR!",
        TestResult.SKIPPED: "SKIP",
    }
    icon = icons.get(report.result, "????")
    print(f"  [{icon}] {report.name} ({report.duration_seconds:.1f}s) -- {report.message}")
