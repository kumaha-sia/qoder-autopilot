"""
Logger — ANSI Colored Structured Logging
==========================================

Provides colored log output for CLI.
"""

import os
import sys
from typing import Optional

# Force UTF-8 output on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ANSI colors
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


# Verbosity levels
_verbosity = 1  # 0=quiet, 1=normal, 2=debug
_account_tag = ""
_log_file = None


def set_verbosity(level: int):
    """Set verbosity level (0=quiet, 1=normal, 2=debug)."""
    global _verbosity
    _verbosity = max(0, min(2, level))


def set_account_tag(tag: str):
    """Set account tag for parallel mode logging."""
    global _account_tag
    _account_tag = tag


def set_log_file(path: str):
    """Set log file path."""
    global _log_file
    try:
        _log_file = open(path, "a", encoding="utf-8")
        return _log_file
    except Exception:
        return None


def close_log_file():
    """Close log file."""
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


def _write_log(message: str, file_only: bool = False):
    """Write to log file if configured."""
    if _log_file:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _log_file.write(f"[{timestamp}] {message}\n")
        _log_file.flush()

    if not file_only:
        try:
            print(message)
        except UnicodeEncodeError:
            # Fallback for Windows cp1252 encoding
            print(message.encode("utf-8", errors="replace").decode("utf-8"))


def log(message: str):
    """Log a standard message."""
    if _verbosity < 1:
        return
    tag = f"{_account_tag} " if _account_tag else ""
    _write_log(f"{tag}{message}")


def log_ok(message: str):
    """Log a success message."""
    if _verbosity < 1:
        return
    tag = f"{_account_tag} " if _account_tag else ""
    _write_log(f"{tag}{Colors.GREEN}✅ {message}{Colors.RESET}")


def log_err(message: str):
    """Log an error message."""
    tag = f"{_account_tag} " if _account_tag else ""
    _write_log(f"{tag}{Colors.RED}❌ {message}{Colors.RESET}")


def log_warn(message: str):
    """Log a warning message."""
    if _verbosity < 1:
        return
    tag = f"{_account_tag} " if _account_tag else ""
    _write_log(f"{tag}{Colors.YELLOW}⚠️  {message}{Colors.RESET}")


def log_step(current: int, total: int, message: str):
    """Log a step in a multi-step process."""
    if _verbosity < 1:
        return
    tag = f"{_account_tag} " if _account_tag else ""
    if total > 0:
        _write_log(f"{tag}{Colors.CYAN}📋 Step {current}/{total}: {message}{Colors.RESET}")
    else:
        _write_log(f"{tag}{Colors.CYAN}📋 {message}{Colors.RESET}")


def log_debug(message: str):
    """Log a debug message (only in verbose mode)."""
    if _verbosity < 2:
        return
    tag = f"{_account_tag} " if _account_tag else ""
    _write_log(f"{tag}{Colors.DIM}🔍 {message}{Colors.RESET}")


def log_banner():
    """Print the application banner."""
    if _verbosity < 1:
        return
    banner = f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════════╗
║       🤖 Pateway Autopilot v0.1.0                ║
║       Automated PatewayAI Account Registration    ║
╚══════════════════════════════════════════════════╝{Colors.RESET}
"""
    _write_log(banner)
