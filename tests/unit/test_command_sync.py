from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest
from discord.ext import commands

from butterbot.config import Settings
from butterbot.discord_app.command_sync import (
    CommandSyncBot,
    CommandSyncOperation,
    synchronize_command_tree,
)

RUNTIME_SERVICE_ATTRIBUTES = {
    "get_bank_balance",
    "get_balance",
    "transfer_money",
    "claim_daily",
    "mine",
    "set_balance",
}


class RuntimeAccessTrackingSyncBot(CommandSyncBot):
    def __init__(self, **kwargs: Any) -> None:
        self.runtime_service_accesses: list[str] = []
        super().__init__(**kwargs)

    def __getattribute__(self, name: str) -> Any:
        if name in RUNTIME_SERVICE_ATTRIBUTES:
            accesses = object.__getattribute__(self, "runtime_service_accesses")
            accesses.append(name)
        return super().__getattribute__(name)


@pytest.mark.asyncio
async def test_sync_bot_loads_every_extension_without_runtime_services_or_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bot = RuntimeAccessTrackingSyncBot(
        owner_id=1,
        dev_guild_id=123,
        include_development_commands=True,
    )
    try:
        await bot.setup_hook()

        assert bot.runtime_service_accesses == []
        assert set(bot.cogs) == {
            "BalanceCog",
            "BankCog",
            "DailyCog",
            "GiveCog",
            "MineCog",
            "SetBalanceCog",
        }
        _assert_directory_empty(tmp_path)
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_production_sync_bot_cannot_register_development_commands() -> None:
    bot = CommandSyncBot(
        owner_id=1,
        dev_guild_id=123,
        include_development_commands=False,
    )
    try:
        await bot.setup_hook()

        assert {command.name for command in bot.tree.get_commands()} == {
            "balance",
            "bank",
            "daily",
            "give",
            "mine",
        }
        assert bot.tree.get_commands(guild=discord.Object(id=123)) == []
        assert "SetBalanceCog" not in bot.cogs
    finally:
        await bot.close()


class FakeTree:
    def __init__(self) -> None:
        self.global_commands = [_command("balance"), _command("daily")]
        self.guild_commands = [_command("old-command")]
        self.remote_global = [_command("balance"), _command("stale-global")]
        self.remote_guild = [_command("old-command"), _command("stale-guild")]
        self.copy_calls: list[int] = []
        self.sync_calls: list[int | None] = []
        self.clear_calls: list[int | None] = []
        self.fail_sync = False
        self.fetch_calls = 0

    def copy_global_to(self, *, guild: discord.abc.Snowflake) -> None:
        self.copy_calls.append(guild.id)
        self.guild_commands.extend(self.global_commands)

    async def fetch_commands(
        self, *, guild: discord.abc.Snowflake | None = None
    ) -> list[Any]:
        self.fetch_calls += 1
        return list(self.remote_global if guild is None else self.remote_guild)

    def get_commands(self, *, guild: discord.abc.Snowflake | None = None) -> list[Any]:
        return list(self.global_commands if guild is None else self.guild_commands)

    def clear_commands(self, *, guild: discord.abc.Snowflake | None) -> None:
        self.clear_calls.append(None if guild is None else guild.id)
        if guild is None:
            self.global_commands.clear()
        else:
            self.guild_commands.clear()

    async def sync(self, *, guild: discord.abc.Snowflake | None = None) -> list[Any]:
        self.sync_calls.append(None if guild is None else guild.id)
        if self.fail_sync:
            response = cast(Any, SimpleNamespace(status=500, reason="failure"))
            raise discord.HTTPException(response, "x")
        return self.get_commands(guild=guild)


class FakeBot:
    def __init__(self) -> None:
        self.tree = FakeTree()


def _command(name: str) -> Any:
    return SimpleNamespace(name=name, type=discord.AppCommandType.chat_input)


def _assert_directory_empty(path: Path) -> None:
    assert list(path.iterdir()) == []


@pytest.mark.asyncio
async def test_development_sync_targets_only_guild_and_reports_stale_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = FakeBot()

    with caplog.at_level(logging.INFO):
        report = await synchronize_command_tree(
            cast(commands.Bot, bot),
            CommandSyncOperation.DEVELOPMENT,
            dev_guild_id=123,
        )

    assert bot.tree.copy_calls == [123]
    assert bot.tree.sync_calls == [123]
    assert report.removed == ("chat_input:stale-guild",)
    assert report.desired == (
        "chat_input:balance",
        "chat_input:daily",
        "chat_input:old-command",
    )
    plan_index = caplog.messages.index("Application-command synchronization plan.")
    complete_index = caplog.messages.index(
        "Application-command synchronization completed."
    )
    assert plan_index < complete_index


@pytest.mark.asyncio
async def test_production_sync_targets_global_only() -> None:
    bot = FakeBot()

    report = await synchronize_command_tree(
        cast(commands.Bot, bot),
        CommandSyncOperation.PRODUCTION,
        dev_guild_id=123,
    )

    assert bot.tree.copy_calls == []
    assert bot.tree.sync_calls == [None]
    assert report.removed == ("chat_input:stale-global",)


@pytest.mark.asyncio
async def test_clear_development_only_clears_and_syncs_selected_guild() -> None:
    bot = FakeBot()

    report = await synchronize_command_tree(
        cast(commands.Bot, bot),
        CommandSyncOperation.CLEAR_DEVELOPMENT,
        dev_guild_id=123,
    )

    assert bot.tree.clear_calls == [123]
    assert bot.tree.sync_calls == [123]
    assert report.desired == ()
    assert report.removed == (
        "chat_input:old-command",
        "chat_input:stale-guild",
    )


@pytest.mark.asyncio
async def test_sync_failure_reconciles_once_without_retrying_sync() -> None:
    bot = FakeBot()
    bot.tree.fail_sync = True

    with pytest.raises(discord.HTTPException):
        await synchronize_command_tree(
            cast(commands.Bot, bot),
            CommandSyncOperation.PRODUCTION,
            dev_guild_id=None,
        )

    assert bot.tree.sync_calls == [None]
    assert bot.tree.fetch_calls == 2


def test_sync_settings_do_not_require_a_database_to_exist(tmp_path: Path) -> None:
    database_path = tmp_path / "must-not-be-created.sqlite3"

    Settings(
        discord_token="token",
        owner_id=1,
        database_path=database_path,
        log_level="INFO",
    )

    assert not database_path.exists()
