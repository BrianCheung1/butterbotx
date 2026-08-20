"""Focused command-line parsing for ButterBot process operations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from butterbot.config import ConfigurationError, Settings
from butterbot.discord_app.command_sync import CommandSyncOperation


@dataclass(frozen=True, slots=True)
class CommandSyncRequest:
    """A parsed command synchronization request and its confirmation state."""

    operation: CommandSyncOperation
    confirmed: bool


def parse_command_sync_request(arguments: list[str]) -> CommandSyncRequest | None:
    """Parse an explicit sync operation, or return None for normal startup."""
    if not arguments:
        return None

    parser = argparse.ArgumentParser(prog="python -m butterbot")
    actions = parser.add_subparsers(dest="action", required=True)
    sync_parser = actions.add_parser(
        "sync-commands", description="Synchronize Discord application commands."
    )
    operations = sync_parser.add_subparsers(dest="operation", required=True)
    operations.add_parser(CommandSyncOperation.DEVELOPMENT.value)
    clear_parser = operations.add_parser(CommandSyncOperation.CLEAR_DEVELOPMENT.value)
    clear_parser.add_argument("--confirm", action="store_true")
    production_parser = operations.add_parser(CommandSyncOperation.PRODUCTION.value)
    production_parser.add_argument("--confirm-production", action="store_true")

    parsed = parser.parse_args(arguments)
    operation = CommandSyncOperation(parsed.operation)
    confirmed = bool(
        getattr(parsed, "confirm", False)
        or getattr(parsed, "confirm_production", False)
    )
    return CommandSyncRequest(operation=operation, confirmed=confirmed)


def validate_command_sync_request(
    request: CommandSyncRequest,
    settings: Settings,
) -> None:
    """Enforce operation-specific configuration and deliberate confirmations."""
    if request.operation is CommandSyncOperation.DEVELOPMENT:
        if not settings.enable_dev_commands:
            raise ConfigurationError(
                "Development synchronization requires ENABLE_DEV_COMMANDS=true."
            )
        if settings.dev_guild_id is None:
            raise ConfigurationError(
                "Development synchronization requires DEV_GUILD_ID."
            )
        return

    if request.operation is CommandSyncOperation.CLEAR_DEVELOPMENT:
        if settings.dev_guild_id is None:
            raise ConfigurationError(
                "Clearing development commands requires DEV_GUILD_ID."
            )
        if not request.confirmed:
            raise ConfigurationError(
                "Clearing development commands requires --confirm."
            )
        return

    if settings.enable_dev_commands:
        raise ConfigurationError(
            "Production synchronization requires ENABLE_DEV_COMMANDS=false."
        )
    if not request.confirmed:
        raise ConfigurationError(
            "Production synchronization requires --confirm-production."
        )
