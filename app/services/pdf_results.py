from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF
from PIL import Image as PILImage

from app.db.models import Entry
from app.services.excel_results import _resolve_photo

logger = logging.getLogger("fura_ochrana")

_HEADERS = ("Дата", "Время", "Поселок", "Участок", "Тип авто", "Стоимость", "Фото")
_WEIGHTS = (22, 18, 52, 36, 40, 24, 48)
_ROW_H = 32
_HEADER_H = 8


def export_results_pdf(
    entries: list[Entry],
    output_path: Path,
    *,
    timezone_name: str = "Europe/Moscow",
) -> Path:
    tz = ZoneInfo(timezone_name)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    regular, bold = _font_files()
    pdf.add_font("Report", "", str(regular))
    pdf.add_font("Report", "B", str(bold))
    pdf.set_margins(8, 8, 8)
    pdf.add_page()

    widths = _widths(pdf.epw)
    _draw_header(pdf, widths)

    if not entries:
        pdf.set_font("Report", "", 10)
        pdf.cell(sum(widths), 10, "Нет записей", border=1, align="C")
    else:
        for entry in entries:
            if pdf.get_y() + _ROW_H > pdf.h - pdf.b_margin:
                pdf.add_page()
                _draw_header(pdf, widths)
            _draw_row(pdf, widths, _row_values(entry, tz), _jpeg_bytes(entry.photo_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return output_path


def _font_files() -> tuple[Path, Path]:
    pairs = (
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
    )
    for regular, bold in pairs:
        if regular.is_file() and bold.is_file():
            return regular, bold
    raise FileNotFoundError("Нет шрифта с кириллицей для PDF (DejaVu или Arial)")


def _widths(page_width: float) -> list[float]:
    total = sum(_WEIGHTS)
    return [page_width * weight / total for weight in _WEIGHTS]


def _draw_header(pdf: FPDF, widths: list[float]) -> None:
    pdf.set_font("Report", "B", 8)
    pdf.set_fill_color(217, 225, 242)
    for title, width in zip(_HEADERS, widths, strict=True):
        pdf.cell(width, _HEADER_H, title, border=1, align="C", fill=True)
    pdf.ln(_HEADER_H)


def _draw_row(pdf: FPDF, widths: list[float], values: list[str], photo: bytes | None) -> None:
    y = pdf.get_y()
    x = pdf.l_margin
    pdf.set_font("Report", "", 8)
    for text, width in zip(values, widths[:-1], strict=True):
        pdf.rect(x, y, width, _ROW_H)
        pdf.set_xy(x + 1, y + (_ROW_H - 4) / 2)
        pdf.cell(width - 2, 4, _fit(text, width - 2))
        x += width

    photo_w = widths[-1]
    pdf.rect(x, y, photo_w, _ROW_H)
    if photo:
        try:
            pdf.image(
                BytesIO(photo),
                x=x + 1,
                y=y + 1,
                w=photo_w - 2,
                h=_ROW_H - 2,
                keep_aspect_ratio=True,
            )
        except Exception:
            logger.exception("Не удалось вставить фото в PDF")
            _photo_label(pdf, x, y, photo_w, "ошибка фото")
    else:
        _photo_label(pdf, x, y, photo_w, "нет фото")
    pdf.set_xy(pdf.l_margin, y + _ROW_H)


def _photo_label(pdf: FPDF, x: float, y: float, width: float, text: str) -> None:
    pdf.set_xy(x + 1, y + (_ROW_H - 4) / 2)
    pdf.cell(width - 2, 4, text, align="C")


def _fit(text: str, width_mm: float) -> str:
    text = " ".join(str(text or "").split())
    max_chars = max(4, int(width_mm / 1.8))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _row_values(entry: Entry, tz: ZoneInfo) -> list[str]:
    dt = entry.created_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local = dt.astimezone(tz)
    amount = entry.price_amount
    amount_text = str(int(amount)) if float(amount).is_integer() else f"{amount:.2f}"
    return [
        local.strftime("%d.%m.%Y"),
        local.strftime("%H:%M:%S"),
        entry.settlement.name if entry.settlement else "",
        entry.plot_name or "",
        entry.vehicle.name if entry.vehicle else "",
        amount_text,
    ]


def _jpeg_bytes(stored: str) -> bytes | None:
    path = _resolve_photo(stored)
    if path is None:
        return None
    image = PILImage.open(path)
    image = image.convert("RGB")
    image.thumbnail((640, 480))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
