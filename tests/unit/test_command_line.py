from __future__ import annotations

from pathlib import Path

import pytest

from butterbot.command_line import (
    CommandSyncRequest,
    parse_command_sync_request,
    validate_command_sync_request,
)
from butterbot.config import ConfigurationError, Settings
from butterbot.discord_app.command_sync import CommandSyncOperation


def settings(
    *, enable_dev_commands: bool = False, dev_guild_id: int | None = None
) -> Settings:
    return Settings(
        discord_token="token",
        owner_id=1,
        database_path=Path("unused.sqlite3"),
        log_level="INFO",
        enable_dev_commands=enable_dev_commands,
        dev_guild_id=dev_guild_id,
    )


def test_no_command_line_operation_preserves_normal_startup() -> None:
    assert parse_command_sync_request([]) is None


@pytest.mark.parametrize(
    ("arguments", "operation", "confirmed"),
    [
        (
            ["sync-commands", "development"],
            CommandSyncOperation.DEVELOPMENT,
            False,
        ),
        (
            ["sync-commands", "clear-development", "--confirm"],
            CommandSyncOperation.CLEAR_DEVELOPMENT,
            True,
        ),
        (
            ["sync-commands", "production", "--confirm-production"],
            CommandSyncOperation.PRODUCTION,
            True,
        ),
    ],
)
def test_parses_explicit_sync_operations(
    arguments: list[str], operation: CommandSyncOperation, confirmed: bool
) -> None:
    assert parse_command_sync_request(arguments) == CommandSyncRequest(
        operation, confirmed
    )


def test_development_sync_requires_enabled_commands() -> None:
    request = CommandSyncRequest(CommandSyncOperation.DEVELOPMENT, False)

    with pytest.raises(ConfigurationError, match="ENABLE_DEV_COMMANDS=true"):
        validate_command_sync_request(request, settings(dev_guild_id=123))


def test_development_sync_accepts_enabled_commands_and_guild() -> None:
    request = CommandSyncRequest(CommandSyncOperation.DEVELOPMENT, False)

    validate_command_sync_request(
        request, settings(enable_dev_commands=True, dev_guild_id=123)
    )


@pytest.mark.parametrize(
    "operation",
    [CommandSyncOperation.CLEAR_DEVELOPMENT, CommandSyncOperation.PRODUCTION],
)
def test_destructive_sync_operations_require_confirmation(
    operation: CommandSyncOperation,
) -> None:
    request = CommandSyncRequest(operation, False)

    with pytest.raises(ConfigurationError, match="requires --"):
        validate_command_sync_request(request, settings(dev_guild_id=123))


def test_clear_development_requires_guild_even_when_dev_commands_are_disabled() -> None:
    request = CommandSyncRequest(CommandSyncOperation.CLEAR_DEVELOPMENT, True)

    with pytest.raises(ConfigurationError, match="DEV_GUILD_ID"):
        validate_command_sync_request(request, settings())


def test_production_sync_rejects_development_extension_mode() -> None:
    request = CommandSyncRequest(CommandSyncOperation.PRODUCTION, True)

    with pytest.raises(ConfigurationError, match="ENABLE_DEV_COMMANDS=false"):
        validate_command_sync_request(
            request, settings(enable_dev_commands=True, dev_guild_id=123)
        )
