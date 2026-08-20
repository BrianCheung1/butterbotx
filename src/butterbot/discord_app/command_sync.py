"""Explicit Discord application-command synchronization operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import discord
from discord.ext import commands

from butterbot.config import Settings
from butterbot.discord_app.extensions import load_extensions

logger = logging.getLogger(__name__)


class CommandSyncOperation(Enum):
    """Supported, deliberately scoped command synchronization operations."""

    DEVELOPMENT = "development"
    CLEAR_DEVELOPMENT = "clear-development"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class CommandSyncReport:
    """Observable command surfaces before and after one synchronization."""

    scope: str
    remote_before: tuple[str, ...]
    desired: tuple[str, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]
    retained: tuple[str, ...]
    synchronized: tuple[str, ...]


class CommandSyncBot(commands.Bot):
    """Load command metadata without constructing ButterBot runtime services."""

    def __init__(
        self,
        *,
        owner_id: int,
        dev_guild_id: int | None,
        include_development_commands: bool,
    ) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.none(),
        )
        self.owner_id = owner_id
        self.dev_guild_id = dev_guild_id
        self._include_development_commands = include_development_commands

    async def setup_hook(self) -> None:
        """Load only the explicitly selected command extensions."""
        await load_extensions(
            self,
            enable_dev_commands=self._include_development_commands,
        )


async def run_command_sync(
    settings: Settings,
    operation: CommandSyncOperation,
) -> CommandSyncReport:
    """Log in for one explicit synchronization operation, then close."""
    bot = CommandSyncBot(
        owner_id=settings.owner_id,
        dev_guild_id=settings.dev_guild_id,
        include_development_commands=operation is CommandSyncOperation.DEVELOPMENT,
    )
    try:
        await bot.login(settings.discord_token)
        return await synchronize_command_tree(
            bot,
            operation,
            dev_guild_id=settings.dev_guild_id,
        )
    finally:
        await bot.close()


async def synchronize_command_tree(
    bot: commands.Bot,
    operation: CommandSyncOperation,
    *,
    dev_guild_id: int | None,
) -> CommandSyncReport:
    """Synchronize exactly one command scope and report its reconciliation."""
    if operation is CommandSyncOperation.PRODUCTION:
        return await _synchronize_scope(bot, guild=None, clear=False)
    if dev_guild_id is None:
        raise ValueError("A development guild is required for guild synchronization.")

    guild = discord.Object(id=dev_guild_id)
    if operation is CommandSyncOperation.DEVELOPMENT:
        bot.tree.copy_global_to(guild=guild)
        return await _synchronize_scope(bot, guild=guild, clear=False)
    return await _synchronize_scope(bot, guild=guild, clear=True)


async def _synchronize_scope(
    bot: commands.Bot,
    *,
    guild: discord.abc.Snowflake | None,
    clear: bool,
) -> CommandSyncReport:
    scope = "global" if guild is None else f"guild:{guild.id}"
    remote_before = await bot.tree.fetch_commands(guild=guild)
    if clear:
        bot.tree.clear_commands(guild=guild)
    desired_commands = bot.tree.get_commands(guild=guild)
    remote_names = _command_names(remote_before)
    desired_names = _command_names(desired_commands)
    added = tuple(sorted(set(desired_names) - set(remote_names)))
    removed = tuple(sorted(set(remote_names) - set(desired_names)))
    retained = tuple(sorted(set(remote_names) & set(desired_names)))

    logger.info(
        "Command sync plan [%s]:\n"
        "  Desired: %s\n"
        "  Added: %s\n"
        "  Retained: %s\n"
        "  Removed: %s",
        _scope_label(guild),
        _visible_command_names(desired_names),
        _visible_command_names(added),
        _visible_command_names(retained),
        _visible_command_names(removed),
        extra={
            "command_scope": scope,
            "remote_before": remote_names,
            "desired": desired_names,
            "added": added,
            "removed": removed,
            "retained": retained,
        },
    )

    try:
        synchronized_commands = await bot.tree.sync(guild=guild)
    except Exception:
        logger.exception(
            "Application-command synchronization failed; it will not be retried.",
            extra={"command_scope": scope},
        )
        await _log_observed_remote_state(bot, guild=guild, scope=scope)
        raise

    synchronized = _command_names(synchronized_commands)
    logger.info(
        "Command sync completed [%s]:\n  Synchronized: %s",
        _scope_label(guild),
        _visible_command_names(synchronized),
        extra={
            "command_scope": scope,
            "synchronized": synchronized,
            "removed": removed,
        },
    )
    return CommandSyncReport(
        scope=scope,
        remote_before=remote_names,
        desired=desired_names,
        added=added,
        removed=removed,
        retained=retained,
        synchronized=synchronized,
    )


async def _log_observed_remote_state(
    bot: commands.Bot,
    *,
    guild: discord.abc.Snowflake | None,
    scope: str,
) -> None:
    try:
        observed = _command_names(await bot.tree.fetch_commands(guild=guild))
    except Exception:
        logger.exception(
            "Could not reconcile command state after synchronization failure.",
            extra={"command_scope": scope},
        )
        return
    logger.error(
        "Observed command state after synchronization failure.",
        extra={"command_scope": scope, "observed": observed},
    )


def _command_names(command_list: list[Any]) -> tuple[str, ...]:
    identities = []
    for command in command_list:
        command_type = getattr(command, "type", discord.AppCommandType.chat_input)
        type_name = getattr(command_type, "name", str(command_type))
        identities.append(f"{type_name}:{command.name}")
    return tuple(sorted(identities))


def _scope_label(guild: discord.abc.Snowflake | None) -> str:
    if guild is None:
        return "global production"
    return f"development guild {guild.id}"


def _visible_command_names(identities: tuple[str, ...]) -> str:
    names = []
    for identity in identities:
        command_type, separator, name = identity.partition(":")
        names.append(name if separator and command_type == "chat_input" else identity)
    return ", ".join(sorted(names)) or "<none>"
