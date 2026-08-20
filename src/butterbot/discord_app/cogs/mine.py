"""Discord presentation for mining."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.mining.mine import Mine
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.mining import (
    InvalidMiningState,
    MiningCooldownActive,
    MiningRewardExceedsWalletLimit,
)

logger = logging.getLogger(__name__)


class MineCog(commands.Cog):
    """Expose one atomic mining action through `/mine`."""

    def __init__(self, mine: Mine) -> None:
        self._mine = mine

    @app_commands.command(name="mine", description="Mine resources for money and XP.")
    @app_commands.guild_only()
    async def mine(self, interaction: discord.Interaction) -> None:
        """Mine once and render the committed result."""
        await interaction.response.defer()
        try:
            result = await self._mine.execute(interaction.user.id)
        except MiningCooldownActive as error:
            timestamp = int(error.next_mine_at.timestamp())
            await interaction.edit_original_response(
                content=f"You're still mining. Try again <t:{timestamp}:R>."
            )
            return
        except MiningRewardExceedsWalletLimit:
            await interaction.edit_original_response(
                content="Your wallet cannot hold the mining reward."
            )
            return
        except InvalidMiningState:
            logger.exception(
                "Invalid persisted mining state.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(
                content=(
                    "I couldn't complete your mining action. Please try again later."
                )
            )
            return
        except Exception:
            logger.exception(
                "Failed to complete mining action.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(
                content=(
                    "I couldn't complete your mining action. Please try again later."
                )
            )
            return

        outcome = result.outcome
        xp_progress = (
            f"{result.xp} XP (maximum level)"
            if result.xp_for_next_level is None
            else f"{result.xp}/{result.xp_for_next_level} XP"
        )
        level_line = f"Level {result.level} · {xp_progress}"
        if result.leveled_up:
            level_line += f"\n🎉 Level up! You reached level {result.level}."
        embed = discord.Embed(
            title="⛏️ Mining Result",
            description=(f"You mined **{outcome.resource}** ({outcome.rarity})!"),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Reward",
            value=(
                f"Base: {format_money(outcome.base_value)}\n"
                f"Level bonus: {format_money(outcome.level_bonus)}\n"
                f"Total: **{format_money(outcome.total_value)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Progress",
            value=f"+{outcome.xp_gained} XP\n{level_line}",
            inline=True,
        )
        embed.add_field(
            name="Wallet",
            value=format_money(result.balance),
            inline=True,
        )
        await interaction.edit_original_response(embed=embed)


class MineBot(Protocol):
    """Bot capabilities required to register the mining cog."""

    mine: Mine

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register the explicitly composed mining command."""
    mine_bot = cast(MineBot, bot)
    await mine_bot.add_cog(MineCog(mine_bot.mine))
