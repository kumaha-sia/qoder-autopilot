"""
Manual CAPTCHA Solver
======================

Pauses execution and waits for user to solve CAPTCHA manually.
Used as fallback when auto-solve fails.
"""

import asyncio
from typing import Optional

from ..utils.logger import log, log_ok, log_err, log_warn


async def wait_for_manual_solve(
    page,
    timeout: int = 120,
    check_interval: float = 2.0,
) -> bool:
    """Wait for user to manually solve CAPTCHA.

    Args:
        page: Playwright page object.
        timeout: Max seconds to wait.
        check_interval: Seconds between checks.

    Returns:
        True if solved within timeout.
    """
    log("⏳ Waiting for manual CAPTCHA solve...")
    log("   Please solve the CAPTCHA in the browser window.")

    start = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start < timeout:
        await asyncio.sleep(check_interval)

        # Check if captcha elements are gone
        captcha_gone = await page.evaluate("""() => {
            const selectors = [
                '[class*="captcha"]',
                '[class*="slider"]',
                '[class*="verify"]',
                '[class*="puzzle"]',
                '.geetest_panel',
                '#captcha',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 10 && rect.height > 10) {
                        return false;  // Still visible
                    }
                }
            }
            return true;  // All gone
        }""")

        if captcha_gone:
            log_ok("CAPTCHA solved!")
            return True

        # Check if page progressed (e.g., OTP input appeared)
        has_progressed = await page.evaluate("""() => {
            // Check for OTP input
            const otpInputs = document.querySelectorAll(
                'input[maxlength="1"], input[placeholder*="code"], input[placeholder*="OTP"]'
            );
            if (otpInputs.length > 0) return true;

            // Check for password input (next step)
            const pwInputs = document.querySelectorAll('input[type="password"]');
            if (pwInputs.length > 0) return true;

            // Check for success message
            const text = document.body?.innerText?.substring(0, 500) || '';
            const successWords = ['success', 'verified', 'welcome', '成功'];
            if (successWords.some(w => text.toLowerCase().includes(w))) return true;

            return false;
        }""")

        if has_progressed:
            log_ok("CAPTCHA solved, page progressed!")
            return True

        elapsed = int(asyncio.get_event_loop().time() - start)
        remaining = timeout - elapsed
        if remaining % 10 < check_interval:
            log(f"   Waiting... {remaining}s remaining")

    log_err(f"Manual CAPTCHA solve timeout ({timeout}s)")
    return False
