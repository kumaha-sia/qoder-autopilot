"""
Proxy Manager — Load and Rotate Proxies
=========================================

Supports format: host:port:username:password
Converts to: http://username:password@host:port

Includes async health check to skip dead/slow proxies before use.
"""

import asyncio
import random
import time
from pathlib import Path

import httpx

from ..utils.logger import log, log_debug, log_ok, log_warn


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


class _ProxyEntry:
    """Tracks a single proxy's state: URL, failure count, last-used time."""

    __slots__ = ("url", "failures", "last_used")

    def __init__(self, url: str):
        self.url = url
        self.failures: int = 0
        self.last_used: float = 0.0

    @property
    def is_dead(self) -> bool:
        return self.failures >= 3

    def reset_if_stale(self, stale_seconds: float = 300.0) -> None:
        """Reset failure count if proxy hasn't been used for 5+ minutes."""
        if self.last_used > 0 and (time.time() - self.last_used > stale_seconds):
            self.failures = 0


class ProxyRotator:
    """Rotates through a list of proxies with failure-aware rotation.

    Features (inspired by mekithil's ProxyManager):
      - Per-proxy failure tracking — dead proxies are skipped, not retried
        immediately.  After 3 consecutive failures a proxy is marked dead.
      - Auto-reset — dead proxies are retried after 5 minutes of inactivity
        (the upstream block may have expired).
      - Country-aware fingerprint hints — map proxy IP to locale/timezone
        so the browser fingerprint matches the proxy's geography.
      - Async health check at startup — skip dead/slow proxies before use.
    """

    def __init__(self, proxies: list[str], shuffle: bool = True):
        """Initialize the rotator.

        Args:
            proxies: List of proxy URLs.
            shuffle: If True, shuffle proxies before rotating (default True).
        """
        self._entries: list[_ProxyEntry] = [_ProxyEntry(p) for p in proxies]
        if shuffle and len(self._entries) > 1:
            random.shuffle(self._entries)
        self._index = 0
        self._healthy: list[str] | None = None  # filled by health_check()
        self._failures_this_run: dict[str, int] = {}

    @property
    def count(self) -> int:
        """Number of proxies available."""
        return len(self._entries)

    @property
    def healthy_count(self) -> int:
        """Number of healthy proxies (after health check + failure tracking)."""
        if self._healthy is not None:
            return len(self._healthy)
        return sum(1 for e in self._entries if not e.is_dead)

    async def health_check(
        self, timeout: float = 8.0, test_url: str = "https://ipv4.webshare.io/"
    ) -> None:
        """Test proxies and cache the healthy ones.

        For large pools (>500), samples 200 random proxies instead of testing
        all — testing 20k proxies concurrently would OOM, and sequential would
        take hours.  Results are extrapolated: if the sample pass rate is high,
        mark all as healthy.

        This should be called once at startup before the first account.
        """
        if not self._entries:
            return

        total = len(self._entries)
        # For large pools, sample instead of testing all.
        sample_size = min(200, total)
        if total > 500:
            import random as _rnd

            sample = _rnd.sample(self._entries, sample_size)
            log(f"🩺 Health-checking {sample_size}/{total} proxies (sampled, timeout={timeout}s)...")
        else:
            sample = self._entries
            log(f"🩺 Health-checking {total} proxies (timeout={timeout}s)...")

        # Batch concurrency with semaphore to avoid OOM.
        _sem = asyncio.Semaphore(50)

        async def _check_one(entry: _ProxyEntry) -> str | None:
            async with _sem:
                try:
                    async with httpx.AsyncClient(
                        proxy=entry.url, timeout=timeout, follow_redirects=True
                    ) as client:
                        resp = await client.get(test_url)
                        if resp.status_code < 400:
                            return entry.url
                except Exception:
                    return None
            return None

        results = await asyncio.gather(*[_check_one(e) for e in sample])
        healthy = [p for p in results if p is not None]
        pass_rate = len(healthy) / len(sample) if sample else 0

        if total > 500:
            # Extrapolate: if sample pass rate >= 50%, mark all as healthy.
            if pass_rate >= 0.5:
                self._healthy = [e.url for e in self._entries]
                log_ok(
                    f"✅ Sample: {len(healthy)}/{sample_size} healthy ({pass_rate:.0%}) — marking all {total} as healthy"
                )
            else:
                # Low pass rate — only use the sampled healthy ones + rest unchecked
                self._healthy = [e.url for e in self._entries]
                log_warn(
                    f"⚠️  Sample: only {len(healthy)}/{sample_size} healthy ({pass_rate:.0%}) — using all anyway"
                )
        elif not healthy:
            log_warn("⚠️  All proxies failed health check — using all anyway")
            self._healthy = [e.url for e in self._entries]
        else:
            self._healthy = healthy
            log_ok(f"✅ {len(healthy)}/{total} proxies are healthy")

    def next(self) -> str | None:
        """Get next healthy proxy in round-robin order.

        Skips dead proxies (3+ consecutive failures).  If all proxies are
        dead, resets all failure counts and starts over.
        """
        if not self._entries:
            return None

        healthy_urls = set(self._healthy) if self._healthy else None

        for _ in range(len(self._entries)):
            entry = self._entries[self._index]
            self._index = (self._index + 1) % len(self._entries)

            entry.reset_if_stale()

            if healthy_urls and entry.url not in healthy_urls:
                continue

            if entry.is_dead:
                continue

            entry.last_used = time.time()
            return entry.url

        # All proxies are dead — reset and try again.
        log_warn("⚠️  All proxies marked bad — resetting failures")
        for e in self._entries:
            e.failures = 0
        entry = self._entries[0]
        entry.last_used = time.time()
        self._index = 1
        return entry.url

    def report_failure(self, proxy_url: str) -> None:
        """Mark a proxy as failed — it will be skipped for the next accounts.

        Called when a proxy's browser launch or page.goto fails.
        Inspired by mekithil's ProxyManager.reportFailure().
        """
        for entry in self._entries:
            if entry.url == proxy_url:
                entry.failures += 1
                self._failures_this_run[proxy_url] = entry.failures
                log_debug(f"Proxy {proxy_url[:40]}… failed ({entry.failures}/3)")
                break

    def report_success(self, proxy_url: str) -> None:
        """Reset failure count for a proxy that worked."""
        for entry in self._entries:
            if entry.url == proxy_url:
                entry.failures = 0
                break

    def status(self) -> dict:
        """Return proxy pool status for logging."""
        healthy = sum(1 for e in self._entries if not e.is_dead)
        dead = sum(1 for e in self._entries if e.is_dead)
        return {
            "total": len(self._entries),
            "healthy": healthy,
            "dead": dead,
            "failures_this_run": dict(self._failures_this_run),
        }

    def get_for_account(self, account_num: int) -> str | None:
        """Get healthy proxy for a specific account number (1-based).

        Uses round-robin with failure-aware rotation.
        """
        if not self._entries:
            return None

        start = (account_num - 1) % len(self._entries)
        for i in range(len(self._entries)):
            entry = self._entries[(start + i) % len(self._entries)]
            entry.reset_if_stale()
            if not entry.is_dead:
                entry.last_used = time.time()
                return entry.url

        # All dead — reset.
        for e in self._entries:
            e.failures = 0
        entry = self._entries[start % len(self._entries)]
        entry.last_used = time.time()
        return entry.url

    def peek(self, index: int = 0) -> str | None:
        """Peek at proxy at given index (0-based)."""
        if not self._entries:
            return None
        return self._entries[index % len(self._entries)].url


# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY → FINGERPRINT MAPPING
# ═══════════════════════════════════════════════════════════════════════════════

# Maps country code → locale + timezone options (inspired by mekithil).
# Used to make the browser fingerprint consistent with the proxy's geography.
PROXY_COUNTRY_MAP: dict[str, dict[str, list[str]]] = {
    "US": {
        "locales": ["en-US"],
        "timezones": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
    },
    "ID": {"locales": ["id-ID"], "timezones": ["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"]},
    "SG": {"locales": ["en-SG", "en-US"], "timezones": ["Asia/Singapore"]},
    "MY": {"locales": ["en-US", "ms-MY"], "timezones": ["Asia/Kuala_Lumpur"]},
    "TH": {"locales": ["th-TH", "en-US"], "timezones": ["Asia/Bangkok"]},
    "PH": {"locales": ["en-PH", "en-US"], "timezones": ["Asia/Manila"]},
    "VN": {"locales": ["vi-VN", "en-US"], "timezones": ["Asia/Ho_Chi_Minh"]},
    "GB": {"locales": ["en-GB"], "timezones": ["Europe/London"]},
    "AU": {"locales": ["en-AU"], "timezones": ["Australia/Sydney", "Australia/Melbourne"]},
    "CA": {"locales": ["en-CA", "en-US"], "timezones": ["America/Toronto", "America/Vancouver"]},
    "DE": {"locales": ["de-DE", "en-US"], "timezones": ["Europe/Berlin"]},
    "FR": {"locales": ["fr-FR", "en-US"], "timezones": ["Europe/Paris"]},
    "JP": {"locales": ["ja-JP", "en-US"], "timezones": ["Asia/Tokyo"]},
    "KR": {"locales": ["ko-KR", "en-US"], "timezones": ["Asia/Seoul"]},
    "IN": {"locales": ["en-IN", "en-US"], "timezones": ["Asia/Kolkata"]},
    "BR": {"locales": ["pt-BR", "en-US"], "timezones": ["America/Sao_Paulo"]},
    "NL": {"locales": ["nl-NL", "en-US"], "timezones": ["Europe/Amsterdam"]},
    # Additional countries (mekithil has 35 total)
    "IT": {"locales": ["it-IT", "en-US"], "timezones": ["Europe/Rome"]},
    "ES": {"locales": ["es-ES", "en-US"], "timezones": ["Europe/Madrid"]},
    "PL": {"locales": ["pl-PL", "en-US"], "timezones": ["Europe/Warsaw"]},
    "SE": {"locales": ["sv-SE", "en-US"], "timezones": ["Europe/Stockholm"]},
    "NO": {"locales": ["nb-NO", "en-US"], "timezones": ["Europe/Oslo"]},
    "DK": {"locales": ["da-DK", "en-US"], "timezones": ["Europe/Copenhagen"]},
    "FI": {"locales": ["fi-FI", "en-US"], "timezones": ["Europe/Helsinki"]},
    "CH": {"locales": ["de-CH", "en-US"], "timezones": ["Europe/Zurich"]},
    "AT": {"locales": ["de-AT", "en-US"], "timezones": ["Europe/Vienna"]},
    "BE": {"locales": ["nl-BE", "en-US"], "timezones": ["Europe/Brussels"]},
    "PT": {"locales": ["pt-PT", "en-US"], "timezones": ["Europe/Lisbon"]},
    "IE": {"locales": ["en-IE", "en-US"], "timezones": ["Europe/Dublin"]},
    "NZ": {"locales": ["en-NZ", "en-US"], "timezones": ["Pacific/Auckland"]},
    "ZA": {"locales": ["en-ZA", "en-US"], "timezones": ["Africa/Johannesburg"]},
    "AE": {"locales": ["ar-AE", "en-US"], "timezones": ["Asia/Dubai"]},
    "SA": {"locales": ["ar-SA", "en-US"], "timezones": ["Asia/Riyadh"]},
    "TR": {"locales": ["tr-TR", "en-US"], "timezones": ["Europe/Istanbul"]},
    "RU": {"locales": ["ru-RU", "en-US"], "timezones": ["Europe/Moscow"]},
    "CN": {"locales": ["zh-CN", "en-US"], "timezones": ["Asia/Shanghai"]},
    "TW": {"locales": ["zh-TW", "en-US"], "timezones": ["Asia/Taipei"]},
    "HK": {"locales": ["zh-HK", "en-US"], "timezones": ["Asia/Hong_Kong"]},
    "MX": {"locales": ["es-MX", "en-US"], "timezones": ["America/Mexico_City"]},
    "AR": {"locales": ["es-AR", "en-US"], "timezones": ["America/Buenos_Aires"]},
    "CL": {"locales": ["es-CL", "en-US"], "timezones": ["America/Santiago"]},
    "CO": {"locales": ["es-CO", "en-US"], "timezones": ["America/Bogota"]},
    "EG": {"locales": ["ar-EG", "en-US"], "timezones": ["Africa/Cairo"]},
    "NG": {"locales": ["en-NG", "en-US"], "timezones": ["Africa/Lagos"]},
    "KE": {"locales": ["en-KE", "en-US"], "timezones": ["Africa/Nairobi"]},
}

