"""Discord presentation for daily wallet rewards."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.claim_daily import ClaimDaily
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.daily_reward import (
    DailyAlreadyClaimed,
    DailyRewardExceedsWalletLimit,
    InvalidDailyClaimState,
)

logger = logging.getLogger(__name__)


class DailyCog(commands.Cog):
    """Expose atomic UTC-calendar daily claims through Discord."""

    @app_commands.command(name="daily", description="Claim your daily reward.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def daily(self, interaction: discord.Interaction) -> None:
        """Claim and render the invoking user's daily reward."""
        await interaction.response.defer()
        try:
            result = await _claim_daily(interaction).execute(interaction.user.id)
        except DailyAlreadyClaimed as error:
            next_claim_timestamp = int(error.next_claim_at.timestamp())
            await interaction.edit_original_response(
                content=(
                    "🕒 You've already claimed your daily today! "
                    f"Come back <t:{next_claim_timestamp}:R> "
                    f"(at <t:{next_claim_timestamp}:t> your time)."
                )
            )
            return
        except DailyRewardExceedsWalletLimit:
            await interaction.edit_original_response(
                content="Your wallet cannot hold the daily reward."
            )
            return
        except InvalidDailyClaimState:
            logger.exception(
                "Invalid persisted daily claim state.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(
                content="I couldn't complete your daily claim. Please try again later."
            )
            return
        except Exception:
            logger.exception(
                "Failed to claim daily reward.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(
                content="I couldn't complete your daily claim. Please try again later."
            )
            return

        logger.info(
            "Daily reward claimed.",
            extra={
                "user_id": interaction.user.id,
                "reward": result.reward.total,
                "streak": result.reward.streak,
                "claim_date": result.claim_date.isoformat(),
            },
        )
        embed = discord.Embed(
            title="Daily Reward",
            description=(
                f"Claimed your daily reward of {format_money(result.reward.total)}!\n"
                f"Daily base: {format_money(result.reward.base)}\n"
                f"Bonus: {format_money(result.reward.bonus)}\n"
                f"Streak: {result.reward.streak} day(s)\n"
                f"Your new balance is {format_money(result.wallet.balance)}."
            ),
            color=discord.Color.green(),
        )
        await interaction.edit_original_response(embed=embed)


class DailyRuntime(Protocol):
    """Runtime service required when the daily command executes."""

    claim_daily: ClaimDaily


def _claim_daily(interaction: discord.Interaction) -> ClaimDaily:
    """Resolve the daily use case only at command execution time."""
    return cast(DailyRuntime, interaction.client).claim_daily


class DailyBot(Protocol):
    """Bot capability required to register the daily cog."""

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register daily metadata without resolving runtime services."""
    daily_bot = cast(DailyBot, bot)
    await daily_bot.add_cog(DailyCog())
