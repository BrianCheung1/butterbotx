"""Application process entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

from butterbot.command_line import (
    parse_command_sync_request,
    validate_command_sync_request,
)
from butterbot.config import ConfigurationError, Settings
from butterbot.discord_app.bot import ButterBot
from butterbot.discord_app.command_sync import run_command_sync
from butterbot.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run_application(settings: Settings) -> None:
    """Start ButterBot and close its resources when the process exits."""
    bot = ButterBot(settings)
    try:
        await bot.start(settings.discord_token)
    finally:
        await bot.close()


def main(arguments: list[str] | None = None) -> None:
    """Load local configuration and run the application."""
    arguments = sys.argv[1:] if arguments is None else arguments
    load_dotenv()
    try:
        sync_request = parse_command_sync_request(arguments)
        settings = Settings.from_environment()
        configure_logging(settings.log_level)
        if sync_request is not None:
            validate_command_sync_request(sync_request, settings)
    except (ConfigurationError, ValueError) as error:
        raise SystemExit(f"Configuration error: {error}") from error

    if sync_request is not None:
        logger.info(
            "Starting explicit application-command synchronization.",
            extra={"sync_operation": sync_request.operation.value},
        )
        try:
            asyncio.run(run_command_sync(settings, sync_request.operation))
        except Exception as error:
            logger.exception(
                "Application-command synchronization operation failed.",
                extra={"sync_operation": sync_request.operation.value},
            )
            raise SystemExit(
                "Command synchronization failed; review the logs for details."
            ) from error
        return

    logger.info("Starting ButterBot.")
    asyncio.run(run_application(settings))
