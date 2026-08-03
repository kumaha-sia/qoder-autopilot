"""
Browser Module — Camoufox Launcher
====================================

Launches Camoufox anti-detect browser with Playwright.
"""

import random
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse

from ..utils.logger import log, log_debug, log_warn


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

    # When using a proxy, Camoufox's geoip lookup tries to fetch the public IP
    # via ipecho.net.  If the proxy is slow or dead, this times out and crashes
    # the whole run.  Retry once with geoip=False as a fallback.
    try:
        async with AsyncCamoufox(
            headless=headless,
            geoip=True,
            proxy=proxy_dict,
        ) as browser:
            log_debug(f"Browser launched (headless={headless}, proxy={proxy})")
            yield browser
    except Exception as exc:
        if "InvalidIP" in type(exc).__name__ or "Failed to get IP" in str(exc):
            log_warn(f"Proxy geoip lookup failed ({exc}) — retrying without geoip")
            async with AsyncCamoufox(
                headless=headless,
                geoip=False,
                proxy=proxy_dict,
            ) as browser:
                log_debug(f"Browser launched (headless={headless}, proxy={proxy}, geoip=False)")
                yield browser
        else:
            raise


async def setup_page(page, fingerprint_hint: dict[str, str] | None = None):
    """Configure page with anti-detect settings.

    Args:
        page: Playwright page object.
        fingerprint_hint: Optional dict with locale, timezone, country keys.
            If provided, applies locale/timezone/headers to match the proxy's
            geography (makes the browser fingerprint consistent with the IP).
    """
    # Random viewport per account (inspired by mekithil's fingerprint.js).
    # Using the same viewport for every account is a bot signal.
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1600, "height": 900},
        {"width": 1680, "height": 1050},
        {"width": 1280, "height": 720},
        {"width": 1280, "height": 800},
    ]
    vp = random.choice(viewports)
    try:
        await page.set_viewport_size(vp)
    except Exception:
        await page.set_viewport_size({"width": 1280, "height": 720})
    log_debug(f"Viewport set to {vp['width']}x{vp['height']}")

    # Apply country-aware fingerprint (locale + timezone + Accept-Language).
    locale = (fingerprint_hint or {}).get("locale", "en-US")
    timezone = (fingerprint_hint or {}).get("timezone", "America/New_York")
    country = (fingerprint_hint or {}).get("country", "US")

    # Set timezone via CDP.
    try:
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Emulation.setTimezoneOverride", {"timezoneId": timezone})
        log_debug(f"Timezone set to {timezone} (country={country})")
    except Exception:
        log_debug(f"Timezone override not supported: {timezone}")

    # Set Accept-Language header to match locale.
    try:
        base_lang = locale.split("-")[0]
        await page.set_extra_http_headers(
            {
                "Accept-Language": f"{locale},{base_lang};q=0.9",
            }
        )
        log_debug(f"Accept-Language set to {locale}")
    except Exception:
        pass

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
