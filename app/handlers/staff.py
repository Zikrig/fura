from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for, staff_card_text
from app.keyboards.menus import (
    settlements_pick_keyboard,
    staff_card_keyboard,
    staff_list_keyboard,
)
from app.services.access import can_manage_directory, can_manage_managers
from app.services.parse_user import user_ref_from_message
from app.states import StaffAdd, StaffEdit

router = Router("staff")

_REF_PROMPT = "Пришлите числовой user_id или перешлите сообщение этого человека."
_REF_FAIL = "Не вижу user_id. Пришлите число или перешлите сообщение человека."


def _nav_kb(back_payload: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="⬅ Назад", payload=back_payload))
    return kb


def _require_staff_role(user_id: int, target_role: str) -> bool:
    role = role_for(user_id)
    if target_role == "manager":
        return can_manage_managers(role)
    if target_role == "guard":
        return can_manage_directory(role)
    return False


@router.message_callback(F.callback.payload.startswith("staff:list:"))
async def cb_staff_list(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    parts = event.callback.payload.split(":")
    # staff:list:manager:0
    if len(parts) < 4:
        return
    target_role, page_s = parts[2], parts[3]
    user_id = event.callback.user.user_id
    if not _require_staff_role(user_id, target_role):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    page = int(page_s)
    with session_scope() as session:
        items = Repo(session).list_staff(target_role)
    title = "Менеджеры" if target_role == "manager" else "Охранники"
    kb = staff_list_keyboard(items, target_role, page)
    await edit_or_answer(event, f"{title} ({len(items)}):", kb)


@router.message_callback(F.callback.payload.startswith("staff:view:"))
async def cb_staff_view(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await clear_ctx(context)
    staff_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        staff = Repo(session).get_staff_by_id(staff_id)
        if not staff:
            await edit_or_answer(event, "Сотрудник не найден.", _nav_kb("menu:main"))
            return
        if not _require_staff_role(event.callback.user.user_id, staff.role):
            await edit_or_answer(event, "Недостаточно прав.")
            return
        text = staff_card_text(staff)
        role = staff.role
    await edit_or_answer(event, text, staff_card_keyboard(staff_id, role))


@router.message_callback(F.callback.payload.startswith("staff:add:"))
async def cb_staff_add(event: MessageCallback, context: MemoryContext):
    await ack(event)
    target_role = event.callback.payload.split(":")[-1]
    if not _require_staff_role(event.callback.user.user_id, target_role):
        await edit_or_answer(event, "Недостаточно прав.")
        return
    await context.set_state(StaffAdd.link)
    await context.update_data(role=target_role)
    await edit_or_answer(
        event,
        _REF_PROMPT,
        _nav_kb(f"staff:list:{target_role}:0"),
    )


@router.message_callback(StaffAdd.link, F.callback.payload.startswith("staff:list:"))
@router.message_callback(StaffAdd.name, F.callback.payload.startswith("staff:list:"))
async def cb_staff_add_back_list(event: MessageCallback, context: MemoryContext):
    await clear_ctx(context)
    await cb_staff_list(event, context)


@router.message_created(StaffAdd.link)
async def staff_add_link(event: MessageCreated, context: MemoryContext):
    user_id, link = user_ref_from_message(event.message)
    data = await context.get_data()
    role = data.get("role", "guard")
    if not user_id:
        await event.message.answer(
            _REF_FAIL,
            attachments=[_nav_kb(f"staff:list:{role}:0").as_markup()],
        )
        return
    await context.update_data(user_id=user_id, max_link=link)
    await context.set_state(StaffAdd.name)
    await event.message.answer(
        "Введите имя сотрудника.",
        attachments=[_nav_kb("staff:back:link").as_markup()],
    )


@router.message_callback(StaffAdd.name, F.callback.payload == "staff:back:link")
async def staff_back_link(event: MessageCallback, context: MemoryContext):
    await ack(event)
    data = await context.get_data()
    role = data.get("role", "guard")
    await context.set_state(StaffAdd.link)
    await edit_or_answer(
        event,
        _REF_PROMPT,
        _nav_kb(f"staff:list:{role}:0"),
    )


@router.message_created(StaffAdd.name)
async def staff_add_name(event: MessageCreated, context: MemoryContext):
    name = ((event.message.body.text if event.message.body else "") or "").strip()
    if not name:
        await event.message.answer("Имя не должно быть пустым.")
        return
    await context.update_data(name=name)
    await context.set_state(StaffAdd.settlement)
    with session_scope() as session:
        items = Repo(session).list_settlements()
    if not items:
        await event.message.answer(
            "Сначала добавьте поселки в меню «Поселки».",
            attachments=[_nav_kb("menu:main").as_markup()],
        )
        await clear_ctx(context)
        return
    kb = settlements_pick_keyboard(
        items,
        page=0,
        pick_prefix="staff:picksett",
        page_prefix="staff:settpage",
        back_payload="staff:back:name",
    )
    await event.message.answer("Выберите поселок:", attachments=[kb.as_markup()])


@router.message_callback(StaffAdd.settlement, F.callback.payload == "staff:back:name")
async def staff_back_name(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(StaffAdd.name)
    await edit_or_answer(event, "Введите имя сотрудника.", _nav_kb("staff:back:link"))


@router.message_callback(StaffAdd.settlement, F.callback.payload.startswith("staff:settpage:"))
async def staff_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        items = Repo(session).list_settlements()
    kb = settlements_pick_keyboard(
        items,
        page=page,
        pick_prefix="staff:picksett",
        page_prefix="staff:settpage",
        back_payload="staff:back:name",
    )
    await edit_or_answer(event, "Выберите поселок:", kb)


@router.message_callback(StaffAdd.settlement, F.callback.payload.startswith("staff:picksett:"))
async def staff_pick_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    sett_id = int(event.callback.payload.split(":")[-1])
    data = await context.get_data()
    role = data["role"]
    with session_scope() as session:
        repo = Repo(session)
        staff = repo.add_staff(
            user_id=int(data["user_id"]),
            role=role,
            name=data["name"],
            max_link=data.get("max_link") or "",
            settlement_id=sett_id,
        )
        staff = repo.get_staff_by_id(staff.id)
        text = "✅ Сохранено\n\n" + staff_card_text(staff)
        sid = staff.id
    await clear_ctx(context)
    await edit_or_answer(event, text, staff_card_keyboard(sid, role))


@router.message_callback(F.callback.payload.startswith("staff:del:"))
async def cb_staff_del(event: MessageCallback, context: MemoryContext):
    await ack(event)
    staff_id = int(event.callback.payload.split(":")[-1])
    with session_scope() as session:
        repo = Repo(session)
        staff = repo.get_staff_by_id(staff_id)
        if not staff:
            await edit_or_answer(event, "Уже удалён.", _nav_kb("menu:main"))
            return
        if not _require_staff_role(event.callback.user.user_id, staff.role):
            await edit_or_answer(event, "Недостаточно прав.")
            return
        role = staff.role
        repo.delete_staff(staff_id)
        items = repo.list_staff(role)
    title = "Менеджеры" if role == "manager" else "Охранники"
    await edit_or_answer(
        event,
        f"Удалено. {title} ({len(items)}):",
        staff_list_keyboard(items, role, 0),
    )


@router.message_callback(F.callback.payload.startswith("staff:edit:"))
async def cb_staff_edit(event: MessageCallback, context: MemoryContext):
    await ack(event)
    # staff:edit:name:12 / staff:edit:link:12 / staff:edit:settlement:12
    parts = event.callback.payload.split(":")
    if len(parts) < 4:
        return
    field, staff_id_s = parts[2], parts[3]
    staff_id = int(staff_id_s)
    with session_scope() as session:
        staff = Repo(session).get_staff_by_id(staff_id)
        if not staff or not _require_staff_role(event.callback.user.user_id, staff.role):
            await edit_or_answer(event, "Недостаточно прав.")
            return
        role = staff.role

    if field == "settlement":
        with session_scope() as session:
            items = Repo(session).list_settlements()
        kb = settlements_pick_keyboard(
            items,
            page=0,
            pick_prefix=f"staff:setsett:{staff_id}",
            page_prefix=f"staff:edsettpage:{staff_id}",
            back_payload=f"staff:view:{staff_id}",
        )
        await edit_or_answer(event, "Выберите новый поселок:", kb)
        return

    await context.set_state(StaffEdit.value)
    await context.update_data(staff_id=staff_id, field=field, role=role)
    prompt = _REF_PROMPT if field == "link" else "Новое имя:"
    await edit_or_answer(event, prompt, _nav_kb(f"staff:view:{staff_id}"))


@router.message_callback(F.callback.payload.startswith("staff:setsett:"))
async def cb_staff_set_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    # staff:setsett:{staff_id}:{sett_id} — wait, pick_prefix is staff:setsett:{staff_id}
    # payload = staff:setsett:12:5
    parts = event.callback.payload.split(":")
    staff_id = int(parts[2])
    sett_id = int(parts[3])
    with session_scope() as session:
        repo = Repo(session)
        repo.update_staff_field(staff_id, settlement_id=sett_id)
        staff = repo.get_staff_by_id(staff_id)
        text = staff_card_text(staff)
        role = staff.role
    await edit_or_answer(event, "Поселок обновлён.\n\n" + text, staff_card_keyboard(staff_id, role))


@router.message_created(StaffEdit.value)
async def staff_edit_value(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    staff_id = int(data["staff_id"])
    field = data["field"]
    text = ((event.message.body.text if event.message.body else "") or "").strip()
    with session_scope() as session:
        repo = Repo(session)
        if field == "name":
            if not text:
                await event.message.answer("Имя пустое.")
                return
            repo.update_staff_field(staff_id, name=text)
        elif field == "link":
            uid, link = user_ref_from_message(event.message)
            if not uid:
                await event.message.answer(_REF_FAIL)
                return
            repo.update_staff_field(staff_id, user_id=uid, max_link=link)
        staff = repo.get_staff_by_id(staff_id)
        body = staff_card_text(staff)
        role = staff.role
    await clear_ctx(context)
    await event.message.answer(body, attachments=[staff_card_keyboard(staff_id, role).as_markup()])
