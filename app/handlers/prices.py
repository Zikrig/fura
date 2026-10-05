from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for, send_file_to_user
from app.keyboards.menus import back_row, price_menu_keyboard
from app.services.access import can_manage_directory
from app.services.excel_prices import export_prices_xlsx, import_prices_xlsx
from app.services.media import download_bytes, first_file_url_from_message_body
from app.states import PriceFlow

router = Router("prices")


def _guard(user_id: int) -> bool:
    return can_manage_directory(role_for(user_id))


@router.message_callback(F.callback.payload == "price:menu")
async def price_menu(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    if not _guard(event.callback.user.user_id):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    await edit_or_answer(
        event,
        "Таблица Цены: транспорт × поселки.\n"
        "Выгрузите Excel, отредактируйте (новые строки/столбцы) и загрузите обратно.",
        price_menu_keyboard(),
    )


@router.message_callback(F.callback.payload == "price:export")
async def price_export(event: MessageCallback, context: MemoryContext):
    await ack(event)
    if not _guard(event.callback.user.user_id):
        return
    path = settings.exports_dir / "prices.xlsx"
    with session_scope() as session:
        export_prices_xlsx(Repo(session), path)
    bot = event._ensure_bot()
    await send_file_to_user(bot, event.callback.user.user_id, path, "Таблица цен")
    await edit_or_answer(event, "Файл отправлен.", price_menu_keyboard())


@router.message_callback(F.callback.payload == "price:import")
async def price_import_ask(event: MessageCallback, context: MemoryContext):
    await ack(event)
    if not _guard(event.callback.user.user_id):
        return
    await context.set_state(PriceFlow.waiting_file)
    kb = InlineKeyboardBuilder()
    kb.row(*back_row("price:menu"))
    await edit_or_answer(event, "Пришлите Excel-файл (.xlsx) с матрицей цен.", kb)


@router.message_created(PriceFlow.waiting_file)
async def price_import_file(event: MessageCreated, context: MemoryContext):
    url, filename = first_file_url_from_message_body(event.message.body)
    if not url:
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("price:menu"))
        await event.message.answer("Нужен файл .xlsx", attachments=[kb.as_markup()])
        return
    raw = await download_bytes(url)
    with session_scope() as session:
        stats = import_prices_xlsx(Repo(session), raw)
    await clear_ctx(context)
    await event.message.answer(
        "Импорт выполнен.\n"
        f"Новый транспорт: {stats['created_vehicles']}\n"
        f"Новые поселки: {stats['created_settlements']}\n"
        f"Обновлено цен: {stats['updated_prices']}",
        attachments=[price_menu_keyboard().as_markup()],
    )
