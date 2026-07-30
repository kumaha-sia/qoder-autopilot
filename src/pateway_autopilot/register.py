"""
PatewayAI Registration Flow
=============================

Complete 7-step registration with human-like behavior:
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

from .auth.credentials import mask_value
from .infra import config
from .infra.temp_mail import TempMailClient
from .captcha.slider import SliderSolver, ManualSolver
from .utils.logger import log, log_ok, log_err, log_warn, log_step, log_debug


# ═══════════════════════════════════════════════════════════════════════════════
# HUMAN-LIKE BEHAVIOR HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


async def human_delay(min_ms: int = 500, max_ms: int = 2000):
    """Random delay that mimics human reaction time."""
    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)


async def human_think(pause_type: str = "normal"):
    """Simulate human thinking time based on action type."""
    delays = {
        "quick": (200, 500),      # Quick glance
        "normal": (500, 1500),    # Normal thinking
        "careful": (1000, 2500),  # Careful consideration
        "reading": (1500, 3000),  # Reading content
        "typing": (50, 150),      # Between keystrokes
    }
    min_ms, max_ms = delays.get(pause_type, delays["normal"])
    await human_delay(min_ms, max_ms)


async def human_move_mouse(page, x: int, y: int):
    """Move mouse to position with human-like curve."""
    # Get current mouse position (approximate)
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    start_x = random.randint(100, viewport["width"] - 100)
    start_y = random.randint(100, viewport["height"] - 100)

    # Calculate distance
    distance = ((x - start_x) ** 2 + (y - start_y) ** 2) ** 0.5
    steps = max(5, int(distance / 50))

    # Move with slight curve
    for i in range(steps):
        progress = i / (steps - 1)
        # Add slight randomness to path
        curve_offset = random.randint(-20, 20)
        current_x = start_x + (x - start_x) * progress + curve_offset
        current_y = start_y + (y - start_y) * progress + random.randint(-5, 5)
        await page.mouse.move(current_x, current_y)
        await asyncio.sleep(random.uniform(0.01, 0.03))

    # Final position
    await page.mouse.move(x, y)


async def human_type(page, text: str, min_delay: int = 30, max_delay: int = 120):
    """Type text with human-like speed variation."""
    for i, char in enumerate(text):
        await page.keyboard.type(char, delay=random.randint(min_delay, max_delay))
        # Occasionally pause longer (like thinking about next char)
        if random.random() < 0.1:  # 10% chance of longer pause
            await asyncio.sleep(random.uniform(0.2, 0.5))


async def human_click(page, element, timeout: int = 10000):
    """Click element with human-like behavior."""
    try:
        # Get element position
        box = await element.bounding_box()
        if box:
            # Move mouse to element with some randomness
            target_x = box["x"] + box["width"] / 2 + random.randint(-10, 10)
            target_y = box["y"] + box["height"] / 2 + random.randint(-5, 5)
            await human_move_mouse(page, target_x, target_y)
            await human_delay(100, 300)

        # Click
        await element.click(timeout=timeout)
        await human_delay(200, 500)

    except Exception as e:
        log_debug(f"Human click failed, using force click: {e}")
        await element.click(timeout=timeout, force=True)


async def human_scroll(page, direction: str = "down", amount: int = None):
    """Scroll page like a human."""
    if amount is None:
        amount = random.randint(100, 300)

    if direction == "down":
        await page.mouse.wheel(0, amount)
    else:
        await page.mouse.wheel(0, -amount)

    await human_delay(300, 800)


async def random_mouse_movement(page):
    """Move mouse to random positions to simulate human behavior."""
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    x = random.randint(100, viewport["width"] - 100)
    y = random.randint(100, viewport["height"] - 100)
    await page.mouse.move(x, y)
    await human_delay(100, 300)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN REGISTRATION FLOW
# ═══════════════════════════════════════════════════════════════════════════════


async def _wait_for_manual_otp(page, timeout: int = 120) -> Optional[str]:
    """Wait for user to manually enter OTP in the browser.

    Monitors OTP input fields for user entry.
    Returns the entered OTP string, or None if timeout.
    """
    import time
    start = time.time()
    log("   ⌨️  Type the OTP code in the browser window...")

    while time.time() - start < timeout:
        await asyncio.sleep(2)

        # Check if OTP fields have been filled
        otp_value = await page.evaluate("""() => {
            // Check individual digit inputs
            const digitInputs = document.querySelectorAll('input[maxlength="1"]');
            if (digitInputs.length >= 6) {
                let code = '';
                for (const inp of digitInputs) {
                    if (inp.value) code += inp.value;
                    else return null;  // Not all filled yet
                }
                if (code.length >= 4) return code;
            }
            // Check single code input
            const codeInput = document.querySelector(
                'input[placeholder*="code"], input[placeholder*="OTP"], input[name*="code"]'
            );
            if (codeInput && codeInput.value && codeInput.value.length >= 4) {
                return codeInput.value;
            }
            return null;
        }""")

        if otp_value:
            log_ok(f"OTP entered: {otp_value}")
            return otp_value

        # Check if page progressed (password inputs appeared)
        has_password = await page.evaluate("""() => {
            return document.querySelectorAll('input[type="password"]').length > 0;
        }""")

        if has_password:
            # Password fields visible means OTP was accepted
            # Try to extract what was entered
            otp_value = await page.evaluate("""() => {
                const digitInputs = document.querySelectorAll('input[maxlength="1"]');
                if (digitInputs.length >= 4) {
                    return Array.from(digitInputs).map(i => i.value).join('');
                }
                const codeInput = document.querySelector(
                    'input[placeholder*="code"], input[placeholder*="OTP"]'
                );
                return codeInput ? codeInput.value : null;
            }""")
            if otp_value:
                log_ok(f"OTP accepted: {otp_value}")
                return otp_value
            log_ok("OTP accepted (password fields visible)")
            return "manual"  # Signal that OTP was entered

        elapsed = int(time.time() - start)
        remaining = timeout - elapsed
        if remaining % 10 < 2:
            log_debug(f"Waiting for manual OTP... {remaining}s remaining")

    return None


async def register_and_verify(
    page,
    email: str,
    identity: dict,
    temp_mail: TempMailClient,
    manual_captcha: bool = False,
    acct_num: int = 0,
    invite_code: str = "",
) -> Optional[str]:
    """Full PatewayAI registration flow with human-like behavior.

    Args:
        page: Playwright/Camoufox page object.
        email: Temp email address to register with.
        identity: Dict with first_name, last_name, display_name, password.
        temp_mail: TempMailClient instance for OTP retrieval.
        manual_captcha: If True, pause for manual captcha solving.
        acct_num: Account number for logging (parallel mode).
        invite_code: Optional invite code.

    Returns:
        API key string if successful, None otherwise.
    """
    config.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    slider_solver = SliderSolver(max_attempts=config.MAX_CAPTCHA_ATTEMPTS)
    manual_solver = ManualSolver(timeout=config.CAPTCHA_TIMEOUT)
    suffix = f"_{acct_num}" if acct_num else ""

    try:
        # ═══ STEP 1: Navigate to PatewayAI ═══
        log_step(1, 7, "Opening PatewayAI...")
        await page.goto(config.PATEWAY_URL, wait_until="networkidle", timeout=30000)

        # Simulate human looking at the page
        await human_think("reading")
        await random_mouse_movement(page)
        await human_delay(1000, 2000)

        # ═══ STEP 2: Click "Get Started" ═══
        log_step(2, 7, "Clicking 'Get Started'...")
        get_started = page.locator('button:has-text("Get Started"), a:has-text("Get Started")').first

        # Move mouse around a bit before clicking
        await random_mouse_movement(page)
        await human_think("normal")

        await human_click(page, get_started, timeout=10000)

        # Wait for modal with human-like patience
        await human_think("careful")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"after_get_started{suffix}.png"))
        
        # Debug: check what page we're on
        current_url = page.url
        page_title = await page.title()
        log_debug(f"After Get Started — URL: {current_url}, Title: {page_title}")

        try:
            await page.wait_for_selector('input[type="email"], input[placeholder*="example"]', timeout=10000)
        except Exception:
            log_warn("Email input not found after Get Started — trying direct navigation to signup")
            # Try direct navigation to signup/register page
            try:
                await page.goto(f"{config.PATEWAY_URL}/#/signup", wait_until="networkidle", timeout=15000)
                await human_think("reading")
                await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"after_signup_nav{suffix}.png"))
            except Exception:
                pass
            try:
                await page.wait_for_selector('input[type="email"], input[placeholder*="example"]', timeout=10000)
            except Exception:
                log_err("Still cannot find email input — page structure may have changed")
                return None

        # Simulate reading the modal
        await human_think("reading")

        # ═══ STEP 3: Enter email and send code ═══
        log_step(3, 7, f"Entering email: {email}")
        email_input = page.locator('input[type="email"], input[placeholder*="example"]').first

        # Click on input field
        await human_click(page, email_input)
        await human_think("quick")

        # Type email like a human
        await human_type(page, email, min_delay=50, max_delay=150)

        # Pause after typing (like reviewing)
        await human_think("reading")

        # Click "Send code"
        send_code_btn = page.locator('button:has-text("Send code"), button:has-text("发送")').first
        await human_click(page, send_code_btn, timeout=5000)

        # Wait for response
        await human_think("careful")
        await asyncio.sleep(random.uniform(2, 3))

        # Check for error messages after clicking "Send code"
        # Use JS to find error text within the modal/form context only
        try:
            error_text = await page.evaluate("""() => {
                const modal = document.querySelector('[class*="modal"], [class*="dialog"], form');
                const root = modal || document.body;
                const errorSelectors = [
                    '.toast-error', '.alert-error', '.el-message--error',
                    '[class*="error-msg"]', '[class*="errorMsg"]', '[class*="error-text"]',
                ];
                for (const sel of errorSelectors) {
                    const el = root.querySelector(sel);
                    if (el && el.offsetParent !== null && el.textContent.trim()) {
                        return el.textContent.trim();
                    }
                }
                return null;
            }""")
            if error_text:
                log_err(f"Send code failed: {error_text}")
                await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"send_code_error{suffix}.png"))
                return None
        except Exception:
            pass

        # Check if CAPTCHA appeared (means email was accepted)
        # Use specific CAPTCHA selectors to avoid false positives from canvas/verify elements
        captcha_visible = False
        try:
            captcha_visible = await page.evaluate("""() => {
                const captchaSelectors = [
                    '[class*="captcha"]', '[id*="captcha"]',
                    '[class*="slider-puzzle"]', '[class*="geetest"]',
                    '[class*="nc_wrapper"]', '[class*="verify-wrap"]',
                ];
                for (const sel of captchaSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 50 && rect.height > 30) return true;
                    }
                }
                return false;
            }""")
        except Exception:
            pass

        if not captcha_visible:
            page_text = await page.evaluate("() => document.body?.innerText?.substring(0, 500) || ''")
            log_err("No CAPTCHA appeared after Send code. Email may be rejected.")
            log_debug(f"Page text: {page_text[:300]}")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"no_captcha{suffix}.png"))
            return None

        # ═══ STEP 4: Solve slider CAPTCHA ═══
        log_step(4, 7, "Solving slider CAPTCHA...")
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"before_captcha{suffix}.png"))

        if manual_captcha:
            captcha_ok = await manual_solver.solve(page)
        else:
            captcha_ok = await slider_solver.solve(page)
            if not captcha_ok:
                log_warn("Auto solve failed, falling back to manual...")
                captcha_ok = await manual_solver.solve(page)

        if not captcha_ok:
            log_err("CAPTCHA solve failed!")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"captcha_fail{suffix}.png"))
            return None

        # Wait after captcha solve (email being sent)
        await human_think("reading")
        await asyncio.sleep(random.uniform(2, 4))
        # Don't screenshot here — OTP/password fields may be visible

        # ═══ STEP 5: Enter OTP and password ═══
        log_step(5, 7, "Waiting for OTP...")

        if temp_mail:
            log(f"   Checking inbox for {email}...")
            # Wait like a human checking their email
            await human_think("reading")
            await asyncio.sleep(random.uniform(3, 5))
            otp = await temp_mail.wait_for_otp(timeout=config.OTP_TIMEOUT)

            if not otp:
                log_err(f"OTP not received within {config.OTP_TIMEOUT}s")
                try:
                    messages = await temp_mail.get_messages()
                    log(f"   Found {len(messages)} messages in inbox")
                    for msg in messages:
                        log(f"   - From: {msg.get('from_address')}, Subject: {msg.get('subject')}")
                except Exception as e:
                    log(f"   Error checking messages: {e}")
                await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"otp_timeout{suffix}.png"))
                return None
        else:
            # User provided their own email — ask for OTP manually
            log(f"   ⏳ Waiting for OTP to {email}...")
            log(f"   📧 Check your email inbox and enter the OTP in the browser")
            # Wait for manual OTP entry
            otp = await _wait_for_manual_otp(page, timeout=config.OTP_TIMEOUT)
            if not otp:
                log_err("Manual OTP entry timeout")
                return None

        log_ok(f"OTP received: {otp}")

        # Simulate human looking at OTP and thinking
        await human_think("careful")

        # Fill OTP
        log_step(5, 7, "Entering OTP and password...")
        otp_inputs = page.locator('input[maxlength="1"]')
        otp_count = await otp_inputs.count()

        if otp_count >= len(otp):
            for i, digit in enumerate(otp):
                await human_click(page, otp_inputs.nth(i))
                await human_think("typing")
                await page.keyboard.type(digit, delay=random.randint(80, 200))
                # Sometimes pause longer between digits
                if random.random() < 0.3:
                    await human_delay(200, 500)
            log_ok("OTP entered!")
        else:
            otp_input = page.locator('input[placeholder*="code"], input[placeholder*="OTP"]').first
            await human_click(page, otp_input)
            await human_type(page, otp, min_delay=80, max_delay=200)
            log_ok("OTP entered (single input)!")

        # Pause before password
        await human_think("normal")

        # Fill password
        pw_inputs = page.locator('input[type="password"]')
        pw_count = await pw_inputs.count()

        if pw_count >= 2:
            await human_click(page, pw_inputs.nth(0))
            await human_type(page, identity["password"], min_delay=50, max_delay=120)
            await human_think("quick")
            await human_click(page, pw_inputs.nth(1))
            await human_type(page, identity["password"], min_delay=50, max_delay=120)
            log_ok("Password filled!")
        elif pw_count == 1:
            await human_click(page, pw_inputs.nth(0))
            await human_type(page, identity["password"], min_delay=50, max_delay=120)
            log_ok("Password filled!")

        # Fill invite code if provided
        if invite_code:
            try:
                invite_input = page.locator(
                    'input[placeholder*="invitation"], input[placeholder*="invite"], input[id*="inviteCode"]'
                ).first
                await human_click(page, invite_input)
                await human_type(page, invite_code, min_delay=60, max_delay=150)
                log(f"   Invite code filled: {invite_code}")
            except Exception:
                log_debug("No invite code field found")

        # Check ToS checkbox with human-like behavior
        await human_think("normal")
        try:
            # Find and click checkbox
            checkbox = page.locator('input[type="checkbox"]').first
            await human_click(page, checkbox)
        except Exception:
            # Fallback to JS
            await page.evaluate("""() => {
                const cb = document.querySelector('input[type="checkbox"]');
                if (cb && !cb.checked) cb.click();
            }""")

        # Scroll down naturally
        await human_scroll(page, "down", random.randint(100, 300))
        await human_think("normal")

        # Click "Sign up"
        log("   Clicking Sign up button...")
        signup_btn = page.locator(
            'button:has-text("Sign up"), button:has-text("注册"), button.btn--dark'
        ).first

        try:
            await human_click(page, signup_btn, timeout=10000)
        except Exception:
            log_debug("Direct click failed, using JS fallback")
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.toLowerCase().includes('sign up')) {
                        btn.click();
                        return true;
                    }
                }
                const darkBtns = document.querySelectorAll('.btn--dark');
                for (const btn of darkBtns) {
                    const t = btn.textContent.toLowerCase();
                    if (t.includes('sign') || t.includes('注册') || t.includes('submit') || t.includes('confirm')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        # Wait for response
        await human_think("careful")
        await asyncio.sleep(random.uniform(2, 4))

        # ═══ STEP 6: Verify account creation ═══
        log_step(7, 7, "Verifying account creation...")

        # Wait for PatewayAI to auto-redirect (no manual navigation!)
        await human_think("reading")
        await asyncio.sleep(random.uniform(3, 5))

        current_url = page.url
        log(f"   Current URL: {current_url}")

        # Check for "Account created" modal — click "Get started" if present
        page_text = await page.evaluate(
            "() => document.body?.innerText?.substring(0, 1000) || ''"
        )
        page_text_lower = page_text.lower()

        has_created_modal = "account created" in page_text_lower or "注册成功" in page_text_lower
        if has_created_modal:
            log_ok("Account created modal detected!")
            try:
                get_started_btn = page.locator('button:has-text("Get started"), button:has-text("开始")').first
                await human_click(page, get_started_btn, timeout=5000)
                await human_think("normal")
                await asyncio.sleep(random.uniform(3, 5))
                current_url = page.url
                log(f"   After Get started — URL: {current_url}")
            except Exception:
                log_debug("No 'Get started' button found")

        # Just wait — PatewayAI handles the redirect automatically
        log_ok(f"Account created! Current page: {current_url}")

        await human_think("normal")

        # ═══ STEP 7: Create API key ═══
        api_key = await create_api_key(page, acct_num=acct_num)
        if api_key:
            log_ok(f"API Key captured: {mask_value(api_key)}")
            return api_key
        else:
            log_err("Failed to capture API key")
            return None

    except Exception as e:
        log_err(f"Registration error: {e}")
        try:
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"error{suffix}.png"))
        except Exception:
            pass
        return None


async def create_api_key(page, acct_num: int = 0) -> Optional[str]:
    """Create and capture API key from Console with human-like behavior."""
    suffix = f"_{acct_num}" if acct_num else ""
    captured_key = None

    async def on_response(response):
        nonlocal captured_key
        try:
            url = response.url
            if any(kw in url for kw in ["apikey", "api-key", "key/create", "keys"]):
                body = await response.json()
                import re
                body_str = str(body)
                match = re.search(r"sk-ptw-[a-zA-Z0-9]+", body_str)
                if match:
                    captured_key = match.group(0)
                    log_ok(f"API key intercepted from response: {mask_value(captured_key)}")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        log("   Preparing to create API key...")
        await human_think("normal")

        # Wait for console page to fully load (SPA rendering)
        log("   Waiting for console page to load...")
        try:
            await page.wait_for_selector('button, table, [class*="key"], [class*="api"]', timeout=15000)
        except Exception:
            log_warn("Console page elements not detected, continuing anyway...")
        await asyncio.sleep(2)

        await human_think("reading")

        await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"before_create_key{suffix}.png"))

        page_text = await page.evaluate(
            "() => document.body?.innerText?.substring(0, 500) || ''"
        )
        log_debug(f"Page text: {page_text[:200]}")

        # Find Create Key button
        log("   Clicking 'Create Key'...")
        create_key_btn = None

        selectors = [
            'button:has-text("Create Key")',
            'button:has-text("创建")',
            'button:has-text("New Key")',
            'button:has-text("Add Key")',
            'button:has-text("Generate")',
            'button[class*="create"]',
            'a:has-text("Create Key")',
        ]

        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    create_key_btn = btn
                    log_debug(f"Found button with selector: {sel}")
                    break
            except Exception:
                continue

        if create_key_btn:
            await human_click(page, create_key_btn, timeout=10000)
            await human_think("normal")
        else:
            log("   Trying JavaScript click for Create Key...")
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a');
                for (const btn of buttons) {
                    const text = btn.textContent.toLowerCase();
                    if ((text.includes('create') || text.includes('add') || text.includes('new')) &&
                        (text.includes('key') || text.includes('创建'))) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            await human_think("normal")

        # Wait for Create Key modal to appear, then fill key name
        key_name = config.KEY_NAME
        log(f"   Setting key name: {key_name}")
        try:
            # Wait for modal/input to appear after clicking Create Key
            key_name_input = page.locator(
                'input[placeholder*="name"], input[placeholder*="Name"], input[id*="name"], input[id*="keyName"]'
            ).first
            await key_name_input.wait_for(state="visible", timeout=10000)

            await human_click(page, key_name_input)
            await human_type(page, key_name, min_delay=60, max_delay=150)
            await human_think("normal")
        except Exception as e:
            log_warn(f"Key name input not found: {e}")
            log_debug("Trying alternative selectors...")
            # Try any visible input in a modal/dialog
            try:
                inputs = page.locator('input:visible')
                count = await inputs.count()
                if count > 0:
                    await human_click(page, inputs.first)
                    await human_type(page, key_name, min_delay=60, max_delay=150)
            except Exception:
                log_err("Could not find any input for key name")
                return None

        log("   Using default Service Mode (Economy)")

        # Click "Create" — wait for it to be visible first
        log("   Clicking 'Create'...")
        try:
            create_btn = page.locator('button:has-text("Create"):not(:has-text("Create Key"))').last
            await create_btn.wait_for(state="visible", timeout=5000)
            await human_click(page, create_btn, timeout=10000)
        except Exception:
            # Fallback: try any button with "Create" text
            create_btn = page.locator('button:has-text("Create")').last
            await human_click(page, create_btn, timeout=10000)

        # Wait for response
        await human_think("careful")
        await asyncio.sleep(random.uniform(3, 5))

        if not captured_key:
            log("   Trying UI extraction...")
            captured_key = await _extract_key_from_ui(page)

        if not captured_key:
            log("   Trying clipboard...")
            captured_key = await _extract_key_from_clipboard(page)

        if captured_key:
            # Save key to a nonlocal so caller can persist before modal closes
            _key_ready_callback = getattr(page, "_on_key_captured", None)
            if _key_ready_callback:
                try:
                    await _key_ready_callback(captured_key)
                except Exception:
                    pass
            try:
                done_btn = page.locator(
                    'button:has-text("Done"), button:has-text("Close"), button:has-text("完成")'
                ).first
                await human_click(page, done_btn, timeout=3000)
            except Exception:
                pass

        return captured_key

    except Exception as e:
        log_err(f"API key creation error: {e}")
        return None

    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass


async def _extract_key_from_ui(page) -> Optional[str]:
    """Extract API key from the 'Key Created' modal."""
    try:
        import re

        elements = await page.query_selector_all("text=/sk-ptw-/")
        for element in elements:
            text = await element.text_content()
            match = re.search(r"sk-ptw-[a-zA-Z0-9]+", text)
            if match:
                return match.group(0)

        code_elements = await page.query_selector_all("code, pre")
        for element in code_elements:
            text = await element.text_content()
            match = re.search(r"sk-ptw-[a-zA-Z0-9]+", text)
            if match:
                return match.group(0)

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

        copy_btns = page.locator('button:has-text("Copy")')
        count = await copy_btns.count()

        for i in range(count):
            try:
                await human_click(page, copy_btns.nth(i), timeout=2000)
                await human_delay(300, 600)

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
