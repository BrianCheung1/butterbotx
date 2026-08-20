"""Explicit Discord extension registration."""

from __future__ import annotations

from typing import Protocol

# Feature vertical slices are registered in explicit production/dev sets.
CORE_EXTENSION_MODULES: tuple[str, ...] = (
    "butterbot.discord_app.cogs.balance",
    "butterbot.discord_app.cogs.bank",
    "butterbot.discord_app.cogs.daily",
    "butterbot.discord_app.cogs.give",
    "butterbot.discord_app.cogs.mine",
)

DEV_EXTENSION_MODULES: tuple[str, ...] = ("butterbot.discord_app.cogs.set_balance",)


class ExtensionLoader(Protocol):
    """The Discord capability required by the explicit extension loader."""

    async def load_extension(self, name: str) -> None:
        """Load one extension by its explicit module name."""


async def load_extensions(bot: ExtensionLoader, *, enable_dev_commands: bool) -> None:
    """Load the explicit production surface and optionally development commands."""
    extension_modules = CORE_EXTENSION_MODULES
    if enable_dev_commands:
        extension_modules += DEV_EXTENSION_MODULES
    for module_name in extension_modules:
        await bot.load_extension(module_name)
