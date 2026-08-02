"""Tests for _handle_cloudflare_turnstile — Pateway anti-bot challenge.

The old implementation failed because it:
  1. Checked for the iframe with a single evaluate() — iframe is lazy-loaded
     by Cloudflare AFTER the server returns decision=challenge, so a single
     synchronous query runs too early and finds nothing.
  2. Clicked the center of the container, not the checkbox position.
     The actual checkbox sits at roughly x+25, y+height/2 inside the iframe
     viewport — clicking the container center often misses the clickable area.
  3. Never waited for the cf-turnstile-response token — it just checked
     whether the iframe "disappeared", which also happens when a challenge
     fails.

These tests drive _handle_cloudflare_turnstile with a fake page that simulates
the real async behavior: iframe appears after a delay, checkbox click sets
the response token, and verify reads the token value.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pateway_autopilot.register import _handle_cloudflare_turnstile

# ═══════════════════════════════════════════════════════════════════════════════
# FAKE PAGE — simulates Cloudflare Turnstile iframe lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeFrame:
    """Simulates the content_frame() of the Turnstile iframe."""

    def __init__(self, page):
        self._page = page

    def locator(self, selector: str):
        return _FakeFrameLocator(self._page)


class _FakeFrameLocator:
    """Locator for elements inside the Turnstile iframe."""

    def __init__(self, page):
        self._page = page

    @property
    def first(self):
        return self

    async def is_visible(self, timeout: int = 0) -> bool:
        return self._page._turnstile_state["checkbox_visible"]

    async def click(self, timeout: int = 0) -> None:
        # Simulate clicking the checkbox: set the response token.
        self._page._turnstile_state["solved"] = True
        self._page._turnstile_state["token"] = "cf-turnstile-token-abc123"


class _FakeIframe:
    """Playwright Locator for the Turnstile iframe element."""

    def __init__(self, page, visible: bool):
        self._page = page
        self._visible = visible

    async def count(self) -> int:
        return 1 if self._visible else 0

    def nth(self, _i: int):
        return self

    @property
    def first(self):
        return self

    async def is_visible(self, timeout: int = 0) -> bool:
        return self._visible

    async def bounding_box(self):
        if not self._visible:
            return None
        return {"x": 100, "y": 200, "width": 300, "height": 65}

    async def content_frame(self):
        return _FakeFrame(self._page)


class FakePage:
    """Mocks a Playwright Page with the Turnstile iframe lifecycle.

    The iframe appears asynchronously after `iframe_delay_ms` milliseconds
    (simulating Cloudflare's lazy load).  Clicking the visible checkbox area
    (x+25, y+height/2) via page.mouse.click toggles the solved state and sets
    the cf-turnstile-response token.  evaluate() returns the current state.
    """

    def __init__(self, iframe_delay_ms: int = 1500, solve_on_click: bool = True):
        self._iframe_delay_ms = iframe_delay_ms
        self._solve_on_click = solve_on_click
        self._iframe_appeared_at: float | None = None
        self._started_at: float = 0.0
        self._turnstile_state = {
            "iframe_present": False,
            "checkbox_visible": False,
            "solved": False,
            "token": "",
        }
        # Track every call for assertions.
        self.mouse_moves: list[tuple[int, int]] = []
        self.mouse_clicks: list[tuple[float, float]] = []
        self.evaluate_calls: list[str] = []
        self.sleeps: list[float] = []
        self.viewport_size = {"width": 1280, "height": 720}

    # ── Playwright API surface used by _handle_cloudflare_turnstile ──────

    def locator(self, selector: str):
        if "challenges.cloudflare.com" in selector:
            now = __import__("time").time() - self._started_at
            appeared = self._turnstile_state["iframe_present"] or (
                now * 1000 >= self._iframe_delay_ms
            )
            if appeared and not self._turnstile_state["iframe_present"]:
                self._turnstile_state["iframe_present"] = True
                self._turnstile_state["checkbox_visible"] = True
                self._iframe_appeared_at = now
            return _FakeIframe(self, self._turnstile_state["iframe_present"])
        return _FakeIframe(self, False)

    @property
    def mouse(self):
        return _FakeMouse(self)

    async def evaluate(self, js: str, *args):
        self.evaluate_calls.append(js)
        # Turnstile detection / solved check.
        # _check_turnstile_solved calls this; _wait_for_turnstile_token also
        # calls this and expects the actual token string (not a bool).
        if "cf-turnstile-response" in js:
            token = self._turnstile_state["token"]
            result = token if (token and len(token) > 10) else None
            print(
                f"[DEBUG] cf-token check: token={token!r} → {result!r}  clicks={self.mouse_clicks}"
            )
            return result
        if "querySelectorAll('iframe[src*=\"challenges" in js:
            present = self._turnstile_state["iframe_present"]
            if present:
                return {
                    "found": True,
                    "width": 300,
                    "height": 65,
                    "x": 100,
                    "y": 200,
                    "src": "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/...",
                }
            return {"found": False}
        if "iframe.offsetParent" in js:  # re-check still present
            return self._turnstile_state["iframe_present"] and not self._turnstile_state["solved"]
        return None

    async def wait_for_selector(self, selector: str, timeout: int = 0):
        import asyncio
        import time as _time

        deadline = _time.time() + (timeout / 1000 if timeout else 5)
        while _time.time() < deadline:
            elapsed_ms = (_time.time() - self._started_at) * 1000
            if "challenges.cloudflare.com" in selector and elapsed_ms >= self._iframe_delay_ms:
                if not self._turnstile_state["iframe_present"]:
                    self._turnstile_state["iframe_present"] = True
                    self._turnstile_state["checkbox_visible"] = True
                return
            await asyncio.sleep(0.05)
        raise TimeoutError(f"wait_for_selector timed out for {selector}")


class _FakeMouse:
    """Simulates Playwright mouse."""

    def __init__(self, page: FakePage):
        self._page = page

    async def move(self, x: int, y: int) -> None:
        self._page.mouse_moves.append((int(x), int(y)))

    async def click(self, x: float, y: float) -> None:
        self._page.mouse_clicks.append((x, y))
        # Coordinate-based solve: clicking anywhere inside the checkbox area
        # (x in [box_x+10..box_x+40], y near center) solves the challenge.
        if self._page._solve_on_click and self._page._turnstile_state["checkbox_visible"]:
            self._page._turnstile_state["solved"] = True
            self._page._turnstile_state["token"] = "cf-turnstile-token-abc123"


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloudflareTurnstile:
    async def test_waits_for_iframe_before_click(self) -> None:
        """The handler must wait for the Cloudflare iframe to appear
        (it's lazy-loaded) before trying to click — not query once and
        give up."""
        page = FakePage(iframe_delay_ms=1500, solve_on_click=True)
        page._started_at = __import__("time").time()

        with (
            patch("pateway_autopilot.register.human_move_mouse", new_callable=AsyncMock),
            patch("pateway_autopilot.register.human_delay", new_callable=AsyncMock),
        ):
            await _handle_cloudflare_turnstile(page)
        # Handler waited for iframe (wait_for_selector) and then clicked.
        assert page.mouse_clicks, "Handler must wait for iframe and then issue a click"
        assert page._turnstile_state["token"] != "", (
            "Turnstile should have been solved and token set"
        )

    async def test_clicks_checkbox_position_not_container_center(self) -> None:
        """The click must target the checkbox offset (left-center of the
        iframe), not the iframe's geometric center."""
        page = FakePage(iframe_delay_ms=0, solve_on_click=False)
        page._started_at = __import__("time").time()

        with (
            patch("pateway_autopilot.register.human_move_mouse", new_callable=AsyncMock),
            patch("pateway_autopilot.register.human_delay", new_callable=AsyncMock),
        ):
            await _handle_cloudflare_turnstile(page)
        assert page.mouse_clicks, "Handler must issue a click"
        x, y = page.mouse_clicks[0]
        box_x, box_y, box_h = 100, 200, 65
        assert box_x + 10 <= x <= box_x + 45, f"click x={x} should be near left edge (~{box_x}+25)"
        assert abs(y - (box_y + box_h / 2)) <= 10, f"click y={y} should be near vertical center"

    async def test_polls_for_cf_turnstile_response_token(self) -> None:
        """After clicking, the handler must poll for the response token
        (input[name=cf-turnstile-response]) — not just check iframe absence."""
        page = FakePage(iframe_delay_ms=0, solve_on_click=True)
        page._started_at = __import__("time").time()

        with (
            patch("pateway_autopilot.register.human_move_mouse", new_callable=AsyncMock),
            patch("pateway_autopilot.register.human_delay", new_callable=AsyncMock),
        ):
            await _handle_cloudflare_turnstile(page)
        assert any("cf-turnstile-response" in js for js in page.evaluate_calls), (
            "Must poll for cf-turnstile-response token after clicking"
        )
        assert page._turnstile_state["token"] == "cf-turnstile-token-abc123"

    async def test_returns_true_when_no_turnstile_present(self) -> None:
        """No Cloudflare iframe at all → return True immediately (no challenge)."""
        page = FakePage(iframe_delay_ms=999_999, solve_on_click=False)
        page._started_at = __import__("time").time()
        with (
            patch("pateway_autopilot.register.human_move_mouse", new_callable=AsyncMock),
            patch("pateway_autopilot.register.human_delay", new_callable=AsyncMock),
        ):
            result = await _handle_cloudflare_turnstile(page)
        assert result is True
        assert page.mouse_clicks == []

    async def test_returns_false_when_unsolvable(self) -> None:
        """Iframe present but click never solves → return False."""
        page = FakePage(iframe_delay_ms=0, solve_on_click=False)
        page._started_at = __import__("time").time()
        with (
            patch("pateway_autopilot.register.human_move_mouse", new_callable=AsyncMock),
            patch("pateway_autopilot.register.human_delay", new_callable=AsyncMock),
        ):
            result = await _handle_cloudflare_turnstile(page)
        assert result is False
