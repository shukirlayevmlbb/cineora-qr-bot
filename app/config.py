from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Small .env loader to keep runtime dependencies minimal."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    database_path: Path
    database_url: str
    admin_ids: frozenset[int]
    log_level: str
    webapp_url: str
    webapp_preview: bool

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN topilmadi. .env faylini .env.example asosida yarating.")

        raw_admins = os.getenv("ADMIN_IDS", "")
        admins: set[int] = set()
        for item in raw_admins.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                admins.add(int(item))
            except ValueError as exc:
                raise RuntimeError(f"ADMIN_IDS ichida noto'g'ri ID: {item}") from exc

        database_path = Path(os.getenv("DATABASE_PATH", "data/qrbot.sqlite3"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            bot_token=token,
            database_path=database_path,
            database_url=os.getenv("DATABASE_URL", "").strip(),
            admin_ids=frozenset(admins),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
            webapp_preview=os.getenv("WEBAPP_PREVIEW", "false").strip().lower() in {"1", "true", "yes"},
        )
