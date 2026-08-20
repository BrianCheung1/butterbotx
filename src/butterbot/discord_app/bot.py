"""Discord lifecycle orchestration for ButterBot."""

from __future__ import annotations

import logging
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

from butterbot.application.economy.claim_daily import ClaimDaily
from butterbot.application.economy.get_balance import GetBalance
from butterbot.application.economy.set_balance import SetBalance
from butterbot.application.economy.transfer_money import TransferMoney
from butterbot.config import Settings
from butterbot.discord_app.extensions import load_extensions
from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase
from butterbot.infrastructure.database.sqlite_daily_claim_repository import (
    SQLiteDailyClaimRepository,
)
from butterbot.infrastructure.database.sqlite_wallet_repository import (
    SQLiteWalletRepository,
)

logger = logging.getLogger(__name__)


class ButterBot(commands.Bot):
    """Coordinate Discord with explicitly owned application resources."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self._settings = settings
        self.owner_id = settings.owner_id
        self.dev_guild_id = settings.dev_guild_id
        self._http_session: aiohttp.ClientSession | None = None
        self._database = SQLiteDatabase(settings.database_path)
        self._wallet_repository = SQLiteWalletRepository(settings.database_path)
        self._daily_claim_repository = SQLiteDailyClaimRepository(
            settings.database_path
        )
        self.claim_daily = ClaimDaily(self._daily_claim_repository)
        self.get_balance = GetBalance(self._wallet_repository)
        self.set_balance = SetBalance(self._wallet_repository)
        self.transfer_money = TransferMoney(self._wallet_repository)

    async def setup_hook(self) -> None:
        """Initialize shared infrastructure before connecting to Discord."""
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(connect=5, sock_read=15, total=30)
        )
        try:
            self._database.open()
            MigrationRunner(_migration_directory()).apply(self._database)
            _log_command_mode(self._settings)
            await load_extensions(
                self,
                enable_dev_commands=self._settings.enable_dev_commands,
            )
        except BaseException:
            await self._close_resources()
            raise
        logger.info("ButterBot infrastructure is ready.")

    async def close(self) -> None:
        """Close shared resources before closing the Discord client."""
        await self._close_resources()
        await super().close()

    async def _close_resources(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        self._daily_claim_repository.close()
        self._wallet_repository.close()
        self._database.close()


def _migration_directory() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "infrastructure"
        / "database"
        / "migrations"
    )


def _log_command_mode(settings: Settings) -> None:
    if settings.enable_dev_commands:
        logger.warning(
            "Development commands are enabled for guild %s.",
            settings.dev_guild_id,
            extra={"dev_guild_id": settings.dev_guild_id},
        )
        return
    logger.info("Development commands are disabled; loading production commands only.")
