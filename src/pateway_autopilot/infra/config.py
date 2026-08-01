"""
Pateway Autopilot — Configuration
===================================

Settings loaded with priority chain (highest → lowest):
    1. Environment variables (PATEWAY_*, .env)
    2. User config (~/.pateway-autopilot/config.json)
    3. Built-in defaults
"""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ═══════════════════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════════════════

PACKAGE_DIR = Path(__file__).parent
PROJECT_DIR = PACKAGE_DIR.parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# USER CONFIG LOADER
# ═══════════════════════════════════════════════════════════════════════════════

USER_CONFIG_DIR = Path.home() / ".pateway-autopilot"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"


def load_user_config() -> dict:
    """Load user config from ~/.pateway-autopilot/config.json."""
    try:
        if USER_CONFIG_FILE.exists():
            import json
            from typing import Any, cast

            with open(USER_CONFIG_FILE) as f:
                return cast(dict[Any, Any], json.load(f))
    except Exception:
        pass
    return {}


def save_user_config(data: dict) -> bool:
    """Save user config to ~/.pateway-autopilot/config.json."""
    try:
        import json
        import stat
        import sys

        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(USER_CONFIG_FILE), 2)
        else:
            os.chmod(str(USER_CONFIG_FILE), stat.S_IRUSR | stat.S_IWUSR)
        return True
    except Exception:
        return False


def set_user_config_value(key: str, value: str) -> bool:
    """Set a single config value. Returns True on success."""
    cfg = load_user_config()
    cfg[key] = value
    return save_user_config(cfg)


def delete_user_config() -> bool:
    """Delete user config file. Returns True if deleted."""
    try:
        if USER_CONFIG_FILE.exists():
            USER_CONFIG_FILE.unlink()
            return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS CLASS
# ═══════════════════════════════════════════════════════════════════════════════


class Settings(BaseSettings):
    """Centralized configuration for Pateway Autopilot.

    All fields can be set via environment variables with the PATEWAY_ prefix.
    Values are also loaded from .env file if present.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PATEWAY_",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def _load_user_config(cls) -> dict:
        """Load user config from ~/.pateway-autopilot/config.json."""
        try:
            return load_user_config()
        except Exception:
            return {}

    def __init__(self, **data):
        # Inject user config as base values
        user_cfg = self._load_user_config()
        for key, value in user_cfg.items():
            if key in data:
                continue
            env_key = f"PATEWAY_{key.upper()}"
            if os.environ.get(env_key):
                continue
            data[key] = value
        super().__init__(**data)

    # ── Temp Mail ───────────────────────────────────────────────────────
    mail_provider: str = Field(
        default="mail.tm",
        description="Temp mail provider: mail.tm, guerrilla, 1secmail, tempik, or gmail",
    )
    tempik_url: str = Field(
        default="https://tempik.webkarya.net/api",
        description="Tempik API base URL (only used if mail_provider=tempik)",
    )

    # ── Gmail (for dot/plus trick + IMAP auto-OTP) ────────────────────
    gmail_email: str = Field(
        default="",
        description="Your Gmail address for dot/plus alias generation",
    )
    gmail_app_password: str = Field(
        default="",
        description="Gmail App Password (16 chars) for IMAP auto-OTP",
    )

    # ── PatewayAI URLs ────────────────────────────────────────────────
    pateway_url: str = Field(
        default="https://pateway.ai",
        description="PatewayAI homepage URL",
    )
    pateway_api_url: str = Field(
        default="https://api.pateway.ai/v1",
        description="PatewayAI API base URL",
    )

    # ── Behavior ──────────────────────────────────────────────────────
    otp_timeout: int = Field(
        default=60,
        description="Max seconds to wait for OTP email",
    )
    captcha_timeout: int = Field(
        default=120,
        description="Max seconds for manual captcha solve",
    )
    max_captcha_attempts: int = Field(
        default=3,
        description="Max auto captcha solve attempts before fallback",
    )
    parallel_delay: int = Field(
        default=30,
        description="Delay between sequential account registrations (seconds)",
    )

    # ── API Key ───────────────────────────────────────────────────────
    key_name: str = Field(
        default="prod",
        description="Default API key name",
    )
    invite_code: str = Field(
        default="",
        description="Invite code for registration",
    )

    # ── 9Router ───────────────────────────────────────────────────────
    ninerouter_url: str = Field(
        default="https://router.muhammadiwa.my.id",
        description="9Router base URL for API key push",
    )
    ninerouter_password: str = Field(
        default="admin123",
        description="9Router admin password for login",
    )

    # ── File paths ────────────────────────────────────────────────────
    screenshots_dir: Path = Field(
        default=Path("screenshots"),
        description="Directory for debug screenshots",
    )
    credentials_file: Path = Field(
        default=Path("pateway_accounts.json"),
        description="JSON file for storing account credentials",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

settings = Settings()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL RE-EXPORTS (property-like access via __getattr__)
# ═══════════════════════════════════════════════════════════════════════════════

# These are lazily resolved from the settings singleton so runtime changes
# (e.g., env var overrides loaded late) are picked up.

_EXPORT_MAP = {
    "TEMPIK_URL": "tempik_url",
    "MAIL_PROVIDER": "mail_provider",
    "GMAIL_EMAIL": "gmail_email",
    "GMAIL_APP_PASSWORD": "gmail_app_password",
    "PATEWAY_URL": "pateway_url",
    "PATEWAY_API_URL": "pateway_api_url",
    "OTP_TIMEOUT": "otp_timeout",
    "CAPTCHA_TIMEOUT": "captcha_timeout",
    "MAX_CAPTCHA_ATTEMPTS": "max_captcha_attempts",
    "PARALLEL_DELAY": "parallel_delay",
    "KEY_NAME": "key_name",
    "INVITE_CODE": "invite_code",
    "NINEROUTER_URL": "ninerouter_url",
    "NINEROUTER_PASSWORD": "ninerouter_password",
    "SCREENSHOTS_DIR": "screenshots_dir",
    "CREDENTIALS_FILE": "credentials_file",
}


def __getattr__(name: str):
    if name in _EXPORT_MAP:
        return getattr(settings, _EXPORT_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Make `from ..infra.config import *` work for lazy constants
__all__ = [
    "settings",
    "Settings",
    "load_user_config",
    "save_user_config",
    "set_user_config_value",
    "delete_user_config",
    "USER_CONFIG_DIR",
    "USER_CONFIG_FILE",
    "PACKAGE_DIR",
    "PROJECT_DIR",
] + list(_EXPORT_MAP.keys())
