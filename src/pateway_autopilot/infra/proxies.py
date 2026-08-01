"""
Proxy Manager — Load and Rotate Proxies
=========================================

Supports format: host:port:username:password
Converts to: socks5://username:password@host:port
"""

import itertools
import random
from pathlib import Path

from ..utils.logger import log, log_warn


def parse_proxy_line(line: str) -> str | None:
    """Parse a proxy line in host:port:user:pass format.

    Args:
        line: Proxy string in format "host:port:username:password"

    Returns:
        Formatted proxy URL (socks5://user:pass@host:port) or None if invalid.
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

    return f"socks5://{user}:{password}@{host}:{port}"


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
    """Rotates through a list of proxies in round-robin order."""

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

    @property
    def count(self) -> int:
        """Number of proxies available."""
        return len(self._proxies)

    def next(self) -> str | None:
        """Get next proxy in rotation.

        Returns:
            Proxy URL or None if no proxies available.
        """
        if not self._cycle:
            return None
        return next(self._cycle)

    def peek(self, index: int = 0) -> str | None:
        """Peek at proxy at given index (0-based).

        Args:
            index: Index into proxy list.

        Returns:
            Proxy URL or None if index out of range.
        """
        if not self._proxies:
            return None
        return self._proxies[index % len(self._proxies)]

    def get_for_account(self, account_num: int) -> str | None:
        """Get proxy for a specific account number (1-based).

        Args:
            account_num: Account number (1, 2, 3, ...).

        Returns:
            Proxy URL or None if no proxies available.
        """
        if not self._proxies:
            return None
        return self._proxies[(account_num - 1) % len(self._proxies)]
