from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill
from PIL import Image as PILImage

from app.config import settings
from app.db.models import Entry

logger = logging.getLogger("fura_ochrana")

HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
HEADER_FONT = Font(bold=True)


def export_results_xlsx(
    entries: list[Entry],
    output_path: Path,
    *,
    timezone_name: str = "Europe/Moscow",
) -> Path:
    tz = ZoneInfo(timezone_name)
    wb = Workbook()
    ws = wb.active
    ws.title = "Результаты"

    headers = ["Дата", "Время", "Поселок", "Участок", "Тип авто", "Стоимость", "Фото"]
    for idx, title in enumerate(headers, start=1):
        cell = ws.cell(1, idx, title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 18

    for row_idx, entry in enumerate(entries, start=2):
        dt = entry.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(tz)
        sett = entry.settlement.name if entry.settlement else ""
        plot_name = entry.plot_name or ""
        vehicle_name = entry.vehicle.name if entry.vehicle else ""

        ws.cell(row_idx, 1, local.strftime("%d.%m.%Y"))
        ws.cell(row_idx, 2, local.strftime("%H:%M:%S"))
        ws.cell(row_idx, 3, sett)
        ws.cell(row_idx, 4, plot_name)
        ws.cell(row_idx, 5, vehicle_name)
        ws.cell(row_idx, 6, entry.price_amount)

        photo = _resolve_photo(entry.photo_path)
        if photo is None:
            ws.cell(row_idx, 7, "нет файла")
            continue
        try:
            img, height_pt = _excel_image(photo)
            ws.row_dimensions[row_idx].height = height_pt
            ws.add_image(img, f"G{row_idx}")
        except Exception:
            logger.exception("Не удалось вставить фото %s", photo)
            ws.cell(row_idx, 7, "не удалось вставить фото")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    _fix_image_targets(output_path)
    return output_path


_ABS_TARGET = re.compile(r'Target="(/xl/[^"]+)"')


def _relative_target(rels_name: str, abs_target: str) -> str:
    """openpyxl пишет Target=\"/xl/...\", часть программ тогда не показывает рисунок."""
    source_dir = Path(rels_name).parent.parent
    rel = os.path.relpath(abs_target.lstrip("/"), source_dir.as_posix())
    return rel.replace("\\", "/")


def _fix_image_targets(path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with ZipFile(path, "r") as zin, ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".rels") and b'Target="/xl/' in data:
                text = data.decode("utf-8")
                text = _ABS_TARGET.sub(
                    lambda m, name=info.filename: f'Target="{_relative_target(name, m.group(1))}"',
                    text,
                )
                data = text.encode("utf-8")
            zout.writestr(info, data)
    tmp.replace(path)


def _resolve_photo(stored: str) -> Path | None:
    raw = Path(stored or "")
    if raw.is_file():
        return raw
    if raw.name:
        candidate = settings.photos_dir / raw.name
        if candidate.is_file():
            return candidate
    return None


class _PngImage(XLImage):
    """openpyxl 3.1.5 читает jpeg через img.fp, Pillow 11 отдаёт пустые байты — картинки в xlsx нет."""

    def __init__(self, image: PILImage.Image):
        super().__init__(image)
        self.format = "png"

    def _data(self) -> bytes:
        image = self.ref
        if not isinstance(image, PILImage.Image):
            image = PILImage.open(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()


def _excel_image(src: Path) -> tuple[_PngImage, float]:
    image = PILImage.open(src)
    image = image.convert("RGB")
    image.thumbnail((240, 180))
    img = _PngImage(image)
    img.width = image.width
    img.height = image.height
    height_pt = max(72, image.height * 0.75 + 6)
    return img, height_pt


def parse_date_ddmmyyyy(value: str) -> datetime | None:
    value = (value or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_date_range(value: str) -> tuple[datetime, datetime] | None:
    raw = (value or "").strip().replace(" ", "")
    if "-" not in raw:
        return None
    left, right = raw.split("-", 1)
    d1 = parse_date_ddmmyyyy(left)
    d2 = parse_date_ddmmyyyy(right)
    if not d1 or not d2:
        return None
    return d1, d2
