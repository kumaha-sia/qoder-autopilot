"""Tests for 9Router client — login and push_keys."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pateway_autopilot.infra.ninerouter import (
    PATEWAY_ANTHROPIC_PROVIDER_ID,
    PATEWAY_OPENAI_PROVIDER_ID,
    NineRouterClient,
    push_keys_to_9router,
)


class TestNineRouterClient:
    """Cover NineRouterClient login and push_keys."""

    async def test_login_stores_cookie_from_set_cookie_header(self) -> None:
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.headers = {"set-cookie": "session=abc123; Path=/"}
            mock_resp.raise_for_status.return_value = None
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            ok = await client.login()
            assert ok is True
            assert client._cookie == "session=abc123"

    async def test_login_stores_token_from_json_body(self) -> None:
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.headers = {}
            mock_resp.raise_for_status.return_value = None
            mock_resp.json = lambda: {"token": "tok_xyz"}
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            ok = await client.login()
            assert ok is True
            assert client._cookie == "token=tok_xyz"

    async def test_login_fails_when_no_cookie_nor_token(self) -> None:
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.headers = {}
            mock_resp.raise_for_status.return_value = None
            mock_resp.json = lambda: {"ok": True}
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            ok = await client.login()
            assert ok is False

    async def test_add_provider_sends_correct_payload(self) -> None:
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            ok = await client.add_provider(
                provider_id="prov-abc",
                name="Pateway-OpenAI-Default-test",
                api_key="sk-ptw-xxx",
            )
            assert ok is True
            call = mock_http.post.call_args
            assert call[1]["json"]["provider"] == "prov-abc"
            assert call[1]["json"]["name"] == "Pateway-OpenAI-Default-test"
            assert call[1]["json"]["apiKey"] == "sk-ptw-xxx"
            assert call[1]["headers"]["Cookie"] == "session=abc"

    async def test_add_provider_409_is_treated_as_success(self) -> None:
        """409 Conflict = key already exists — not a fatal error."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.status_code = 409
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            ok = await client.add_provider("prov-abc", "Test", "sk-ptw-xxx")
            assert ok is True

    async def test_push_keys_creates_4_entries_for_both_keys(self) -> None:
        """Both Default and Economy keys → 4 provider entries."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with (
            patch.object(client, "login", new_callable=AsyncMock, return_value=True),
            patch.object(
                client, "add_provider", new_callable=AsyncMock, return_value=True
            ) as mock_add,
        ):
            results = await client.push_keys(
                email="virtu.alvi.t.e@gmail.com",
                key_default="sk-ptw-default",
                key_economy="sk-ptw-economy",
            )
            assert len(results) == 4
            assert all(results.values())

            # Verify 4 calls with correct provider IDs and names.
            calls = mock_add.call_args_list
            assert len(calls) == 4
            names = [c[0][1] for c in calls]  # positional arg 1 = name
            assert any("OpenAI-Default" in n for n in names)
            assert any("OpenAI-Economy" in n for n in names)
            assert any("Anthropic-Default" in n for n in names)
            assert any("Anthropic-Economy" in n for n in names)

            # Verify correct provider IDs were used.
            provider_ids = [c[0][0] for c in calls]
            assert PATEWAY_OPENAI_PROVIDER_ID in provider_ids
            assert PATEWAY_ANTHROPIC_PROVIDER_ID in provider_ids

    async def test_push_keys_only_default_when_economy_missing(self) -> None:
        """Only Default key → 2 entries (OpenAI + Anthropic Default)."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with (
            patch.object(client, "login", new_callable=AsyncMock, return_value=True),
            patch.object(
                client, "add_provider", new_callable=AsyncMock, return_value=True
            ) as mock_add,
        ):
            results = await client.push_keys(
                email="test@gmail.com",
                key_default="sk-ptw-default",
                key_economy=None,
            )
            assert len(results) == 2
            assert all(results.values())
            names = [c[0][1] for c in mock_add.call_args_list]
            # Names contain email alias + random suffix — check prefix only.
            assert names[0].startswith("Pateway-OpenAI-Default-test-")
            assert names[1].startswith("Pateway-Anthropic-Default-test-")

    async def test_push_keys_only_economy_when_default_missing(self) -> None:
        """Only Economy key → 2 entries (OpenAI + Anthropic Economy)."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with (
            patch.object(client, "login", new_callable=AsyncMock, return_value=True),
            patch.object(
                client, "add_provider", new_callable=AsyncMock, return_value=True
            ) as mock_add,
        ):
            results = await client.push_keys(
                email="test@gmail.com",
                key_default=None,
                key_economy="sk-ptw-economy",
            )
            assert len(results) == 2
            assert all(results.values())
            names = [c[0][1] for c in mock_add.call_args_list]
            assert names[0].startswith("Pateway-OpenAI-Economy-test-")
            assert names[1].startswith("Pateway-Anthropic-Economy-test-")

    async def test_push_keys_neither_key_returns_empty(self) -> None:
        """No keys → 0 entries."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        with patch.object(client, "login", new_callable=AsyncMock, return_value=True):
            results = await client.push_keys(
                email="test@gmail.com",
                key_default=None,
                key_economy=None,
            )
            assert len(results) == 0

    async def test_push_keys_aborts_when_login_fails(self) -> None:
        """Login failure → return empty dict, don't attempt pushes."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        with patch.object(client, "login", new_callable=AsyncMock, return_value=False):
            results = await client.push_keys(
                email="test@gmail.com",
                key_default="sk-ptw-default",
                key_economy="sk-ptw-economy",
            )
            assert len(results) == 0

    async def test_email_prefix_keeps_dots_and_adds_suffix(self) -> None:
        """Email prefix for naming: keeps dots (so different Gmail aliases
        produce different names) and appends a random suffix for uniqueness."""
        client = NineRouterClient(base_url="https://r.example.com", password="pass")
        client._cookie = "session=abc"
        with (
            patch.object(client, "login", new_callable=AsyncMock, return_value=True),
            patch.object(
                client, "add_provider", new_callable=AsyncMock, return_value=True
            ) as mock_add,
        ):
            await client.push_keys(
                email="vi.r.tual.vit.e@gmail.com",
                key_default="sk-ptw-d",
                key_economy=None,
            )
            names = [c[0][1] for c in mock_add.call_args_list]
            # Prefix keeps dots: "vi.r.tual.vit.e" — NOT "virtualvite"
            assert "vi.r.tual.vit.e" in names[0], (
                f"Name should contain dotted alias, got: {names[0]}"
            )
            assert "virtualvite" not in names[0], (
                f"Name should NOT contain dot-stripped alias, got: {names[0]}"
            )


class TestPushKeysTo9router:
    """Convenience wrapper test."""

    async def test_wrapper_creates_client_and_pushes(self) -> None:
        with patch("pateway_autopilot.infra.ninerouter.NineRouterClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.push_keys.return_value = {"Entry-1": True}
            mock_cls.return_value = mock_client

            result = await push_keys_to_9router("test@gmail.com", "sk-d", "sk-e")
            assert result == {"Entry-1": True}
            mock_client.push_keys.assert_called_once_with("test@gmail.com", "sk-d", "sk-e")
            mock_client.close.assert_called_once()
