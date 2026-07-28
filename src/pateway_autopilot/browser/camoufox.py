"""
Browser Module — Camoufox Launcher
====================================

Launches Camoufox anti-detect browser with Playwright.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from ..utils.logger import log, log_debug


@asynccontextmanager
async def launch_browser(
    headless: bool = True,
    window_width: int = 900,
    window_height: int = 600,
    proxy: Optional[str] = None,
):
    """Launch Camoufox browser with anti-detect settings.

    Args:
        headless: Run in headless mode.
        window_width: Browser window width.
        window_height: Browser window height.
        proxy: Proxy URL (socks5://host:port or http://host:port).

    Yields:
        Browser instance.
    """
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        raise ImportError(
            "camoufox is required. Install with: pip install camoufox[geoip]"
        )

    log("🦊 Launching Camoufox browser...")

    async with AsyncCamoufox(
        headless=headless,
        geoip=True,
        proxy=proxy,
    ) as browser:
        log_debug(f"Browser launched (headless={headless}, proxy={proxy})")
        yield browser


async def setup_page(page):
    """Configure page with anti-detect settings.

    Args:
        page: Playwright page object.
    """
    # Set viewport
    await page.set_viewport_size({"width": 1280, "height": 720})

    # Set realistic user agent (Camoufox handles this, but we can override)
    # await page.set_extra_http_headers({
    #     "Accept-Language": "en-US,en;q=0.9",
    # })

    # Disable webdriver flag
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
    """)

    log_debug("Page configured with anti-detect settings")


async def tile_all_camoufox_windows():
    """Tile all Camoufox windows (macOS only).

    On other platforms, this is a no-op.
    """
    import platform

    if platform.system() != "Darwin":
        return

    try:
        from .window_tiler import tile_all_camoufox_windows as tile

        tile()
    except Exception:
        pass
