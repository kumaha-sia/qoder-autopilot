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

        try:
            await human_click(page, get_started, timeout=10000)
        except Exception:
            log_debug("Get Started click failed, trying JS click")
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a');
                for (const btn of buttons) {
                    if (btn.textContent.trim().toLowerCase().includes('get started')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        # Wait for modal with human-like patience
        await human_think("careful")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"after_get_started{suffix}.png"))
        
        # Debug: check what page we're on
        current_url = page.url
        page_title = await page.title()
        log_debug(f"After Get Started — URL: {current_url}, Title: {page_title}")

        # Check if email input is visible — if not, try direct signup navigation
        try:
            await page.wait_for_selector('input[type="email"], input[placeholder*="example"]', timeout=5000)
        except Exception:
            log_debug("Email input not found after Get Started — checking for auth modal")
            # Check if auth modal is already visible (sometimes modal opens but email input
            # has a different selector)
            has_auth_modal = await page.evaluate("""() => {
                const modal = document.querySelector('[class*="auth-modal"], [class*="modal"]');
                if (modal && modal.offsetParent !== null) return true;
                const emailInput = document.querySelector('input[type="email"]');
                if (emailInput && emailInput.offsetParent !== null) return true;
                return false;
            }""")
            if has_auth_modal:
                log_debug("Auth modal found with different selector")
            else:
                log_warn("Email input not found — trying direct navigation to signup")
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

        # Fill email directly (more reliable than human_click + human_type for Ant Design)
        try:
            await email_input.fill(email)
        except Exception:
            await human_click(page, email_input)
            await human_type(page, email, min_delay=50, max_delay=150)

        # Pause after typing (like reviewing)
        await human_think("reading")

        # Click "Send code" — try multiple methods
        log("   Clicking 'Send code'...")
        send_code_clicked = False
        send_code_selectors = [
            'button:has-text("Send code")',
            'button:has-text("发送")',
            'button:has-text("Send Code")',
            '.auth-modal button[type="submit"]',
            '.auth-modal .ant-btn-primary',
        ]
        for sel in send_code_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(force=True)
                    send_code_clicked = True
                    log_debug(f"Send code clicked via: {sel}")
                    break
            except Exception:
                continue

        if not send_code_clicked:
            log_debug("Send code button not found via selectors, trying JS click")
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const t = btn.textContent.toLowerCase().trim();
                    if (t.includes('send code') || t.includes('发送')) {
                        btn.click();
                        return true;
                    }
                }
                // Try primary button in auth modal
                const modal = document.querySelector('[class*="auth-modal"]');
                if (modal) {
                    const btn = modal.querySelector('button[type="submit"], .ant-btn-primary');
                    if (btn) btn.click();
                }
                return false;
            }""")

        # Wait for response
        await human_think("careful")

        # Poll for either CAPTCHA or direct OTP/password modal (up to 15s)
        # PatewayAI may show CAPTCHA puzzle before sending OTP, OR may skip
        # CAPTCHA entirely and go straight to the registration modal.
        captcha_visible = False
        otp_modal_visible = False
        captcha_poll_start = asyncio.get_running_loop().time()
        captcha_poll_timeout = 15

        while asyncio.get_running_loop().time() - captcha_poll_start < captcha_poll_timeout:
            await asyncio.sleep(1)

            # Check for error messages after clicking "Send code"
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

            # Check if CAPTCHA appeared (means email was accepted, need to solve first)
            try:
                captcha_visible = await page.evaluate("""() => {
                    const captchaSelectors = [
                        '[class*="captcha"]', '[id*="captcha"]',
                        '[class*="slider-puzzle"]', '[class*="geetest"]',
                        '[class*="nc_wrapper"]', '[class*="verify-wrap"]',
                        '[class*="slider-track"]', 'canvas',
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
                if captcha_visible:
                    log("   CAPTCHA detected — solving required before OTP is sent")
                    break
            except Exception:
                pass

            # Check if registration modal appeared directly (no CAPTCHA needed)
            # PatewayAI sometimes skips CAPTCHA and goes straight to OTP/password fields
            try:
                otp_modal_visible = await page.evaluate("""() => {
                    // Look for OTP input or password fields in a modal/form
                    const modal = document.querySelector(
                        '[class*="auth-modal"], [class*="modal"], [class*="dialog"], form'
                    );
                    if (!modal || modal.offsetParent === null) return false;
                    // Check for OTP, password, or verification code inputs
                    const otpInputs = modal.querySelectorAll(
                        'input[placeholder*="code"], input[placeholder*="OTP"], ' +
                        'input[placeholder*="验证"], input[maxlength="1"], ' +
                        'input[type="password"]'
                    );
                    return otpInputs.length > 0;
                }""")
                if otp_modal_visible:
                    log_ok("Registration modal detected directly (no CAPTCHA needed)")
                    break
            except Exception:
                pass

        if not captcha_visible and not otp_modal_visible:
            page_text = await page.evaluate("() => document.body?.innerText?.substring(0, 500) || ''")
            log_err("No CAPTCHA or registration modal appeared after Send code.")
            log_debug(f"Page text: {page_text[:300]}")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"no_captcha{suffix}.png"))
            return None

        # ═══ STEP 4: Solve slider CAPTCHA (only if CAPTCHA appeared) ═══
        if captcha_visible:
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
        else:
            log_step(4, 7, "No CAPTCHA needed — proceeding to OTP")
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

        # Fill OTP — PatewayAI uses single input field (not per-digit)
        log_step(5, 7, "Entering OTP and password...")
        otp_input = page.locator('input[placeholder*="code"], input[placeholder*="OTP"], input[placeholder*="验证"]').first
        try:
            await otp_input.wait_for(state="visible", timeout=5000)
            await otp_input.fill(otp)
            log_ok("OTP entered!")
        except Exception:
            # Fallback: try per-digit inputs
            otp_inputs = page.locator('input[maxlength="1"]')
            otp_count = await otp_inputs.count()
            if otp_count >= len(otp):
                for i, digit in enumerate(otp):
                    await human_click(page, otp_inputs.nth(i))
                    await human_think("typing")
                    await page.keyboard.type(digit, delay=random.randint(80, 200))
                    if random.random() < 0.3:
                        await human_delay(200, 500)
                log_ok("OTP entered (per-digit)!")
            else:
                log_err("Could not find OTP input field")
                return None

        # Pause before password
        await human_think("normal")

        # Fill password — use fill() directly to avoid human_click timeout issues
        # with Ant Design inputs (they have wrapper elements that intercept mouse events)
        pw_inputs = page.locator('input[type="password"]')
        pw_count = await pw_inputs.count()

        if pw_count >= 2:
            await pw_inputs.nth(0).fill(identity["password"])
            await human_think("quick")
            await pw_inputs.nth(1).fill(identity["password"])
            log_ok("Password filled!")
        elif pw_count == 1:
            await pw_inputs.nth(0).fill(identity["password"])
            log_ok("Password filled!")

        # Fill invite code if provided
        if invite_code:
            try:
                invite_input = page.locator(
                    'input[placeholder*="invitation"], input[placeholder*="invite"], input[id*="inviteCode"]'
                ).first
                await invite_input.fill(invite_code)
                log(f"   Invite code filled: {invite_code}")
            except Exception:
                log_debug("No invite code field found")

        # Check ToS checkbox — From the actual PatewayAI UI, the checkbox text is:
        # "By signing up, you agree to our Terms of Service and Privacy Policy"
        # The checkbox is an Ant Design checkbox that sits ABOVE the Sign up button.
        # We must trigger the React onChange by clicking the wrapper element.
        await human_think("normal")
        checkbox_checked = False
        for attempt in range(3):
            try:
                # Method 1: Click the Ant Design checkbox wrapper (the visible clickable area)
                checkbox_wrapper = page.locator('.ant-checkbox-wrapper, label:has(input[type="checkbox"])').first
                if await checkbox_wrapper.is_visible(timeout=2000):
                    await checkbox_wrapper.click(force=True)
                    await asyncio.sleep(0.5)
                    is_checked = await page.evaluate(
                        "() => document.querySelector('input[type=\"checkbox\"]')?.checked || false"
                    )
                    if is_checked:
                        checkbox_checked = True
                        break
            except Exception:
                pass

            # Method 2: Click the checkbox text label (e.g. "By signing up, you agree...")
            try:
                tos_label = page.locator('label:has-text("Terms"), span:has-text("Terms")').first
                if await tos_label.is_visible(timeout=2000):
                    await tos_label.click(force=True)
                    await asyncio.sleep(0.5)
                    is_checked = await page.evaluate(
                        "() => document.querySelector('input[type=\"checkbox\"]')?.checked || false"
                    )
                    if is_checked:
                        checkbox_checked = True
                        break
            except Exception:
                pass

            # Method 3: JS click the native input
            try:
                await page.evaluate("""() => {
                    const cb = document.querySelector('input[type="checkbox"]');
                    if (cb) cb.click();
                }""")
                await asyncio.sleep(0.5)
                is_checked = await page.evaluate(
                    "() => document.querySelector('input[type=\"checkbox\"]')?.checked || false"
                )
                if is_checked:
                    checkbox_checked = True
                    break
            except Exception:
                pass

        if not checkbox_checked:
            log_warn("Could not verify ToS checkbox is checked — form may not submit")

        # Scroll down naturally
        await human_scroll(page, "down", random.randint(100, 300))
        await human_think("normal")

        # Click "Sign up" — From the actual PatewayAI UI, this is:
        # <button type="submit" class="...ant-btn-primary ant-btn-block auth-submit-btn">Sign up now</button>
        # The button is disabled until form is valid (OTP + password + checkbox checked).
        # We must wait for it to be enabled, then click.
        log("   Clicking Sign up button...")
        signup_clicked = False
        for attempt in range(5):
            # Check if signup button is enabled
            btn_state = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button[type="submit"], button');
                for (const btn of buttons) {
                    const t = btn.textContent.toLowerCase().trim();
                    if (t.includes('sign up') || t.includes('注册')) {
                        return { enabled: !btn.disabled, text: btn.textContent.trim() };
                    }
                }
                return { enabled: false, text: '' };
            }""")
            if not btn_state.get("enabled"):
                log_debug(f"Sign up button disabled (attempt {attempt+1}/5), waiting...")
                await asyncio.sleep(2)
                continue

            # Click via JS — dispatch React-compatible click event
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button[type="submit"], button');
                for (const btn of buttons) {
                    const t = btn.textContent.toLowerCase().trim();
                    if ((t.includes('sign up') || t.includes('注册')) && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            signup_clicked = True
            break

        if not signup_clicked:
            log_warn("Sign up button still disabled after retries — trying click anyway")
            await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button[type="submit"], button');
                for (const btn of buttons) {
                    const t = btn.textContent.toLowerCase().trim();
                    if (t.includes('sign up') || t.includes('注册')) {
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
        log_step(6, 7, "Verifying account creation...")

        # Wait for PatewayAI to process signup and show success modal or redirect
        # Poll for up to 30s for either a success modal or URL change
        signup_success = False
        poll_start = asyncio.get_running_loop().time()
        poll_timeout = 30

        while asyncio.get_running_loop().time() - poll_start < poll_timeout:
            await asyncio.sleep(2)

            current_url = page.url
            page_text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 1000) || ''"
            )
            page_text_lower = page_text.lower()

            # Check for success indicators
            # From actual PatewayAI UI: "Account created" with "◆3 reward has been added"
            has_created_modal = (
                "account created" in page_text_lower
                or "注册成功" in page_text_lower
                or "reward has been added" in page_text_lower
            )
            has_error = "failed" in page_text_lower and "sign up" in page_text_lower

            if has_created_modal:
                log_ok("Account created modal detected!")
                # Wait for modal animation to complete
                await asyncio.sleep(2)
                try:
                    # Click "Get started" button in the success modal
                    # From actual UI: <button>Get started</button> inside the modal
                    await page.evaluate("""() => {
                        const buttons = document.querySelectorAll('button, a');
                        for (const btn of buttons) {
                            const t = btn.textContent.toLowerCase().trim();
                            if (t === 'get started' || t.includes('开始')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    log("   Waiting for redirect to Console...")
                    await asyncio.sleep(3)
                except Exception:
                    log_debug("No 'Get started' button found")
                signup_success = True
                break

            if has_error:
                log_err("Signup failed — error detected on page")
                await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"signup_error{suffix}.png"))
                return None

            # Check if already redirected to console
            if "/console" in current_url or "/#/console" in current_url:
                log_ok(f"Already on Console: {current_url}")
                signup_success = True
                break

        if not signup_success:
            current_url = page.url
            log_warn(f"No success modal detected after {poll_timeout}s — URL: {current_url}")
            log_debug(f"Page text: {page_text[:300]}")

        log_ok(f"Account created! Current page: {page.url}")

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
        log("   Waiting for Console page to load...")
        try:
            # Wait for API Keys table or "Create Key" button to appear
            await page.wait_for_selector(
                'button:has-text("Create Key"), table, [class*="api-key"], [class*="empty"]',
                timeout=15000
            )
            log_ok("Console page loaded")
        except Exception:
            log_warn("Console page elements not detected, waiting more...")
            await asyncio.sleep(3)

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
            # Wait for modal CONTENT to be visible (not just the overlay root)
            # Ant Design modals: .ant-modal-body contains the actual form
            await page.wait_for_selector('.ant-modal-body, [class*="modal-body"], [class*="modal"] form', timeout=10000)
            await asyncio.sleep(1)
            await human_think("reading")

            # Find key name input — try multiple selectors
            key_name_input = None
            input_selectors = [
                '.ant-modal-body input[type="text"]',
                '.ant-modal-body input:not([type="hidden"])',
                '[class*="modal-body"] input[type="text"]',
                'input[placeholder*="name"]',
                'input[placeholder*="Name"]',
                'input[placeholder*="prod"]',
            ]
            for sel in input_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        key_name_input = el
                        log_debug(f"Found key name input: {sel}")
                        break
                except Exception:
                    continue

            if key_name_input:
                await key_name_input.fill(key_name)
                log_debug(f"Key name set to: {key_name}")
            else:
                log_warn("Key name input not found with specific selectors, trying broader search...")
                # Last resort: any visible text input inside the page
                inputs = page.locator('input[type="text"]:visible')
                count = await inputs.count()
                if count > 0:
                    await inputs.first.fill(key_name)
                else:
                    log_err("Could not find any input for key name")
                    await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"no_key_input{suffix}.png"))
                    return None

        except Exception as e:
            log_err(f"Key name input error: {e}")
            await page.screenshot(path=str(config.SCREENSHOTS_DIR / f"key_input_error{suffix}.png"))
            return None

        log("   Using default Service Mode (Economy)")

        # Click "Create" button in modal
        log("   Clicking 'Create'...")
        try:
            # Ant Design: buttons inside .ant-modal-footer or .ant-modal-body
            create_btn = None
            create_selectors = [
                '.ant-modal-footer button:has-text("Create"):not(:has-text("Key"))',
                '.ant-modal-body button:has-text("Create"):not(:has-text("Key"))',
                '.ant-modal button.ant-btn-primary',
                'button:has-text("Create"):not(:has-text("Key")):not(:has-text("Create Key"))',
            ]
            for sel in create_selectors:
                try:
                    el = page.locator(sel).last
                    if await el.is_visible(timeout=2000):
                        create_btn = el
                        log_debug(f"Found Create button: {sel}")
                        break
                except Exception:
                    continue

            if create_btn:
                # Use JS click instead of human_click — the button may be overlapped
                # by modal elements, and we need to trigger React's onClick handler
                await create_btn.click(force=True)
            else:
                log_warn("Create button not found, trying JS click...")
                await page.evaluate("""() => {
                    const modals = document.querySelectorAll('.ant-modal-body, .ant-modal-footer');
                    for (const modal of modals) {
                        const btn = modal.querySelector('button.ant-btn-primary, button:last-child');
                        if (btn && btn.textContent.trim().toLowerCase().includes('create')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")

            await human_think("normal")
        except Exception as e:
            log_err(f"Create button click failed: {e}")
            return None

        # Wait for API key response
        await human_think("careful")
        await asyncio.sleep(random.uniform(3, 5))

        # Wait for "Key Created" modal to appear
        # From actual PatewayAI UI: modal with "Key Created" title, green check icon,
        # and API key displayed as "sk-ptw-..."
        log("   Waiting for Key Created modal...")
        try:
            # Wait for the key created modal text to appear
            await page.wait_for_selector(
                'text="Key Created", text="key created"',
                timeout=10000
            )
            log_ok("Key Created modal detected")
            await human_think("reading")
        except Exception:
            log_warn("Key Created modal not detected, trying broader search...")
            # Broader: check if API key text is visible on page
            try:
                await page.wait_for_selector("text=/sk-ptw-/", timeout=5000)
                log_ok("API key text found on page")
            except Exception:
                log_warn("No API key text found on page")

        # Try to capture API key
        if not captured_key:
            log("   Trying UI extraction...")
            captured_key = await _extract_key_from_ui(page)

        if not captured_key:
            log("   Trying clipboard...")
            captured_key = await _extract_key_from_clipboard(page)

        if captured_key:
            log_ok(f"API Key captured: {mask_value(captured_key)}")
            # Click "Done, close" to dismiss the Key Created modal
            try:
                await page.evaluate("""() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const t = btn.textContent.toLowerCase().trim();
                        if (t.includes('done') || t.includes('close') || t.includes('完成')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
            except Exception:
                pass
        else:
            log_err("Could not capture API key from any method")

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
