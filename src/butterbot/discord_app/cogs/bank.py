"""Discord presentation for protected bank balances."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.get_bank_balance import GetBankBalance
from butterbot.discord_app.formatting.money import format_money

logger = logging.getLogger(__name__)


class BankCog(
    commands.GroupCog, group_name="bank", group_description="Manage your bank."
):
    """Expose the capacity-limited protected bank command family."""

    @app_commands.command(name="balance", description="Check a bank balance.")
    @app_commands.describe(user="The user whose bank balance should be shown.")
    @app_commands.guild_only()
    async def balance(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        """Show liquid wallet money and protected bank state."""
        selected_user = user or interaction.user
        await interaction.response.defer()
        try:
            overview = await _get_bank_balance(interaction).execute(selected_user.id)
        except Exception:
            logger.exception(
                "Failed to retrieve bank balance.",
                extra={"target_user_id": selected_user.id},
            )
            await interaction.edit_original_response(
                content=(
                    "I couldn't retrieve that bank balance right now. "
                    "Please try again later."
                )
            )
            return

        account = overview.account
        embed = discord.Embed(
            title=f"{selected_user.name}'s Bank",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Wallet Balance",
            value=format_money(overview.wallet.balance),
            inline=True,
        )
        embed.add_field(
            name="Bank Balance",
            value=format_money(account.balance),
            inline=True,
        )
        embed.add_field(
            name="Total Capacity",
            value=format_money(account.capacity),
            inline=True,
        )
        embed.add_field(
            name="Remaining Capacity",
            value=format_money(account.remaining_capacity),
            inline=True,
        )
        embed.add_field(name="Bank Level", value=str(account.level), inline=True)
        await interaction.edit_original_response(embed=embed)


class BankRuntime(Protocol):
    """Runtime service required when a bank command executes."""

    get_bank_balance: GetBankBalance


def _get_bank_balance(interaction: discord.Interaction) -> GetBankBalance:
    """Resolve the bank lookup use case only at command execution time."""
    return cast(BankRuntime, interaction.client).get_bank_balance


class BankBot(Protocol):
    """Bot capability required to register the bank command group."""

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register bank command metadata without resolving runtime services."""
    bank_bot = cast(BankBot, bot)
    await bank_bot.add_cog(BankCog())
