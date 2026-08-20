"""SQLite connection lifecycle."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

Result = TypeVar("Result")


class SQLiteDatabase:
    """Own one serialized SQLite connection for startup infrastructure."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def open(self) -> None:
        """Create the parent directory and open the configured SQLite database."""
        with self._lock:
            if self._connection is not None:
                return

            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = _open_connection(self._path)

    def close(self) -> None:
        """Close the connection if it is open."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def run(self, operation: Callable[[sqlite3.Connection], Result]) -> Result:
        """Run one startup-only database operation under the database lock."""
        with self._lock:
            if self._connection is None:
                raise RuntimeError("SQLite connection has not been opened.")
            return operation(self._connection)


def _open_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL").fetchone()
    return connection