# Cache: proxy_url → (country_code, locale, timezone)
_country_cache: dict[str, tuple[str, str, str]] = {}


def get_fingerprint_hint(proxy_url: str | None, default_country: str = "US") -> dict[str, str]:
    """Get locale + timezone fingerprint hint for a proxy URL.

    Uses cached country detection if available.  Falls back to default_country
    mapping if detection hasn't been done yet.

    Returns:
        {"locale": "en-US", "timezone": "America/New_York", "country": "US"}
    """
    if proxy_url and proxy_url in _country_cache:
        country, locale, tz = _country_cache[proxy_url]
        return {"locale": locale, "timezone": tz, "country": country}

    # No cache yet — use default.
    country = default_country.upper()
    mapping = PROXY_COUNTRY_MAP.get(country, PROXY_COUNTRY_MAP["US"])
    return {
        "locale": mapping["locales"][0],
        "timezone": mapping["timezones"][0],
        "country": country,
    }


def _extract_ip(proxy_url: str) -> str | None:
    """Extract the IP address from a proxy URL string.

    Supports:
        - http://user:pass@1.2.3.4:8080  → "1.2.3.4"
        - socks5://user:pass@1.2.3.4:8080 → "1.2.3.4"
        - 1.2.3.4:8080:user:pass         → "1.2.3.4"
        - 1.2.3.4:8080                    → "1.2.3.4"
    """
    if not proxy_url:
        return None
    # URL format: extract host after "@"
    if "@" in proxy_url:
        after_at = proxy_url.split("@")[-1]
        return after_at.split(":")[0].strip()
    # ip:port:user:pass or ip:port
    return proxy_url.split(":")[0].strip()


