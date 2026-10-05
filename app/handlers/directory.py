from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for
from app.keyboards.menus import (
    back_row,
    paginated_named_keyboard,
)
from app.services.access import can_manage_directory
from app.states import SettlementFlow, VehicleFlow

router = Router("directory")


def _nav(back: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(*back_row(back))
    return kb


def _guard(user_id: int) -> bool:
    return can_manage_directory(role_for(user_id))


# ---------- Поселки ----------
@router.message_callback(F.callback.payload.startswith("settl:list:"))
async def settl_list(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    if not _guard(event.callback.user.user_id):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        items = Repo(session).list_settlements()
    kb = paginated_named_keyboard(
        items,
        page=page,
        view_prefix="settl:view",
        list_prefix="settl:list",
        add_payload="settl:add",
        back_payload="menu:main",
    )
    await edit_or_answer(event, f"Поселки ({len(items)}):", kb)


@router.message_callback(F.callback.payload == "settl:add")
async def settl_add(event: MessageCallback, context: MemoryContext):
    await ack(event)
    if not _guard(event.callback.user.user_id):
        return
    await context.set_state(SettlementFlow.name)
    await context.update_data(mode="add")
    await edit_or_answer(event, "Введите название поселка:", _nav("settl:list:0"))


@router.message_callback(F.callback.payload.startswith("settl:view:"))
async def settl_view(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    sett_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        item = Repo(session).get_settlement(sett_id)
        if not item:
            await edit_or_answer(event, "Не найден.", _nav("settl:list:0"))
            return
        name = item.name
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Переименовать", payload=f"settl:rename:{sett_id}"))
    kb.row(CallbackButton(text="🗑 Удалить", payload=f"settl:del:{sett_id}"))
    kb.row(*back_row("settl:list:0"))
    await edit_or_answer(event, f"Поселок: {name}", kb)


@router.message_callback(F.callback.payload.startswith("settl:rename:"))
async def settl_rename(event: MessageCallback, context: MemoryContext):
    await ack(event)
    sett_id = int(event.callback.payload.split(":")[-1])
    await context.set_state(SettlementFlow.name)
    await context.update_data(mode="rename", settlement_id=sett_id)
    await edit_or_answer(event, "Новое название поселка:", _nav(f"settl:view:{sett_id}"))


@router.message_callback(F.callback.payload.startswith("settl:del:"))
async def settl_del(event: MessageCallback, context: MemoryContext):
    await ack(event)
    sett_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        Repo(session).delete_settlement(sett_id)
        items = Repo(session).list_settlements()
    kb = paginated_named_keyboard(
        items,
        page=0,
        view_prefix="settl:view",
        list_prefix="settl:list",
        add_payload="settl:add",
        back_payload="menu:main",
    )
    await edit_or_answer(event, f"Удалено. Поселки ({len(items)}):", kb)


@router.message_created(SettlementFlow.name)
async def settl_name_input(event: MessageCreated, context: MemoryContext):
    name = ((event.message.body.text if event.message.body else "") or "").strip()
    if not name:
        await event.message.answer("Название пустое.")
        return
    data = await context.get_data()
    with session_scope() as session:
        repo = Repo(session)
        if data.get("mode") == "rename":
            repo.rename_settlement(int(data["settlement_id"]), name)
        else:
            if repo.get_settlement_by_name(name):
                await event.message.answer("Такой поселок уже есть.")
                return
            repo.add_settlement(name)
        items = repo.list_settlements()
    await clear_ctx(context)
    kb = paginated_named_keyboard(
        items,
        page=0,
        view_prefix="settl:view",
        list_prefix="settl:list",
        add_payload="settl:add",
        back_payload="menu:main",
    )
    await event.message.answer(f"Сохранено. Поселки ({len(items)}):", attachments=[kb.as_markup()])


# ---------- Транспорт ----------
@router.message_callback(F.callback.payload.startswith("veh:list:"))
async def veh_list(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    if not _guard(event.callback.user.user_id):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        items = Repo(session).list_vehicles()
    kb = paginated_named_keyboard(
        items,
        page=page,
        view_prefix="veh:view",
        list_prefix="veh:list",
        add_payload="veh:add",
        back_payload="menu:main",
    )
    await edit_or_answer(event, f"Транспорт ({len(items)}):", kb)


@router.message_callback(F.callback.payload == "veh:add")
async def veh_add(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(VehicleFlow.name)
    await context.update_data(mode="add")
    await edit_or_answer(event, "Введите название транспорта:", _nav("veh:list:0"))


@router.message_callback(F.callback.payload.startswith("veh:view:"))
async def veh_view(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    veh_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        item = Repo(session).get_vehicle(veh_id)
        if not item:
            await edit_or_answer(event, "Не найден.", _nav("veh:list:0"))
            return
        name = item.name
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Переименовать", payload=f"veh:rename:{veh_id}"))
    kb.row(CallbackButton(text="🗑 Удалить", payload=f"veh:del:{veh_id}"))
    kb.row(*back_row("veh:list:0"))
    await edit_or_answer(event, f"Транспорт: {name}", kb)


@router.message_callback(F.callback.payload.startswith("veh:rename:"))
async def veh_rename(event: MessageCallback, context: MemoryContext):
    await ack(event)
    veh_id = int(event.callback.payload.split(":")[-1])
    await context.set_state(VehicleFlow.name)
    await context.update_data(mode="rename", vehicle_id=veh_id)
    await edit_or_answer(event, "Новое название транспорта:", _nav(f"veh:view:{veh_id}"))


@router.message_callback(F.callback.payload.startswith("veh:del:"))
async def veh_del(event: MessageCallback, context: MemoryContext):
    await ack(event)
    veh_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        Repo(session).delete_vehicle(veh_id)
        items = Repo(session).list_vehicles()
    kb = paginated_named_keyboard(
        items,
        page=0,
        view_prefix="veh:view",
        list_prefix="veh:list",
        add_payload="veh:add",
        back_payload="menu:main",
    )
    await edit_or_answer(event, f"Удалено. Транспорт ({len(items)}):", kb)


@router.message_created(VehicleFlow.name)
async def veh_name_input(event: MessageCreated, context: MemoryContext):
    name = ((event.message.body.text if event.message.body else "") or "").strip()
    if not name:
        await event.message.answer("Название пустое.")
        return
    data = await context.get_data()
    with session_scope() as session:
        repo = Repo(session)
        if data.get("mode") == "rename":
            repo.rename_vehicle(int(data["vehicle_id"]), name)
        else:
            if repo.get_vehicle_by_name(name):
                await event.message.answer("Такой транспорт уже есть.")
                return
            repo.add_vehicle(name)
        items = repo.list_vehicles()
    await clear_ctx(context)
    kb = paginated_named_keyboard(
        items,
        page=0,
        view_prefix="veh:view",
        list_prefix="veh:list",
        add_payload="veh:add",
        back_payload="menu:main",
    )
    await event.message.answer(f"Сохранено. Транспорт ({len(items)}):", attachments=[kb.as_markup()])
