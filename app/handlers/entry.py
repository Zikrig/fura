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
from app.keyboards.menus import back_row, entry_vehicle_keyboard, plots_pick_keyboard
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


@router.message_callback(EntryFlow.vehicle, F.callback.payload.startswith("entry:veh:"))
async def entry_pick_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    vehicle_id = int(event.callback.payload.split(":")[-1])
    await context.update_data(vehicle_id=vehicle_id)
    user_id = event.callback.user.user_id
    role = role_for(user_id)

    with session_scope() as session:
        repo = Repo(session)
        if role == Role.GUARD:
            staff = repo.get_staff(user_id)
            plot_id = staff.plot_id if staff else None
            if not plot_id:
                await edit_or_answer(
                    event,
                    "У охранника не указан участок. Попросите менеджера заполнить карточку.",
                    InlineKeyboardBuilder().row(*back_row("menu:main")),
                )
                await clear_ctx(context)
                return
            await _finish_entry(event, context, user_id, vehicle_id, plot_id)
            return

        plots = repo.list_plots()
        if not plots:
            await edit_or_answer(event, "Нет участков.", InlineKeyboardBuilder().row(*back_row("menu:main")))
            await clear_ctx(context)
            return
        await context.set_state(EntryFlow.plot)
        kb = plots_pick_keyboard(
            plots,
            page=0,
            pick_prefix="entry:plot",
            page_prefix="entry:plotpage",
            back_payload="entry:back_vehicle",
            with_settlement=True,
        )
        await edit_or_answer(event, "Выберите участок:", kb)


@router.message_callback(EntryFlow.vehicle, F.callback.payload == "entry:back_vehicle")
@router.message_callback(EntryFlow.plot, F.callback.payload == "entry:back_vehicle")
async def entry_back_vehicle(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(EntryFlow.vehicle)
    with session_scope() as session:
        vehicles = Repo(session).list_vehicles()
    await edit_or_answer(event, "Выберите тип авто:", entry_vehicle_keyboard(vehicles, 0))


@router.message_callback(EntryFlow.plot, F.callback.payload.startswith("entry:plotpage:"))
async def entry_plot_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        plots = Repo(session).list_plots()
    kb = plots_pick_keyboard(
        plots,
        page=page,
        pick_prefix="entry:plot",
        page_prefix="entry:plotpage",
        back_payload="entry:back_vehicle",
        with_settlement=True,
    )
    await edit_or_answer(event, "Выберите участок:", kb)


@router.message_callback(EntryFlow.plot, F.callback.payload.startswith("entry:plot:"))
async def entry_pick_plot(event: MessageCallback, context: MemoryContext):
    await ack(event)
    plot_id = int(event.callback.payload.split(":")[-1])
    data = await context.get_data()
    vehicle_id = int(data["vehicle_id"])
    user_id = event.callback.user.user_id
    await _finish_entry(event, context, user_id, vehicle_id, plot_id)


async def _finish_entry(event, context: MemoryContext, user_id: int, vehicle_id: int, plot_id: int) -> None:
    data = await context.get_data()
    photo_path = data.get("photo_path")
    if not photo_path:
        await edit_or_answer(event, "Фото потеряно, начните заново.", InlineKeyboardBuilder().row(*back_row("menu:main")))
        await clear_ctx(context)
        return

    now = datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    with session_scope() as session:
        repo = Repo(session)
        price = repo.get_price(vehicle_id, plot_id)
        amount = price.amount if price else 0.0
        vehicle = repo.get_vehicle(vehicle_id)
        plot = repo.get_plot(plot_id)
        repo.add_entry(
            created_at=now,
            plot_id=plot_id,
            vehicle_id=vehicle_id,
            price_amount=amount,
            photo_path=photo_path,
            reporter_user_id=user_id,
        )
        sett = plot.settlement.name if plot and plot.settlement else "?"
        plot_name = plot.name if plot else "?"
        veh_name = vehicle.name if vehicle else "?"

    await clear_ctx(context)
    text = (
        "✅ Въезд зафиксирован\n"
        f"Дата: {now.strftime('%d.%m.%Y')}\n"
        f"Время: {now.strftime('%H:%M:%S')}\n"
        f"Участок: {sett} / {plot_name}\n"
        f"Тип авто: {veh_name}\n"
        f"Стоимость: {amount}"
    )
    await edit_or_answer(event, text, InlineKeyboardBuilder().row(*back_row("menu:main")))