# Rate limit state for ip-api.com (45 req/min → ~1.3s between requests).
_last_geo_query: float = 0.0


async def detect_proxy_country(proxy_url: str, timeout: float = 5.0) -> str | None:
    """Detect the country of a proxy IP via ip-api.com (free, no API key).

    Unlike ipinfo.io, ip-api.com works WITHOUT going through the proxy —
    we extract the IP first, then query directly.  This avoids the problem
    where the proxy itself blocks ipinfo.io.

    Caches the result per proxy URL so we only query once per proxy.
    Returns the 2-letter country code (e.g., "US", "ID", "SG") or None.
    """
    global _last_geo_query
    if proxy_url in _country_cache:
        return _country_cache[proxy_url][0]

    ip = _extract_ip(proxy_url)
    if not ip:
        log_debug(f"Could not extract IP from {proxy_url[:30]}…")
        return None

    # Rate limit: wait if needed (ip-api.com: 45 req/min).
    elapsed = time.time() - _last_geo_query
    if elapsed < 1.3:
        await asyncio.sleep(1.3 - elapsed)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,countryCode,country,city,isp"},
            )
            _last_geo_query = time.time()
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    country = str(data.get("countryCode", "US"))
                    city = str(data.get("city", ""))
                    isp = str(data.get("isp", ""))
                    mapping = PROXY_COUNTRY_MAP.get(country, PROXY_COUNTRY_MAP["US"])
                    locale = mapping["locales"][0]
                    tz = mapping["timezones"][0]
                    _country_cache[proxy_url] = (country, locale, tz)
                    log_debug(f"GeoDetect {ip} → {country} ({city}, {isp}) → {locale}/{tz}")
                    return country
    except Exception as exc:
        log_debug(f"Country detection failed for {ip}: {exc}")
    return None


async def detect_all_proxy_countries(rotator: "ProxyRotator", timeout: float = 5.0) -> None:
    """Detect country for a sample of proxies — sequential with rate limiting.

    For large pools (>100), only checks 10 random proxies since they typically
    share the same gateway host (e.g., Webshare rotating = all p.webshare.io).
    Results are cached per proxy URL; get_fingerprint_hint() falls back to
    default_country for unchecked proxies.

    Called once at startup alongside health_check().
    """
    if not rotator._entries:
        return

    total = len(rotator._entries)
    # Sample for large pools — all proxies from same provider usually share
    # the same gateway, so checking a few is enough.
    if total > 100:
        import random as _rnd

        sample_urls = [e.url for e in _rnd.sample(rotator._entries, 10)]
        log(f"🌍 Detecting countries for 10/{total} proxies (sampled)...")
    else:
        sample_urls = [e.url for e in rotator._entries]
        log(f"🌍 Detecting countries for {total} proxies...")

    detected = 0
    countries_found: set[str] = set()
    for url in sample_urls:
        country = await detect_proxy_country(url, timeout)
        if country:
            detected += 1
            countries_found.add(country)
        # Rate limit: ip-api.com allows 45 req/min → ~1.3s between requests.
        await asyncio.sleep(1.5)

    # If we found countries in the sample, propagate to all proxies from
    # the same host so get_fingerprint_hint() returns correct locale/timezone.
    if countries_found:
        detected_country = countries_found.pop()
        for entry in rotator._entries:
            if entry.url not in _country_cache:
                mapping = PROXY_COUNTRY_MAP.get(detected_country, PROXY_COUNTRY_MAP["US"])
                _country_cache[entry.url] = (
                    detected_country,
                    mapping["locales"][0],
                    mapping["timezones"][0],
                )
        log_ok(
            f"🌍 Detected {detected_country} — applied to all {total} proxies"
        )
    else:
        log_warn(f"🌍 Could not detect proxy country ({detected}/{len(sample_urls)})")
