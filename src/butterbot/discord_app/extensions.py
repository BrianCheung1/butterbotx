"""Explicit Discord extension registration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

# Feature vertical slices are registered here deliberately.
EXTENSION_MODULES: tuple[str, ...] = (
    "butterbot.discord_app.cogs.balance",
    "butterbot.discord_app.cogs.give",
)


class ExtensionLoader(Protocol):
    """The Discord capability required by the explicit extension loader."""

    async def load_extension(self, name: str) -> None:
        """Load one extension by its explicit module name."""


async def load_extensions(
    bot: ExtensionLoader, extension_modules: Iterable[str] = EXTENSION_MODULES
) -> None:
    """Load the explicitly registered Discord extensions in the given order."""
    for module_name in extension_modules:
        await bot.load_extension(module_name)
