"""
Gmail Alias Generator
======================

Generates unique email aliases from a single Gmail account using:
1. Dot trick — Gmail ignores dots in local part
   user@gmail.com = u.ser@gmail.com = u.s.e.r@gmail.com
2. Plus trick — Gmail ignores everything after + in local part
   user+anything@gmail.com → user@gmail.com

Combined: u.ser+pateway1@gmail.com → user@gmail.com

This allows unlimited unique email addresses from ONE Gmail account.
"""

import random
import string


def generate_dot_variations(local_part: str, count: int = 10) -> list[str]:
    """Generate dot variations of a Gmail local part.

    Args:
        local_part: The part before @gmail.com (e.g., "johndoe")
        count: Number of variations to generate.

    Returns:
        List of local parts with dots inserted at random positions.
        The original (no-dots) is NOT included — callers that want it
        should add it themselves.

    Example:
        "johndoe" → ["john.doe", "j.ohndoe", "jo.hndoe", ...]
    """
    variations: set[str] = set()
    chars = list(local_part)

    # For short local parts there may not be enough unique dot positions;
    # cap the requested count to the maximum possible unique variants.
    max_possible = 2 ** (len(chars) - 1) - 1  # 2^(n-1) - 1 dot placements
    target = min(count, max(1, max_possible))

    while len(variations) < target:
        # Pick random positions to insert dots (1 to min(len-1, 5) dots)
        num_dots = random.randint(1, min(len(chars) - 1, 5))
        positions = sorted(random.sample(range(1, len(chars)), num_dots))

        # Build variant with dots
        variant = list(chars)
        for pos in reversed(positions):  # Reverse to maintain indices
            variant.insert(pos, ".")

        result = "".join(variant)
        if result != local_part and result not in variations:
            variations.add(result)

    return list(variations)[:target]


def generate_plus_variations(
    local_part: str, count: int = 10, prefix: str = "pateway"
) -> list[str]:
    """Generate plus-addressing variations.

    Args:
        local_part: The part before @gmail.com (e.g., "johndoe")
        count: Number of variations to generate.
        prefix: Prefix for plus tags (default: "pateway").

    Returns:
        List of email local parts with plus tags.

    Example:
        ("johndoe", 3, "pateway") → [
            "johndoe+pateway1",
            "johndoe+pateway2",
            "johndoe+pateway3",
        ]
    """
    variations = []
    for i in range(1, count + 1):
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        variations.append(f"{local_part}+{prefix}{i}{suffix}")
    return variations


def generate_combined_variations(
    local_part: str, count: int = 10, prefix: str = "pateway"
) -> list[str]:
    """Generate combined dot + plus variations for maximum uniqueness.

    Args:
        local_part: The part before @gmail.com (e.g., "johndoe")
        count: Number of variations to generate.
        prefix: Prefix for plus tags.

    Returns:
        List of email local parts combining dot and plus tricks.

    Example:
        ("johndoe", 3, "pateway") → [
            "johndoe+pateway1a3x",
            "jo.hndoe+pateway2b7y",
            "j.ohn.doe+pateway3c9z",
        ]
    """
    variations: set[str] = set()

    while len(variations) < count:
        # Random dot variation
        dot_var = random.choice(generate_dot_variations(local_part, 5))

        # Plus tag with random suffix
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        tag_num = random.randint(1, 9999)
        plus_var = f"{dot_var}+{prefix}{tag_num}{suffix}"

        variations.add(plus_var)

    return list(variations)[:count]


def generate_alias(base_email: str, method: str = "plus", prefix: str = "pateway") -> str:
    """Generate a single alias from a base Gmail address.

    Args:
        base_email: Full Gmail address (e.g., "user@gmail.com").
        method: "dot", "plus", or "combined".
        prefix: Prefix for plus tags.

    Returns:
        New alias email address.

    Raises:
        ValueError: If email is not a Gmail address.
    """
    if "@gmail.com" not in base_email.lower() and "@googlemail.com" not in base_email.lower():
        raise ValueError(f"Not a Gmail address: {base_email}")

    local_part, domain = base_email.split("@", 1)

    if method == "dot":
        variations = generate_dot_variations(local_part, 1)
        return f"{variations[0]}@{domain}"
    elif method == "plus":
        variations = generate_plus_variations(local_part, 1, prefix)
        return f"{variations[0]}@{domain}"
    elif method == "combined":
        variations = generate_combined_variations(local_part, 1, prefix)
        return f"{variations[0]}@{domain}"
    else:
        raise ValueError(f"Unknown method: {method}. Use 'dot', 'plus', or 'combined'")


class GmailAliasGenerator:
    """Generate Gmail aliases for bulk registration."""

    def __init__(self, base_email: str, method: str = "combined", prefix: str = "pateway"):
        """Initialize generator.

        Args:
            base_email: Your Gmail address (e.g., "you@gmail.com").
            method: Alias method — "dot", "plus", or "combined" (default).
            prefix: Prefix for plus tags.
        """
        if "@gmail.com" not in base_email.lower() and "@googlemail.com" not in base_email.lower():
            raise ValueError(f"Not a Gmail address: {base_email}")

        self.base_email = base_email
        self.local_part, self.domain = base_email.split("@", 1)
        self.method = method
        self.prefix = prefix
        self._used: set[str] = set()
        self._counter = 0

    def next(self) -> str:
        """Generate next unique alias.

        Returns:
            New unique Gmail alias.
        """
        while True:
            self._counter += 1
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))

            if self.method == "dot":
                dots = generate_dot_variations(self.local_part, 5)
                base = random.choice(dots)
                alias = f"{base}@{self.domain}"
            elif self.method == "plus":
                alias = f"{self.local_part}+{self.prefix}{self._counter}{suffix}@{self.domain}"
            else:  # combined
                dots = generate_dot_variations(self.local_part, 5)
                base = random.choice(dots)
                alias = f"{base}+{self.prefix}{self._counter}{suffix}@{self.domain}"

            if alias not in self._used:
                self._used.add(alias)
                return alias

    def get(self, index: int) -> str:
        """Get alias by index (1-based).

        Args:
            index: Alias number (1, 2, 3, ...).

        Returns:
            Gmail alias for the given index.
        """
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))

        if self.method == "dot":
            dots = generate_dot_variations(self.local_part, max(index, 5))
            base = dots[(index - 1) % len(dots)]
            return f"{base}@{self.domain}"
        elif self.method == "plus":
            return f"{self.local_part}+{self.prefix}{index}{suffix}@{self.domain}"
        else:  # combined
            dots = generate_dot_variations(self.local_part, max(index, 5))
            base = dots[(index - 1) % len(dots)]
            return f"{base}+{self.prefix}{index}{suffix}@{self.domain}"

    def batch(self, count: int) -> list[str]:
        """Generate a batch of unique aliases.

        Args:
            count: Number of aliases to generate.

        Returns:
            List of unique Gmail aliases.
        """
        return [self.next() for _ in range(count)]
