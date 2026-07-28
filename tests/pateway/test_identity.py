"""
Tests for Pateway Autopilot — Identity Generator
"""

import pytest

from pateway_autopilot.auth.identity import gen_identity, gen_email_address, _gen_password


def test_gen_identity():
    """Test identity generation."""
    identity = gen_identity()

    assert "first_name" in identity
    assert "last_name" in identity
    assert "display_name" in identity
    assert "password" in identity

    assert identity["display_name"] == f"{identity['first_name']} {identity['last_name']}"
    assert len(identity["password"]) >= 12


def test_gen_email_address():
    """Test email address generation."""
    email = gen_email_address()
    assert "@" in email
    assert email.endswith("@webkarya.net")

    # Custom domain
    email = gen_email_address("example.com")
    assert email.endswith("@example.com")


def test_gen_password():
    """Test password generation."""
    pw = _gen_password()
    assert len(pw) == 16

    # Check it has mixed characters
    has_upper = any(c.isupper() for c in pw)
    has_lower = any(c.islower() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    has_special = any(c in "!@#$%&*" for c in pw)

    assert has_upper
    assert has_lower
    assert has_digit
    assert has_special
