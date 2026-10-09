from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for
from app.keyboards.menus import back_row, entry_vehicle_keyboard, settlements_pick_keyboard
from app.services.access import Role, can_use_bot
from app.services.media import download_to_photos, first_image_url_from_message_body
from app.states import EntryFlow

router = Router("entry")


def _plot_keyboard(back_payload: str = "entry:back_settlement") -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(*back_row(back_payload))
    return kb


def _settlements_for(repo: Repo, user_id: int, role: Role) -> list:
    if role != Role.GUARD:
        return repo.list_settlements()
    staff = repo.get_staff(user_id, with_settlements=True)
    if not staff:
        return []
    return list(staff.settlements)


async def _ask_plot(
    event,
    context: MemoryContext,
    *,
    settlement_id: int,
    back_payload: str,
) -> None:
    await context.update_data(settlement_id=settlement_id, settlement_back=back_payload)
    await context.set_state(EntryFlow.plot)
    await edit_or_answer(event, "Введите участок:", _plot_keyboard(back_payload))


async def _show_entry_vehicles(event: MessageCallback, context: MemoryContext) -> None:
    await context.set_state(EntryFlow.vehicle)
    with session_scope() as session:
        vehicles = Repo(session).list_vehicles()
    await edit_or_answer(event, "Выберите тип авто:", entry_vehicle_keyboard(vehicles, 0))


async def _show_entry_settlements(event: MessageCallback, context: MemoryContext, page: int) -> None:
    user_id = event.callback.user.user_id
    role = role_for(user_id)
    with session_scope() as session:
        items = _settlements_for(Repo(session), user_id, role)
    if role == Role.GUARD and len(items) == 1:
        await _ask_plot(
            event,
            context,
            settlement_id=items[0].id,
            back_payload="entry:back_vehicle",
        )
        return
    if not items:
        text = (
            "Вам не назначены поселки. Обратитесь к администратору."
            if role == Role.GUARD
            else "Сначала добавьте поселки."
        )
        await edit_or_answer(
            event,
            text,
            InlineKeyboardBuilder().row(*back_row("menu:main")),
        )
        await clear_ctx(context)
        return
    await context.set_state(EntryFlow.settlement)
    kb = settlements_pick_keyboard(
        items,
        page=page,
        pick_prefix="entry:sett",
        page_prefix="entry:settpage",
        back_payload="entry:back_vehicle",
    )
    await edit_or_answer(event, "Выберите поселок:", kb)


@router.message_callback(F.callback.payload == "entry:start")
async def entry_start(event: MessageCallback, context: MemoryContext):
    await ack(event)
    user_id = event.callback.user.user_id
    role = role_for(user_id)
    if not can_use_bot(role):
        await edit_or_answer(event, "Нет доступа.")
        return
    await clear_ctx(context)
    await context.set_state(EntryFlow.photo)
    kb = InlineKeyboardBuilder()
    kb.row(*back_row("menu:main"))
    await edit_or_answer(event, "Отправьте фото въезда:", kb)


