"""
Multi-Provider Temp Mail Client
=================================

Supports multiple disposable email providers with automatic fallback:
  1. mail.tm — rotating domains, good API, rarely blocked
  2. 1secmail.com — simple API, reliable
  3. Tempik (webkarya.net) — original, may be blocked on some sites

Usage:
    client = TempMailClient()
    email = await client.create()
    messages = await client.get_messages()
    otp = await client.wait_for_otp(timeout=120)
"""

import asyncio
import re
import time
from typing import Any, cast

import httpx

from ..utils.logger import log_debug, log_err, log_ok, log_warn

# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: mail.tm
# ═══════════════════════════════════════════════════════════════════════════════


class MailTmClient:
    """mail.tm temp mail client."""

    BASE_URL = "https://api.mail.tm"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self.address: str | None = None
        self._password: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_domains(self) -> list[str]:
        """Get available domains."""
        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/domains")
        resp.raise_for_status()
        data = resp.json()
        return [d["domain"] for d in data.get("hydra:member", data) if d.get("domain")]

    async def create(self) -> str:
        """Create a new temp email account. Returns email address."""
        import random
        import string

        client = await self._get_client()

        # Get available domains
        domains = await self.get_domains()
        if not domains:
            raise RuntimeError("No domains available from mail.tm")

        domain = random.choice(domains)
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        self.address = f"{local}@{domain}"
        self._password = "".join(random.choices(string.ascii_letters + string.digits + "!@#", k=16))

        # Create account
        resp = await client.post(
            f"{self.BASE_URL}/accounts",
            json={
                "address": self.address,
                "password": self._password,
            },
        )
        resp.raise_for_status()

        # Get auth token
        resp = await client.post(
            f"{self.BASE_URL}/token",
            json={
                "address": self.address,
                "password": self._password,
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]

        log_debug(f"mail.tm: created {self.address}")
        return self.address

    async def get_messages(self) -> list[dict]:
        """Get messages for the account."""
        if not self._token:
            return []

        client = await self._get_client()
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = await client.get(f"{self.BASE_URL}/messages", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("hydra:member", data) if isinstance(data, dict) else data

        result = []
        for msg in messages:
            result.append(
                {
                    "id": msg.get("id", ""),
                    "from_address": msg.get("from", {}).get("address", ""),
                    "subject": msg.get("subject", ""),
                    "body": msg.get("text", "") or msg.get("intro", ""),
                    "received_at": msg.get("createdAt", ""),
                }
            )
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: 1secmail.com
# ═══════════════════════════════════════════════════════════════════════════════


class OneSecMailClient:
    """1secmail.com temp mail client."""

    BASE_URL = "https://www.1secmail.com/api/v1"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self.address: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def create(self) -> str:
        """Create a new temp email. Returns email address."""
        import random
        import string

        client = await self._get_client()

        # Get available domains
        resp = await client.get(f"{self.BASE_URL}/?action=genRandomMailbox&count=1")
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list):
            self.address = data[0]
        else:
            # Fallback: generate manually
            local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
            resp2 = await client.get(f"{self.BASE_URL}/?action=getDomainList")
            resp2.raise_for_status()
            domains = resp2.json()
            domain = random.choice(domains) if domains else "1secmail.com"
            self.address = f"{local}@{domain}"

        log_debug(f"1secmail: created {self.address}")
        return self.address

    async def get_messages(self) -> list[dict]:
        """Get messages for the inbox."""
        if not self.address:
            return []

        client = await self._get_client()
        local, domain = self.address.split("@")
        resp = await client.get(
            f"{self.BASE_URL}/?action=getMessages&login={local}&domain={domain}"
        )
        resp.raise_for_status()
        messages = resp.json()

        result = []
        for msg in messages:
            # Fetch full message
            try:
                detail_resp = await client.get(
                    f"{self.BASE_URL}/?action=readMessage&login={local}&domain={domain}&id={msg['id']}"
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()
                body = detail.get("textBody", "") or detail.get("body", "")
            except Exception:
                body = msg.get("body", "")

            result.append(
                {
                    "id": str(msg.get("id", "")),
                    "from_address": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "body": body,
                    "received_at": msg.get("date", ""),
                }
            )
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: Guerrilla Mail
# ═══════════════════════════════════════════════════════════════════════════════


class GuerrillaMailClient:
    """Guerrilla Mail temp mail client."""

    BASE_URL = "https://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._sid: str | None = None
        self.address: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def create(self) -> str:
        """Create a new temp email. Returns email address."""
        client = await self._get_client()

        # Get email address from Guerrilla Mail
        resp = await client.get(f"{self.BASE_URL}?f=get_email_address&ip=127.0.0.1&agent=Mozilla")
        resp.raise_for_status()
        data = resp.json()

        self.address = data["email_addr"]
        self._sid = data.get("sid_token", "")

        log_debug(f"Guerrilla Mail: created {self.address}")
        return self.address

    async def get_messages(self) -> list[dict]:
        """Get messages for the inbox."""
        if not self._sid:
            return []

        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}?f=check_email&seq=0&sid_token={self._sid}")
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("list", [])

        result = []
        for msg in messages:
            body = msg.get("mail_body", "") or msg.get("mail_excerpt", "")
            # Strip HTML
            import re

            body = re.sub(r"<[^>]+>", " ", body).strip()

            result.append(
                {
                    "id": str(msg.get("mail_id", "")),
                    "from_address": msg.get("mail_from", ""),
                    "subject": msg.get("mail_subject", ""),
                    "body": body,
                    "received_at": str(msg.get("mail_date", "")),
                }
            )
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: Tempik (webkarya.net) — original
# ═══════════════════════════════════════════════════════════════════════════════


class TempikClient:
    """Tempik temp mail client (webkarya.net)."""

    def __init__(self, base_url: str = "https://tempik.webkarya.net/api"):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self.session_id: str | None = None
        self.address: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def create(self) -> str:
        """Create a new temp email. Returns email address."""
        client = await self._get_client()

        # Create session
        resp = await client.get(f"{self.base_url}/session")
        resp.raise_for_status()
        self.session_id = resp.json()["sessionId"]

        # Create inbox
        headers = {"x-session-id": self.session_id}
        resp = await client.post(f"{self.base_url}/inboxes", headers=headers, json={})
        resp.raise_for_status()
        self.address = resp.json()["address"]

        log_debug(f"Tempik: created {self.address}")
        return self.address

    async def get_messages(self) -> list[dict]:
        """Get messages for the inbox."""
        if not self.session_id or not self.address:
            return []

        client = await self._get_client()
        headers = {"x-session-id": self.session_id}
        from urllib.parse import quote

        encoded = quote(self.address, safe="")
        resp = await client.get(f"{self.base_url}/inboxes/{encoded}/messages", headers=headers)
        resp.raise_for_status()
        return cast(list[dict[Any, Any]], resp.json())


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-PROVIDER CLIENT WITH FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDER_ORDER = ["mail.tm", "tempmail.lol", "guerrilla", "1secmail", "tempik"]


class TempMailClient:
    """Multi-provider temp mail client with automatic fallback."""

    def __init__(self, preferred_provider: str | None = None):
        """Initialize with optional preferred provider.

        Args:
            preferred_provider: Provider name to try first ("mail.tm", "1secmail", "tempik").
                              If None, tries in default order.
        """
        self._preferred = preferred_provider
        self._active_client: Any = None
        self._active_provider: str | None = None
        self.address: str | None = None

    def _get_provider_order(self) -> list[str]:
        """Get provider try order."""
        if self._preferred and self._preferred in PROVIDER_ORDER:
            order = [self._preferred] + [p for p in PROVIDER_ORDER if p != self._preferred]
            return order
        return list(PROVIDER_ORDER)

    def _create_client(self, provider: str):
        """Create client for given provider."""
        if provider == "mail.tm":
            return MailTmClient()
        elif provider == "guerrilla":
            return GuerrillaMailClient()
        elif provider == "1secmail":
            return OneSecMailClient()
        elif provider == "tempik":
            return TempikClient()
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def create(self) -> str:
        """Create temp email, trying providers in order.

        Returns:
            Email address.

        Raises:
            RuntimeError: If all providers fail.
        """
        errors = []
        for provider in self._get_provider_order():
            try:
                client = self._create_client(provider)
                address = await client.create()
                self._active_client = client
                self._active_provider = provider
                self.address = address
                log_ok(f"Temp email ({provider}): {address}")
                return cast(str, address)
            except Exception as e:
                errors.append(f"{provider}: {e}")
                log_warn(f"Provider {provider} failed: {e}")
                continue

        raise RuntimeError(
            "All temp mail providers failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    async def get_messages(self) -> list[dict]:
        """Get messages from active provider."""
        if not self._active_client:
            return []
        return cast(list[dict[Any, Any]], await self._active_client.get_messages())

    async def wait_for_otp(
        self,
        timeout: int = 120,
        poll_interval: float = 2.0,
        otp_pattern: str = r"\b(\d{6})\b",
    ) -> str | None:
        """Poll inbox until OTP email arrives.

        Args:
            timeout: Max seconds to wait.
            poll_interval: Seconds between polls.
            otp_pattern: Regex pattern to match OTP.

        Returns:
            OTP string if found, None if timeout.
        """
        start = time.time()
        pattern = re.compile(otp_pattern)
        check_count = 0

        while time.time() - start < timeout:
            check_count += 1
            try:
                messages = await self.get_messages()
                for msg in messages:
                    subject = msg.get("subject", "")
                    body = msg.get("body", "") or msg.get("text", "")

                    # Check subject first — OTP often in subject
                    for text in [subject, body]:
                        if not isinstance(text, str):
                            continue
                        match = pattern.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(
                                f"OTP found after {elapsed}s ({check_count} checks): {match.group(1)}"
                            )
                            return match.group(1)

                if check_count % 10 == 0:
                    elapsed = int(time.time() - start)
                    log_debug(
                        f"OTP check #{check_count} ({elapsed}s): {len(messages)} messages, no OTP yet"
                    )

            except Exception as e:
                log_debug(f"OTP poll error (will retry): {e}")

            await asyncio.sleep(poll_interval)

        log_err(f"OTP not received within {timeout}s ({check_count} checks)")
        return None

    async def close(self):
        """Close active client."""
        if self._active_client:
            try:
                await self._active_client.close()
            except Exception:
                pass

    @property
    def provider(self) -> str | None:
        """Name of active provider."""
        return self._active_provider
