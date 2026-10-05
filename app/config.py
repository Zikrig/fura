from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out


def _resolve_path(raw: str, default: str) -> Path:
    value = (raw or default).strip()
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


class Settings:
    BOT_TOKEN: str = (os.getenv("MAX_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    ADMIN_USER_IDS: set[int] = _parse_ids(os.getenv("ADMIN_USER_IDS", "") or os.getenv("ADMINS", ""))
    MAX_API_URL: str = (
        os.getenv("MAX_API_URL", "https://platform-api2.max.ru").strip().rstrip("/")
    )
    TIMEZONE: str = (
        os.getenv("TIMEZONE") or os.getenv("APP_TZ") or "Europe/Moscow"
    ).strip()

    WEBHOOK_PUBLIC_URL: str | None = os.getenv("WEBHOOK_PUBLIC_URL", "").strip() or None
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/") or "/"
    WEBHOOK_SECRET: str | None = os.getenv("WEBHOOK_SECRET", "").strip() or None
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))

    DATA_DIR: Path = _resolve_path(os.getenv("DATA_DIR", ""), "data")
    SQLITE_PATH: Path = _resolve_path(os.getenv("SQLITE_PATH", ""), "data/bot.sqlite3")

    @property
    def photos_dir(self) -> Path:
        return self.DATA_DIR / "photos"

    @property
    def exports_dir(self) -> Path:
        return self.DATA_DIR / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
