from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest

from butterbot.discord_app.cogs.bank import BankCog
from butterbot.domain.bank import BankAccount, BankOverview
from butterbot.domain.wallet import Wallet


@dataclass
class FakeUser:
    id: int
    name: str


class FakeResponse:
    def __init__(self) -> None:
        self.deferred = False

    async def defer(self) -> None:
        self.deferred = True


class FakeInteraction:
    def __init__(self, user: FakeUser, get_bank_balance: Any) -> None:
        self.user = user
        self.client = SimpleNamespace(get_bank_balance=get_bank_balance)
        self.response = FakeResponse()
        self.edits: list[dict[str, Any]] = []

    async def edit_original_response(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class StubGetBankBalance:
    def __init__(
        self, result: BankOverview | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[int] = []

    async def execute(self, user_id: int) -> BankOverview:
        self.calls.append(user_id)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("Stub bank overview was not configured.")
        return self.result


def callback() -> Any:
    return cast(Any, BankCog.balance.callback)


def overview(user_id: int = 10) -> BankOverview:
    return BankOverview(
        wallet=Wallet(user_id, 8_500),
        account=BankAccount(user_id, 25_000, 1),
    )


@pytest.mark.asyncio
async def test_bank_balance_defaults_to_caller_and_renders_complete_overview() -> None:
    service = StubGetBankBalance(result=overview())
    interaction = FakeInteraction(FakeUser(10, "Butter"), service)

    await callback()(BankCog(), interaction, user=None)

    assert interaction.response.deferred is True
    assert service.calls == [10]
    embed = interaction.edits[0]["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Butter's Bank"
    assert [(field.name, field.value) for field in embed.fields] == [
        ("Wallet Balance", "$8,500"),
        ("Bank Balance", "$25,000"),
        ("Total Capacity", "$150,000"),
        ("Remaining Capacity", "$125,000"),
        ("Bank Level", "1"),
    ]


@pytest.mark.asyncio
async def test_bank_balance_uses_selected_user() -> None:
    service = StubGetBankBalance(result=overview(20))
    interaction = FakeInteraction(FakeUser(10, "Caller"), service)

    await callback()(BankCog(), interaction, user=FakeUser(20, "Friend"))

    assert service.calls == [20]
    assert interaction.edits[0]["embed"].title == "Friend's Bank"


@pytest.mark.asyncio
async def test_bank_balance_maps_internal_failure_to_safe_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = StubGetBankBalance(error=RuntimeError("private database detail"))
    interaction = FakeInteraction(FakeUser(10, "Butter"), service)

    await callback()(BankCog(), interaction, user=None)

    assert interaction.edits == [
        {
            "content": "I couldn't retrieve that bank balance right now. "
            "Please try again later."
        }
    ]
    assert "Failed to retrieve bank balance" in caplog.text
    assert "private database detail" not in interaction.edits[0]["content"]


def test_bank_balance_has_canonical_group_name_and_guild_context() -> None:
    assert cast(Any, BankCog).__cog_group_name__ == "bank"
    command = BankCog.balance
    assert command.name == "balance"
    assert [parameter.name for parameter in command.parameters] == ["user"]
    assert command.parameters[0].required is False
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is False
    assert command.allowed_contexts.private_channel is False
