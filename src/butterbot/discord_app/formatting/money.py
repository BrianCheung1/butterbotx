"""Exact money rendering for Discord responses."""

from __future__ import annotations


def format_money(amount: int) -> str:
    """Format nonnegative integer dollars exactly for Discord presentation."""
    if amount < 0:
        raise ValueError("Money amount cannot be negative.")
    return f"${amount:,}"
