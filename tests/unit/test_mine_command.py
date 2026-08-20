from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import discord
import pytest

from butterbot.discord_app.cogs.mine import MineCog
from butterbot.domain.mining import (
    InvalidMiningState,
    MiningCooldownActive,
    MiningOutcome,
    MiningResult,
    MiningRewardExceedsWalletLimit,
)


@dataclass
class FakeUser:
    id: int


class FakeResponse:
    def __init__(self) -> None:
        self.deferred = False

    async def defer(self) -> None:
        self.deferred = True


class FakeInteraction:
    def __init__(self, user_id: int) -> None:
        self.user = FakeUser(user_id)
        self.response = FakeResponse()
        self.edits: list[dict[str, Any]] = []

    async def edit_original_response(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class StubMine:
    def __init__(
        self, result: MiningResult | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[int] = []

    async def execute(self, user_id: int) -> MiningResult:
        self.calls.append(user_id)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("Stub result was not configured.")
        return self.result


def callback() -> Any:
    return cast(Any, MineCog.mine.callback)


def successful_result(*, leveled_up: bool = False) -> MiningResult:
    return MiningResult(
        outcome=MiningOutcome("gold", "Rare", 200, 24, 224, 8),
        previous_level=6 if leveled_up else 7,
        level=7,
        xp=440,
        xp_for_next_level=588,
        total_actions=59,
        total_earned=5_663,
        balance=12_345,
        next_mine_at=datetime(2026, 8, 20, 12, 0, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_mine_for_caller_renders_exact_result() -> None:
    interaction = FakeInteraction(42)
    service = StubMine(result=successful_result())
    cog = MineCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.response.deferred is True
    assert service.calls == [42]
    embed = interaction.edits[0]["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "⛏️ Mining Result"
    assert embed.description == "You mined **gold** (Rare)!"
    assert embed.fields[0].value == ("Base: $200\nLevel bonus: $24\nTotal: **$224**")
    assert embed.fields[1].value == "+8 XP\nLevel 7 · 440/588 XP"
    assert embed.fields[2].value == "$12,345"


@pytest.mark.asyncio
async def test_mine_announces_level_up() -> None:
    interaction = FakeInteraction(42)
    cog = MineCog(StubMine(result=successful_result(leveled_up=True)))  # type: ignore[arg-type]

    await callback()(cog, interaction)

    embed = interaction.edits[0]["embed"]
    assert "Level up! You reached level 7." in embed.fields[1].value


@pytest.mark.asyncio
async def test_mine_renders_cooldown_timestamp() -> None:
    next_mine_at = datetime(2026, 8, 20, 12, 0, 30, tzinfo=UTC)
    interaction = FakeInteraction(42)
    cog = MineCog(StubMine(error=MiningCooldownActive(next_mine_at)))  # type: ignore[arg-type]

    await callback()(cog, interaction)

    timestamp = int(next_mine_at.timestamp())
    assert interaction.edits == [
        {"content": f"You're still mining. Try again <t:{timestamp}:R>."}
    ]


@pytest.mark.asyncio
async def test_mine_maps_wallet_limit_to_safe_response() -> None:
    interaction = FakeInteraction(42)
    cog = MineCog(StubMine(error=MiningRewardExceedsWalletLimit()))  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.edits == [
        {"content": "Your wallet cannot hold the mining reward."}
    ]


@pytest.mark.parametrize(
    "error",
    [InvalidMiningState("bad state"), RuntimeError("private detail")],
)
@pytest.mark.asyncio
async def test_mine_hides_and_logs_internal_failures(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    interaction = FakeInteraction(42)
    cog = MineCog(StubMine(error=error))  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.edits == [
        {"content": ("I couldn't complete your mining action. Please try again later.")}
    ]
    assert "mining" in caplog.text.lower()
    assert str(error) not in interaction.edits[0]["content"]


def test_mine_command_has_canonical_name_and_is_guild_only() -> None:
    command = MineCog.mine

    assert command.name == "mine"
    assert command.parameters == []
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is False
    assert command.allowed_contexts.private_channel is False
