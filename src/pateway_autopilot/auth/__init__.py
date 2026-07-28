"""
Auth module — Credentials storage, identity generation.
"""

from .credentials import save_creds, load_creds
from .identity import gen_identity

__all__ = ["save_creds", "load_creds", "gen_identity"]
