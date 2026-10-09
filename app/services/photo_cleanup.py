from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.database import session_scope
from app.db.repo import Repo, _unlink_entry_photo

logger = logging.getLogger("fura_ochrana")

PHOTO_TTL = timedelta(days=30)


def purge_old_photos(now: datetime | None = None) -> int:
    """Удаляет файлы фото въездов старше 30 дней. Сами записи въездов остаются."""
    moment = now or datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    cutoff = moment - PHOTO_TTL
    with session_scope() as session:
        repo = Repo(session)
        expired = repo.take_expired_photo_paths(cutoff)
        live_names = repo.live_photo_names()

    removed = 0
    for stored in expired:
        _unlink_entry_photo(stored)
        removed += 1

    photos_dir = settings.photos_dir
    if not photos_dir.is_dir():
        return removed
    deadline = time.time() - PHOTO_TTL.total_seconds()
    for path in photos_dir.iterdir():
        if not path.is_file() or path.name in live_names:
            continue
        try:
            if path.stat().st_mtime >= deadline:
                continue
            path.unlink()
            removed += 1
        except OSError:
            logger.exception("Не удалось удалить старое фото %s", path)
    return removed
