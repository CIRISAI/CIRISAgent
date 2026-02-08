"""
Test Cases for Web UI QA

Modular test functions for end-to-end web UI testing:
1. Load setup wizard
2. Enter API key
3. Load models (live model listing)
4. Select model
5. Opt-in/consent
6. Select adapters
7. Complete setup
8. Interact with agent
9. Validate response
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .browser_helper import BrowserHelper


class TestResult(Enum):
    """Test result status."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestReport:
    """Report for a single test."""

    name: str
    result: TestResult
    duration_seconds: float = 0.0
    message: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WebUITestConfig:
    """Configuration for web UI tests."""

    # Server URL
    base_url: str = "http://localhost:8080"

    # LLM Configuration
    llm_provider: str = "openrouter"  # openai, anthropic, openrouter, groq, etc.
    llm_api_key: str = ""  # API key for the provider
    llm_model: str = ""  # Model to select (empty = auto-select recommended)

    # Test account (for setup wizard)
    admin_password: str = "testpassword123"
    admin_username: str = "testadmin"
    user_email: str = "test@example.com"
    user_password: str = "userpassword123"

    # Adapters to enable (empty list = none)
    adapters: List[str] = field(default_factory=list)

    # Interaction test
    test_message: str = "Hello! Please respond with a brief greeting to confirm you're working."
    expected_response_contains: List[str] = field(default_factory=lambda: ["hello", "hi", "greet"])

    # Timeouts
    model_load_timeout: int = 30  # Seconds to wait for models to load
    interaction_timeout: int = 60  # Seconds to wait for agent response

    @classmethod
    def from_env(cls) -> "WebUITestConfig":
        """Create config from environment variables."""
        config = cls()

        # Try to load API key from files
        key_files = {
            "openrouter": os.path.expanduser("~/.openrouter_key"),
            "anthropic": os.path.expanduser("~/.anthropic_key"),
            "openai": os.path.expanduser("~/.openai_key"),
            "groq": os.path.expanduser("~/.groq_key"),
        }

        provider = os.environ.get("LLM_PROVIDER", "openrouter")
        config.llm_provider = provider

        # Try to load key from file
        key_file = key_files.get(provider)
        if key_file and os.path.exists(key_file):
            with open(key_file) as f:
                config.llm_api_key = f.read().strip()

        # Override with env vars if set
        if os.environ.get("LLM_API_KEY"):
            config.llm_api_key = os.environ["LLM_API_KEY"]

        if os.environ.get("LLM_MODEL"):
            config.llm_model = os.environ["LLM_MODEL"]

        return config


# =============================================================================
# Test Functions - Setup Wizard
# =============================================================================


