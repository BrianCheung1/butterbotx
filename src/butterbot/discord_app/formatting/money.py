"""Exact money rendering for Discord responses."""

from __future__ import annotations


def format_money(amount_cents: int) -> str:
    """Format nonnegative integer cents exactly for Discord presentation."""
    if amount_cents < 0:
        raise ValueError("Money amount cannot be negative.")

    dollars, cents = divmod(amount_cents, 100)
    if cents == 0:
        return f"${dollars:,}"
    return f"${dollars:,}.{cents:02d}"
