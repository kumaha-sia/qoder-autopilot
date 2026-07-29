"""
Slider Puzzle CAPTCHA Solver
==============================

Detects puzzle gap position and drags slider to solve.
Uses OpenCV for gap detection and Playwright for interaction.
"""

import asyncio
import random
from typing import Optional

from ..utils.logger import log, log_ok, log_err, log_warn


class SliderSolver:
    """Solver for slider puzzle CAPTCHAs."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts

    async def solve(self, page, slider_selector: str = None) -> bool:
        """Solve slider CAPTCHA on the page.

        Args:
            page: Playwright page object.
            slider_selector: CSS selector for slider handle.
                           If None, auto-detects.

        Returns:
            True if solved successfully.
        """
        for attempt in range(1, self.max_attempts + 1):
            log(f"   Slider solve attempt {attempt}/{self.max_attempts}")

            try:
                # Take screenshot for analysis
                screenshot = await page.screenshot()

                # Detect gap position
                gap_x = await self._detect_gap(page, screenshot)
                if gap_x is None:
                    log_warn("Could not detect gap position")
                    continue

                # Get slider position
                slider = await self._find_slider(page, slider_selector)
                if slider is None:
                    log_warn("Could not find slider element")
                    continue

                # Calculate drag distance
                slider_box = await slider.bounding_box()
                if not slider_box:
                    log_warn("Could not get slider bounding box")
                    continue

                start_x = slider_box["x"] + slider_box["width"] / 2
                start_y = slider_box["y"] + slider_box["height"] / 2
                distance = gap_x - start_x

                log(f"   Gap at x={gap_x}, slider at x={start_x}, drag={distance}px")

                # Perform drag
                success = await self._drag_slider(page, start_x, start_y, distance)
                if success:
                    log_ok("Slider solved!")
                    return True

            except Exception as e:
                log_err(f"Slider solve error: {e}")

            await asyncio.sleep(1)

        log_err("Slider solve failed after all attempts")
        return False

    async def _detect_gap(self, page, screenshot: bytes) -> Optional[int]:
        """Detect the horizontal position of the puzzle gap.

        Uses edge detection to find the gap in the image.
        Returns x-coordinate of gap center, or None if not found.
        """
        try:
            import cv2
            import numpy as np

            # Convert screenshot to numpy array
            nparr = np.frombuffer(screenshot, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Edge detection
            edges = cv2.Canny(blurred, 50, 150)

            # Find contours
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Look for rectangular contours that could be the gap
            # The gap is typically a dark/empty rectangular region
            height, width = gray.shape
            min_gap_x = width * 0.2  # Gap is usually in the right portion
            max_gap_x = width * 0.9

            candidates = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)

                # Filter by size and position
                if (
                    w > 30
                    and w < 150
                    and h > 30
                    and h < 150
                    and min_gap_x < x < max_gap_x
                    and h / w > 0.8  # Roughly square
                    and h / w < 1.5
                ):
                    # Check if this region is darker than surroundings
                    roi = gray[y : y + h, x : x + w]
                    avg_brightness = roi.mean()

                    # Gap is typically darker
                    if avg_brightness < 100:
                        candidates.append((x + w // 2, avg_brightness, w * h))

            if candidates:
                # Sort by brightness (darkest first), then by area
                candidates.sort(key=lambda c: (c[1], -c[2]))
                return candidates[0][0]

            # Fallback: try with different thresholds
            # Collect candidates and sort by brightness (best match first)
            blurred2 = cv2.GaussianBlur(gray, (7, 7), 0)
            edges2 = cv2.Canny(blurred2, 30, 100)
            contours2, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidates2 = []
            for contour in contours2:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 25 and w < 160 and h > 25 and h < 160 and min_gap_x < x < max_gap_x:
                    roi = gray[y : y + h, x : x + w]
                    avg_brightness = roi.mean()
                    if avg_brightness < 130:
                        candidates2.append((x + w // 2, avg_brightness, w * h))

            if candidates2:
                candidates2.sort(key=lambda c: (c[1], -c[2]))
                return candidates2[0][0]

            # Last resort: return None to indicate failure (don't guess)
            return None

        except ImportError:
            log_warn("OpenCV not installed, using fallback gap detection")
            # Fallback: estimate based on page dimensions
            viewport = page.viewport_size
            if viewport:
                return int(viewport["width"] * 0.65)
            return None

        except Exception as e:
            log_err(f"Gap detection error: {e}")
            return None

    async def _find_slider(self, page, selector: str = None):
        """Find the slider element on the page.

        Tries multiple selectors if none provided.
        """
        if selector:
            return page.locator(selector).first

        # Common slider selectors
        selectors = [
            '[class*="slider"]',
            '[class*="drag"]',
            '[class*="handler"]',
            '[class*="handle"]',
            '[class*="captcha"] [class*="btn"]',
            '[class*="verify"] [class*="icon"]',
            'div[draggable="true"]',
            # Specific to some captcha providers
            "#slider",
            ".slider-btn",
            ".drag-btn",
        ]

        for sel in selectors:
            try:
                element = page.locator(sel).first
                if await element.is_visible():
                    return element
            except Exception:
                continue

        # Fallback: look for elements with cursor: grab
        try:
            element = await page.query_selector('[style*="cursor: grab"]')
            if element:
                return element
        except Exception:
            pass

        return None

    async def _drag_slider(
        self, page, start_x: float, start_y: float, distance: float
    ) -> bool:
        """Perform the slider drag with human-like movement.

        Uses smoothstep easing for natural movement with realistic physics.
        """
        try:
            target_x = start_x + distance

            # Small random delay before starting (human reaction time)
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # Move to slider with slight overshoot
            overshoot = random.randint(3, 10)
            await page.mouse.move(start_x - overshoot, start_y + random.randint(-3, 3))
            await asyncio.sleep(random.uniform(0.05, 0.15))

            # Move to exact position
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(random.uniform(0.08, 0.2))

            # Press down
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.1, 0.25))

            # Move with easing (smoothstep) - human-like acceleration/deceleration
            steps = random.randint(20, 35)
            for i in range(steps):
                progress = i / (steps - 1)

                # Smoothstep easing with slight randomness
                eased = progress * progress * (3 - 2 * progress)

                # Add micro-corrections like a human
                micro_correction = 0
                if 0.3 < progress < 0.7:  # Middle of drag - more wobble
                    micro_correction = random.uniform(-2, 2)
                elif progress > 0.9:  # End - slight overshoot then correct
                    if i == steps - 2:
                        micro_correction = random.uniform(1, 5)
                    elif i == steps - 1:
                        micro_correction = 0

                x = start_x + distance * eased + micro_correction
                y = start_y + random.uniform(-3, 3)  # Vertical wobble

                await page.mouse.move(x, y)

                # Variable speed - faster in middle, slower at start/end
                if progress < 0.2 or progress > 0.8:
                    await asyncio.sleep(random.uniform(0.02, 0.05))
                else:
                    await asyncio.sleep(random.uniform(0.01, 0.03))

            # Final position - snap to target
            await page.mouse.move(target_x, start_y)
            await asyncio.sleep(random.uniform(0.05, 0.15))

            # Release with slight delay
            await page.mouse.up()
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # Check if solve was successful
            return await self._verify_solve(page)

        except Exception as e:
            log_err(f"Drag error: {e}")
            return False

    async def _verify_solve(self, page) -> bool:
        """Verify if the slider solve was successful.

        Checks for success indicators or absence of captcha.
        Also verifies page is not in an error/crash state.
        """
        await asyncio.sleep(1)

        # Check if page is in a valid state (not error/crash page)
        page_state = await page.evaluate("""() => {
            const url = window.location.href;
            const body = document.body?.innerText?.substring(0, 200) || '';
            // Detect error pages
            if (body.includes('500') && body.length < 50) return 'error_page';
            if (body.includes('Application Error') || body.includes('This site can')) return 'error_page';
            if (document.body === null) return 'blank_page';
            return 'ok';
        }""")

        if page_state in ('error_page', 'blank_page'):
            log_warn(f"Page in {page_state} state — CAPTCHA verify assuming failure")
            return False

        # Check if captcha is still visible
        captcha_visible = await page.evaluate("""() => {
            const selectors = [
                '[class*="captcha"]',
                '[class*="slider"]',
                '[class*="verify"]',
                '[class*="puzzle"]'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 30) {
                        return true;
                    }
                }
            }
            return false;
        }""")

        if not captcha_visible:
            return True

        # Check for success message (stricter matching to avoid false positives)
        page_text = await page.evaluate(
            "() => document.body?.innerText?.substring(0, 500) || ''"
        )
        text_lower = page_text.lower()
        # Check for specific success phrases, not just substrings
        success_phrases = [
            "success", "verified", "passed", "成功", "验证通过",
            "solved", "confirmed", "approved",
        ]
        # Only match if NOT preceded by negation words
        negations = ["not ", "un", "fail", "error", "invalid"]
        for phrase in success_phrases:
            if phrase in text_lower:
                # Check context around the match to rule out negation
                idx = text_lower.index(phrase)
                context_start = max(0, idx - 10)
                context = text_lower[context_start:idx]
                if not any(neg in context for neg in negations):
                    return True
        return False


class ManualSolver:
    """Manual CAPTCHA solver - pauses for user to solve."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    async def solve(self, page) -> bool:
        """Pause and wait for user to solve CAPTCHA manually.

        Args:
            page: Playwright page object.

        Returns:
            True if solved within timeout.
        """
        from ..utils.logger import log_step

        log_step(0, 0, "Manual CAPTCHA mode — please solve the slider in the browser")

        # Make sure browser is visible (not headless)
        # Wait for captcha to be solved
        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < self.timeout:
            await asyncio.sleep(2)

            # Check if captcha is gone
            captcha_visible = await page.evaluate("""() => {
                const selectors = [
                    '[class*="captcha"]',
                    '[class*="slider"]',
                    '[class*="verify"]',
                    '[class*="puzzle"]'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            }""")

            if not captcha_visible:
                log_ok("CAPTCHA solved manually!")
                return True

            # Check for page progression (OTP page appeared)
            has_otp = await page.evaluate("""() => {
                const inputs = document.querySelectorAll(
                    'input[maxlength="1"], input[placeholder*="code"], input[placeholder*="OTP"]'
                );
                return inputs.length > 0;
            }""")

            if has_otp:
                log_ok("CAPTCHA solved, OTP page detected!")
                return True

        log_err(f"Manual CAPTCHA solve timeout ({self.timeout}s)")
        return False
