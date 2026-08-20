from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from butterbot.config import ConfigurationError
from butterbot.discord_app.cogs.set_balance import SetBalanceCog, setup
from butterbot.domain.wallet import Wallet


@dataclass
class FakeUser:
    id: int
    name: str
    mention: str


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.deferred: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    async def defer(self, **kwargs: Any) -> None:
        self.deferred.append(kwargs)


class FakeInteraction:
    def __init__(self, user: FakeUser, guild_id: int | None, set_balance: Any) -> None:
        self.user = user
        self.guild_id = guild_id
        self.client = SimpleNamespace(set_balance=set_balance)
        self.response = FakeResponse()
        self.edits: list[dict[str, Any]] = []

    async def edit_original_response(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class StubSetBalance:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, int]] = []

    async def execute(self, user_id: int, amount: int) -> Wallet:
        self.calls.append((user_id, amount))
        if self.error is not None:
            raise self.error
        return Wallet(user_id, amount)


def callback() -> Any:
    return cast(Any, SetBalanceCog.set_balance.callback)


@pytest.mark.asyncio
async def test_set_balance_owner_sets_exact_whole_dollar_balance() -> None:
    service = StubSetBalance()
    interaction = FakeInteraction(
        FakeUser(1, "Owner", "<@1>"), guild_id=10, set_balance=service
    )
    target = FakeUser(2, "Target", "<@2>")
    cog = SetBalanceCog(owner_id=1, dev_guild_id=10)

    await callback()(cog, interaction, user=target, amount=1_999)

    assert service.calls == [(2, 1_999)]
    assert interaction.response.deferred == []
    assert interaction.response.messages == [
        {"content": "✅ Set <@2>'s balance to $1,999."}
    ]


@pytest.mark.asyncio
async def test_set_balance_accepts_zero() -> None:
    service = StubSetBalance()
    interaction = FakeInteraction(
        FakeUser(1, "Owner", "<@1>"), guild_id=10, set_balance=service
    )
    cog = SetBalanceCog(owner_id=1, dev_guild_id=10)

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Target", "<@2>"),
        amount=0,
    )

    assert service.calls == [(2, 0)]
    assert interaction.response.messages == [
        {"content": "✅ Set <@2>'s balance to $0."}
    ]


@pytest.mark.parametrize(
    ("caller_id", "guild_id", "expected"),
    [
        (2, 10, "You are not authorized to use this command."),
        (1, 20, "This command is only available in the development server."),
        (1, None, "This command is only available in the development server."),
    ],
)
@pytest.mark.asyncio
async def test_set_balance_rejects_unauthorized_context_before_service(
    caller_id: int, guild_id: int | None, expected: str
) -> None:
    service = StubSetBalance()
    interaction = FakeInteraction(
        FakeUser(caller_id, "Caller", f"<@{caller_id}>"),
        guild_id=guild_id,
        set_balance=service,
    )
    cog = SetBalanceCog(owner_id=1, dev_guild_id=10)

    await callback()(
        cog,
        interaction,
        user=FakeUser(3, "Target", "<@3>"),
        amount=100,
    )

    assert service.calls == []
    assert interaction.response.messages == [{"content": expected, "ephemeral": True}]
    assert interaction.response.deferred == []


@pytest.mark.asyncio
async def test_set_balance_maps_invalid_amount_to_safe_response() -> None:
    service = StubSetBalance(ValueError("internal validation detail"))
    interaction = FakeInteraction(
        FakeUser(1, "Owner", "<@1>"), guild_id=10, set_balance=service
    )
    cog = SetBalanceCog(owner_id=1, dev_guild_id=10)

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Target", "<@2>"),
        amount=100,
    )

    assert interaction.response.messages == [
        {
            "content": "That balance is outside the supported range.",
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_set_balance_hides_and_logs_unexpected_error(caplog: Any) -> None:
    service = StubSetBalance(RuntimeError("private database detail"))
    interaction = FakeInteraction(
        FakeUser(1, "Owner", "<@1>"), guild_id=10, set_balance=service
    )
    cog = SetBalanceCog(owner_id=1, dev_guild_id=10)

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Target", "<@2>"),
        amount=100,
    )

    assert interaction.response.messages == [
        {
            "content": "I couldn't set that balance right now. Please try again later.",
            "ephemeral": True,
        }
    ]
    assert "Failed to set wallet balance" in caplog.text
    assert "private database detail" not in interaction.response.messages[0]["content"]


def test_set_balance_command_contract_is_canonical() -> None:
    command = SetBalanceCog.set_balance

    assert command.name == "set-balance"
    parameters = {parameter.name: parameter for parameter in command.parameters}
    assert parameters["user"].required is True
    assert parameters["amount"].required is True
    assert parameters["amount"].min_value == 0
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is False
    assert command.allowed_contexts.private_channel is False
    assert command.allowed_installs is not None
    assert command.allowed_installs.guild is True
    assert command.allowed_installs.user is False


class FakeSetBalanceBot:
    def __init__(self, dev_guild_id: int | None) -> None:
        self.owner_id = 1
        self.dev_guild_id = dev_guild_id
        self.registrations: list[tuple[Any, Any]] = []

    async def add_cog(self, cog: Any, /, **kwargs: Any) -> None:
        self.registrations.append((cog, kwargs.get("guild")))


@pytest.mark.asyncio
async def test_set_balance_registers_only_in_development_guild() -> None:
    bot = FakeSetBalanceBot(dev_guild_id=10)

    await setup(bot)  # type: ignore[arg-type]

    assert len(bot.registrations) == 1
    cog, guild = bot.registrations[0]
    assert isinstance(cog, SetBalanceCog)
    assert guild.id == 10


@pytest.mark.asyncio
async def test_set_balance_feature_requires_development_guild_at_composition() -> None:
    bot = FakeSetBalanceBot(dev_guild_id=None)

    with pytest.raises(ConfigurationError, match=r"DEV_GUILD_ID.*set-balance"):
        await setup(bot)  # type: ignore[arg-type]

    assert bot.registrations == []
