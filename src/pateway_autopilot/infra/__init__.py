"""
Infrastructure module — Temp mail, config, etc.
"""

from .config import settings
from .tempik import TempikClient

__all__ = ["TempikClient", "settings"]
