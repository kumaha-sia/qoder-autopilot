"""
Identity Generator
===================

Generates random Indonesian-style identities for registration.
Uses Faker with id_ID locale.
"""

import secrets
import string

try:
    from faker import Faker

    fake: Faker | None = Faker("id_ID")
except ImportError:
    fake = None


# Fallback name pools
FIRST_NAMES = [
    "Raihan",
    "Ahmad",
    "Budi",
    "Dimas",
    "Eko",
    "Fajar",
    "Gilang",
    "Hadi",
    "Irfan",
    "Joko",
    "Kevin",
    "Lukman",
    "Muhammad",
    "Naufal",
    "Omar",
    "Putra",
    "Rizky",
    "Satria",
    "Taufik",
    "Umar",
    "Vino",
    "Wahyu",
    "Yusuf",
    "Zaki",
    "Andi",
    "Bayu",
    "Cahya",
    "Dani",
    "Elang",
    "Faris",
]

LAST_NAMES = [
    "Pratama",
    "Saputra",
    "Wijaya",
    "Kurniawan",
    "Hidayat",
    "Nugraha",
    "Santoso",
    "Wibowo",
    "Permadi",
    "Ramadhan",
    "Setiawan",
    "Utama",
    "Firmansyah",
    "Gunawan",
    "Hakim",
    "Ibrahim",
    "Jaya",
    "Kusuma",
    "Lesmana",
    "Mulyadi",
    "Nurhadi",
    "Prasetyo",
    "Rahman",
    "Siregar",
    "Sinaga",
]


def gen_identity() -> dict:
    """Generate a random identity.

    Returns:
        Dict with keys: first_name, last_name, display_name, password.
    """
    if fake:
        first_name = fake.first_name()
        last_name = fake.last_name()
    else:
        first_name = secrets.choice(FIRST_NAMES)
        last_name = secrets.choice(LAST_NAMES)

    # Generate password
    password = _gen_password()

    return {
        "first_name": first_name,
        "last_name": last_name,
        "display_name": f"{first_name} {last_name}",
        "password": password,
    }


def gen_email_address(domain: str = "webkarya.net") -> str:
    """Generate a random email local part.

    Args:
        domain: Email domain.

    Returns:
        Email address string.
    """
    if fake:
        # Indonesian-style: e.g., kopihujan42
        local = fake.user_name()
    else:
        # Fallback: random string
        local = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))

    # Add random number
    local += str(secrets.randbelow(90) + 10)

    return f"{local}@{domain}"


def _gen_password(length: int = 16) -> str:
    """Generate a secure random password.

    Args:
        length: Password length (default: 16).

    Returns:
        Password string with mixed case, digits, and special chars.
    """
    # Ensure at least one of each type
    chars = string.ascii_letters + string.digits + "!@#$%&*"
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*"),
    ]
    password.extend(secrets.choice(chars) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)
