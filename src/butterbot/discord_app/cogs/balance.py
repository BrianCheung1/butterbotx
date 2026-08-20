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

    def __init__(self, get_balance: GetBalance) -> None:
        self._get_balance = get_balance

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
            balance = await self._get_balance.execute(selected_user.id)
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


class BalanceBot(Protocol):
    """Bot capabilities required to register the balance cog."""

    get_balance: GetBalance

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register the explicitly composed balance command."""
    balance_bot = cast(BalanceBot, bot)
    await balance_bot.add_cog(BalanceCog(balance_bot.get_balance))
