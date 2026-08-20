"""Discord presentation for wallet transfers."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.transfer_money import TransferMoney
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.money_transfer import (
    InsufficientFunds,
    InvalidTransfer,
    WalletLimitExceeded,
)

logger = logging.getLogger(__name__)


class GiveCog(commands.Cog):
    """Expose atomic wallet transfers as the `/give` command."""

    def __init__(self, transfer_money: TransferMoney) -> None:
        self._transfer_money = transfer_money

    @app_commands.command(name="give", description="Give another player money.")
    @app_commands.describe(
        user="The user to give money to.", amount="The amount to give."
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, None],
    ) -> None:
        """Transfer a positive whole-dollar amount to another user."""
        if interaction.user.id == user.id:
            await interaction.response.send_message(
                content="❌ You can't perform this action on yourself!",
                ephemeral=True,
            )
            return
        if user.bot:
            await interaction.response.send_message(
                content="❌ You can't perform this action on bots!", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await self._transfer_money.execute(
                sender_id=interaction.user.id,
                recipient_id=user.id,
                amount=amount,
            )
        except InsufficientFunds as error:
            await interaction.edit_original_response(
                content=(
                    "You don't have enough balance for this action. "
                    f"Current balance is {format_money(error.available_balance)}."
                )
            )
            return
        except WalletLimitExceeded:
            await interaction.edit_original_response(
                content="That wallet cannot hold the transfer amount."
            )
            return
        except InvalidTransfer:
            await interaction.edit_original_response(
                content="That transfer is invalid. Please check the amount and users."
            )
            return
        except Exception:
            logger.exception(
                "Failed to transfer wallet money.",
                extra={
                    "sender_id": interaction.user.id,
                    "recipient_id": user.id,
                    "amount": amount,
                },
            )
            await interaction.edit_original_response(
                content="I couldn't complete that transfer. Please try again later."
            )
            return

        logger.info(
            "Wallet transfer completed.",
            extra={
                "sender_id": interaction.user.id,
                "recipient_id": user.id,
                "amount": amount,
            },
        )
        await interaction.edit_original_response(
            content=(
                f"✅ You've successfully given {format_money(amount)} "
                f"to {user.mention}!"
            )
        )


class GiveBot(Protocol):
    """Bot capabilities required to register the give cog."""

    transfer_money: TransferMoney

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register the explicitly composed give command."""
    give_bot = cast(GiveBot, bot)
    await give_bot.add_cog(GiveCog(give_bot.transfer_money))
