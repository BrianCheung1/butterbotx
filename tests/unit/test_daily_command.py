from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

import discord
import pytest

from butterbot.discord_app.cogs.daily import DailyCog
from butterbot.domain.daily_reward import (
    DailyAlreadyClaimed,
    DailyClaimResult,
    DailyReward,
    DailyRewardExceedsWalletLimit,
    InvalidDailyClaimState,
)
from butterbot.domain.wallet import Wallet


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


class StubClaimDaily:
    def __init__(
        self, result: DailyClaimResult | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[int] = []

    async def execute(self, user_id: int) -> DailyClaimResult:
        self.calls.append(user_id)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("Stub result was not configured.")
        return self.result


def callback() -> Any:
    return cast(Any, DailyCog.daily.callback)


def successful_result() -> DailyClaimResult:
    return DailyClaimResult(
        wallet=Wallet(42, 12_345),
        reward=DailyReward(base=1_000, bonus=2_000, total=3_000, streak=3),
        claim_date=date(2026, 8, 19),
    )


@pytest.mark.asyncio
async def test_daily_claims_for_caller_and_renders_exact_embed() -> None:
    interaction = FakeInteraction(42)
    service = StubClaimDaily(result=successful_result())
    cog = DailyCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.response.deferred is True
    assert service.calls == [42]
    embed = interaction.edits[0]["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Daily Reward"
    assert embed.description == (
        "Claimed your daily reward of $3,000!\n"
        "Daily base: $1,000\n"
        "Bonus: $2,000\n"
        "Streak: 3 day(s)\n"
        "Your new balance is $12,345."
    )
    assert embed.color == discord.Color.green()


@pytest.mark.asyncio
async def test_daily_renders_next_utc_midnight_when_already_claimed() -> None:
    next_claim_at = datetime(2026, 8, 20, tzinfo=UTC)
    interaction = FakeInteraction(42)
    service = StubClaimDaily(error=DailyAlreadyClaimed(next_claim_at))
    cog = DailyCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction)

    timestamp = int(next_claim_at.timestamp())
    assert interaction.edits == [
        {
            "content": "🕒 You've already claimed your daily today! "
            f"Come back <t:{timestamp}:R> (at <t:{timestamp}:t> your time)."
        }
    ]


@pytest.mark.asyncio
async def test_daily_maps_wallet_limit_to_safe_response() -> None:
    interaction = FakeInteraction(42)
    service = StubClaimDaily(error=DailyRewardExceedsWalletLimit())
    cog = DailyCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.edits == [
        {"content": "Your wallet cannot hold the daily reward."}
    ]


@pytest.mark.parametrize(
    "error",
    [InvalidDailyClaimState("bad persisted state"), RuntimeError("private detail")],
)
@pytest.mark.asyncio
async def test_daily_hides_and_logs_internal_failures(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    interaction = FakeInteraction(42)
    service = StubClaimDaily(error=error)
    cog = DailyCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction)

    assert interaction.edits == [
        {"content": "I couldn't complete your daily claim. Please try again later."}
    ]
    assert "daily" in caplog.text.lower()
    assert str(error) not in interaction.edits[0]["content"]


def test_daily_command_has_canonical_name_and_contexts() -> None:
    command = DailyCog.daily

    assert command.name == "daily"
    assert command.parameters == []
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is True
    assert command.allowed_contexts.private_channel is True
    assert command.allowed_installs is not None
    assert command.allowed_installs.guild is True
    assert command.allowed_installs.user is True
