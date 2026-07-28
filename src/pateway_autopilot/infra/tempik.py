"""
Tempik Temp Mail Client
========================

REST API client for Tempik disposable email service.
Tempik runs on Cloudflare Workers + D1.

API: https://tempik.webkarya.net/api/
Docs: https://github.com/kumaha-sia/tempik
"""

import asyncio
import re
import time
from typing import Optional

import httpx


class TempikClient:
    """Client for Tempik temp mail API."""

    def __init__(self, base_url: str = "https://tempik.webkarya.net/api"):
        self.base_url = base_url.rstrip("/")
        self.session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def create_session(self) -> str:
        """Create anonymous session. Returns session ID."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/session")
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["sessionId"]
        return self.session_id

    async def _ensure_session(self) -> str:
        """Ensure session exists, create if needed."""
        if not self.session_id:
            await self.create_session()
        return self.session_id

    async def create_inbox(self, local_part: Optional[str] = None) -> str:
        """Create temp email address.

        Args:
            local_part: Custom username (e.g., "myinbox").
                       If None, generates random Indonesian-style name.

        Returns:
            Full email address (e.g., "kopihujan42@webkarya.net").
        """
        session_id = await self._ensure_session()
        client = await self._get_client()

        headers = {"x-session-id": session_id}
        body = {}
        if local_part:
            body["localPart"] = local_part

        resp = await client.post(
            f"{self.base_url}/inboxes",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["address"]

    async def get_messages(self, address: str) -> list[dict]:
        """Get all messages for an inbox.

        Args:
            address: Full email address (e.g., "kopihujan42@webkarya.net").

        Returns:
            List of message dicts with keys:
            - id: Message ID
            - inbox_address: Recipient email
            - from_address: Sender email
            - subject: Email subject
            - body: Email body text
            - received_at: Timestamp string
        """
        session_id = await self._ensure_session()
        client = await self._get_client()

        headers = {"x-session-id": session_id}
        # URL-encode the email address
        encoded_address = httpx.URL(path=address).path

        resp = await client.get(
            f"{self.base_url}/inboxes/{encoded_address}/messages",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_inbox(self, address: str) -> bool:
        """Remove inbox from session (does not delete from DB).

        Args:
            address: Full email address.

        Returns:
            True if successful.
        """
        session_id = await self._ensure_session()
        client = await self._get_client()

        headers = {"x-session-id": session_id}
        encoded_address = httpx.URL(path=address).path

        resp = await client.delete(
            f"{self.base_url}/inboxes/{encoded_address}",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json().get("ok", False)

    async def get_config(self) -> dict:
        """Get Tempik app configuration.

        Returns:
            Dict with keys: appName, mailDomain, mailDomains, webHost.
        """
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/config")
        resp.raise_for_status()
        return resp.json()

    async def wait_for_otp(
        self,
        address: str,
        timeout: int = 60,
        poll_interval: float = 2.0,
        otp_pattern: str = r"\b(\d{6})\b",
    ) -> Optional[str]:
        """Poll inbox until OTP email arrives.

        Args:
            address: Full email address.
            timeout: Max seconds to wait.
            poll_interval: Seconds between polls.
            otp_pattern: Regex pattern to match OTP (default: 6-digit code).

        Returns:
            OTP string if found, None if timeout.
        """
        start = time.time()
        pattern = re.compile(otp_pattern)

        while time.time() - start < timeout:
            try:
                messages = await self.get_messages(address)
                for msg in messages:
                    body = msg.get("body", "") or msg.get("text", "")
                    subject = msg.get("subject", "")

                    # Try to find OTP in body first, then subject
                    for text in [body, subject]:
                        match = pattern.search(text)
                        if match:
                            return match.group(1)
            except Exception:
                # Ignore transient errors, keep polling
                pass

            await asyncio.sleep(poll_interval)

        return None

    async def generate(self) -> dict:
        """Generate a new temp email (convenience method).

        Returns:
            Dict with keys: address, session_id.
        """
        await self._ensure_session()
        address = await self.create_inbox()
        return {
            "address": address,
            "session_id": self.session_id,
        }


# Synchronous wrapper for compatibility
class TempikClientSync:
    """Synchronous wrapper for TempikClient."""

    def __init__(self, base_url: str = "https://tempik.webkarya.net/api"):
        self._client = TempikClient(base_url)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coro):
        """Run coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    def create_session(self) -> str:
        return self._run(self._client.create_session())

    def create_inbox(self, local_part: Optional[str] = None) -> str:
        return self._run(self._client.create_inbox(local_part))

    def get_messages(self, address: str) -> list[dict]:
        return self._run(self._client.get_messages(address))

    def delete_inbox(self, address: str) -> bool:
        return self._run(self._client.delete_inbox(address))

    def get_config(self) -> dict:
        return self._run(self._client.get_config())

    def wait_for_otp(self, address: str, timeout: int = 60) -> Optional[str]:
        return self._run(self._client.wait_for_otp(address, timeout))

    def generate(self) -> dict:
        return self._run(self._client.generate())

    def close(self):
        self._run(self._client.close())
