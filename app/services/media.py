from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config import settings


def first_image_url_from_message_body(body) -> str | None:
    if not body or not getattr(body, "attachments", None):
        return None
    from maxapi.enums.attachment import AttachmentType

    for att in body.attachments:
        if att.payload is None:
            continue
        url = getattr(att.payload, "url", None)
        if not url:
            continue
        t = att.type
        if t == AttachmentType.IMAGE or t == "image":
            return url
        if t == AttachmentType.FILE or t == "file":
            fn = (getattr(att, "filename", None) or "").lower()
            path = urlparse(url).path.lower()
            if any(x.endswith(ext) for x in (fn, path) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
                return url
    return None


def first_file_url_from_message_body(body) -> tuple[str | None, str]:
    """URL файла и имя (для Excel upload)."""
    if not body or not getattr(body, "attachments", None):
        return None, ""
    from maxapi.enums.attachment import AttachmentType

    for att in body.attachments:
        if att.payload is None:
            continue
        url = getattr(att.payload, "url", None)
        if not url:
            continue
        t = att.type
        fn = getattr(att, "filename", None) or ""
        if t == AttachmentType.FILE or t == "file":
            return url, fn
        if (fn or url).lower().endswith((".xlsx", ".xlsm", ".xls")):
            return url, fn
    return None, ""


def _guess_ext(url: str, fallback: str = ".jpg") -> str:
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".xlsx"):
        if path.endswith(ext):
            return ext
    return fallback


def _download_sync(url: str, dest: Path) -> None:
    req = Request(url, headers={"User-Agent": "fura-ochrana-bot/1.0"})
    with urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


async def download_to_photos(url: str) -> Path:
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    ext = _guess_ext(url, ".jpg")
    dest = settings.photos_dir / f"{uuid.uuid4().hex}{ext}"
    tmp = settings.photos_dir / f".tmp_{uuid.uuid4().hex}"
    try:
        await asyncio.to_thread(_download_sync, url, tmp)
        tmp.replace(dest)
        return dest
    except Exception:
        if tmp.is_file():
            tmp.unlink()
        raise


async def download_bytes(url: str) -> bytes:
    tmp = settings.exports_dir / f".dl_{uuid.uuid4().hex}"
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(_download_sync, url, tmp)
        return tmp.read_bytes()
    finally:
        if tmp.is_file():
            tmp.unlink()
