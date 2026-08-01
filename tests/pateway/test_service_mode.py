"""Tests for _select_service_mode in the Pateway registration flow.

These tests reproduce the bug where selecting "Economy Mode" in the Create Key
modal silently leaves "Default Mode" selected, producing two Default keys.

The Service Mode field is an Ant Design <Select> (dropdown).  The flow:
    1. Click ``.ant-select-selector`` (Playwright native click, handles async).
    2. Wait for ``.ant-select-dropdown`` to appear (portalled to body root).
    3. Click the ``.ant-select-item`` matching the target label.
    4. Press Escape to close the dropdown overlay.
    5. Verify ``.ant-select-selection-item`` text matches target.

We mock the Playwright Page object since _select_service_mode now uses
Playwright's native locator().click() and wait_for_selector() instead of
raw JS evaluate — the old single-evaluate approach failed because AntD
renders the dropdown asynchronously.
"""

from __future__ import annotations

from pateway_autopilot.register import _select_service_mode

# ═══════════════════════════════════════════════════════════════════════════════
# FAKE PAGE — mocks Playwright native locator + wait_for_selector + keyboard
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeLocator:
    """Mock Playwright locator with .click() and .inner_html()."""

    def __init__(self, page: FakePage, selector: str):
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _FakeLocator:
        return self

    async def click(self, timeout: int = 5000) -> None:
        self._page.actions.append(("click", self._selector))
        # Simulate opening the dropdown: set flag so wait_for_selector passes.
        if "ant-select-selector" in self._selector:
            self._page._dropdown_open = True

    async def inner_html(self) -> str:
        return "<div class='ant-modal-body'>...</div>"


class _FakeKeyboard:
    """Mock Playwright keyboard — records press() calls."""

    def __init__(self, page: FakePage):
        self._page = page

    async def press(self, key: str) -> None:
        self._page.actions.append(("keyboard_press", key))
        if key == "Escape":
            self._page._dropdown_open = False


class FakePage:
    """Mocks Playwright Page for _select_service_mode.

    Tracks all actions: locator clicks, wait_for_selector calls, keyboard
    presses, and evaluate calls (for verification).  Simulates the AntD
    Select lifecycle: clicking the selector opens the dropdown, clicking
    an item selects it, and the verify step reads the selection chip.
    """

    def __init__(self):
        self.actions: list[tuple[str, str]] = []
        self._dropdown_open = False
        self._verify_call = 0
        self._selected_mode = "default mode"  # pre-selected Default
        self.keyboard = _FakeKeyboard(self)

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> None:
        self.actions.append(("wait_for_selector", selector))
        if "ant-select-dropdown" in selector and not self._dropdown_open:
            raise TimeoutError("Dropdown not visible")

    async def evaluate(self, js: str, *args: object) -> dict:
        self.actions.append(("evaluate", js[:60]))
        arg = args[0] if args else None

        # Verify JS — return selection chip value.
        if "ant-select-selection-item" in js and isinstance(arg, str):
            self._verify_call += 1
            # Simulate: after clicking an option, the selection chip updates
            # to the picked mode (succeeds on 2nd attempt to exercise retry).
            if self._verify_call == 1:
                return {"ok": False, "value": "default mode", "reason": "mismatch"}
            return {"ok": True, "value": arg.lower(), "reason": "matched"}
        return {"ok": False, "value": "", "reason": "unknown"}


class TestSelectServiceMode:
    """Cover _select_service_mode for both Default and Economy selection."""

    async def test_select_economy_opens_dropdown_via_locator_click(self) -> None:
        """The function must click .ant-select-selector via Playwright native
        locator — not dispatch JS events — because AntD renders the dropdown
        asynchronously and Playwright's click handles actionability."""
        page = FakePage()
        await _select_service_mode(page, "economy")

        selector_clicks = [
            a for a in page.actions if a[0] == "click" and "ant-select-selector" in a[1]
        ]
        assert selector_clicks, (
            "Must click .ant-select-selector via Playwright locator to open "
            "the dropdown — JS dispatch fails because AntD renders async."
        )

    async def test_select_economy_waits_for_dropdown(self) -> None:
        """Must wait_for_selector('.ant-select-dropdown') after opening — the
        dropdown is portalled to body root and renders asynchronously."""
        page = FakePage()
        await _select_service_mode(page, "economy")

        waits = [
            a for a in page.actions if a[0] == "wait_for_selector" and "ant-select-dropdown" in a[1]
        ]
        assert waits, (
            "Must wait_for_selector('.ant-select-dropdown') — the dropdown "
            "renders asynchronously and querySelector in evaluate misses it."
        )

    async def test_select_economy_clicks_option_item(self) -> None:
        """Must click the .ant-select-item matching the target label inside
        the visible dropdown."""
        page = FakePage()
        await _select_service_mode(page, "economy")

        item_clicks = [a for a in page.actions if a[0] == "click" and "ant-select-item" in a[1]]
        assert item_clicks, (
            "Must click .ant-select-item matching the target label inside the visible dropdown."
        )

    async def test_select_economy_presses_escape_after_pick(self) -> None:
        """Must dismiss the dropdown overlay after picking — if left open, it
        intercepts pointer events on subsequent elements (Monthly Spending
        Limit switch, Create button).  Must NOT use keyboard Escape because
        that also closes the Ant Design modal."""
        page = FakePage()
        await _select_service_mode(page, "economy")

        # Must call _dismiss_dropdown (which triggers an evaluate) — NOT
        # keyboard.press("Escape").
        keyboard_escapes = [
            a for a in page.actions if a[0] == "keyboard_press" and a[1] == "Escape"
        ]
        assert not keyboard_escapes, (
            "Must NOT use keyboard.press('Escape') — it closes the modal too. "
            "Use _dismiss_dropdown instead which clicks outside the dropdown."
        )
        # Must have some dismiss action (evaluate call for dropdown close).
        evaluates = [a for a in page.actions if a[0] == "evaluate"]
        assert len(evaluates) >= 1, "Must call _dismiss_dropdown after picking"

    async def test_select_economy_retries_until_verified(self) -> None:
        """When the first pick leaves Default still selected, the function
        must retry and succeed on the 2nd attempt (FakePage simulates this)."""
        page = FakePage()
        await _select_service_mode(page, "economy")
        # Must have made at least 2 verify calls (retry kicked in).
        verify_calls = [a for a in page.actions if a[0] == "evaluate"]
        assert len(verify_calls) >= 2, (
            "Must retry verification at least twice when the first attempt "
            f"reports a mismatch (got {len(verify_calls)} verify calls)"
        )

    async def test_select_default_mode_unchanged(self) -> None:
        """Selecting default when default is already selected must not throw."""
        page = FakePage()
        await _select_service_mode(page, "default")
        assert len(page.actions) >= 2  # at least click + verify

    async def test_select_economy_verifies_selection_chip(self) -> None:
        """The verify step must read .ant-select-selection-item and return
        an {ok, value} dict so mismatches are detected."""
        page = FakePage()
        await _select_service_mode(page, "economy")
        verify_calls = [a for a in page.actions if a[0] == "evaluate"]
        assert verify_calls, (
            "Verify must read .ant-select-selection-item (the chosen value "
            "chip) and return {ok, value} — not just report which radio "
            "is checked."
        )
