#!/usr/bin/env python3
"""
Test the Setup Wizard UI with live model listing feature.
Uses Playwright with Firefox to test the setup page.
"""

import asyncio
import os

from playwright.async_api import async_playwright


async def test_setup_wizard():
    """Test the setup wizard with model listing."""

    # Get API key from file for testing live model listing
    openrouter_key = None
    key_file = os.path.expanduser("~/.openrouter_key")
    if os.path.exists(key_file):
        with open(key_file) as f:
            openrouter_key = f.read().strip()
            print(f"Found OpenRouter key: {openrouter_key[:15]}...")

    async with async_playwright() as p:
        # Launch Firefox (not headless so we can see it)
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 1200})  # Taller viewport
        page = await context.new_page()

        print("\n=== Testing CIRIS Setup Wizard - Model Listing Feature ===\n")

        # Navigate to setup page
        print("1. Navigating to setup page...")
        await page.goto("http://localhost:8080/setup")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Click "Continue to LLM Setup"
        print("2. Clicking 'Continue to LLM Setup'...")
        continue_btn = page.get_by_text("Continue to LLM Setup")
        if await continue_btn.count() > 0:
            await continue_btn.click()
            await asyncio.sleep(2)
            print("   Navigated to LLM configuration")

        # Select OpenRouter provider
        print("3. Selecting OpenRouter provider...")
        openrouter_option = page.get_by_text("OpenRouter", exact=False)
        if await openrouter_option.count() > 0:
            await openrouter_option.first.click()
            await asyncio.sleep(1)
            print("   Selected OpenRouter")

        # Enter API key
        if openrouter_key:
            print("4. Entering API key...")
            api_input = page.locator("input[type='password']").first
            if await api_input.count() > 0:
                await api_input.fill(openrouter_key)
                print("   API key entered")

                # Tab out or click elsewhere to trigger the model loading
                await api_input.press("Tab")
                await asyncio.sleep(1)

        # Scroll down to see model selection
        print("5. Scrolling to see model selection...")
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(3)  # Wait for models to load

        # Take full page screenshot
        await page.screenshot(path="/tmp/setup_model_section.png", full_page=True)
        print("   Full page screenshot: /tmp/setup_model_section.png")

        # Look for model-related elements
        print("\n6. Analyzing model selection UI...")

        # Check for select/dropdown elements
        selects = page.locator("select")
        select_count = await selects.count()
        print(f"   Found {select_count} dropdown(s)")

        if select_count > 0:
            for i in range(select_count):
                sel = selects.nth(i)
                options = await sel.locator("option").all_text_contents()
                print(f"   Dropdown {i}: {len(options)} options")
                if options:
                    for opt in options[:8]:
                        print(f"      - {opt[:60]}...")

        # Check for any elements with "model" in their text
        model_elements = page.locator("text=/model/i")
        model_count = await model_elements.count()
        print(f"   Found {model_count} elements mentioning 'model'")

        # Check for loading indicators
        loading = page.locator("text=/loading/i")
        if await loading.count() > 0:
            print("   Loading indicator found - models still loading")

        # Check for recommended/compatible indicators
        recommended = page.locator("text=/recommended/i")
        compatible = page.locator("text=/compatible/i")
        print(f"   Recommended indicators: {await recommended.count()}")
        print(f"   Compatible indicators: {await compatible.count()}")

        # Check page content for specific model names
        content = await page.content()
        model_names = ["claude", "gpt-4", "gpt-3.5", "llama", "mistral", "gemini"]
        found_models = [m for m in model_names if m.lower() in content.lower()]
        if found_models:
            print(f"   Model names found in page: {found_models}")

        # Wait and take another screenshot after more loading time
        print("\n7. Waiting for full model list to load...")
        await asyncio.sleep(5)
        await page.screenshot(path="/tmp/setup_models_loaded.png", full_page=True)
        print("   Screenshot after loading: /tmp/setup_models_loaded.png")

        # Final analysis
        content = await page.content()
        if "★" in content or "recommended" in content.lower():
            print("\n   ✓ Model recommendations appear to be showing!")
        if "✓" in content or "compatible" in content.lower():
            print("   ✓ Compatibility indicators found!")

        # Keep browser open for manual inspection
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
