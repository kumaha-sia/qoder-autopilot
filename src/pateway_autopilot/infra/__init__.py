"""
Infrastructure module — Temp mail, config, etc.
"""

from .tempik import TempikClient
from .config import settings

__all__ = ["TempikClient", "settings"]
