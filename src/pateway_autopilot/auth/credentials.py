"""
Credentials Storage
====================

Stores account credentials securely in JSON file.
File permissions set to 600 (owner-only read/write).
"""

import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..utils.logger import log, log_ok, log_err


# Thread-safe file lock for parallel mode
# In asyncio context, all coroutines run in the same thread so threading.Lock
# is never contended. This protects against concurrent async file operations.
_file_lock = None


def _get_lock():
    """Get or create file lock."""
    global _file_lock
    if _file_lock is None:
        try:
            import threading

            _file_lock = threading.Lock()
        except ImportError:
            _file_lock = type("NullLock", (), {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
            })()
    return _file_lock


def save_creds(creds: dict, filepath: Optional[Path] = None) -> bool:
    """Save credentials to JSON file.

    Args:
        creds: Credential dict to save.
        filepath: Path to credentials file.
                 Defaults to config.CREDENTIALS_FILE.

    Returns:
        True if saved successfully.
    """
    if filepath is None:
        from ..infra.config import CREDENTIALS_FILE
        filepath = CREDENTIALS_FILE

    lock = _get_lock()

    with lock:
        try:
            # Load existing data
            existing = []
            if filepath.exists():
                with open(filepath) as f:
                    existing = json.load(f)

            # Add timestamp
            creds["created_at"] = datetime.now().isoformat()

            # Append new credentials
            existing.append(creds)

            # Write atomically
            filepath.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = filepath.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            # Set permissions before rename
            if sys.platform == "win32":
                try:
                    import subprocess
                    # Set owner-only ACL via icacls (removes inherited, grants current user Full only)
                    subprocess.run(
                        ["icacls", str(tmp_path), "/inheritance:r",
                         "/grant:r", f"{os.environ.get('USERNAME', os.getlogin())}:(F)"],
                        capture_output=True, check=False,
                    )
                except Exception:
                    pass
            else:
                os.chmod(str(tmp_path), stat.S_IRUSR | stat.S_IWUSR)

            # Atomic rename
            tmp_path.replace(filepath)

            log_ok(f"Credentials saved to {filepath}")
            return True

        except Exception as e:
            log_err(f"Failed to save credentials: {e}")
            return False


def load_creds(filepath: Optional[Path] = None) -> list[dict]:
    """Load credentials from JSON file.

    Args:
        filepath: Path to credentials file.

    Returns:
        List of credential dicts.
    """
    if filepath is None:
        from ..infra.config import CREDENTIALS_FILE
        filepath = CREDENTIALS_FILE

    try:
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
    except Exception as e:
        log_err(f"Failed to load credentials: {e}")

    return []


def mask_value(value: str) -> str:
    """Mask sensitive value for display.

    Args:
        value: Value to mask.

    Returns:
        Masked string.
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]
