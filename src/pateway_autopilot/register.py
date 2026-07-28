"""
PatewayAI Registration Flow
=============================

Complete 7-step registration:
    1. Navigate to homepage → Click "Get Started"
    2. Enter email → Click "Send code"
    3. Solve slider puzzle CAPTCHA
    4. Enter OTP + password + invite code → "Sign up"
    5. Account created → Click "Get started"
    6. Console → API Keys → "Create Key"
    7. Capture API key (shown only once!)
"""

import asyncio
import random
import time
from typing import Optional

from .infra import config
from .infra.tempik import TempikClient
from .captcha.slider import SliderSolver, ManualSolver
from .utils.logger import log, log_ok, log_err, log_warn, log_step, log_debug


async def register_and_verify(
    page,
    email: str,
    identity: dict,
    tempik: TempikClient,
    manual_captcha: bool = False,
    acct_num: int = 0,
    invite_code: str = "",
) -> Optional[str]:
    """Full PatewayAI registration flow.

    Args:
        page: Playwright/Camoufox page object.
        email: Temp email address to register with.
        identity: Dict with first_name, last_name, display_name, password.
        tempik: TempikClient instance for OTP retrieval.
        manual_captcha: If True, pause for manual captcha solving.
        acct_num: Account number for logging (parallel mode).
        invite_code: Optional invite code.

    Returns:
        API key string if successful, None otherwise.
    """
    config.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    slider_solver = SliderSolver(max_attempts=config.MAX_CAPTCHA_ATTEMPTS)
    manual_solver = ManualSolver(timeout=config.CAPTCHA_TIMEOUT)

    try:
        # ═══ STEP 1: Navigate to PatewayAI ═══
        log_step(1, 7, "Opening PatewayAI...")
        await page.goto(config.PATEWAY_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        # ═══ STEP 2: Click "Get Started" ═══
        log_step(2, 7, "Clicking 'Get Started'...")
        get_started = page.locator('button:has-text("Get Started"), a:has-text("Get Started")').first
        await get_started.click(timeout=10000)
        await asyncio.sleep(1)

        # Wait for modal
        await page.wait_for_selector('input[type="email"], input[placeholder*="example"]', timeout=10000)

        # ═══ STEP 3: Enter email and send code ═══
        log_step(3, 7, f"Entering email: {email}")
        email_input = page.locator('input[type="email"], input[placeholder*="example"]').first
        await email_input.fill(email)
        await asyncio.sleep(0.3)

        # Click "Send code"
        send_code_btn = page.locator('button:has-text("Send code"), button:has-text("发送")').first
        await send_code_btn.click(timeout=5000)
        await asyncio.sleep(1)

        # ═══ STEP 4: Solve slider CAPTCHA ═══
        log_step(4, 7, "Solving slider CAPTCHA...")
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "before_captcha.png"))

        if manual_captcha:
            captcha_ok = await manual_solver.solve(page)
        else:
            captcha_ok = await slider_solver.solve(page)
            if not captcha_ok:
                log_warn("Auto solve failed, falling back to manual...")
                captcha_ok = await manual_solver.solve(page)

        if not captcha_ok:
            log_err("CAPTCHA solve failed!")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / "captcha_fail.png"))
            return None

        await asyncio.sleep(1)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "after_captcha.png"))

        # ═══ STEP 5: Enter OTP and password ═══
        log_step(5, 7, "Waiting for OTP...")
        otp = await tempik.wait_for_otp(email, timeout=config.OTP_TIMEOUT)

        if not otp:
            log_err(f"OTP not received within {config.OTP_TIMEOUT}s")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / "otp_timeout.png"))
            return None

        log_ok(f"OTP received: {otp}")

        # Fill OTP
        log_step(6, 7, "Entering OTP and password...")
        otp_inputs = page.locator('input[maxlength="1"]')
        otp_count = await otp_inputs.count()

        if otp_count >= len(otp):
            for i, digit in enumerate(otp):
                await otp_inputs.nth(i).click()
                await page.keyboard.type(digit, delay=random.randint(10, 30))
                await asyncio.sleep(random.uniform(0.05, 0.1))
            log_ok("OTP entered!")
        else:
            # Single input fallback
            otp_input = page.locator('input[placeholder*="code"], input[placeholder*="OTP"]').first
            await otp_input.fill(otp)
            log_ok("OTP entered (single input)!")

        # Fill password
        pw_inputs = page.locator('input[type="password"]')
        pw_count = await pw_inputs.count()

        if pw_count >= 2:
            await pw_inputs.nth(0).fill(identity["password"])
            await pw_inputs.nth(1).fill(identity["password"])
            log_ok("Password filled!")
        elif pw_count == 1:
            await pw_inputs.nth(0).fill(identity["password"])
            log_ok("Password filled!")

        # Fill invite code if provided
        if invite_code:
            try:
                invite_input = page.locator(
                    'input[placeholder*="invitation"], input[placeholder*="invite"]'
                ).first
                await invite_input.fill(invite_code)
                log(f"   Invite code filled: {invite_code}")
            except Exception:
                log_debug("No invite code field found")

        # Check ToS checkbox
        try:
            await page.evaluate("""() => {
                const cb = document.querySelector('input[type="checkbox"]');
                if (cb && !cb.checked) cb.click();
            }""")
        except Exception:
            pass

        # Click "Sign up"
        signup_btn = page.locator('button:has-text("Sign up"), button:has-text("注册")').first
        await signup_btn.click(timeout=5000)
        await asyncio.sleep(2)

        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "after_signup.png"))

        # ═══ STEP 6: Verify account creation ═══
        log_step(7, 7, "Verifying account creation...")

        # Check for success modal
        try:
            await page.wait_for_selector(
                'text=/Account created|account created|注册成功/',
                timeout=15000,
            )
            log_ok("Account created successfully!")
        except Exception:
            # Check page text for success
            page_text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 500) || ''"
            )
            if "created" in page_text.lower() or "成功" in page_text:
                log_ok("Account created!")
            else:
                log_warn("Could not confirm account creation, continuing...")

        # Click "Get started" to proceed
        try:
            get_started_btn = page.locator('button:has-text("Get started")').first
            await get_started_btn.click(timeout=5000)
            await asyncio.sleep(2)
        except Exception:
            log_debug("No 'Get started' button found, may already be on dashboard")

        # ═══ STEP 7: Create API key ═══
        api_key = await create_api_key(page)
        if api_key:
            log_ok(f"API Key captured: {api_key[:20]}...")
            return api_key
        else:
            log_err("Failed to capture API key")
            return None

    except Exception as e:
        log_err(f"Registration error: {e}")
        try:
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / "error.png"))
        except Exception:
            pass
        return None


