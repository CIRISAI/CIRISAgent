#!/usr/bin/env python3
"""
Test the Setup Wizard UI with live model listing feature.
Uses Playwright with Firefox to test the setup page.
"""

import asyncio
import os
from typing import Optional

import aiofiles
from playwright.async_api import Page, async_playwright


async def _load_api_key() -> Optional[str]:
    """Load OpenRouter API key from file."""
    key_file = os.path.expanduser("~/.openrouter_key")
    if not os.path.exists(key_file):
        return None

    async with aiofiles.open(key_file) as f:
        key = (await f.read()).strip()
        print(f"Found OpenRouter key: {key[:15]}...")
        return key


async def _navigate_to_llm_setup(page: Page) -> None:
    """Navigate to the LLM setup section."""
    print("1. Navigating to setup page...")
    await page.goto("http://localhost:8080/setup")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    print("2. Clicking 'Continue to LLM Setup'...")
    continue_btn = page.get_by_text("Continue to LLM Setup")
    if await continue_btn.count() > 0:
        await continue_btn.click()
        await asyncio.sleep(2)
        print("   Navigated to LLM configuration")


async def _select_provider_and_enter_key(page: Page, api_key: Optional[str]) -> None:
    """Select OpenRouter and enter API key."""
    print("3. Selecting OpenRouter provider...")
    openrouter_option = page.get_by_text("OpenRouter", exact=False)
    if await openrouter_option.count() > 0:
        await openrouter_option.first.click()
        await asyncio.sleep(1)
        print("   Selected OpenRouter")

    if api_key:
        print("4. Entering API key...")
        api_input = page.locator("input[type='password']").first
        if await api_input.count() > 0:
            await api_input.fill(api_key)
            await api_input.press("Tab")
            await asyncio.sleep(1)
            print("   API key entered")


async def _analyze_dropdowns(page: Page) -> None:
    """Analyze dropdown elements on the page."""
    selects = page.locator("select")
    select_count = await selects.count()
    print(f"   Found {select_count} dropdown(s)")

    for i in range(min(select_count, 5)):
        sel = selects.nth(i)
        options = await sel.locator("option").all_text_contents()
        print(f"   Dropdown {i}: {len(options)} options")
        for opt in options[:8]:
            print(f"      - {opt[:60]}...")


async def _analyze_model_ui(page: Page) -> None:
    """Analyze model selection UI elements."""
    print("\n6. Analyzing model selection UI...")
    await _analyze_dropdowns(page)

    model_count = await page.locator("text=/model/i").count()
    print(f"   Found {model_count} elements mentioning 'model'")

    if await page.locator("text=/loading/i").count() > 0:
        print("   Loading indicator found - models still loading")

    print(f"   Recommended indicators: {await page.locator('text=/recommended/i').count()}")
    print(f"   Compatible indicators: {await page.locator('text=/compatible/i').count()}")


async def _check_model_names(page: Page) -> None:
    """Check for known model names in page content."""
    content = await page.content()
    model_names = ["claude", "gpt-4", "gpt-3.5", "llama", "mistral", "gemini"]
    found_models = [m for m in model_names if m.lower() in content.lower()]
    if found_models:
        print(f"   Model names found in page: {found_models}")


async def _final_analysis(page: Page) -> None:
    """Perform final analysis of page content."""
    content = await page.content()
    if "★" in content or "recommended" in content.lower():
        print("\n   ✓ Model recommendations appear to be showing!")
    if "✓" in content or "compatible" in content.lower():
        print("   ✓ Compatibility indicators found!")


async def test_setup_wizard() -> None:
    """Test the setup wizard with model listing."""
    openrouter_key = await _load_api_key()

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 1200})
        page = await context.new_page()

        print("\n=== Testing CIRIS Setup Wizard - Model Listing Feature ===\n")

        await _navigate_to_llm_setup(page)
        await _select_provider_and_enter_key(page, openrouter_key)

        print("5. Scrolling to see model selection...")
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(3)

        await page.screenshot(path="/tmp/setup_model_section.png", full_page=True)
        print("   Full page screenshot: /tmp/setup_model_section.png")

        await _analyze_model_ui(page)
        await _check_model_names(page)

        print("\n7. Waiting for full model list to load...")
        await asyncio.sleep(5)
        await page.screenshot(path="/tmp/setup_models_loaded.png", full_page=True)
        print("   Screenshot after loading: /tmp/setup_models_loaded.png")

        await _final_analysis(page)

        print("\n=== Browser open for 90 seconds - manually test the model dropdown ===")
        print("Try selecting different models and see the live listing\n")

        try:
            await asyncio.sleep(90)
        except KeyboardInterrupt:
            print("Closing...")

        await browser.close()
        print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(test_setup_wizard())
