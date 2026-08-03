"""
Proxy Manager — Load and Rotate Proxies
=========================================

Supports format: host:port:username:password
Converts to: http://username:password@host:port

Includes async health check to skip dead/slow proxies before use.
"""

import asyncio
import itertools
import random
from pathlib import Path

import httpx

from ..utils.logger import log, log_ok, log_warn


def parse_proxy_line(line: str) -> str | None:
    """Parse a proxy line in host:port:user:pass format.

    Args:
        line: Proxy string in format "host:port:username:password"

    Returns:
        Formatted proxy URL (http://user:pass@host:port) or None if invalid.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Support socks5:// or http:// prefixed lines (pass-through)
    if line.startswith("socks5://") or line.startswith("http://") or line.startswith("https://"):
        return line

    parts = line.split(":")
    if len(parts) != 4:
        log_warn(f"Invalid proxy format (expected host:port:user:pass): {line[:20]}...")
        return None

    host, port, user, password = parts
    if not host or not port:
        log_warn(f"Invalid proxy: missing host or port in {line[:20]}...")
        return None

    return f"http://{user}:{password}@{host}:{port}"


def load_proxies(filepath: str) -> list[str]:
    """Load proxies from a file.

    Args:
        filepath: Path to proxy list file.

    Returns:
        List of formatted proxy URLs.
    """
    path = Path(filepath)
    if not path.exists():
        log_warn(f"Proxy file not found: {filepath}")
        return []

    proxies = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            proxy = parse_proxy_line(line)
            if proxy:
                proxies.append(proxy)

    if not proxies:
        log_warn(f"No valid proxies found in {filepath}")
    else:
        log(f"📋 Loaded {len(proxies)} proxies from {filepath}")

    return proxies


class ProxyRotator:
    """Rotates through a list of proxies in round-robin order.

    Supports async health checking — dead/slow proxies are skipped so
    accounts don't waste 30s on a browser launch that will timeout.
    """

    def __init__(self, proxies: list[str], shuffle: bool = True):
        """Initialize the rotator.

        Args:
            proxies: List of proxy URLs.
            shuffle: If True, shuffle proxies before rotating (default True).
        """
        self._proxies = list(proxies)
        if shuffle and len(self._proxies) > 1:
            random.shuffle(self._proxies)
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._lock = None  # Lazy init for async safety
        self._healthy: list[str] | None = None  # Lazy: filled by health_check()
        self._healthy_cycle: itertools.cycle[str] | None = None

    @property
    def count(self) -> int:
        """Number of proxies available."""
        return len(self._proxies)

    @property
    def healthy_count(self) -> int:
        """Number of healthy proxies (after health check)."""
        return len(self._healthy) if self._healthy is not None else self.count

    async def health_check(
        self, timeout: float = 8.0, test_url: str = "https://www.google.com"
    ) -> None:
        """Test all proxies and cache the healthy ones.

        Tries a quick HTTP GET through each proxy.  Proxies that respond
        within ``timeout`` seconds are marked healthy; the rest are skipped.

        This should be called once at startup before the first account.
        """
        if not self._proxies:
            return

        log(f"🩺 Health-checking {len(self._proxies)} proxies (timeout={timeout}s)...")

        async def _check_one(proxy_url: str) -> str | None:
            # httpx uses the proxy URL directly for all schemes.
            try:
                async with httpx.AsyncClient(
                    proxy=proxy_url, timeout=timeout, follow_redirects=True
                ) as client:
                    resp = await client.get(test_url)
                    if resp.status_code < 400:
                        return proxy_url
            except Exception:
                return None
            return None

        # Run all checks concurrently for speed.
        results = await asyncio.gather(*[_check_one(p) for p in self._proxies])
        healthy = [p for p in results if p is not None]

        if not healthy:
            log_warn("⚠️  All proxies failed health check — using all anyway")
            self._healthy = list(self._proxies)
        else:
            self._healthy = healthy
            log_ok(f"✅ {len(healthy)}/{len(self._proxies)} proxies are healthy")

        if self._healthy and len(self._healthy) > 1:
            random.shuffle(self._healthy)
        self._healthy_cycle = itertools.cycle(self._healthy) if self._healthy else None

    def next(self) -> str | None:
        """Get next healthy proxy in rotation.

        Returns:
            Proxy URL or None if no proxies available.
        """
        cycle = self._healthy_cycle or self._cycle
        if not cycle:
            return None
        return next(cycle)

    def peek(self, index: int = 0) -> str | None:
        """Peek at proxy at given index (0-based).

        Args:
            index: Index into proxy list.

        Returns:
            Proxy URL or None if index out of range.
        """
        source = self._healthy or self._proxies
        if not source:
            return None
        return source[index % len(source)]

    def get_for_account(self, account_num: int) -> str | None:
        """Get healthy proxy for a specific account number (1-based).

        Args:
            account_num: Account number (1, 2, 3, ...).

        Returns:
            Proxy URL or None if no proxies available.
        """
        source = self._healthy or self._proxies
        if not source:
            return None
        return source[(account_num - 1) % len(source)]
