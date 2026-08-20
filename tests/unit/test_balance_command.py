from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest

from butterbot.discord_app.cogs.balance import BalanceCog
from butterbot.domain.wallet import Wallet


@dataclass
class FakeUser:
    id: int
    name: str


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class FakeInteraction:
    def __init__(self, user: FakeUser, get_balance: Any) -> None:
        self.user = user
        self.client = SimpleNamespace(get_balance=get_balance)
        self.response = FakeResponse()


class StubGetBalance:
    def __init__(self, wallet: Wallet) -> None:
        self.wallet = wallet
        self.requested_user_ids: list[int] = []

    async def execute(self, user_id: int) -> Wallet:
        self.requested_user_ids.append(user_id)
        return self.wallet


class FailingGetBalance:
    async def execute(self, user_id: int) -> Wallet:
        raise RuntimeError(f"database unavailable for {user_id}")


@pytest.mark.asyncio
async def test_balance_defaults_to_interaction_user() -> None:
    caller = FakeUser(id=10, name="Butter")
    service = StubGetBalance(Wallet(user_id=10, balance=1_999))
    interaction = FakeInteraction(caller, service)
    cog = BalanceCog()

    callback = cast(Any, BalanceCog.balance.callback)
    await callback(cog, interaction, user=None)

    assert service.requested_user_ids == [10]
    assert len(interaction.response.messages) == 1
    message = interaction.response.messages[0]
    embed = message["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Butter's Balance"
    assert embed.description == "💰 $1,999"
    assert embed.color == discord.Color.green()
    assert "ephemeral" not in message


@pytest.mark.asyncio
async def test_balance_uses_selected_user() -> None:
    caller = FakeUser(id=10, name="Butter")
    selected = FakeUser(id=20, name="Friend")
    service = StubGetBalance(Wallet(user_id=20, balance=0))
    interaction = FakeInteraction(caller, service)
    cog = BalanceCog()

    callback = cast(Any, BalanceCog.balance.callback)
    await callback(cog, interaction, user=selected)

    assert service.requested_user_ids == [20]
    assert interaction.response.messages[0]["embed"].title == "Friend's Balance"


@pytest.mark.asyncio
async def test_balance_converts_internal_failure_to_safe_response(caplog: Any) -> None:
    interaction = FakeInteraction(FakeUser(id=10, name="Butter"), FailingGetBalance())
    cog = BalanceCog()

    callback = cast(Any, BalanceCog.balance.callback)
    await callback(cog, interaction, user=None)

    assert interaction.response.messages == [
        {
            "content": "I couldn't retrieve that balance right now. "
            "Please try again later.",
            "ephemeral": True,
        }
    ]
    assert "Failed to retrieve wallet balance" in caplog.text
    assert "database unavailable" not in interaction.response.messages[0]["content"]


def test_balance_supports_guild_dm_private_and_user_install_contexts() -> None:
    command = BalanceCog.balance

    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is True
    assert command.allowed_contexts.private_channel is True
    assert command.allowed_installs is not None
    assert command.allowed_installs.guild is True
    assert command.allowed_installs.user is True
