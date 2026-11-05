from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class UserSettings:
    default_style: str = "classic"
    history_enabled: bool = True
    save_wifi_history: bool = False
    language: str = "uz"
    theme: str = "auto"


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
    design_json: str = "{}"
    is_favorite: bool = False


class Database:
    """One storage interface for local SQLite and production PostgreSQL."""

    def __init__(self, path: Path, database_url: str = "") -> None:
        self.path = path
        self.database_url = database_url.strip()
        self._pool: Any = None

    @property
    def is_postgres(self) -> bool:
        return bool(self.database_url)

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
        if self.is_postgres:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=1,
                max_size=5,
                command_timeout=30,
                statement_cache_size=0,
            )
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        default_style TEXT NOT NULL DEFAULT 'classic',
                        history_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        save_wifi_history BOOLEAN NOT NULL DEFAULT FALSE,
                        language TEXT NOT NULL DEFAULT 'uz',
                        theme TEXT NOT NULL DEFAULT 'auto',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS qr_records (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        qr_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        label TEXT NOT NULL,
                        style TEXT NOT NULL,
                        design_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        is_saved BOOLEAN NOT NULL DEFAULT TRUE,
                        is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_records_user_created
                    ON qr_records(user_id, created_at DESC);
                    """
                )
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        def operation(connection: sqlite3.Connection) -> None:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    default_style TEXT NOT NULL DEFAULT 'classic',
                    history_enabled INTEGER NOT NULL DEFAULT 1,
                    save_wifi_history INTEGER NOT NULL DEFAULT 0,
                    language TEXT NOT NULL DEFAULT 'uz',
                    theme TEXT NOT NULL DEFAULT 'auto',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qr_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    qr_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    label TEXT NOT NULL,
                    style TEXT NOT NULL,
                    design_json TEXT NOT NULL DEFAULT '{}',
                    is_saved INTEGER NOT NULL DEFAULT 1,
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_records_user_created
                ON qr_records(user_id, created_at DESC);
                """
            )
            user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
            record_columns = {row[1] for row in connection.execute("PRAGMA table_info(qr_records)")}
            if "language" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'uz'")
            if "theme" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'auto'")
            if "design_json" not in record_columns:
                connection.execute("ALTER TABLE qr_records ADD COLUMN design_json TEXT NOT NULL DEFAULT '{}'")
            if "is_favorite" not in record_columns:
                connection.execute("ALTER TABLE qr_records ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")

        await self._run(operation)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def ensure_user(self, user_id: int) -> None:
        if self._pool is not None:
            await self._pool.execute(
                "INSERT INTO users(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING", user_id
            )
            return
        now = datetime.now(UTC).isoformat()
        await self._run(
            lambda conn: conn.execute(
                "INSERT OR IGNORE INTO users(user_id, created_at) VALUES(?, ?)", (user_id, now)
            )
        )

    async def get_settings(self, user_id: int) -> UserSettings:
        await self.ensure_user(user_id)
        if self._pool is not None:
            row = await self._pool.fetchrow(
                """SELECT default_style, history_enabled, save_wifi_history, language, theme
                   FROM users WHERE user_id = $1""",
                user_id,
            )
            return UserSettings(
                row["default_style"], bool(row["history_enabled"]), bool(row["save_wifi_history"]),
                row["language"], row["theme"],
            )

        def operation(conn: sqlite3.Connection) -> UserSettings:
            row = conn.execute(
                """SELECT default_style, history_enabled, save_wifi_history, language, theme
                   FROM users WHERE user_id = ?""", (user_id,),
            ).fetchone()
            assert row is not None
            return UserSettings(
                row["default_style"], bool(row["history_enabled"]), bool(row["save_wifi_history"]),
                row["language"], row["theme"],
            )

        return await self._run(operation)

    async def set_setting(self, user_id: int, field: str, value: Any) -> None:
        allowed = {"default_style", "history_enabled", "save_wifi_history", "language", "theme"}
        if field not in allowed:
            raise ValueError("Noto‘g‘ri sozlama")
        await self.ensure_user(user_id)
        if self._pool is not None:
            await self._pool.execute(f"UPDATE users SET {field} = $1 WHERE user_id = $2", value, user_id)
            return
        await self._run(lambda conn: conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id)))

    async def add_record(
        self, user_id: int, qr_type: str, payload: str, label: str, style: str,
        is_saved: bool, design_json: str = "{}",
    ) -> int:
        await self.ensure_user(user_id)
        design_json = self._safe_design(design_json)
        if self._pool is not None:
            return int(await self._pool.fetchval(
                """INSERT INTO qr_records(user_id, qr_type, payload, label, style, design_json, is_saved)
                   VALUES($1, $2, $3, $4, $5, $6::jsonb, $7) RETURNING id""",
                user_id, qr_type, payload, label, style, design_json, is_saved,
            ))
        now = datetime.now(UTC).isoformat()

        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                """INSERT INTO qr_records(
                       user_id, qr_type, payload, label, style, design_json, is_saved, created_at
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, qr_type, payload, label, style, design_json, int(is_saved), now),
            )
            return int(cursor.lastrowid)

        return await self._run(operation)

    async def get_record(self, record_id: int, user_id: int) -> QRRecord | None:
        if self._pool is not None:
            row = await self._pool.fetchrow(
                """SELECT id, user_id, qr_type, payload, label, style, is_saved,
                          created_at::text, design_json::text AS design_json, is_favorite
                   FROM qr_records WHERE id = $1 AND user_id = $2""", record_id, user_id,
            )
            return self._to_record(row) if row else None

        def operation(conn: sqlite3.Connection) -> QRRecord | None:
            row = conn.execute(
                "SELECT * FROM qr_records WHERE id = ? AND user_id = ?", (record_id, user_id)
            ).fetchone()
            return self._to_record(row) if row else None

        return await self._run(operation)

    async def update_style(self, record_id: int, user_id: int, style: str) -> None:
        if self._pool is not None:
            await self._pool.execute(
                "UPDATE qr_records SET style = $1 WHERE id = $2 AND user_id = $3", style, record_id, user_id
            )
            return
        await self._run(lambda conn: conn.execute(
            "UPDATE qr_records SET style = ? WHERE id = ? AND user_id = ?", (style, record_id, user_id)
        ))

    async def update_design(self, record_id: int, user_id: int, design_json: str) -> None:
        design_json = self._safe_design(design_json)
        if self._pool is not None:
            await self._pool.execute(
                "UPDATE qr_records SET design_json = $1::jsonb WHERE id = $2 AND user_id = $3",
                design_json, record_id, user_id,
            )
            return
        await self._run(lambda conn: conn.execute(
            "UPDATE qr_records SET design_json = ? WHERE id = ? AND user_id = ?",
            (design_json, record_id, user_id),
        ))

    async def set_favorite(self, record_id: int, user_id: int, value: bool) -> bool:
        if self._pool is not None:
            status = await self._pool.execute(
                "UPDATE qr_records SET is_favorite = $1 WHERE id = $2 AND user_id = $3",
                value, record_id, user_id,
            )
            return status.endswith("1")

        def operation(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                "UPDATE qr_records SET is_favorite = ? WHERE id = ? AND user_id = ?",
                (int(value), record_id, user_id),
            )
            return cursor.rowcount > 0

        return await self._run(operation)

    async def list_history(
        self, user_id: int, limit: int = 10, offset: int = 0, favorites_only: bool = False,
    ) -> list[QRRecord]:
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        if self._pool is not None:
            favorite_clause = "AND is_favorite = TRUE" if favorites_only else ""
            rows = await self._pool.fetch(
                f"""SELECT id, user_id, qr_type, payload, label, style, is_saved,
                           created_at::text, design_json::text AS design_json, is_favorite
                    FROM qr_records WHERE user_id = $1 AND is_saved = TRUE {favorite_clause}
                    ORDER BY id DESC LIMIT $2 OFFSET $3""", user_id, limit, offset,
            )
            return [self._to_record(row) for row in rows]

        def operation(conn: sqlite3.Connection) -> list[QRRecord]:
            favorite_clause = "AND is_favorite = 1" if favorites_only else ""
            rows = conn.execute(
                f"""SELECT * FROM qr_records WHERE user_id = ? AND is_saved = 1 {favorite_clause}
                    ORDER BY id DESC LIMIT ? OFFSET ?""", (user_id, limit, offset),
            ).fetchall()
            return [self._to_record(row) for row in rows]

        return await self._run(operation)

    async def history_count(self, user_id: int) -> int:
        if self._pool is not None:
            return int(await self._pool.fetchval(
                "SELECT COUNT(*) FROM qr_records WHERE user_id = $1 AND is_saved = TRUE", user_id
            ))
        return await self._run(lambda conn: int(conn.execute(
            "SELECT COUNT(*) FROM qr_records WHERE user_id = ? AND is_saved = 1", (user_id,)
        ).fetchone()[0]))

    async def delete_record(self, record_id: int, user_id: int) -> bool:
        if self._pool is not None:
            status = await self._pool.execute(
                "DELETE FROM qr_records WHERE id = $1 AND user_id = $2", record_id, user_id
            )
            return status.endswith("1")

        def operation(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("DELETE FROM qr_records WHERE id = ? AND user_id = ?", (record_id, user_id))
            return cursor.rowcount > 0

        return await self._run(operation)

    async def clear_history(self, user_id: int) -> int:
        if self._pool is not None:
            status = await self._pool.execute(
                "DELETE FROM qr_records WHERE user_id = $1 AND is_saved = TRUE", user_id
            )
            return int(status.rsplit(" ", 1)[-1])

        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM qr_records WHERE user_id = ? AND is_saved = 1", (user_id,))
            return cursor.rowcount

        return await self._run(operation)

    async def cleanup_temporary(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=1)
        if self._pool is not None:
            status = await self._pool.execute(
                "DELETE FROM qr_records WHERE is_saved = FALSE AND created_at < $1", cutoff
            )
            return int(status.rsplit(" ", 1)[-1])

        def operation(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "DELETE FROM qr_records WHERE is_saved = 0 AND created_at < ?", (cutoff.isoformat(),)
            )
            return cursor.rowcount

        return await self._run(operation)

    async def stats(self) -> dict[str, int]:
        local_now = datetime.now(ZoneInfo("Asia/Tashkent"))
        today = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        if self._pool is not None:
            users = int(await self._pool.fetchval("SELECT COUNT(*) FROM users"))
            total = int(await self._pool.fetchval("SELECT COUNT(*) FROM qr_records"))
            today_total = int(await self._pool.fetchval(
                "SELECT COUNT(*) FROM qr_records WHERE created_at >= $1", today
            ))
            return {"users": users, "total": total, "today": today_total}

        def operation(conn: sqlite3.Connection) -> dict[str, int]:
            users = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            total = int(conn.execute("SELECT COUNT(*) FROM qr_records").fetchone()[0])
            today_total = int(conn.execute(
                "SELECT COUNT(*) FROM qr_records WHERE created_at >= ?", (today.isoformat(),)
            ).fetchone()[0])
            return {"users": users, "total": total, "today": today_total}

        return await self._run(operation)

    @staticmethod
    def _safe_design(value: str) -> str:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Noto‘g‘ri dizayn ma’lumoti") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Dizayn obyekt bo‘lishi kerak")
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _to_record(row: Any) -> QRRecord:
        keys = set(row.keys())
        return QRRecord(
            id=int(row["id"]), user_id=int(row["user_id"]), qr_type=row["qr_type"],
            payload=row["payload"], label=row["label"], style=row["style"],
            is_saved=bool(row["is_saved"]), created_at=str(row["created_at"]),
            design_json=row["design_json"] if "design_json" in keys else "{}",
            is_favorite=bool(row["is_favorite"]) if "is_favorite" in keys else False,
        )
