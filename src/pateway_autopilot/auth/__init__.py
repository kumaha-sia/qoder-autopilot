"""
Auth module — Credentials storage, identity generation.
"""

from .credentials import load_creds, save_creds
from .identity import gen_identity

__all__ = ["save_creds", "load_creds", "gen_identity"]
