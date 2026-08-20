from __future__ import annotations

import pytest

from butterbot.discord_app.extensions import (
    CORE_EXTENSION_MODULES,
    DEV_EXTENSION_MODULES,
    load_extensions,
)


class FakeBot:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    async def load_extension(self, name: str) -> None:
        self.loaded.append(name)


@pytest.mark.asyncio
async def test_production_loads_only_core_extensions() -> None:
    bot = FakeBot()

    await load_extensions(bot, enable_dev_commands=False)  # type: ignore[arg-type]

    assert CORE_EXTENSION_MODULES == (
        "butterbot.discord_app.cogs.balance",
        "butterbot.discord_app.cogs.daily",
        "butterbot.discord_app.cogs.give",
    )
    assert bot.loaded == [
        "butterbot.discord_app.cogs.balance",
        "butterbot.discord_app.cogs.daily",
        "butterbot.discord_app.cogs.give",
    ]


@pytest.mark.asyncio
async def test_development_commands_load_after_core_extensions() -> None:
    bot = FakeBot()

    await load_extensions(bot, enable_dev_commands=True)  # type: ignore[arg-type]

    assert DEV_EXTENSION_MODULES == ("butterbot.discord_app.cogs.set_balance",)
    assert bot.loaded == [
        "butterbot.discord_app.cogs.balance",
        "butterbot.discord_app.cogs.daily",
        "butterbot.discord_app.cogs.give",
        "butterbot.discord_app.cogs.set_balance",
    ]
