from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from maxapi import Bot, Dispatcher
from maxapi.enums.update import UpdateType

from app.config import settings
from app.db.database import init_db
from app.handlers import setup_routers
from app.max_api_url import apply_max_api_url

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class MoscowFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, MOSCOW_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(MoscowFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def main() -> None:
    _setup_logging()
    logger = logging.getLogger("fura_ochrana")

    if not settings.BOT_TOKEN:
        raise RuntimeError("Задайте MAX_BOT_TOKEN (или BOT_TOKEN) в .env")
    if not settings.WEBHOOK_PUBLIC_URL:
        raise RuntimeError("Задайте WEBHOOK_PUBLIC_URL в .env")

    init_db()
    bot = Bot(token=settings.BOT_TOKEN)
    apply_max_api_url(bot)

    dp = Dispatcher()
    setup_routers(dp)

    await bot.subscribe_webhook(
        url=settings.WEBHOOK_PUBLIC_URL,
        update_types=[
            UpdateType.MESSAGE_CREATED,
            UpdateType.MESSAGE_CALLBACK,
            UpdateType.BOT_STARTED,
        ],
        secret=settings.WEBHOOK_SECRET,
    )
    logger.info("Webhook subscribed: %s", settings.WEBHOOK_PUBLIC_URL)

    await dp.handle_webhook(
        bot,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT,
        path=settings.WEBHOOK_PATH,
        secret=settings.WEBHOOK_SECRET,
    )


if __name__ == "__main__":
    asyncio.run(main())
