"""Persistence protocol for bank-owned operations."""

from __future__ import annotations

from typing import Protocol

from butterbot.domain.bank import BankOverview


class BankRepository(Protocol):
    """Persist bank state across the tables required by bank invariants."""

    async def get_or_create_overview(self, user_id: int) -> BankOverview:
        """Return liquid and protected balances, creating defaults if needed."""
        ...
