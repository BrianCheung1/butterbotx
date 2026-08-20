"""Discord presentation for the balance feature."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.get_balance import GetBalance
from butterbot.discord_app.formatting.money import format_money

logger = logging.getLogger(__name__)


class BalanceCog(commands.Cog):
    """Expose wallet balance lookup as a Discord slash command."""

    @app_commands.command(
        name="balance", description="Check your balance or someone else's."
    )
    @app_commands.describe(user="The user to check the balance of.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def balance(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        """Show the selected user's wallet, defaulting to the caller."""
        selected_user = user or interaction.user
        try:
            balance = await _get_balance(interaction).execute(selected_user.id)
        except Exception:
            logger.exception(
                "Failed to retrieve wallet balance.",
                extra={"target_user_id": selected_user.id},
            )
            await interaction.response.send_message(
                content=(
                    "I couldn't retrieve that balance right now. "
                    "Please try again later."
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"{selected_user.name}'s Balance",
            description=f"💰 {format_money(balance.balance)}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


class BalanceRuntime(Protocol):
    """Runtime service required when the balance command executes."""

    get_balance: GetBalance


def _get_balance(interaction: discord.Interaction) -> GetBalance:
    """Resolve the balance use case only at command execution time."""
    return cast(BalanceRuntime, interaction.client).get_balance


class BalanceBot(Protocol):
    """Bot capability required to register the balance cog."""

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register balance metadata without resolving runtime services."""
    balance_bot = cast(BalanceBot, bot)
    await balance_bot.add_cog(BalanceCog())
