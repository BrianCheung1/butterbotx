from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import discord
import pytest

from butterbot.discord_app.cogs.mine import (
    FIRST_STAGE_SECONDS,
    MINE_AGAIN_TIMEOUT_SECONDS,
    SECOND_STAGE_SECONDS,
    MineAgainView,
    MineCog,
)
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
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.deferred = False
        self.messages: list[dict[str, Any]] = []

    async def defer(self) -> None:
        self.events.append("defer")
        self.deferred = True

    async def send_message(self, content: str, *, ephemeral: bool) -> None:
        self.events.append("response")
        self.messages.append({"content": content, "ephemeral": ephemeral})


class FakeFollowup:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.messages: list[dict[str, Any]] = []

    async def send(self, content: str, *, ephemeral: bool) -> None:
        self.events.append("followup")
        self.messages.append({"content": content, "ephemeral": ephemeral})


class FakeMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, Any]] = []

    async def edit(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class FakeInteraction:
    def __init__(self, user_id: int, *, fail_edits: set[int] | None = None) -> None:
        self.user = FakeUser(user_id)
        self.events: list[str] = []
        self.response = FakeResponse(self.events)
        self.followup = FakeFollowup(self.events)
        self.edits: list[dict[str, Any]] = []
        self.edit_attempts = 0
        self.fail_edits = fail_edits or set()
        self.message = FakeMessage()

    async def edit_original_response(self, **kwargs: Any) -> FakeMessage:
        self.edit_attempts += 1
        self.events.append(f"edit:{self.edit_attempts}")
        if self.edit_attempts in self.fail_edits:
            raise RuntimeError("message edit failed")
        self.edits.append(kwargs)
        return self.message


class StubMine:
    def __init__(self, outcomes: list[MiningResult | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[int] = []
        self.events: list[str] | None = None

    async def execute(self, user_id: int) -> MiningResult:
        self.calls.append(user_id)
        if self.events is not None:
            self.events.append("execute")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class BlockingMine:
    def __init__(self, result: MiningResult) -> None:
        self.result = result
        self.calls: list[int] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, user_id: int) -> MiningResult:
        self.calls.append(user_id)
        self.started.set()
        await self.release.wait()
        return self.result


class RecordingDelay:
    def __init__(self, events: list[str] | None = None) -> None:
        self.calls: list[float] = []
        self.events = events

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self.events is not None:
            self.events.append(f"delay:{seconds}")


def command_callback() -> Any:
    return cast(Any, MineCog.mine.callback)


async def click(view: MineAgainView, interaction: FakeInteraction) -> None:
    await cast(Any, view.mine_again.callback)(interaction)


def mining_result(
    *,
    resource: str = "gold",
    balance: int = 12_345,
    next_second: int = 30,
    leveled_up: bool = False,
) -> MiningResult:
    return MiningResult(
        outcome=MiningOutcome(resource, "Rare", 200, 24, 224, 8),
        previous_level=6 if leveled_up else 7,
        level=7,
        xp=440,
        xp_for_next_level=588,
        total_actions=59,
        total_earned=5_663,
        balance=balance,
        next_mine_at=datetime(2026, 8, 20, 12, 0, next_second, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_command_commits_before_three_fast_presentation_stages() -> None:
    interaction = FakeInteraction(42)
    service = StubMine([mining_result()])
    service.events = interaction.events
    delay = RecordingDelay(interaction.events)
    cog = MineCog(service, delay)  # type: ignore[arg-type]

    await command_callback()(cog, interaction)

    assert service.calls == [42]
    assert interaction.events == [
        "defer",
        "execute",
        "edit:1",
        f"delay:{FIRST_STAGE_SECONDS}",
        "edit:2",
        f"delay:{SECOND_STAGE_SECONDS}",
        "edit:3",
    ]
    assert delay.calls == [FIRST_STAGE_SECONDS, SECOND_STAGE_SECONDS]
    assert len(interaction.edits) == 3
    for stage in interaction.edits[:2]:
        embed = stage["embed"]
        assert "gold" not in (embed.description or "")
        assert embed.fields == []

    final = interaction.edits[2]
    embed = final["embed"]
    assert embed.title == "⛏️ Mining Result"
    assert embed.description == "You mined **gold** (Rare)!"
    assert embed.fields[0].value == ("Base: $200\nLevel bonus: $24\nTotal: **$224**")
    assert embed.fields[1].value == "+8 XP\nLevel 7 · 440/588 XP"
    assert embed.fields[2].value == "$12,345"
    timestamp = int(mining_result().next_mine_at.timestamp())
    assert embed.fields[3].value == f"<t:{timestamp}:R>"
    assert isinstance(final["view"], MineAgainView)
    assert final["view"].timeout == MINE_AGAIN_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_command_announces_level_up_in_final_stage() -> None:
    interaction = FakeInteraction(42)
    cog = MineCog(
        cast(Any, StubMine([mining_result(leveled_up=True)])), RecordingDelay()
    )

    await command_callback()(cog, interaction)

    final_embed = interaction.edits[-1]["embed"]
    assert "Level up! You reached level 7." in final_embed.fields[1].value


@pytest.mark.asyncio
async def test_command_cooldown_skips_animation() -> None:
    next_mine_at = datetime(2026, 8, 20, 12, 0, 30, tzinfo=UTC)
    interaction = FakeInteraction(42)
    delay = RecordingDelay()
    service = StubMine([MiningCooldownActive(next_mine_at)])
    cog = MineCog(service, delay)  # type: ignore[arg-type]

    await command_callback()(cog, interaction)

    timestamp = int(next_mine_at.timestamp())
    assert interaction.edits == [
        {"content": f"You're still mining. Try again <t:{timestamp}:R>."}
    ]
    assert delay.calls == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            MiningRewardExceedsWalletLimit(),
            "Your wallet cannot hold the mining reward.",
        ),
        (
            InvalidMiningState("bad state"),
            "I couldn't complete your mining action. Please try again later.",
        ),
        (
            RuntimeError("private detail"),
            "I couldn't complete your mining action. Please try again later.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_command_maps_service_errors_without_animation(
    error: Exception, expected: str
) -> None:
    interaction = FakeInteraction(42)
    delay = RecordingDelay()
    cog = MineCog(StubMine([error]), delay)  # type: ignore[arg-type]

    await command_callback()(cog, interaction)

    assert interaction.edits == [{"content": expected}]
    assert delay.calls == []


@pytest.mark.asyncio
async def test_view_rejects_other_users_ephemerally() -> None:
    service = StubMine([mining_result()])
    view = MineAgainView(service, owner_id=42, delay=RecordingDelay())  # type: ignore[arg-type]
    interaction = FakeInteraction(99)

    allowed = await view.interaction_check(interaction)  # type: ignore[arg-type]

    assert allowed is False
    assert service.calls == []
    assert interaction.response.messages == [
        {
            "content": "Only the miner who started this session can use Mine Again.",
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_early_mine_again_is_ephemeral_and_preserves_public_result() -> None:
    next_mine_at = datetime(2026, 8, 20, 12, 0, 30, tzinfo=UTC)
    service = StubMine([MiningCooldownActive(next_mine_at)])
    view = MineAgainView(service, owner_id=42, delay=RecordingDelay())  # type: ignore[arg-type]
    interaction = FakeInteraction(42)

    await click(view, interaction)

    timestamp = int(next_mine_at.timestamp())
    assert interaction.response.deferred is True
    assert service.calls == [42]
    assert interaction.edits == []
    assert interaction.followup.messages == [
        {
            "content": f"You're still mining. Try again <t:{timestamp}:R>.",
            "ephemeral": True,
        }
    ]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            MiningRewardExceedsWalletLimit(),
            "Your wallet cannot hold the mining reward.",
        ),
        (
            InvalidMiningState("bad state"),
            "I couldn't complete your mining action. Please try again later.",
        ),
        (
            RuntimeError("private detail"),
            "I couldn't complete your mining action. Please try again later.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_mine_again_errors_are_ephemeral_and_preserve_public_result(
    error: Exception, expected: str
) -> None:
    service = StubMine([error])
    view = MineAgainView(service, owner_id=42, delay=RecordingDelay())  # type: ignore[arg-type]
    interaction = FakeInteraction(42)

    await click(view, interaction)

    assert service.calls == [42]
    assert interaction.edits == []
    assert interaction.followup.messages == [{"content": expected, "ephemeral": True}]


@pytest.mark.asyncio
async def test_eligible_mine_again_reuses_service_view_and_message() -> None:
    first = mining_result()
    second = mining_result(resource="diamond", balance=12_569, next_second=59)
    service = StubMine([first, second])
    delay = RecordingDelay()
    command_interaction = FakeInteraction(42)
    cog = MineCog(service, delay)  # type: ignore[arg-type]
    await command_callback()(cog, command_interaction)
    view = command_interaction.edits[-1]["view"]
    button_interaction = FakeInteraction(42)

    await click(view, button_interaction)

    assert service.calls == [42, 42]
    assert button_interaction.response.deferred is True
    assert len(button_interaction.edits) == 3
    assert all(edit["view"] is view for edit in button_interaction.edits)
    assert button_interaction.edits[-1]["embed"].description == (
        "You mined **diamond** (Rare)!"
    )
    assert view.message is button_interaction.message


@pytest.mark.asyncio
async def test_rapid_double_click_calls_mine_only_once() -> None:
    service = BlockingMine(mining_result())
    view = MineAgainView(service, owner_id=42, delay=RecordingDelay())  # type: ignore[arg-type]
    first_interaction = FakeInteraction(42)
    second_interaction = FakeInteraction(42)

    first_click = asyncio.create_task(click(view, first_interaction))
    await service.started.wait()
    await click(view, second_interaction)
    service.release.set()
    await first_click

    assert service.calls == [42]
    assert second_interaction.response.messages == [
        {
            "content": "A mining action is already being processed.",
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_view_clears_busy_flag_after_service_failure() -> None:
    service = StubMine([RuntimeError("failure"), mining_result()])
    view = MineAgainView(service, owner_id=42, delay=RecordingDelay())  # type: ignore[arg-type]

    await click(view, FakeInteraction(42))
    second = FakeInteraction(42)
    await click(view, second)

    assert service.calls == [42, 42]
    assert len(second.edits) == 3


@pytest.mark.asyncio
async def test_timeout_disables_button_with_best_effort_edit() -> None:
    view = MineAgainView(
        cast(Any, StubMine([mining_result()])),
        owner_id=42,
        delay=RecordingDelay(),
    )
    message = FakeMessage()
    view.message = cast(Any, message)

    await view.on_timeout()

    assert view.timeout == 300
    assert all(
        item.disabled for item in view.children if isinstance(item, discord.ui.Button)
    )
    assert message.edits == [{"view": view}]


@pytest.mark.asyncio
async def test_animation_edit_failure_reveals_without_retrying_mine(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = FakeInteraction(42, fail_edits={1})
    service = StubMine([mining_result()])
    cog = MineCog(service, RecordingDelay())  # type: ignore[arg-type]

    await command_callback()(cog, interaction)

    assert service.calls == [42]
    assert interaction.edit_attempts == 2
    assert interaction.edits[-1]["embed"].title == "⛏️ Mining Result"
    assert "after the action committed" in caplog.text


@pytest.mark.asyncio
async def test_final_edit_failure_does_not_retry_mine(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = FakeInteraction(42, fail_edits={3})
    service = StubMine([mining_result()])
    cog = MineCog(service, RecordingDelay())  # type: ignore[arg-type]

    await command_callback()(cog, interaction)

    assert service.calls == [42]
    assert interaction.edit_attempts == 3
    assert "committed mining result" in caplog.text


def test_mine_command_has_canonical_name_and_is_guild_only() -> None:
    command = MineCog.mine

    assert command.name == "mine"
    assert command.parameters == []
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is False
    assert command.allowed_contexts.private_channel is False
