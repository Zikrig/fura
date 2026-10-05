from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for
from app.keyboards.menus import (
    PAGE_SIZE,
    back_row,
    paginated_named_keyboard,
    settlements_pick_keyboard,
)
from app.services.access import can_manage_directory
from app.states import PlotFlow, SettlementFlow, VehicleFlow

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


# ---------- Участки ----------
@router.message_callback(F.callback.payload.startswith("plot:root:"))
async def plot_root(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    if not _guard(event.callback.user.user_id):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        items = Repo(session).list_settlements()
    if not items:
        await edit_or_answer(
            event,
            "Сначала добавьте поселки.",
            _nav("menu:main"),
        )
        return
    kb = settlements_pick_keyboard(
        items,
        page=page,
        pick_prefix="plot:sett",
        page_prefix="plot:root",
        back_payload="menu:main",
    )
    await edit_or_answer(event, "Выберите поселок для участков:", kb)


@router.message_callback(F.callback.payload.startswith("plot:sett:"))
async def plot_list_for_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    parts = event.callback.payload.split(":")
    # plot:sett:3 or plot:sett:3:0
    sett_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    with session_scope() as session:
        repo = Repo(session)
        sett = repo.get_settlement(sett_id)
        items = repo.list_plots(sett_id)
        sett_name = sett.name if sett else "?"
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        kb.row(CallbackButton(text=item.name[:60], payload=f"plot:view:{item.id}"))
    nav = []
    if page > 0:
        nav.append(CallbackButton(text=f"◀ {page}", payload=f"plot:sett:{sett_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(CallbackButton(text=f"{page + 2} ▶", payload=f"plot:sett:{sett_id}:{page + 1}"))
    if nav:
        kb.row(*nav)
    kb.row(CallbackButton(text="➕ Добавить участок", payload=f"plot:add:{sett_id}"))
    kb.row(*back_row("plot:root:0"))
    await edit_or_answer(event, f"Участки поселка «{sett_name}» ({total}):", kb)


@router.message_callback(F.callback.payload.startswith("plot:add:"))
async def plot_add(event: MessageCallback, context: MemoryContext):
    await ack(event)
    sett_id = int(event.callback.payload.split(":")[-1])
    await context.set_state(PlotFlow.name)
    await context.update_data(mode="add", settlement_id=sett_id)
    await edit_or_answer(event, "Введите название участка:", _nav(f"plot:sett:{sett_id}"))


@router.message_callback(F.callback.payload.startswith("plot:view:"))
async def plot_view(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    plot_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        plot = Repo(session).get_plot(plot_id)
        if not plot:
            await edit_or_answer(event, "Не найден.", _nav("plot:root:0"))
            return
        sett_name = plot.settlement.name if plot.settlement else "?"
        name = plot.name
        sett_id = plot.settlement_id
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Переименовать", payload=f"plot:rename:{plot_id}"))
    kb.row(CallbackButton(text="🗑 Удалить", payload=f"plot:del:{plot_id}"))
    kb.row(*back_row(f"plot:sett:{sett_id}"))
    await edit_or_answer(event, f"Участок: {sett_name} / {name}", kb)


@router.message_callback(F.callback.payload.startswith("plot:rename:"))
async def plot_rename(event: MessageCallback, context: MemoryContext):
    await ack(event)
    plot_id = int(event.callback.payload.split(":")[-1])
    await context.set_state(PlotFlow.name)
    await context.update_data(mode="rename", plot_id=plot_id)
    await edit_or_answer(event, "Новое название участка:", _nav(f"plot:view:{plot_id}"))


@router.message_callback(F.callback.payload.startswith("plot:del:"))
async def plot_del(event: MessageCallback, context: MemoryContext):
    await ack(event)
    plot_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        repo = Repo(session)
        plot = repo.get_plot(plot_id)
        sett_id = plot.settlement_id if plot else 0
        sett = repo.get_settlement(sett_id) if sett_id else None
        sett_name = sett.name if sett else "?"
        repo.delete_plot(plot_id)
        items = repo.list_plots(sett_id) if sett_id else []
    kb = InlineKeyboardBuilder()
    for item in items[:PAGE_SIZE]:
        kb.row(CallbackButton(text=item.name[:60], payload=f"plot:view:{item.id}"))
    if sett_id:
        kb.row(CallbackButton(text="➕ Добавить участок", payload=f"plot:add:{sett_id}"))
    kb.row(*back_row("plot:root:0"))
    await edit_or_answer(event, f"Удалено. Участки поселка «{sett_name}» ({len(items)}):", kb)


@router.message_created(PlotFlow.name)
async def plot_name_input(event: MessageCreated, context: MemoryContext):
    name = ((event.message.body.text if event.message.body else "") or "").strip()
    if not name:
        await event.message.answer("Название пустое.")
        return
    data = await context.get_data()
    with session_scope() as session:
        repo = Repo(session)
        if data.get("mode") == "rename":
            plot = repo.rename_plot(int(data["plot_id"]), name)
            sett_id = plot.settlement_id if plot else 0
        else:
            sett_id = int(data["settlement_id"])
            if repo.get_plot_by_name(sett_id, name):
                await event.message.answer("Такой участок уже есть в поселке.")
                return
            repo.add_plot(sett_id, name)
        items = repo.list_plots(sett_id)
        sett = repo.get_settlement(sett_id)
        sett_name = sett.name if sett else "?"
    await clear_ctx(context)
    kb = InlineKeyboardBuilder()
    for item in items[:PAGE_SIZE]:
        kb.row(CallbackButton(text=item.name[:60], payload=f"plot:view:{item.id}"))
    kb.row(CallbackButton(text="➕ Добавить участок", payload=f"plot:add:{sett_id}"))
    kb.row(*back_row("plot:root:0"))
    await event.message.answer(
        f"Сохранено. Участки поселка «{sett_name}» ({len(items)}):",
        attachments=[kb.as_markup()],
    )


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
