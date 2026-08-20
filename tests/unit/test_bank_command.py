from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest
from discord import app_commands

from butterbot.discord_app.cogs.bank import BankCog
from butterbot.domain.bank import (
    BankAccount,
    BankCapacityExceeded,
    BankDepositResult,
    BankDepositSelectionConflict,
    BankDepositSelectionRequired,
    BankDepositWouldBeZero,
    BankHasNoCapacity,
    BankOverview,
    InsufficientWalletBalance,
)
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
    def __init__(self, user: FakeUser, **services: Any) -> None:
        self.user = user
        self.client = SimpleNamespace(**services)
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


class StubDepositToBank:
    def __init__(
        self, result: BankDepositResult | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[int, int | None, int | None]] = []

    async def execute(
        self,
        user_id: int,
        *,
        amount: int | None = None,
        percentage: int | None = None,
    ) -> BankDepositResult:
        self.calls.append((user_id, amount, percentage))
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("Stub bank deposit was not configured.")
        return self.result


def callback() -> Any:
    return cast(Any, BankCog.balance.callback)


def deposit_callback() -> Any:
    return cast(Any, BankCog.deposit.callback)


def overview(user_id: int = 10) -> BankOverview:
    return BankOverview(
        wallet=Wallet(user_id, 8_500),
        account=BankAccount(user_id, 25_000, 1),
    )


def deposit_result(*, capped: bool = False) -> BankDepositResult:
    return BankDepositResult(
        overview=BankOverview(
            wallet=Wallet(10, 7_500),
            account=BankAccount(10, 27_500, 1),
        ),
        amount=2_500,
        percentage=50 if capped else None,
        filled_remaining_capacity=capped,
    )


@pytest.mark.asyncio
async def test_bank_balance_defaults_to_caller_and_renders_complete_overview() -> None:
    service = StubGetBankBalance(result=overview())
    interaction = FakeInteraction(FakeUser(10, "Butter"), get_bank_balance=service)

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
    interaction = FakeInteraction(FakeUser(10, "Caller"), get_bank_balance=service)

    await callback()(BankCog(), interaction, user=FakeUser(20, "Friend"))

    assert service.calls == [20]
    assert interaction.edits[0]["embed"].title == "Friend's Bank"


@pytest.mark.asyncio
async def test_bank_balance_maps_internal_failure_to_safe_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = StubGetBankBalance(error=RuntimeError("private database detail"))
    interaction = FakeInteraction(FakeUser(10, "Butter"), get_bank_balance=service)

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


@pytest.mark.asyncio
async def test_bank_deposit_passes_exact_amount_for_caller_and_renders_result() -> None:
    service = StubDepositToBank(result=deposit_result())
    interaction = FakeInteraction(FakeUser(10, "Butter"), deposit_to_bank=service)

    await deposit_callback()(BankCog(), interaction, amount=2_500, percentage=None)

    assert interaction.response.deferred is True
    assert service.calls == [(10, 2_500, None)]
    embed = interaction.edits[0]["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Bank Deposit"
    assert embed.description == "Deposited $2,500 into your bank."
    assert [(field.name, field.value) for field in embed.fields] == [
        ("Wallet Balance", "$7,500"),
        ("Bank Balance", "$27,500"),
        ("Remaining Capacity", "$122,500"),
    ]


@pytest.mark.asyncio
async def test_bank_deposit_passes_choice_value_and_reports_capacity_cap() -> None:
    service = StubDepositToBank(result=deposit_result(capped=True))
    interaction = FakeInteraction(FakeUser(10, "Butter"), deposit_to_bank=service)
    choice = app_commands.Choice(name="50%", value=50)

    await deposit_callback()(BankCog(), interaction, amount=None, percentage=choice)

    assert service.calls == [(10, None, 50)]
    assert interaction.edits[0]["embed"].description == (
        "Deposited $2,500 into your bank. This filled your remaining bank capacity."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            BankDepositSelectionRequired("required"),
            "Choose either an exact amount or a percentage to deposit.",
        ),
        (
            BankDepositSelectionConflict("conflict"),
            "Choose an exact amount or a percentage, not both.",
        ),
        (
            BankDepositWouldBeZero("zero"),
            "That percentage rounds down to $0, so nothing was deposited.",
        ),
        (
            BankHasNoCapacity("full"),
            "Your bank is full and cannot accept another deposit.",
        ),
        (
            BankCapacityExceeded(1_000),
            "That amount exceeds your remaining bank capacity of $1,000.",
        ),
        (
            InsufficientWalletBalance(500),
            "You don't have enough money in your wallet. Available: $500.",
        ),
    ],
)
async def test_bank_deposit_maps_expected_errors_safely(
    error: Exception, message: str
) -> None:
    service = StubDepositToBank(error=error)
    interaction = FakeInteraction(FakeUser(10, "Butter"), deposit_to_bank=service)

    await deposit_callback()(BankCog(), interaction, amount=1, percentage=None)

    assert interaction.edits == [{"content": message}]


@pytest.mark.asyncio
async def test_bank_deposit_maps_internal_failure_without_exposing_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = StubDepositToBank(error=RuntimeError("private database detail"))
    interaction = FakeInteraction(FakeUser(10, "Butter"), deposit_to_bank=service)

    await deposit_callback()(BankCog(), interaction, amount=1, percentage=None)

    assert interaction.edits == [
        {"content": "I couldn't complete that bank deposit. Please try again later."}
    ]
    assert "Failed to deposit money into bank" in caplog.text
    assert "private database detail" not in interaction.edits[0]["content"]


def test_bank_deposit_has_canonical_parameters_choices_and_guild_context() -> None:
    command = BankCog.deposit
    assert command.name == "deposit"
    assert [parameter.name for parameter in command.parameters] == [
        "amount",
        "percentage",
    ]
    assert all(parameter.required is False for parameter in command.parameters)
    assert command.parameters[0].min_value == 1
    assert [choice.value for choice in command.parameters[1].choices] == [
        25,
        50,
        75,
        100,
    ]
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is False
