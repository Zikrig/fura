from __future__ import annotations

import re

# Ссылки профиля MAX / числовой user_id (паттерны из рабочих ботов + типичные URL).
_ID_IN_URL = re.compile(
    r"(?:max\.ru/(?:u|user|id)/|user_id=|id=|/id/)(\d{3,})",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"^\d{3,}$")
_ANY_LONG_DIGITS = re.compile(r"(?<!\d)(\d{6,})(?!\d)")


def parse_max_user_ref(text: str) -> tuple[int | None, str]:
    """
    Возвращает (user_id или None, исходную ссылку/строку).
    Принимает числовой id или ссылку, из которой удаётся извлечь id.
    """
    raw = (text or "").strip()
    if not raw:
        return None, ""
    if _DIGITS.fullmatch(raw):
        return int(raw), raw
    m = _ID_IN_URL.search(raw)
    if m:
        return int(m.group(1)), raw
    m2 = _ANY_LONG_DIGITS.search(raw)
    if m2 and ("max.ru" in raw.lower() or "http" in raw.lower()):
        return int(m2.group(1)), raw
    return None, raw