async def create_api_key(page) -> Optional[str]:
    """Create and capture API key from Console.

    The API key is shown only once — must capture immediately!

    Args:
        page: Playwright page object (already on dashboard).

    Returns:
        API key string if captured, None otherwise.
    """
    captured_key = None

    # Set up response listener
    async def on_response(response):
        nonlocal captured_key
        try:
            url = response.url
            if any(kw in url for kw in ["apikey", "api-key", "key/create", "keys"]):
                body = await response.json()
                # Look for sk-ptw-* pattern
                import re

                body_str = str(body)
                match = re.search(r"sk-ptw-[a-zA-Z0-9]+", body_str)
                if match:
                    captured_key = match.group(0)
                    log_ok(f"API key intercepted from response: {captured_key[:20]}...")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        # Navigate to API Keys page
        log("   Navigating to API Keys...")
        await asyncio.sleep(1)

        # Click "API Keys" in sidebar or navigate directly
        try:
            api_keys_link = page.locator('text="API Keys"').first
            await api_keys_link.click(timeout=5000)
        except Exception:
            # Try direct navigation
            current_url = page.url
            if "/console" in current_url or "/dashboard" in current_url:
                log_debug("Already on console page")

        await asyncio.sleep(1)

        # Click "Create Key"
        log("   Clicking 'Create Key'...")
        create_key_btn = page.locator(
            'button:has-text("Create Key"), button:has-text("创建")'
        ).first
        await create_key_btn.click(timeout=5000)
        await asyncio.sleep(1)

        # Fill key name
        key_name = config.KEY_NAME
        log(f"   Setting key name: {key_name}")
        key_name_input = page.locator(
            'input[placeholder*="name"], input[placeholder*="Name"]'
        ).first
        await key_name_input.fill(key_name)

        # Service Mode - default is "Economy Mode", no need to change
        log("   Using default Service Mode (Economy)")

        # Click "Create"
        log("   Clicking 'Create'...")
        create_btn = page.locator('button:has-text("Create")').last
        await create_btn.click(timeout=5000)

        # Wait for response
        await asyncio.sleep(2)

        # If response listener didn't capture, try UI extraction
        if not captured_key:
            log("   Trying UI extraction...")
            captured_key = await _extract_key_from_ui(page)

        # If still not captured, try clipboard
        if not captured_key:
            log("   Trying clipboard...")
            captured_key = await _extract_key_from_clipboard(page)

        if captured_key:
            # Click "Done, close" or similar
            try:
                done_btn = page.locator(
                    'button:has-text("Done"), button:has-text("Close"), button:has-text("完成")'
                ).first
                await done_btn.click(timeout=3000)
            except Exception:
                pass

        return captured_key

    except Exception as e:
        log_err(f"API key creation error: {e}")
        return None

    finally:
        # Remove response listener
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass


async def _extract_key_from_ui(page) -> Optional[str]:
    """Extract API key from the 'Key Created' modal."""
    try:
        import re

        # Look for elements containing sk-ptw- pattern
        elements = await page.query_selector_all("text=/sk-ptw-/")
        for element in elements:
            text = await element.text_content()
            match = re.search(r"sk-ptw-[a-zA-Z0-9]+", text)
            if match:
                return match.group(0)

        # Try code/pre elements
        code_elements = await page.query_selector_all("code, pre")
        for element in code_elements:
            text = await element.text_content()
            match = re.search(r"sk-ptw-[a-zA-Z0-9]+", text)
            if match:
                return match.group(0)

        # Try any element with key-like content
        all_text = await page.evaluate("""() => {
            const elements = document.querySelectorAll('[class*="key"], [class*="code"], [class*="value"]');
            return Array.from(elements).map(el => el.textContent).join('\\n');
        }""")
        match = re.search(r"sk-ptw-[a-zA-Z0-9]+", all_text)
        if match:
            return match.group(0)

    except Exception as e:
        log_debug(f"UI extraction failed: {e}")

    return None


async def _extract_key_from_clipboard(page) -> Optional[str]:
    """Extract API key by clicking copy button and reading clipboard."""
    try:
        import re

        # Find and click copy button
        copy_btns = page.locator('button:has-text("Copy")')
        count = await copy_btns.count()

        for i in range(count):
            try:
                await copy_btns.nth(i).click(timeout=2000)
                await asyncio.sleep(0.5)

                # Read clipboard
                clipboard = await page.evaluate("navigator.clipboard.readText()")
                if clipboard:
                    match = re.search(r"sk-ptw-[a-zA-Z0-9]+", clipboard)
                    if match:
                        return match.group(0)
            except Exception:
                continue

    except Exception as e:
        log_debug(f"Clipboard extraction failed: {e}")

    return None
