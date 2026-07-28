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

            with open(USER_CONFIG_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_user_config(data: dict) -> bool:
    """Save user config to ~/.pateway-autopilot/config.json."""
    try:
        import json

        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
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

    # ── Tempik ─────────────────────────────────────────────────────────
    tempik_url: str = Field(
        default="https://tempik.webkarya.net/api",
        description="Tempik API base URL",
    )
    tempik_domain: str = Field(
        default="webkarya.net",
        description="Email domain for temp addresses",
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
# MODULE-LEVEL RE-EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

# Tempik
TEMPIK_URL = settings.tempik_url
TEMPIK_DOMAIN = settings.tempik_domain

# PatewayAI
PATEWAY_URL = settings.pateway_url
PATEWAY_API_URL = settings.pateway_api_url

# Behavior
OTP_TIMEOUT = settings.otp_timeout
CAPTCHA_TIMEOUT = settings.captcha_timeout
MAX_CAPTCHA_ATTEMPTS = settings.max_captcha_attempts
PARALLEL_DELAY = settings.parallel_delay

# API Key
KEY_NAME = settings.key_name
INVITE_CODE = settings.invite_code

# File paths
SCREENSHOTS_DIR = settings.screenshots_dir
CREDENTIALS_FILE = settings.credentials_file
