"""Discord presentation for protected bank balances."""

from __future__ import annotations

import logging
from typing import Protocol, cast

import discord
from discord import app_commands
from discord.ext import commands

from butterbot.application.economy.deposit_to_bank import DepositToBank
from butterbot.application.economy.get_bank_balance import GetBankBalance
from butterbot.discord_app.formatting.money import format_money
from butterbot.domain.bank import (
    BankCapacityExceeded,
    BankDepositSelectionConflict,
    BankDepositSelectionRequired,
    BankDepositWouldBeZero,
    BankHasNoCapacity,
    InsufficientWalletBalance,
    InvalidBankDepositAmount,
    InvalidBankDepositPercentage,
)

logger = logging.getLogger(__name__)


class BankCog(
    commands.GroupCog, group_name="bank", group_description="Manage your bank."
):
    """Expose the capacity-limited protected bank command family."""

    @app_commands.command(
        name="deposit", description="Move wallet money into protected bank storage."
    )
    @app_commands.describe(
        amount="Exact whole-dollar amount to deposit.",
        percentage="Percentage of your current wallet to deposit.",
    )
    @app_commands.choices(
        percentage=[
            app_commands.Choice(name="25%", value=25),
            app_commands.Choice(name="50%", value=50),
            app_commands.Choice(name="75%", value=75),
            app_commands.Choice(name="100%", value=100),
        ]
    )
    @app_commands.guild_only()
    async def deposit(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, None] | None = None,
        percentage: app_commands.Choice[int] | None = None,
    ) -> None:
        """Deposit an exact amount or supported percentage for the caller."""
        await interaction.response.defer()
        selected_percentage = None if percentage is None else percentage.value
        try:
            result = await _deposit_to_bank(interaction).execute(
                interaction.user.id,
                amount=amount,
                percentage=selected_percentage,
            )
        except BankDepositSelectionRequired:
            await interaction.edit_original_response(
                content="Choose either an exact amount or a percentage to deposit."
            )
            return
        except BankDepositSelectionConflict:
            await interaction.edit_original_response(
                content="Choose an exact amount or a percentage, not both."
            )
            return
        except (InvalidBankDepositAmount, InvalidBankDepositPercentage):
            await interaction.edit_original_response(
                content="That deposit selection is invalid. Please try again."
            )
            return
        except BankDepositWouldBeZero:
            await interaction.edit_original_response(
                content="That percentage rounds down to $0, so nothing was deposited."
            )
            return
        except BankHasNoCapacity:
            await interaction.edit_original_response(
                content="Your bank is full and cannot accept another deposit."
            )
            return
        except BankCapacityExceeded as error:
            await interaction.edit_original_response(
                content=(
                    "That amount exceeds your remaining bank capacity of "
                    f"{format_money(error.remaining_capacity)}."
                )
            )
            return
        except InsufficientWalletBalance as error:
            await interaction.edit_original_response(
                content=(
                    "You don't have enough money in your wallet. "
                    f"Available: {format_money(error.available_balance)}."
                )
            )
            return
        except Exception:
            logger.exception(
                "Failed to deposit money into bank.",
                extra={"user_id": interaction.user.id},
            )
            await interaction.edit_original_response(
                content="I couldn't complete that bank deposit. Please try again later."
            )
            return

        overview = result.overview
        description = f"Deposited {format_money(result.amount)} into your bank."
        if result.filled_remaining_capacity:
            description += " This filled your remaining bank capacity."
        embed = discord.Embed(
            title="Bank Deposit",
            description=description,
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Wallet Balance",
            value=format_money(overview.wallet.balance),
            inline=True,
        )
        embed.add_field(
            name="Bank Balance",
            value=format_money(overview.account.balance),
            inline=True,
        )
        embed.add_field(
            name="Remaining Capacity",
            value=format_money(overview.account.remaining_capacity),
            inline=True,
        )
        await interaction.edit_original_response(embed=embed)
        logger.info(
            "Bank deposit completed.",
            extra={
                "user_id": interaction.user.id,
                "amount": result.amount,
                "requested_percentage": result.percentage,
                "capacity_filled": result.filled_remaining_capacity,
                "wallet_balance": overview.wallet.balance,
                "bank_balance": overview.account.balance,
            },
        )

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
    deposit_to_bank: DepositToBank


def _get_bank_balance(interaction: discord.Interaction) -> GetBankBalance:
    """Resolve the bank lookup use case only at command execution time."""
    return cast(BankRuntime, interaction.client).get_bank_balance


def _deposit_to_bank(interaction: discord.Interaction) -> DepositToBank:
    """Resolve the bank deposit use case only at command execution time."""
    return cast(BankRuntime, interaction.client).deposit_to_bank


class BankBot(Protocol):
    """Bot capability required to register the bank command group."""

    async def add_cog(self, cog: commands.Cog, /, *, override: bool = False) -> None:
        """Register a Discord cog."""


async def setup(bot: commands.Bot) -> None:
    """Register bank command metadata without resolving runtime services."""
    bank_bot = cast(BankBot, bot)
    await bank_bot.add_cog(BankCog())
