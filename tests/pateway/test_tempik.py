"""
Tests for Pateway Autopilot — Tempik Client
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from pateway_autopilot.infra.tempik import TempikClient


@pytest.fixture
def tempik():
    """Create TempikClient instance."""
    return TempikClient(base_url="https://tempik.webkarya.net/api")


@pytest.mark.asyncio
async def test_create_session(tempik):
    """Test session creation."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"sessionId": "test-session-123"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(tempik, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        session_id = await tempik.create_session()
        assert session_id == "test-session-123"
        assert tempik.session_id == "test-session-123"


@pytest.mark.asyncio
async def test_create_inbox(tempik):
    """Test inbox creation."""
    tempik.session_id = "test-session"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "address": "kopihujan42@webkarya.net",
        "created_at": "2026-07-28 20:00:00",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(tempik, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_get_client.return_value = mock_client

        address = await tempik.create_inbox()
        assert address == "kopihujan42@webkarya.net"


@pytest.mark.asyncio
async def test_create_inbox_with_local_part(tempik):
    """Test inbox creation with custom local part."""
    tempik.session_id = "test-session"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "address": "myinbox@webkarya.net",
        "created_at": "2026-07-28 20:00:00",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(tempik, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_get_client.return_value = mock_client

        address = await tempik.create_inbox("myinbox")
        assert address == "myinbox@webkarya.net"


@pytest.mark.asyncio
async def test_get_messages(tempik):
    """Test message retrieval."""
    tempik.session_id = "test-session"

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "id": "msg_123",
            "inbox_address": "test@webkarya.net",
            "from_address": "noreply@pateway.ai",
            "subject": "Your verification code",
            "body": "Your code is 123456",
            "received_at": "2026-07-28 20:00:00",
        }
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(tempik, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        messages = await tempik.get_messages("test@webkarya.net")
        assert len(messages) == 1
        assert messages[0]["subject"] == "Your verification code"


@pytest.mark.asyncio
async def test_wait_for_otp(tempik):
    """Test OTP waiting and extraction."""
    tempik.session_id = "test-session"

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "id": "msg_123",
            "body": "Your verification code is 820610",
            "subject": "PatewayAI Verification",
        }
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(tempik, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        otp = await tempik.wait_for_otp("test@webkarya.net", timeout=5)
        assert otp == "820610"


@pytest.mark.asyncio
async def test_generate(tempik):
    """Test convenience generate method."""
    with patch.object(tempik, "create_session") as mock_session:
        mock_session.return_value = "test-session"

        with patch.object(tempik, "create_inbox") as mock_inbox:
            mock_inbox.return_value = "random@webkarya.net"

            result = await tempik.generate()
            assert result["address"] == "random@webkarya.net"
            assert result["session_id"] == "test-session"
