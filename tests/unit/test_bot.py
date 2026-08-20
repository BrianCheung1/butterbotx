from __future__ import annotations

import logging
from pathlib import Path

import pytest

from butterbot.config import Settings
from butterbot.discord_app.bot import _log_command_mode


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
