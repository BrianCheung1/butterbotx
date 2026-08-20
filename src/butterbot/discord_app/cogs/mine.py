"""Discord presentation for mining."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.mining.mine import Mine
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.mining import (
    InvalidMiningState,
    MiningCooldownActive,
    MiningResult,
    MiningRewardExceedsWalletLimit,
)

logger = logging.getLogger(__name__)

MiningDelay = Callable[[float], Awaitable[None]]
FIRST_STAGE_SECONDS = 4.0
SECOND_STAGE_SECONDS = 5.0
MINE_AGAIN_TIMEOUT_SECONDS = 300.0


class MineCog(commands.Cog):
    """Expose staged, atomic mining actions through `/mine`."""

    def __init__(self, mine: Mine, delay: MiningDelay = asyncio.sleep) -> None:
        self._mine = mine
        self._delay = delay

    @app_commands.command(name="mine", description="Mine resources for money and XP.")
    @app_commands.guild_only()
    async def mine(self, interaction: discord.Interaction) -> None:
        """Commit one mine, animate it, and reveal the persisted result."""
        await interaction.response.defer()
        try:
            result = await self._mine.execute(interaction.user.id)
        except MiningCooldownActive as error:
            await interaction.edit_original_response(
                content=_cooldown_message(error.next_mine_at.timestamp())
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
            await interaction.edit_original_response(content=_safe_failure_message())
            return
        except Exception:
            logger.exception(
                "Failed to complete mining action.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(content=_safe_failure_message())
            return

        view = MineAgainView(
            self._mine,
            owner_id=interaction.user.id,
            delay=self._delay,
        )
        await _animate_and_reveal(interaction, result, view, self._delay)


class MineAgainView(discord.ui.View):
    """Temporary owner-bound control for repeating the mining use case."""

    def __init__(
        self,
        mine: Mine,
        *,
        owner_id: int,
        delay: MiningDelay = asyncio.sleep,
    ) -> None:
        super().__init__(timeout=MINE_AGAIN_TIMEOUT_SECONDS)
        self._mine = mine
        self._owner_id = owner_id
        self._delay = delay
        self._action_in_progress = False
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the reusable control to the initiating Discord user."""
        if interaction.user.id == self._owner_id:
            return True
        await interaction.response.send_message(
            "Only the miner who started this session can use Mine Again.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Mine Again", style=discord.ButtonStyle.primary, emoji="⛏️")
    async def mine_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Run the same mining use case and update the existing result message."""
        del button
        if self._action_in_progress:
            await interaction.response.send_message(
                "A mining action is already being processed.",
                ephemeral=True,
            )
            return

        self._action_in_progress = True
        try:
            await interaction.response.defer()
            try:
                result = await self._mine.execute(self._owner_id)
            except MiningCooldownActive as error:
                await interaction.followup.send(
                    _cooldown_message(error.next_mine_at.timestamp()),
                    ephemeral=True,
                )
                return
            except MiningRewardExceedsWalletLimit:
                await interaction.followup.send(
                    "Your wallet cannot hold the mining reward.",
                    ephemeral=True,
                )
                return
            except InvalidMiningState:
                logger.exception(
                    "Invalid persisted mining state from Mine Again.",
                    extra={"user_id": self._owner_id},
                )
                await interaction.followup.send(_safe_failure_message(), ephemeral=True)
                return
            except Exception:
                logger.exception(
                    "Failed to complete Mine Again action.",
                    extra={"user_id": self._owner_id},
                )
                await interaction.followup.send(_safe_failure_message(), ephemeral=True)
                return

            await _animate_and_reveal(interaction, result, self, self._delay)
        finally:
            self._action_in_progress = False

    async def on_timeout(self) -> None:
        """Disable the expired button with a best-effort message update."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except Exception:
            logger.exception(
                "Failed to disable expired Mine Again view.",
                extra={"user_id": self._owner_id},
            )


async def _animate_and_reveal(
    interaction: discord.Interaction,
    result: MiningResult,
    view: MineAgainView,
    delay: MiningDelay,
) -> None:
    """Animate only after a committed result, then reveal that exact result."""
    try:
        message = await interaction.edit_original_response(
            content=None,
            embed=_animation_embed(
                "⛏️ Mining...",
                "You enter the mine and choose a promising tunnel...",
            ),
            view=view,
        )
        view.message = message
        await delay(FIRST_STAGE_SECONDS)
        message = await interaction.edit_original_response(
            content=None,
            embed=_animation_embed(
                "💥 Mining...",
                "Your pickaxe strikes something beneath the rock...",
            ),
            view=view,
        )
        view.message = message
        await delay(SECOND_STAGE_SECONDS)
    except Exception:
        logger.exception(
            "Mining animation failed after the action committed.",
            extra={"user_id": interaction.user.id},
        )
        await _reveal_committed_result(interaction, result, view)
        return

    await _reveal_committed_result(interaction, result, view)


async def _reveal_committed_result(
    interaction: discord.Interaction,
    result: MiningResult,
    view: MineAgainView,
) -> None:
    """Best-effort reveal that never retries the committed mining action."""
    try:
        message = await interaction.edit_original_response(
            content=None,
            embed=_result_embed(result),
            view=view,
        )
        view.message = message
    except Exception:
        logger.exception(
            "Failed to reveal a committed mining result.",
            extra={"user_id": interaction.user.id},
        )


def _animation_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_gold(),
    )


def _result_embed(result: MiningResult) -> discord.Embed:
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
        description=f"You mined **{outcome.resource}** ({outcome.rarity})!",
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
    timestamp = int(result.next_mine_at.timestamp())
    embed.add_field(
        name="Next Mine",
        value=f"<t:{timestamp}:R>",
        inline=False,
    )
    return embed


def _cooldown_message(timestamp: float) -> str:
    return f"You're still mining. Try again <t:{int(timestamp)}:R>."


def _safe_failure_message() -> str:
    return "I couldn't complete your mining action. Please try again later."


class MineBot(Protocol):
    """Bot capabilities required to register the mining cog."""

    mine: Mine

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register the explicitly composed mining command."""
    mine_bot = cast(MineBot, bot)
    await mine_bot.add_cog(MineCog(mine_bot.mine))