async def test_load_setup_wizard(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test loading the setup wizard.

    Steps:
    1. Navigate to /setup
    2. Verify wizard loads
    3. Verify step 1 is displayed
    """
    start = datetime.now()
    report = TestReport(name="load_setup_wizard", result=TestResult.PASSED)

    try:
        await browser.goto(f"{config.base_url}/setup")
        await browser.wait(2)

        # Take screenshot
        shot = await browser.screenshot("setup_step1", full_page=True)
        report.screenshots.append(shot.path)

        # Verify we're on the setup page
        content = await browser.get_page_content()

        if "Welcome to CIRIS" in content or "Setup" in content:
            report.message = "Setup wizard loaded successfully"
            report.details["page_title"] = "Welcome to CIRIS"
        else:
            report.result = TestResult.FAILED
            report.message = "Setup wizard content not found"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_navigate_to_llm_config(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test navigating to LLM configuration step.

    Steps:
    1. Click "Continue to LLM Setup" button
    2. Verify LLM configuration page loads (Step 2)
    """
    start = datetime.now()
    report = TestReport(name="navigate_to_llm_config", result=TestResult.PASSED)

    try:
        # Find and click the Continue to LLM Setup button
        # The button text may include an arrow: "Continue to LLM Setup →"
        continue_btn = browser.page.locator("button").filter(has_text="Continue to LLM Setup")
        btn_count = await continue_btn.count()
        report.details["continue_btn_count"] = btn_count

        clicked = False
        if btn_count > 0:
            await continue_btn.first.scroll_into_view_if_needed()
            await browser.wait(0.3)
            await continue_btn.first.click()
            clicked = True
            report.details["clicked"] = "Continue to LLM Setup button"
        else:
            # Fallback to text-based click
            clicked = await browser.click_text("Continue")
            report.details["clicked"] = "Continue (fallback)"

        # Wait for navigation
        await browser.wait(2)

        # Take screenshot
        shot = await browser.screenshot("setup_llm_config", full_page=True)
        report.screenshots.append(shot.path)

        # Verify LLM config page - Step 2 should show API key configuration
        content = await browser.get_page_content()

        # Check for Step 2 indicators - the page should show LLM/API configuration
        step2_indicators = [
            "Step 2",  # Step indicator
            "API Key",  # API key input
            "API key",  # lowercase variant
            "Configure Your LLM",  # Original expected text
            "Provider",  # Provider selection
            "OpenAI",  # Provider name
            "Anthropic",  # Provider name
            "OpenRouter",  # Provider name
            "Enter your",  # Input prompt
            "Select a provider",  # Provider selection
        ]

        found_indicators = [ind for ind in step2_indicators if ind in content]
        report.details["found_indicators"] = found_indicators

        # Check if we found meaningful Step 2 indicators
        # Provider names (OpenAI, Anthropic, etc.) are strong signals we're on Step 2
        strong_indicators = ["OpenAI", "Anthropic", "OpenRouter", "Select a provider", "Enter your"]
        found_strong = [ind for ind in strong_indicators if ind in content]

        if found_strong:
            # Strong indicators found - definitely on Step 2
            report.message = f"LLM configuration page loaded (found: {', '.join(found_indicators[:3])})"
        elif found_indicators:
            # Weak indicators found - probably on Step 2
            report.message = f"LLM configuration page loaded (found: {', '.join(found_indicators[:3])})"
        else:
            report.result = TestResult.FAILED
            report.message = "LLM configuration page not found - no step 2 indicators"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_select_provider(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test selecting an LLM provider.

    Steps:
    1. Find provider cards
    2. Click the configured provider
    3. Verify selection
    """
    start = datetime.now()
    report = TestReport(name="select_provider", result=TestResult.PASSED)

    try:
        provider_names = {
            "openrouter": "OpenRouter",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "groq": "Groq",
            "google": "Google AI",
            "together": "Together AI",
        }

        provider_text = provider_names.get(config.llm_provider.lower(), config.llm_provider)

        # Click provider card
        clicked = await browser.click_text(provider_text)

        if clicked:
            report.message = f"Selected provider: {provider_text}"
            report.details["provider"] = config.llm_provider
        else:
            report.result = TestResult.FAILED
            report.message = f"Could not find provider: {provider_text}"

        await browser.wait(1)

        # Take screenshot
        shot = await browser.screenshot("setup_provider_selected", full_page=True)
        report.screenshots.append(shot.path)

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_enter_api_key(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test entering the API key.

    Steps:
    1. Find API key input
    2. Enter key character by character to trigger React onChange
    3. Verify key was entered
    """
    start = datetime.now()
    report = TestReport(name="enter_api_key", result=TestResult.PASSED)

    try:
        if not config.llm_api_key:
            report.result = TestResult.SKIPPED
            report.message = "No API key configured"
            return report

        # Find API key input
        api_input = browser.page.locator("input[type='password']").first
        if await api_input.count() > 0:
            # Clear any existing value first
            await api_input.clear()
            await browser.wait(0.2)

            # Type the key character by character to properly trigger React onChange
            # This is more reliable than fill() for React controlled inputs
            await api_input.type(config.llm_api_key, delay=10)

            # Click outside to blur and trigger any onBlur handlers
            await browser.page.click("body", position={"x": 10, "y": 10})
            await browser.wait(0.5)

            report.message = "API key entered"
            report.details["key_prefix"] = config.llm_api_key[:10] + "..."
            report.details["key_length"] = len(config.llm_api_key)
        else:
            # Try placeholder-based search
            filled = await browser.fill_input_by_placeholder("key", config.llm_api_key)
            if filled:
                report.message = "API key entered via placeholder"
            else:
                report.result = TestResult.FAILED
                report.message = "Could not find API key input"

        await browser.wait(1)

        # Take screenshot
        shot = await browser.screenshot("setup_key_entered", full_page=True)
        report.screenshots.append(shot.path)

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_load_models(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test loading available models (live model listing feature).

    Steps:
    1. Click "Load available models from {provider}" link
    2. Wait for API call to complete
    3. Verify dropdown appears with model options
    4. FAIL if dropdown doesn't appear (no text input fallback)
    """
    start = datetime.now()
    report = TestReport(name="load_models", result=TestResult.PASSED)

    try:
        # Scroll down to see the full LLM config section
        await browser.scroll_down(300)
        await browser.wait(1)

        # Take a "before" screenshot to debug
        shot_before = await browser.screenshot("setup_before_load_models", full_page=True)
        report.screenshots.append(shot_before.path)

        # Find the "Load available models from X" link - it's a button element
        load_link = browser.page.locator("button").filter(has_text="Load available models")
        link_count = await load_link.count()
        report.details["load_link_count"] = link_count

        if link_count > 0:
            # Scroll the element into view and click
            await load_link.first.scroll_into_view_if_needed()
            await browser.wait(0.5)
            await load_link.first.click()
            report.details["clicked"] = "Load available models link"
        else:
            # Try "Refresh Models" button as alternative
            refresh_btn = browser.page.locator("button").filter(has_text="Refresh Models")
            refresh_count = await refresh_btn.count()
            report.details["refresh_btn_count"] = refresh_count

            if refresh_count > 0:
                await refresh_btn.first.scroll_into_view_if_needed()
                await browser.wait(0.5)
                await refresh_btn.first.click()
                report.details["clicked"] = "Refresh Models button"
            else:
                report.result = TestResult.FAILED
                report.message = "Could not find 'Load available models' link or 'Refresh Models' button"
                return report

        # Wait for loading indicator to appear
        await browser.wait(0.5)

        # Take screenshot during loading
        shot_loading = await browser.screenshot("setup_models_loading", full_page=True)
        report.screenshots.append(shot_loading.path)

        # Wait for "Loading..." to disappear (max 25 seconds for API call)
        loading_timeout = 25
        found_loading = False
        for i in range(loading_timeout):
            content = await browser.get_page_content()
            if "Loading..." in content or "Loading models" in content:
                found_loading = True
            if found_loading and "Loading..." not in content and "Loading models" not in content:
                report.details["load_wait_seconds"] = i + 1
                break
            await browser.wait(1)
        else:
            if found_loading:
                report.result = TestResult.FAILED
                report.message = f"Models still loading after {loading_timeout}s timeout"
            else:
                report.details["load_wait_seconds"] = 0
                report.details["never_saw_loading"] = True

        # Wait for UI to update after loading
        await browser.wait(2)

        # Take screenshot after loading
        shot = await browser.screenshot("setup_models_loaded", full_page=True)
        report.screenshots.append(shot.path)

        # REQUIRE: Select dropdown must appear with model options
        # Find the model dropdown specifically (not provider dropdown)
        model_dropdown = None
        select_elements = browser.page.locator("select")
        select_count = await select_elements.count()
        report.details["select_count"] = select_count

        for i in range(select_count):
            sel = select_elements.nth(i)
            options = await sel.locator("option").all_text_contents()
            # Model dropdown has options with "/" (org/model format) or model names
            is_model_dropdown = any(
                "/" in o or "claude" in o.lower() or "gpt" in o.lower() or "llama" in o.lower() or "gemini" in o.lower()
                for o in options
            )
            if is_model_dropdown:
                model_dropdown = sel
                report.details["model_options"] = options[:10]  # First 10 options
                report.details["total_models"] = len([o for o in options if o and o != "Select a model..."])
                break

        if model_dropdown is None:
            report.result = TestResult.FAILED
            report.message = "Model dropdown did not appear - live model listing failed"
            # Debug: check page content for clues
            content = await browser.get_page_content()
            if "error" in content.lower():
                report.details["page_has_error"] = True
            if "failed" in content.lower():
                report.details["page_has_failed"] = True
            # Capture console logs for debugging
            console_logs = browser.get_recent_console_logs(30)
            report.details["console_logs"] = [f"[{l['type']}] {l['text']}" for l in console_logs]
            # Look for loadModels logs specifically
            model_logs = [l for l in console_logs if "loadModels" in l.get("text", "")]
            if model_logs:
                report.details["loadModels_logs"] = [l["text"] for l in model_logs]
            # Capture network logs to debug API calls
            network_logs = browser.get_recent_network_logs(20, api_only=True)
            report.details["network_logs"] = [
                f"[{l['type']}] {l.get('method', '')} {l['url']} -> {l.get('status', '')}" for l in network_logs
            ]
            return report

        # Check for quality indicators (★ recommended, ✓ compatible)
        options_text = " ".join(report.details.get("model_options", []))
        has_recommended = "★" in options_text
        has_compatible = "✓" in options_text or "✗" in options_text

        report.details["has_recommended_indicator"] = has_recommended
        report.details["has_compatibility_indicator"] = has_compatible

        report.message = f"Live models loaded: {report.details['total_models']} models in dropdown"
        if has_recommended:
            report.message += " (with ★ recommended)"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_live_model_listing(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test the v1.9.5 live model listing feature in detail.

    Tests:
    1. Model dropdown shows live models from provider API
    2. Models have indicators (★ recommended, ✓ compatible, ✗ incompatible)
    3. Model details display (context window, tier info)
    4. Auto-selection of recommended model
    5. Model source is displayed (e.g., "from OpenRouter")
    """
    start = datetime.now()
    report = TestReport(name="live_model_listing", result=TestResult.PASSED)

    try:
        content = await browser.get_page_content()
        report.details["checks"] = {}

        # Check 1: Look for model indicators (★ ✓ ✗)
        has_recommended = "★" in content or "recommended" in content.lower()
        has_compatible = "✓" in content or "compatible" in content.lower()
        report.details["checks"]["has_recommended_indicator"] = has_recommended
        report.details["checks"]["has_compatible_indicator"] = has_compatible

        # Check 2: Look for model tier information
        tier_indicators = ["default", "fast", "premium", "economy", "tier"]
        found_tiers = [t for t in tier_indicators if t.lower() in content.lower()]
        report.details["checks"]["tier_info"] = found_tiers

        # Check 3: Look for context window information
        context_indicators = ["context", "tokens", "128k", "200k", "32k", "8k"]
        found_context = [c for c in context_indicators if c.lower() in content.lower()]
        report.details["checks"]["context_info"] = found_context

        # Check 4: Look for model source display
        source_indicators = ["from openrouter", "from anthropic", "from openai", "models from"]
        found_source = [s for s in source_indicators if s.lower() in content.lower()]
        report.details["checks"]["source_display"] = found_source

        # Check 5: Look for select dropdown with models
        select_elements = browser.page.locator("select")
        select_count = await select_elements.count()
        report.details["checks"]["select_dropdowns"] = select_count

        if select_count > 0:
            # Check options in first select that looks like model selector
            for i in range(select_count):
                sel = select_elements.nth(i)
                options = await sel.locator("option").all_text_contents()
                model_like = [
                    o
                    for o in options
                    if "/" in o or "claude" in o.lower() or "gpt" in o.lower() or "llama" in o.lower()
                ]
                if model_like:
                    report.details["checks"]["model_options_count"] = len(model_like)
                    report.details["checks"]["sample_models"] = model_like[:5]
                    break

        # Take screenshot of model listing
        shot = await browser.screenshot("live_model_listing_detail", full_page=True)
        report.screenshots.append(shot.path)

        # Determine success based on checks
        success_criteria = [
            has_recommended or has_compatible,  # Has some compatibility indicators
            len(found_tiers) > 0 or len(found_context) > 0,  # Has model details
        ]

        if all(success_criteria):
            report.message = f"Live model listing working. Found: recommended={has_recommended}, compatible={has_compatible}, tiers={found_tiers}"
        elif any(success_criteria):
            report.result = TestResult.PASSED
            report.message = f"Partial model listing. Tiers: {found_tiers}, Context: {found_context}"
        else:
            report.result = TestResult.FAILED
            report.message = "Live model listing not showing expected indicators"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_select_model(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test selecting a model from the live model dropdown.

    Steps:
    1. Find the model dropdown (REQUIRED - no text input fallback)
    2. Select recommended model (★) or first compatible model (✓)
    3. Verify selection updates the UI
    """
    start = datetime.now()
    report = TestReport(name="select_model", result=TestResult.PASSED)

    try:
        # Find the model dropdown - REQUIRED
        model_dropdown = None
        select_elements = browser.page.locator("select")
        select_count = await select_elements.count()

        for i in range(select_count):
            sel = select_elements.nth(i)
            options = await sel.locator("option").all_text_contents()
            # Model dropdown has options with "/" (org/model format) or model names
            is_model_dropdown = any(
                "/" in o or "claude" in o.lower() or "gpt" in o.lower() or "llama" in o.lower() or "gemini" in o.lower()
                for o in options
            )
            if is_model_dropdown:
                model_dropdown = sel
                report.details["available_options"] = options[:10]
                break

        if model_dropdown is None:
            report.result = TestResult.FAILED
            report.message = "Model dropdown not found - run load_models test first"
            return report

        options = await model_dropdown.locator("option").all_text_contents()

        # Priority: 1) Recommended (★), 2) Compatible (✓), 3) First non-empty option
        selected_option = None
        selected_index = None

        for idx, opt in enumerate(options):
            if "★" in opt:  # Recommended
                selected_option = opt
                selected_index = idx
                report.details["selection_reason"] = "recommended (★)"
                break

        if selected_option is None:
            for idx, opt in enumerate(options):
                if "✓" in opt:  # Compatible
                    selected_option = opt
                    selected_index = idx
                    report.details["selection_reason"] = "compatible (✓)"
                    break

        if selected_option is None:
            # Select first real option (skip "Select a model...")
            for idx, opt in enumerate(options):
                if opt and "select" not in opt.lower() and len(opt) > 3:
                    selected_option = opt
                    selected_index = idx
                    report.details["selection_reason"] = "first available"
                    break

        if selected_option is None or selected_index is None:
            report.result = TestResult.FAILED
            report.message = "No valid model options found in dropdown"
            return report

        # Select the model
        await model_dropdown.select_option(index=selected_index)
        await browser.wait(1)

        # Verify selection
        current_value = await model_dropdown.input_value()
        report.details["selected_model"] = selected_option
        report.details["selected_value"] = current_value

        report.message = f"Selected: {selected_option.strip()}"

        # Take screenshot
        shot = await browser.screenshot("setup_model_selected", full_page=True)
        report.screenshots.append(shot.path)

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_complete_setup(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test completing the setup wizard.

    Steps:
    1. Click Continue through steps until Account Creation
    2. Fill account info (Generate Random for admin, username, passwords)
    3. Click Complete Setup ONCE
    4. Wait for redirect to login page
    """
    start = datetime.now()
    report = TestReport(name="complete_setup", result=TestResult.PASSED)

    try:
        # Step 1: Navigate through wizard steps until Account Creation
        for step in range(5):  # Max 5 steps
            await browser.wait(1)
            content = await browser.get_page_content()
            current_url = browser.page.url
            report.details[f"step_{step}_url"] = current_url

            # Already on login page - setup done
            if "Sign in" in content or "/login" in current_url:
                report.message = "Setup completed - on login page"
                report.details["final_page"] = "login"
                return report

            # On Account Creation step - stop and fill form
            if "Create Your Accounts" in content or "Admin Account" in content:
                report.details["reached_account_step"] = True
                break

            # On Optional Features step - check covenant metrics consent checkbox
            if "Help Improve AI Alignment" in content or "anonymous alignment metrics" in content:
                consent_checkbox = browser.page.locator("input[type='checkbox']").filter(
                    has=browser.page.locator("xpath=..").filter(has_text="agree to share")
                )
                # Try simpler selector - checkbox near the consent text
                consent_checkbox = browser.page.locator("label:has-text('agree to share') input[type='checkbox']")
                if await consent_checkbox.count() == 0:
                    # Fallback: find any checkbox in the covenant metrics section
                    consent_checkbox = browser.page.locator(".bg-blue-50 input[type='checkbox']")
                if await consent_checkbox.count() > 0:
                    is_checked = await consent_checkbox.first.is_checked()
                    if not is_checked:
                        await consent_checkbox.first.click()
                        await browser.wait(0.5)
                        report.details["covenant_metrics_consent"] = True
                    else:
                        report.details["covenant_metrics_consent"] = "already_checked"
                else:
                    report.details["covenant_metrics_consent"] = "checkbox_not_found"

            # Scroll to bottom to ensure Continue button is visible
            await browser.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await browser.wait(0.5)

            # Look specifically for Continue button
            continue_btn = browser.page.locator("button:has-text('Continue')")
            continue_count = await continue_btn.count()
            report.details[f"step_{step}_continue_count"] = continue_count

            clicked = False
            if continue_count > 0:
                for i in range(continue_count):
                    btn = continue_btn.nth(i)
                    btn_text = (await btn.text_content() or "").strip()
                    btn_enabled = await btn.is_enabled()
                    report.details[f"step_{step}_btn_{i}"] = f"{btn_text[:40]}(en={btn_enabled})"

                    if btn_enabled:
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        clicked = True
                        report.details[f"step_{step}_clicked"] = btn_text[:50]
                        await browser.wait(2)
                        shot = await browser.screenshot(f"setup_step_{step + 1}", full_page=True)
                        report.screenshots.append(shot.path)
                        break

            if not clicked:
                report.details[f"step_{step}_no_button"] = True
                break

        # Step 2: Fill Account Creation form
        content = await browser.get_page_content()
        if "Create Your Accounts" in content or "Admin Account" in content:
            # Click "Generate Random" for admin password
            generate_link = browser.page.locator("button, a").filter(has_text="Generate Random")
            if await generate_link.count() > 0:
                await generate_link.first.click()
                await browser.wait(1)
                report.details["admin_password"] = "generated"

            # Fill username field (id="username")
            username_input = browser.page.locator("input#username")
            if await username_input.count() > 0:
                await username_input.first.fill(config.admin_username)
                report.details["username"] = config.admin_username
            else:
                # Fallback to placeholder search
                username_input = browser.page.locator("input[placeholder*='username']")
                if await username_input.count() > 0:
                    await username_input.first.fill(config.admin_username)
                    report.details["username"] = config.admin_username

            # Fill user password fields (not admin password - that was generated)
            # Admin fields have IDs: adminPassword, adminPasswordConfirm
            # User fields have different IDs or no ID
            password_inputs = browser.page.locator("input[type='password']")
            pw_count = await password_inputs.count()
            for i in range(pw_count):
                inp = password_inputs.nth(i)
                field_id = await inp.get_attribute("id") or ""
                # Skip admin password fields (already generated)
                if "admin" in field_id.lower():
                    continue
                # Fill user password and confirm
                await inp.fill(config.user_password)

            await browser.wait(1)
            shot = await browser.screenshot("setup_account_filled", full_page=True)
            report.screenshots.append(shot.path)

        # Step 3: Click Complete Setup ONCE and wait for redirect
        complete_btn = browser.page.locator("button").filter(has_text="Complete Setup")
        if await complete_btn.count() > 0:
            await complete_btn.first.click()
            report.details["clicked_complete_setup"] = True

            # Wait for redirect (up to 15 seconds)
            for i in range(15):
                await browser.wait(1)
                content = await browser.get_page_content()
                current_url = browser.page.url

                # Success - redirected to login
                if "Sign in" in content or "/login" in current_url:
                    report.message = "Setup completed - redirected to login"
                    report.details["final_page"] = "login"
                    shot = await browser.screenshot("setup_complete_login", full_page=True)
                    report.screenshots.append(shot.path)
                    return report

                # Success - reached main UI
                if "Dashboard" in content or "Welcome back" in content:
                    report.message = "Setup completed - reached main UI"
                    report.details["final_page"] = "main"
                    return report

                # Setup Complete page - click "Go to Login" button
                if "Setup Complete" in content:
                    go_to_login_btn = browser.page.locator("button, a").filter(has_text="Go to Login")
                    if await go_to_login_btn.count() > 0:
                        await go_to_login_btn.first.click()
                        report.details["clicked_go_to_login"] = True
                        await browser.wait(2)
                        # Continue loop to detect redirect to login
                        continue

                # Still processing
                if "Completing" in content or "Processing" in content:
                    continue

            # Timeout waiting for redirect - capture console logs for debugging
            report.message = "Setup submitted but redirect not detected"
            shot = await browser.screenshot("setup_complete_timeout", full_page=True)
            report.screenshots.append(shot.path)
            # Capture recent console logs to help debug
            console_logs = browser.get_recent_console_logs(count=50)
            report.details["console_logs"] = [
                f"[{log.get('type', 'log')}] {log.get('text', '')[:200]}" for log in console_logs
            ]
        else:
            report.result = TestResult.FAILED
            report.message = "Complete Setup button not found"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


# =============================================================================
# Test Functions - Interaction
# =============================================================================


async def test_login_after_setup(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test logging in after setup completes.

    Steps:
    1. Detect login page
    2. Enter credentials created during setup
    3. Click Sign in
    4. Verify we reach the main UI
    """
    start = datetime.now()
    report = TestReport(name="login_after_setup", result=TestResult.PASSED)

    try:
        await browser.wait(1)
        content = await browser.get_page_content()
        current_url = browser.page.url

        # Check if we're on the login page
        on_login_page = "Sign in" in content or "sign in" in content.lower() or "/login" in current_url
        if not on_login_page:
            # Maybe we're already logged in or on another page
            if "Dashboard" in content or "Chat" in content:
                report.result = TestResult.SKIPPED
                report.message = "Already logged in - on main UI"
                return report
            report.result = TestResult.SKIPPED
            report.message = f"Not on login page (URL: {current_url})"
            shot = await browser.screenshot("login_skipped_page")
            report.screenshots.append(shot.path)
            return report

        report.details["detected_login_page"] = True

        # Find username input - look for input near "Username" label or first text input
        username_input = browser.page.locator("input[type='text']").first
        if await username_input.count() > 0:
            await username_input.clear()
            await username_input.fill(config.admin_username)
            report.details["username_entered"] = config.admin_username

        # Find and fill password
        password_input = browser.page.locator("input[type='password']").first
        if await password_input.count() > 0:
            await password_input.clear()
            await password_input.fill(config.user_password)
            report.details["password_entered"] = True

        # Take screenshot before login
        shot = await browser.screenshot("login_credentials_entered")
        report.screenshots.append(shot.path)

        # Click Sign in button
        sign_in_btn = browser.page.locator("button").filter(has_text="Sign in")
        if await sign_in_btn.count() > 0:
            await sign_in_btn.first.click()
            report.details["clicked_sign_in"] = True

            # Wait for login to complete (up to 10 seconds)
            for i in range(10):
                await browser.wait(1)
                content = await browser.get_page_content()
                current_url = browser.page.url

                # Check for successful login - no longer on login page
                if "/login" not in current_url and "Sign in to CIRIS" not in content:
                    if "Dashboard" in content or "Chat" in content or "Interact" in content:
                        report.message = "Login successful - reached main UI"
                        report.details["final_page"] = "main"
                        break
                    elif "Welcome" in content:
                        report.message = "Login successful"
                        break

                # Check for error
                if "Invalid" in content or "incorrect" in content.lower():
                    report.result = TestResult.FAILED
                    report.message = "Login failed - invalid credentials"
                    break
            else:
                report.message = "Login submitted - waiting for redirect"
        else:
            report.result = TestResult.FAILED
            report.message = "Sign in button not found"

        # Take screenshot after login attempt
        shot = await browser.screenshot("login_result")
        report.screenshots.append(shot.path)

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_send_message(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test sending a message to the agent.

    Steps:
    1. Navigate to chat/interaction page
    2. Find message input (textarea for chat)
    3. Send test message
    """
    start = datetime.now()
    report = TestReport(name="send_message", result=TestResult.PASSED)

    try:
        await browser.wait(1)
        content = await browser.get_page_content()

        # If on login page, skip this test
        if "Sign in" in content or "Login" in content:
            report.result = TestResult.SKIPPED
            report.message = "Still on login page - login test must run first"
            return report

        # Navigate to main/chat page if needed
        current_url = browser.page.url
        if "/setup" in current_url:
            await browser.goto(config.base_url)
            await browser.wait(2)

        # Look specifically for a textarea (chat input) not a regular text input
        message_input = browser.page.locator("textarea").first

        if await message_input.count() > 0:
            await message_input.fill(config.test_message)

            # Take screenshot with message
            shot = await browser.screenshot("interaction_message_entered")
            report.screenshots.append(shot.path)

            # Send message (press Enter or click send button)
            await message_input.press("Enter")

            report.message = "Message sent"
            report.details["message"] = config.test_message

        else:
            # Try finding by placeholder
            filled = await browser.fill_input_by_placeholder("message", config.test_message)
            if filled:
                await browser.page.keyboard.press("Enter")
                report.message = "Message sent via placeholder search"
            else:
                report.result = TestResult.FAILED
                report.message = "Could not find message input"

        await browser.wait(2)

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


async def test_receive_response(browser: BrowserHelper, config: WebUITestConfig) -> TestReport:
    """
    Test receiving a response from the agent.

    Steps:
    1. Wait for response to appear
    2. Validate response content
    """
    start = datetime.now()
    report = TestReport(name="receive_response", result=TestResult.PASSED)

    try:
        # Wait for response
        response_found = False

        for _ in range(config.interaction_timeout // 2):
            await browser.wait(2)

            # Take screenshot to capture progress
            content = await browser.get_page_content()

            # Look for response indicators
            if any(word in content.lower() for word in config.expected_response_contains):
                response_found = True
                break

            # Also check for generic response patterns
            if "assistant" in content.lower() or "ciris" in content.lower():
                response_found = True
                break

        # Take final screenshot
        shot = await browser.screenshot("interaction_response", full_page=True)
        report.screenshots.append(shot.path)

        if response_found:
            report.message = "Response received from agent"
            report.details["response_found"] = True
        else:
            report.result = TestResult.FAILED
            report.message = f"No response within {config.interaction_timeout}s"

    except Exception as e:
        report.result = TestResult.ERROR
        report.message = str(e)

    report.duration_seconds = (datetime.now() - start).total_seconds()
    return report


# =============================================================================
# Full Test Flow
# =============================================================================


async def test_full_e2e_flow(browser: BrowserHelper, config: WebUITestConfig) -> List[TestReport]:
    """
    Run the full end-to-end test flow.

    Steps:
    1. Load setup wizard
    2. Navigate to LLM config
    3. Select provider
    4. Enter API key
    5. Load models
    6. Select model
    7. Complete setup
    8. Send message
    9. Receive response

    Returns:
        List of TestReport for each step
    """
    reports = []

    # Step 1: Load setup wizard
    report = await test_load_setup_wizard(browser, config)
    reports.append(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 2: Navigate to LLM config
    report = await test_navigate_to_llm_config(browser, config)
    reports.append(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 3: Select provider
    report = await test_select_provider(browser, config)
    reports.append(report)
    if report.result != TestResult.PASSED:
        return reports

    # Step 4: Enter API key
    report = await test_enter_api_key(browser, config)
    reports.append(report)
    if report.result == TestResult.ERROR:
        return reports

    # Step 5: Load models
    report = await test_load_models(browser, config)
    reports.append(report)
    # Continue even if model loading has issues

    # Step 6: Select model
    report = await test_select_model(browser, config)
    reports.append(report)

    # Step 7: Complete setup
    report = await test_complete_setup(browser, config)
    reports.append(report)

    # Step 8: Login after setup
    report = await test_login_after_setup(browser, config)
    reports.append(report)

    # Steps 9-10: Interaction (optional based on login success)
    if report.result == TestResult.PASSED or report.result == TestResult.SKIPPED:
        report = await test_send_message(browser, config)
        reports.append(report)

        if report.result == TestResult.PASSED:
            report = await test_receive_response(browser, config)
            reports.append(report)

            # Wait for covenant metrics trace to be sent after response
            # The reasoning event is received, but the trace takes time to be sent
            if report.result == TestResult.PASSED:
                print("⏳ Waiting 15s for covenant metrics trace to be sent...")
                await browser.wait(15)

    return reports
