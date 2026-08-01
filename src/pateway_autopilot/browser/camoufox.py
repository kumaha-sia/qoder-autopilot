"""
Browser Module — Camoufox Launcher
====================================

Launches Camoufox anti-detect browser with Playwright.
"""

from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse

from ..utils.logger import log, log_debug


def _parse_proxy_url(proxy_url: str) -> dict:
    """Convert a proxy URL string to the dict format Camoufox expects.

    "socks5://user:pass@host:port" → {"server": "socks5://host:port", "username": "user", "password": "pass"}
    "http://host:port"             → {"server": "http://host:port"}
    """
    parsed = urlparse(proxy_url)
    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    result: dict = {"server": server}
    if parsed.username:
        result["username"] = unquote(parsed.username)
    if parsed.password:
        result["password"] = unquote(parsed.password)
    return result


@asynccontextmanager
async def launch_browser(
    headless: bool = True,
    proxy: str | None = None,
    viewport_width: int = 1280,
    viewport_height: int = 720,
):
    """Launch Camoufox browser with anti-detect settings.

    Args:
        headless: Run in headless mode.
        proxy: Proxy URL (socks5://host:port or http://host:port).
        viewport_width: Page viewport width (set after launch).
        viewport_height: Page viewport height (set after launch).

    Yields:
        Browser instance.
    """
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        raise ImportError(
            "camoufox is required. Install with: pip install camoufox[geoip]"
        ) from None

    log("🦊 Launching Camoufox browser...")

    # Camoufox/Playwright expect proxy as a dict, not a URL string.
    # Convert "socks5://user:pass@host:port" → {"server": ..., "username": ..., "password": ...}
    proxy_dict: dict | None = None
    if proxy:
        proxy_dict = _parse_proxy_url(proxy)

    async with AsyncCamoufox(
        headless=headless,
        geoip=True,
        proxy=proxy_dict,
    ) as browser:
        log_debug(f"Browser launched (headless={headless}, proxy={proxy})")
        yield browser


async def setup_page(page):
    """Configure page with anti-detect settings.

    Args:
        page: Playwright page object.
    """
    # Set viewport (Camoufox manages window size; viewport follows)
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        await page.set_viewport_size(vp)
    except Exception:
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
        from .window_tiler import tile_all_camoufox_windows_async as tile_async

        await tile_async()
    except Exception:
        pass
