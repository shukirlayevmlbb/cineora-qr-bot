from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar
from zoneinfo import ZoneInfo


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class UserSettings:
    default_style: str = "classic"
    history_enabled: bool = True
    save_wifi_history: bool = False


@dataclass(frozen=True, slots=True)
class QRRecord:
    id: int
    user_id: int
    qr_type: str
    payload: str
    label: str
    style: str
    is_saved: bool
    created_at: str


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    async def _run(self, callback: Callable[[sqlite3.Connection], T]) -> T:
        def sync_run() -> T:
            with self._connect() as connection:
                return callback(connection)
        return await asyncio.to_thread(sync_run)

    async def initialize(self) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    default_style TEXT NOT NULL DEFAULT 'classic',
                    history_enabled INTEGER NOT NULL DEFAULT 1,
                    save_wifi_history INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS qr_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    qr_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    label TEXT NOT NULL,
                    style TEXT NOT NULL,
                    is_saved INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_records_user_created
                ON qr_records(user_id, created_at DESC);
                """
            )
        await self._run(operation)

    async def ensure_user(self, user_id: int) -> None:
        now = datetime.now(UTC).isoformat()
        await self._run(
            lambda conn: conn.execute(
                "INSERT OR IGNORE INTO users(user_id, created_at) VALUES(?, ?)",
                (user_id, now),
            )
        )

    async def get_settings(self, user_id: int) -> UserSettings:
        await self.ensure_user(user_id)

        def operation(conn: sqlite3.Connection) -> UserSettings:
            row = conn.execute(
                "SELECT default_style, history_enabled, save_wifi_history FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            assert row is not None
            return UserSettings(row["default_style"], bool(row["history_enabled"]), bool(row["save_wifi_history"]))
        return await self._run(operation)

    async def set_setting(self, user_id: int, field: str, value: Any) -> None:
        allowed = {"default_style", "history_enabled", "save_wifi_history"}
        if field not in allowed:
            raise ValueError("Noto‘g‘ri sozlama")
        await self.ensure_user(user_id)
        await self._run(lambda conn: conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id)))

    async def add_record(
        self, user_id: int, qr_type: str, payload: str, label: str, style: str, is_saved: bool
    ) -> int:
        await self.ensure_user(user_id)
        now = datetime.now(UTC).isoformat()

        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                """INSERT INTO qr_records(user_id, qr_type, payload, label, style, is_saved, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (user_id, qr_type, payload, label, style, int(is_saved), now),
            )
            return int(cursor.lastrowid)
        return await self._run(operation)

    async def get_record(self, record_id: int, user_id: int) -> QRRecord | None:
        def operation(conn: sqlite3.Connection) -> QRRecord | None:
            row = conn.execute(
                "SELECT * FROM qr_records WHERE id = ? AND user_id = ?", (record_id, user_id)
            ).fetchone()
            return self._to_record(row) if row else None
        return await self._run(operation)

    async def update_style(self, record_id: int, user_id: int, style: str) -> None:
        await self._run(
            lambda conn: conn.execute(
                "UPDATE qr_records SET style = ? WHERE id = ? AND user_id = ?",
                (style, record_id, user_id),
            )
        )

    async def list_history(self, user_id: int, limit: int = 10, offset: int = 0) -> list[QRRecord]:
        def operation(conn: sqlite3.Connection) -> list[QRRecord]:
            rows = conn.execute(
                """SELECT * FROM qr_records
                   WHERE user_id = ? AND is_saved = 1
                   ORDER BY id DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            ).fetchall()
            return [self._to_record(row) for row in rows]
        return await self._run(operation)

    async def history_count(self, user_id: int) -> int:
        return await self._run(
            lambda conn: int(conn.execute(
                "SELECT COUNT(*) FROM qr_records WHERE user_id = ? AND is_saved = 1", (user_id,)
            ).fetchone()[0])
        )

    async def delete_record(self, record_id: int, user_id: int) -> bool:
        def operation(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("DELETE FROM qr_records WHERE id = ? AND user_id = ?", (record_id, user_id))
            return cursor.rowcount > 0
        return await self._run(operation)

    async def clear_history(self, user_id: int) -> int:
        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM qr_records WHERE user_id = ? AND is_saved = 1", (user_id,))
            return cursor.rowcount
        return await self._run(operation)

    async def cleanup_temporary(self) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM qr_records WHERE is_saved = 0 AND created_at < ?", (cutoff,))
            return cursor.rowcount
        return await self._run(operation)

    async def stats(self) -> dict[str, int]:
        def operation(conn: sqlite3.Connection) -> dict[str, int]:
            users = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            total = int(conn.execute("SELECT COUNT(*) FROM qr_records").fetchone()[0])
            local_now = datetime.now(ZoneInfo("Asia/Tashkent"))
            today = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()
            today_total = int(conn.execute(
                "SELECT COUNT(*) FROM qr_records WHERE created_at >= ?", (today,)
            ).fetchone()[0])
            return {"users": users, "total": total, "today": today_total}
        return await self._run(operation)

    @staticmethod
    def _to_record(row: sqlite3.Row) -> QRRecord:
        return QRRecord(
            id=int(row["id"]), user_id=int(row["user_id"]), qr_type=row["qr_type"],
            payload=row["payload"], label=row["label"], style=row["style"],
            is_saved=bool(row["is_saved"]), created_at=row["created_at"],
        )
