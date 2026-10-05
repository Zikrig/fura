from __future__ import annotations

from typing import Any

from app.config import settings


def apply_max_api_url(bot: Any) -> None:
    bot.set_api_url(settings.MAX_API_URL)
