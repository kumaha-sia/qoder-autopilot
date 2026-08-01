"""
9Router Client
===============
Pushes Pateway API keys to a self-hosted 9Router instance.

Flow:
    1. Login → cookie (auth token)
    2. For each (key, provider) combo: POST /api/providers

Provider IDs are fixed for the Pateway instance:
    - Pateway (OpenAI):    openai-compatible-chat-7c82b631-...
    - Pateway (Anthropic): anthropic-compatible-1bb1b01a-...

Usage:
    client = NineRouterClient()
    await client.login()
    await client.push_keys(
        email="vi.r.tual.vit.e@gmail.com",
        key_default="sk-ptw-...",
        key_economy="sk-ptw-...",
    )
"""

from __future__ import annotations

import random
import string
from typing import Any, cast

import httpx

from ..utils.logger import log_err, log_ok, log_warn
from . import config

# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER IDS — fixed for this 9Router deployment
# ═══════════════════════════════════════════════════════════════════════════════

PATEWAY_OPENAI_PROVIDER_ID = "openai-compatible-chat-7c82b631-d279-4abc-b02a-7649c202863d"
PATEWAY_ANTHROPIC_PROVIDER_ID = "anthropic-compatible-1bb1b01a-2fff-47ca-a405-e67bd858b250"


class NineRouterClient:
    """Async client for 9Router API — login and push provider keys."""

    def __init__(
        self,
        base_url: str | None = None,
        password: str | None = None,
    ):
        self.base_url = (base_url or config.NINEROUTER_URL).rstrip("/")
        self.password = password or config.NINEROUTER_PASSWORD
        self._client: httpx.AsyncClient | None = None
        self._cookie: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def login(self) -> bool:
        """Login to 9Router and store auth cookie.

        Returns:
            True if login succeeded, False otherwise.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.base_url}/api/auth/login",
                json={"password": self.password},
            )
            resp.raise_for_status()

            # Extract cookie from Set-Cookie header.
            cookie_header = resp.headers.get("set-cookie", "")
            if not cookie_header:
                # Some deployments return token in JSON body.
                data = cast(dict[str, Any], resp.json())
                token = data.get("token") or data.get("accessToken")
                if token:
                    self._cookie = f"token={token}"
                    log_ok("9Router: logged in (token from body)")
                    return True
                log_err("9Router: login succeeded but no cookie/token found")
                return False

            # Parse cookie — take the first key=value pair.
            self._cookie = cookie_header.split(";")[0]
            log_ok("9Router: logged in")
            return True

        except Exception as e:
            log_err(f"9Router: login failed: {e}")
            return False

    async def add_provider(
        self,
        provider_id: str,
        name: str,
        api_key: str,
        auth_type: str = "apikey",
    ) -> bool:
        """Add a single API key to a provider in 9Router.

        Args:
            provider_id: 9Router provider UUID.
            name: Display name for this key entry.
            api_key: The API key value (sk-ptw-...).
            auth_type: Auth type (default "apikey").

        Returns:
            True if added successfully, False otherwise.
        """
        if not self._cookie:
            log_err("9Router: not logged in — call login() first")
            return False

        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.base_url}/api/providers",
                json={
                    "provider": provider_id,
                    "name": name,
                    "authType": auth_type,
                    "apiKey": api_key,
                },
                headers={"Cookie": self._cookie},
            )
            if resp.status_code in (200, 201):
                log_ok(f"9Router: added '{name}'")
                return True

            # 409 Conflict = key already exists — not fatal.
            if resp.status_code == 409:
                log_warn(f"9Router: '{name}' already exists (409)")
                return True

            body = resp.text[:200]
            log_err(f"9Router: add '{name}' failed: {resp.status_code} {body}")
            return False

        except Exception as e:
            log_err(f"9Router: add '{name}' failed: {e}")
            return False

    async def push_keys(
        self,
        email: str,
        key_default: str | None,
        key_economy: str | None,
    ) -> dict[str, bool]:
        """Push both Default and Economy keys to both Pateway providers.

        Creates 4 entries total:
            - Pateway-OpenAI-Default-{email_prefix}
            - Pateway-OpenAI-Economy-{email_prefix}
            - Pateway-Anthropic-Default-{email_prefix}
            - Pateway-Anthropic-Economy-{email_prefix}

        Args:
            email: Account email (used for naming).
            key_default: Default Mode API key (sk-ptw-...).
            key_economy: Economy Mode API key (sk-ptw-...).

        Returns:
            Dict mapping entry name → success bool.
        """
        # Derive a short prefix from the email for naming.  We keep the
        # dots in the alias (e.g., "v.irt.ualvi.te") so different Gmail dot
        # aliases produce different names — removing dots would collapse
        # all aliases of the same base email into the same prefix.
        # We also append a short random suffix to guarantee uniqueness
        # across runs (e.g., two accounts with the same alias prefix).
        email_local = email.split("@")[0][:25]  # keep dots, cap length
        unique_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))

        results: dict[str, bool] = {}

        # Login first.
        if not await self.login():
            log_err("9Router: aborting push — login failed")
            return results

        # Build the 4 push targets — name includes email alias (with dots)
        # plus a random suffix for uniqueness.
        pushes: list[tuple[str, str, str]] = []
        if key_default:
            pushes.append(
                (
                    PATEWAY_OPENAI_PROVIDER_ID,
                    f"Pateway-OpenAI-Default-{email_local}-{unique_suffix}",
                    key_default,
                )
            )
            pushes.append(
                (
                    PATEWAY_ANTHROPIC_PROVIDER_ID,
                    f"Pateway-Anthropic-Default-{email_local}-{unique_suffix}",
                    key_default,
                )
            )
        else:
            log_warn("9Router: no Default key — skipping Default pushes")

        if key_economy:
            pushes.append(
                (
                    PATEWAY_OPENAI_PROVIDER_ID,
                    f"Pateway-OpenAI-Economy-{email_local}-{unique_suffix}",
                    key_economy,
                )
            )
            pushes.append(
                (
                    PATEWAY_ANTHROPIC_PROVIDER_ID,
                    f"Pateway-Anthropic-Economy-{email_local}-{unique_suffix}",
                    key_economy,
                )
            )
        else:
            log_warn("9Router: no Economy key — skipping Economy pushes")

        for provider_id, name, api_key in pushes:
            ok = await self.add_provider(provider_id, name, api_key)
            results[name] = ok

        succeeded = sum(1 for v in results.values() if v)
        total = len(results)
        if succeeded == total:
            log_ok(f"9Router: all {total} keys pushed successfully")
        else:
            log_warn(f"9Router: {succeeded}/{total} keys pushed")

        return results


async def push_keys_to_9router(
    email: str,
    key_default: str | None,
    key_economy: str | None,
    base_url: str | None = None,
    password: str | None = None,
) -> dict[str, bool]:
    """Convenience wrapper — creates client, pushes keys, closes client.

    Args:
        email: Account email (for naming).
        key_default: Default Mode API key.
        key_economy: Economy Mode API key.
        base_url: Override 9Router URL.
        password: Override 9Router password.

        Returns:
            Dict mapping entry name → success bool.
    """
    client = NineRouterClient(base_url=base_url, password=password)
    try:
        return await client.push_keys(email, key_default, key_economy)
    finally:
        await client.close()