@router.message_callback(F.callback.payload == "entry:back_photo")
async def entry_back_photo(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(EntryFlow.photo)
    kb = InlineKeyboardBuilder()
    kb.row(*back_row("menu:main"))
    await edit_or_answer(event, "Отправьте фото въезда:", kb)


@router.message_created(EntryFlow.photo)
async def entry_photo(event: MessageCreated, context: MemoryContext):
    url = first_image_url_from_message_body(event.message.body)
    if not url:
        kb = InlineKeyboardBuilder()
        kb.row(*back_row("menu:main"))
        await event.message.answer("Нужно фото.", attachments=[kb.as_markup()])
        return
    path = await download_to_photos(url)
    await context.update_data(photo_path=str(path))
    await context.set_state(EntryFlow.vehicle)
    with session_scope() as session:
        vehicles = Repo(session).list_vehicles()
    if not vehicles:
        await clear_ctx(context)
        await event.message.answer(
            "Список транспорта пуст. Админ/менеджер должен заполнить раздел «Транспорт».",
            attachments=[InlineKeyboardBuilder().row(*back_row("menu:main")).as_markup()],
        )
        return
    kb = entry_vehicle_keyboard(vehicles, 0)
    await event.message.answer("Выберите тип авто:", attachments=[kb.as_markup()])


@router.message_callback(EntryFlow.vehicle, F.callback.payload.startswith("entry:vehpage:"))
async def entry_veh_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        vehicles = Repo(session).list_vehicles()
    await edit_or_answer(event, "Выберите тип авто:", entry_vehicle_keyboard(vehicles, page))


@router.message_callback(EntryFlow.vehicle, F.callback.payload.startswith("entry:veh:"))
async def entry_pick_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    vehicle_id = int(event.callback.payload.split(":")[-1])
    await context.update_data(vehicle_id=vehicle_id)
    await _show_entry_settlements(event, context, 0)


@router.message_callback(EntryFlow.vehicle, F.callback.payload == "entry:back_vehicle")
@router.message_callback(EntryFlow.settlement, F.callback.payload == "entry:back_vehicle")
@router.message_callback(EntryFlow.plot, F.callback.payload == "entry:back_vehicle")
async def entry_back_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await _show_entry_vehicles(event, context)


@router.message_callback(EntryFlow.plot, F.callback.payload == "entry:back_settlement")
async def entry_back_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    user_id = event.callback.user.user_id
    role = role_for(user_id)
    if role == Role.GUARD:
        with session_scope() as session:
            assigned = _settlements_for(Repo(session), user_id, role)
        if len(assigned) <= 1:
            await _show_entry_vehicles(event, context)
            return
    await _show_entry_settlements(event, context, 0)


@router.message_callback(EntryFlow.settlement, F.callback.payload.startswith("entry:settpage:"))
async def entry_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    await _show_entry_settlements(event, context, page)


@router.message_callback(EntryFlow.settlement, F.callback.payload.startswith("entry:sett:"))
async def entry_pick_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    settlement_id = int(event.callback.payload.split(":")[-1])
    user_id = event.callback.user.user_id
    role = role_for(user_id)
    with session_scope() as session:
        allowed = {item.id for item in _settlements_for(Repo(session), user_id, role)}
    if settlement_id not in allowed:
        await edit_or_answer(event, "Этот поселок вам не назначен.", _plot_keyboard("entry:back_vehicle"))
        return
    await _ask_plot(
        event,
        context,
        settlement_id=settlement_id,
        back_payload="entry:back_settlement",
    )


@router.message_created(EntryFlow.plot)
async def entry_plot(event: MessageCreated, context: MemoryContext):
    plot_name = ((event.message.body.text if event.message.body else "") or "").strip()
    data = await context.get_data()
    kb = _plot_keyboard(data.get("settlement_back") or "entry:back_settlement")
    if not plot_name:
        await event.message.answer("Участок пустой.", attachments=[kb.as_markup()])
        return
    settlement_id = data.get("settlement_id")
    vehicle_id = data.get("vehicle_id")
    if not settlement_id or not vehicle_id:
        await event.message.answer(
            "Данные въезда потеряны, начните заново.",
            attachments=[InlineKeyboardBuilder().row(*back_row("menu:main")).as_markup()],
        )
        await clear_ctx(context)
        return
    user_id = event.message.sender.user_id if event.message.sender else None
    if not user_id:
        return
    await _finish_entry(event, context, user_id, int(vehicle_id), int(settlement_id), plot_name)


async def _finish_entry(
    event,
    context: MemoryContext,
    user_id: int,
    vehicle_id: int,
    settlement_id: int,
    plot_name: str,
) -> None:
    data = await context.get_data()
    photo_path = data.get("photo_path")
    if not photo_path:
        await edit_or_answer(
            event,
            "Фото потеряно, начните заново.",
            InlineKeyboardBuilder().row(*back_row("menu:main")),
        )
        await clear_ctx(context)
        return

    role = role_for(user_id)
    now = datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    with session_scope() as session:
        repo = Repo(session)
        allowed = {item.id for item in _settlements_for(repo, user_id, role)}
        if settlement_id not in allowed:
            await edit_or_answer(
                event,
                "Этот поселок вам не назначен.",
                InlineKeyboardBuilder().row(*back_row("menu:main")),
            )
            await clear_ctx(context)
            return
        price = repo.get_price(vehicle_id, settlement_id)
        amount = price.amount if price else 0.0
        vehicle = repo.get_vehicle(vehicle_id)
        settlement = repo.get_settlement(settlement_id)
        repo.add_entry(
            created_at=now,
            settlement_id=settlement_id,
            plot_name=plot_name,
            vehicle_id=vehicle_id,
            price_amount=amount,
            photo_path=photo_path,
            reporter_user_id=user_id,
        )
        sett = settlement.name if settlement else "?"
        veh_name = vehicle.name if vehicle else "?"

    await clear_ctx(context)
    text = (
        "✅ Въезд зафиксирован\n"
        f"Дата: {now.strftime('%d.%m.%Y')}\n"
        f"Время: {now.strftime('%H:%M:%S')}\n"
        f"Поселок: {sett}\n"
        f"Участок: {plot_name}\n"
        f"Тип авто: {veh_name}\n"
        f"Стоимость: {amount}"
    )
    await edit_or_answer(event, text, InlineKeyboardBuilder().row(*back_row("menu:main")))
