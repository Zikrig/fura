from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
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


@router.message_callback(F.callback.payload == "entry:start")
async def entry_start(event: MessageCallback, context: MemoryContext):
    await ack(event)
    user_id = event.callback.user.user_id
    role = role_for(user_id)
    if not can_use_bot(role):
        await edit_or_answer(event, "Нет доступа.")
        return
    await context.set_state(EntryFlow.photo)
    await context.update_data({})
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


def _plot_prompt_kb(back_payload: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(*back_row(back_payload))
    return kb


async def _ask_plot(event, context: MemoryContext, settlement_id: int, back_payload: str) -> None:
    await context.update_data(settlement_id=settlement_id, plot_back=back_payload)
    await context.set_state(EntryFlow.plot)
    await edit_or_answer(event, "Введите участок:", _plot_prompt_kb(back_payload))


@router.message_callback(EntryFlow.vehicle, F.callback.payload.startswith("entry:veh:"))
async def entry_pick_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    vehicle_id = int(event.callback.payload.split(":")[-1])
    await context.update_data(vehicle_id=vehicle_id)
    user_id = event.callback.user.user_id
    role = role_for(user_id)

    if role == Role.GUARD:
        with session_scope() as session:
            staff = Repo(session).get_staff(user_id)
            settlement_id = staff.settlement_id if staff else None
        if not settlement_id:
            await edit_or_answer(
                event,
                "У охранника не указан поселок. Попросите менеджера заполнить карточку.",
                InlineKeyboardBuilder().row(*back_row("menu:main")),
            )
            await clear_ctx(context)
            return
        await _ask_plot(event, context, settlement_id, "entry:back_vehicle")
        return

    with session_scope() as session:
        settlements = Repo(session).list_settlements()
    if not settlements:
        await edit_or_answer(
            event,
            "Сначала добавьте поселки.",
            InlineKeyboardBuilder().row(*back_row("menu:main")),
        )
        await clear_ctx(context)
        return
    await context.set_state(EntryFlow.settlement)
    kb = settlements_pick_keyboard(
        settlements,
        page=0,
        pick_prefix="entry:sett",
        page_prefix="entry:settpage",
        back_payload="entry:back_vehicle",
    )
    await edit_or_answer(event, "Выберите поселок:", kb)


@router.message_callback(EntryFlow.vehicle, F.callback.payload == "entry:back_vehicle")
@router.message_callback(EntryFlow.settlement, F.callback.payload == "entry:back_vehicle")
@router.message_callback(EntryFlow.plot, F.callback.payload == "entry:back_vehicle")
async def entry_back_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(EntryFlow.vehicle)
    with session_scope() as session:
        vehicles = Repo(session).list_vehicles()
    await edit_or_answer(event, "Выберите тип авто:", entry_vehicle_keyboard(vehicles, 0))


@router.message_callback(EntryFlow.settlement, F.callback.payload.startswith("entry:settpage:"))
async def entry_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        settlements = Repo(session).list_settlements()
    kb = settlements_pick_keyboard(
        settlements,
        page=page,
        pick_prefix="entry:sett",
        page_prefix="entry:settpage",
        back_payload="entry:back_vehicle",
    )
    await edit_or_answer(event, "Выберите поселок:", kb)


@router.message_callback(EntryFlow.settlement, F.callback.payload.startswith("entry:sett:"))
async def entry_pick_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    settlement_id = int(event.callback.payload.split(":")[-1])
    await _ask_plot(event, context, settlement_id, "entry:back_settlement")


@router.message_callback(EntryFlow.plot, F.callback.payload == "entry:back_settlement")
async def entry_back_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(EntryFlow.settlement)
    with session_scope() as session:
        settlements = Repo(session).list_settlements()
    kb = settlements_pick_keyboard(
        settlements,
        page=0,
        pick_prefix="entry:sett",
        page_prefix="entry:settpage",
        back_payload="entry:back_vehicle",
    )
    await edit_or_answer(event, "Выберите поселок:", kb)


@router.message_created(EntryFlow.plot)
async def entry_plot_text(event: MessageCreated, context: MemoryContext):
    plot_name = ((event.message.body.text if event.message.body else "") or "").strip()
    data = await context.get_data()
    back = data.get("plot_back") or "entry:back_vehicle"
    if not plot_name:
        await event.message.answer(
            "Участок пустой. Введите участок:",
            attachments=[_plot_prompt_kb(back).as_markup()],
        )
        return
    user_id = event.message.sender.user_id if event.message.sender else None
    if not user_id:
        return
    vehicle_id = int(data["vehicle_id"])
    settlement_id = int(data["settlement_id"])
    await _finish_entry(event, context, user_id, vehicle_id, settlement_id, plot_name)


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
        await event.message.answer(
            "Фото потеряно, начните заново.",
            attachments=[InlineKeyboardBuilder().row(*back_row("menu:main")).as_markup()],
        )
        await clear_ctx(context)
        return

    now = datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    with session_scope() as session:
        repo = Repo(session)
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
    await event.message.answer(text, attachments=[InlineKeyboardBuilder().row(*back_row("menu:main")).as_markup()])
