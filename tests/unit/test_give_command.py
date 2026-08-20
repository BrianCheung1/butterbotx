from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from butterbot.discord_app.cogs.give import GiveCog
from butterbot.domain.money_transfer import (
    InsufficientFunds,
    TransferResult,
    WalletLimitExceeded,
)
from butterbot.domain.wallet import Wallet


@dataclass
class FakeUser:
    id: int
    name: str
    mention: str
    bot: bool = False


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.deferred = False

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    async def defer(self) -> None:
        self.deferred = True


class FakeInteraction:
    def __init__(self, user: FakeUser) -> None:
        self.user = user
        self.response = FakeResponse()
        self.edits: list[dict[str, Any]] = []

    async def edit_original_response(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class StubTransferMoney:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, int, int]] = []

    async def execute(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        self.calls.append((sender_id, recipient_id, amount))
        if self.error is not None:
            raise self.error
        return TransferResult(
            Wallet(sender_id, 0), Wallet(recipient_id, amount), amount
        )


def callback() -> Any:
    return cast(Any, GiveCog.give.callback)


@pytest.mark.asyncio
async def test_give_transfers_whole_dollars_and_renders_success() -> None:
    sender = FakeUser(1, "Sender", "<@1>")
    recipient = FakeUser(2, "Recipient", "<@2>")
    interaction = FakeInteraction(sender)
    service = StubTransferMoney()
    cog = GiveCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction, user=recipient, amount=1_999)

    assert interaction.response.deferred is True
    assert service.calls == [(1, 2, 1_999)]
    assert interaction.edits == [
        {"content": "✅ You've successfully given $1,999 to <@2>!"}
    ]


@pytest.mark.parametrize(
    ("recipient", "expected"),
    [
        (
            FakeUser(1, "Sender", "<@1>"),
            "❌ You can't perform this action on yourself!",
        ),
        (
            FakeUser(2, "Bot", "<@2>", bot=True),
            "❌ You can't perform this action on bots!",
        ),
    ],
)
@pytest.mark.asyncio
async def test_give_rejects_invalid_discord_target_before_service(
    recipient: FakeUser, expected: str
) -> None:
    interaction = FakeInteraction(FakeUser(1, "Sender", "<@1>"))
    service = StubTransferMoney()
    cog = GiveCog(service)  # type: ignore[arg-type]

    await callback()(cog, interaction, user=recipient, amount=100)

    assert interaction.response.messages == [{"content": expected, "ephemeral": True}]
    assert interaction.response.deferred is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_give_renders_insufficient_balance_safely() -> None:
    interaction = FakeInteraction(FakeUser(1, "Sender", "<@1>"))
    service = StubTransferMoney(InsufficientFunds(123))
    cog = GiveCog(service)  # type: ignore[arg-type]

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Recipient", "<@2>"),
        amount=200,
    )

    assert interaction.edits == [
        {
            "content": "You don't have enough balance for this action. "
            "Current balance is $123."
        }
    ]


@pytest.mark.asyncio
async def test_give_renders_recipient_limit_safely() -> None:
    interaction = FakeInteraction(FakeUser(1, "Sender", "<@1>"))
    service = StubTransferMoney(WalletLimitExceeded())
    cog = GiveCog(service)  # type: ignore[arg-type]

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Recipient", "<@2>"),
        amount=100,
    )

    assert interaction.edits == [
        {"content": "That wallet cannot hold the transfer amount."}
    ]


@pytest.mark.asyncio
async def test_give_hides_and_logs_unexpected_error(caplog: Any) -> None:
    interaction = FakeInteraction(FakeUser(1, "Sender", "<@1>"))
    service = StubTransferMoney(RuntimeError("private database detail"))
    cog = GiveCog(service)  # type: ignore[arg-type]

    await callback()(
        cog,
        interaction,
        user=FakeUser(2, "Recipient", "<@2>"),
        amount=100,
    )

    assert interaction.edits == [
        {"content": "I couldn't complete that transfer. Please try again later."}
    ]
    assert "Failed to transfer wallet money" in caplog.text
    assert "private database detail" not in interaction.edits[0]["content"]


def test_give_command_name_and_contexts_are_canonical() -> None:
    command = GiveCog.give

    assert command.name == "give"
    amount_parameter = next(
        parameter for parameter in command.parameters if parameter.name == "amount"
    )
    assert amount_parameter.min_value == 1
    assert command.allowed_contexts is not None
    assert command.allowed_contexts.guild is True
    assert command.allowed_contexts.dm_channel is True
    assert command.allowed_contexts.private_channel is True
    assert command.allowed_installs is not None
    assert command.allowed_installs.guild is True
    assert command.allowed_installs.user is True
