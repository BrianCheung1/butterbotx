from __future__ import annotations

import pytest

from butterbot.discord_app.extensions import EXTENSION_MODULES, load_extensions


class FakeBot:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    async def load_extension(self, name: str) -> None:
        self.loaded.append(name)


@pytest.mark.asyncio
async def test_extensions_are_empty_until_a_feature_registers_one() -> None:
    bot = FakeBot()

    await load_extensions(bot)  # type: ignore[arg-type]

    assert EXTENSION_MODULES == ()
    assert bot.loaded == []


@pytest.mark.asyncio
async def test_extensions_load_in_explicit_order() -> None:
    bot = FakeBot()

    await load_extensions(
        bot, ("butterbot.features.first", "butterbot.features.second")
    )  # type: ignore[arg-type]

    assert bot.loaded == ["butterbot.features.first", "butterbot.features.second"]
