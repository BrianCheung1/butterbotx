from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from butterbot.config import Settings
from butterbot.discord_app.bot import ButterBot, _log_command_mode
from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase


def settings(*, enable_dev_commands: bool, dev_guild_id: int | None) -> Settings:
    return Settings(
        discord_token="test-token",
        owner_id=1,
        database_path=Path("test.sqlite3"),
        log_level="INFO",
        enable_dev_commands=enable_dev_commands,
        dev_guild_id=dev_guild_id,
    )


def test_startup_logs_development_command_mode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        _log_command_mode(settings(enable_dev_commands=True, dev_guild_id=456))

    assert "Development commands are enabled for guild 456" in caplog.text
    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.__dict__["dev_guild_id"] == 456


def test_startup_logs_production_command_mode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        _log_command_mode(settings(enable_dev_commands=False, dev_guild_id=None))

    assert (
        "Development commands are disabled; loading production commands only"
        in caplog.text
    )


@pytest.mark.asyncio
async def test_normal_setup_never_synchronizes_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_settings = Settings(
        discord_token="test-token",
        owner_id=1,
        database_path=tmp_path / "runtime.sqlite3",
        log_level="INFO",
    )
    monkeypatch.setattr(SQLiteDatabase, "open", lambda self: None)
    monkeypatch.setattr(MigrationRunner, "apply", lambda self, database: [])
    load_extensions = AsyncMock()
    monkeypatch.setattr("butterbot.discord_app.bot.load_extensions", load_extensions)
    bot = ButterBot(runtime_settings)
    sync = AsyncMock()
    cast(Any, bot.tree).sync = sync
    try:
        await bot.setup_hook()
    finally:
        await bot.close()

    load_extensions.assert_awaited_once()
    sync.assert_not_awaited()
