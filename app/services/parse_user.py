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


def _enum_value(value) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").lower()


def _uid(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def user_ref_from_message(message) -> tuple[int | None, str]:
    """
    user_id человека из сообщения админа:
    пересланное сообщение, упоминание, контакт, либо текст с id/ссылкой.
    Отправитель самого сообщения (админ) не используется.
    """
    link = getattr(message, "link", None)
    if link is not None and _enum_value(getattr(link, "type", None)) == "forward":
        sender = getattr(link, "sender", None)
        uid = _uid(getattr(sender, "user_id", None))
        if uid:
            return uid, ""

    body = getattr(message, "body", None)
    markup = getattr(body, "markup", None) or []
    for item in markup:
        if _enum_value(getattr(item, "type", None)) not in {"user_mention", "usermention"}:
            continue
        uid = _uid(getattr(item, "user_id", None))
        if uid:
            return uid, (getattr(item, "user_link", None) or "")

    attachments = getattr(body, "attachments", None) or []
    for item in attachments:
        if _enum_value(getattr(item, "type", None)) != "contact":
            continue
        payload = getattr(item, "payload", None)
        info = getattr(payload, "max_info", None)
        uid = _uid(getattr(info, "user_id", None))
        if uid:
            return uid, ""

    text = getattr(body, "text", None) or ""
    return parse_max_user_ref(text)
