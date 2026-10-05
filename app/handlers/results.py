from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for, send_file_to_user
from app.keyboards.menus import back_row, results_period_keyboard, results_settlement_keyboard
from app.services.access import can_manage_directory
from app.services.excel_results import export_results_xlsx, parse_date_ddmmyyyy, parse_date_range
from app.states import ResultsFlow

router = Router("results")


def _guard(user_id: int) -> bool:
    return can_manage_directory(role_for(user_id))


def _day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    return start, end


@router.message_callback(F.callback.payload == "res:period")
async def res_period(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    if not _guard(event.callback.user.user_id):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    await edit_or_answer(event, "Выберите период выгрузки:", results_period_keyboard())


@router.message_callback(F.callback.payload.startswith("res:p:"))
async def res_pick_period(event: MessageCallback, context: MemoryContext):
    await ack(event)
    if not _guard(event.callback.user.user_id):
        return
    kind = event.callback.payload.split(":")[-1]
    now = datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)

    if kind == "date":
        await context.set_state(ResultsFlow.date)
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("res:period"))
        await edit_or_answer(event, "Введите дату в формате 14.08.2026", kb)
        return
    if kind == "range":
        await context.set_state(ResultsFlow.range)
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("res:period"))
        await edit_or_answer(
            event,
            "Введите диапазон в формате 14.08.2026-16.08.2026",
            kb,
        )
        return

    date_from: datetime | None = None
    date_to: datetime | None = None
    if kind == "today":
        date_from, date_to = _day_bounds(now)
    elif kind == "yesterday":
        date_from, date_to = _day_bounds(now - timedelta(days=1))
    elif kind == "3d":
        date_from = _day_bounds(now - timedelta(days=2))[0]
        date_to = _day_bounds(now)[1]
    elif kind == "week":
        date_from = _day_bounds(now - timedelta(days=6))[0]
        date_to = _day_bounds(now)[1]
    elif kind == "all":
        date_from, date_to = None, None
    else:
        await edit_or_answer(event, "Неизвестный период.", results_period_keyboard())
        return

    await context.update_data(
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )
    await _ask_settlement(event)


@router.message_created(ResultsFlow.date)
async def res_date_input(event: MessageCreated, context: MemoryContext):
    text = ((event.message.body.text if event.message.body else "") or "").strip()
    day = parse_date_ddmmyyyy(text)
    if not day:
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("res:period"))
        await event.message.answer("Неверный формат. Пример: 14.08.2026", attachments=[kb.as_markup()])
        return
    date_from, date_to = _day_bounds(day)
    await context.update_data(date_from=date_from.isoformat(), date_to=date_to.isoformat())
    await context.set_state(None)
    with session_scope() as session:
        items = Repo(session).list_settlements()
    await event.message.answer(
        "Выберите поселок:",
        attachments=[results_settlement_keyboard(items, 0).as_markup()],
    )


@router.message_created(ResultsFlow.range)
async def res_range_input(event: MessageCreated, context: MemoryContext):
    text = ((event.message.body.text if event.message.body else "") or "").strip()
    parsed = parse_date_range(text)
    if not parsed:
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("res:period"))
        await event.message.answer(
            "Неверный формат. Пример: 14.08.2026-16.08.2026",
            attachments=[kb.as_markup()],
        )
        return
    d1, d2 = parsed
    date_from = _day_bounds(d1)[0]
    date_to = _day_bounds(d2)[1]
    await context.update_data(date_from=date_from.isoformat(), date_to=date_to.isoformat())
    await context.set_state(None)
    with session_scope() as session:
        items = Repo(session).list_settlements()
    await event.message.answer(
        "Выберите поселок:",
        attachments=[results_settlement_keyboard(items, 0).as_markup()],
    )


async def _ask_settlement(event: MessageCallback) -> None:
    with session_scope() as session:
        items = Repo(session).list_settlements()
    await edit_or_answer(event, "Выберите поселок:", results_settlement_keyboard(items, 0))


@router.message_callback(F.callback.payload.startswith("res:settpage:"))
async def res_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        items = Repo(session).list_settlements()
    await edit_or_answer(event, "Выберите поселок:", results_settlement_keyboard(items, page))


@router.message_callback(F.callback.payload.startswith("res:sett:"))
async def res_export(event: MessageCallback, context: MemoryContext):
    await ack(event)
    if not _guard(event.callback.user.user_id):
        return
    token = event.callback.payload.split(":")[-1]
    settlement_id = None if token == "all" else int(token)
    data = await context.get_data()
    date_from = datetime.fromisoformat(data["date_from"]) if data.get("date_from") else None
    date_to = datetime.fromisoformat(data["date_to"]) if data.get("date_to") else None

    path = settings.exports_dir / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with session_scope() as session:
        entries = Repo(session).list_entries(
            date_from=date_from,
            date_to=date_to,
            settlement_id=settlement_id,
        )
        count = len(entries)
        export_results_xlsx(entries, path, timezone_name=settings.TIMEZONE)

    bot = event._ensure_bot()
    await send_file_to_user(
        bot,
        event.callback.user.user_id,
        path,
        f"Результаты: {count} записей",
    )
    await clear_ctx(context)
    await edit_or_answer(
        event,
        f"Выгрузка готова ({count} записей).",
        results_period_keyboard(),
    )
