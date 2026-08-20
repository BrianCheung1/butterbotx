"""Discord presentation for owner wallet administration."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.set_balance import SetBalance
from butterbot.config import ConfigurationError
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.wallet import MAX_MONEY

logger = logging.getLogger(__name__)


class SetBalanceCog(commands.Cog):
    """Expose owner-only wallet balance replacement in one development guild."""

    def __init__(
        self,
        set_balance: SetBalance,
        owner_id: int,
        dev_guild_id: int,
    ) -> None:
        self._set_balance = set_balance
        self._owner_id = owner_id
        self._dev_guild_id = dev_guild_id

    @app_commands.command(
        name="set-balance", description="Set a user's wallet balance."
    )
    @app_commands.describe(
        user="The user whose balance should be set.",
        amount="The nonnegative whole-dollar balance.",
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def set_balance(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 0, None],
    ) -> None:
        """Set a wallet balance after enforcing guild and owner authorization."""
        if interaction.guild_id != self._dev_guild_id:
            await interaction.response.send_message(
                content="This command is only available in the development server.",
                ephemeral=True,
            )
            return
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(
                content="You are not authorized to use this command.",
                ephemeral=True,
            )
            return
        if amount > MAX_MONEY:
            await interaction.response.send_message(
                content="That balance is outside the supported range.",
                ephemeral=True,
            )
            return

        try:
            wallet = await self._set_balance.execute(user.id, amount)
        except ValueError:
            await interaction.response.send_message(
                content="That balance is outside the supported range.",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception(
                "Failed to set wallet balance.",
                extra={
                    "actor_user_id": interaction.user.id,
                    "target_user_id": user.id,
                    "amount": amount,
                },
            )
            await interaction.response.send_message(
                content=(
                    "I couldn't set that balance right now. Please try again later."
                ),
                ephemeral=True,
            )
            return

        logger.info(
            "Owner set wallet balance.",
            extra={
                "actor_user_id": interaction.user.id,
                "target_user_id": user.id,
                "amount": wallet.balance,
            },
        )
        await interaction.response.send_message(
            content=(
                f"✅ Set {user.mention}'s balance to {format_money(wallet.balance)}."
            )
        )


class SetBalanceBot(Protocol):
    """Bot capabilities required to register the set-balance cog."""

    set_balance: SetBalance
    owner_id: int
    dev_guild_id: int | None

    async def add_cog(
        self,
        cog: commands.Cog,
        /,
        *,
        override: bool = False,
        guild: discord.abc.Snowflake | None = None,
    ) -> None:
        """Register a Discord cog, optionally for one guild."""


async def setup(bot: commands.Bot) -> None:
    """Register set-balance in its configured development guild."""
    set_balance_bot = cast(SetBalanceBot, bot)
    if set_balance_bot.dev_guild_id is None:
        raise ConfigurationError(
            "DEV_GUILD_ID is required when the /set-balance feature is selected."
        )
    development_guild = discord.Object(id=set_balance_bot.dev_guild_id)
    await set_balance_bot.add_cog(
        SetBalanceCog(
            set_balance_bot.set_balance,
            set_balance_bot.owner_id,
            set_balance_bot.dev_guild_id,
        ),
        guild=development_guild,
    )
