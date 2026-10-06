from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.db.database import session_scope
from app.db.repo import Repo
from app.handlers.common import ack, clear_ctx, edit_or_answer, role_for, staff_card_text
from app.keyboards.menus import settlements_multi_keyboard, staff_card_keyboard, staff_list_keyboard
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


def _selected_ids(data: dict) -> list[int]:
    return [int(item) for item in (data.get("settlement_ids") or [])]


async def _render_guard_settlements(
    event,
    context: MemoryContext,
    *,
    page: int,
    mode: str,
    staff_id: int | None = None,
    notice: str = "",
) -> None:
    data = await context.get_data()
    selected = set(_selected_ids(data))
    with session_scope() as session:
        items = Repo(session).list_settlements()
    if not items:
        await edit_or_answer(
            event,
            "Сначала добавьте поселки в меню «Поселки».",
            _nav_kb("menu:main"),
        )
        await clear_ctx(context)
        return
    if mode == "edit":
        kb = settlements_multi_keyboard(
            items,
            page=page,
            selected_ids=selected,
            toggle_prefix=f"staff:etgl:{staff_id}",
            page_prefix=f"staff:epage:{staff_id}",
            ok_payload=f"staff:eok:{staff_id}",
            back_payload=f"staff:view:{staff_id}",
        )
    else:
        kb = settlements_multi_keyboard(
            items,
            page=page,
            selected_ids=selected,
            toggle_prefix="staff:tgl",
            page_prefix="staff:settpage",
            ok_payload="staff:settok",
            back_payload="staff:back:name",
        )
    text = f"Выберите поселки (выбрано: {len(selected)}) и нажмите Ок:"
    if notice:
        text = f"{notice}\n\n{text}"
    if isinstance(event, MessageCallback):
        await edit_or_answer(event, text, kb)
    else:
        await event.message.answer(text, attachments=[kb.as_markup()])


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
@router.message_callback(StaffAdd.settlement, F.callback.payload.startswith("staff:list:"))
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
    await context.update_data(name=name, settlement_ids=[])
    data = await context.get_data()
    role = data["role"]
    if role == "guard":
        await context.set_state(StaffAdd.settlement)
        await _render_guard_settlements(event, context, page=0, mode="add")
        return
    with session_scope() as session:
        repo = Repo(session)
        staff = repo.add_staff(
            user_id=int(data["user_id"]),
            role=role,
            name=name,
            max_link=data.get("max_link") or "",
        )
        staff = repo.get_staff_by_id(staff.id)
        text = "✅ Сохранено\n\n" + staff_card_text(staff)
        sid = staff.id
    await clear_ctx(context)
    await event.message.answer(text, attachments=[staff_card_keyboard(sid, role).as_markup()])


@router.message_callback(StaffAdd.settlement, F.callback.payload == "staff:back:name")
async def staff_back_name(event: MessageCallback, context: MemoryContext):
    await ack(event)
    await context.set_state(StaffAdd.name)
    await edit_or_answer(event, "Введите имя сотрудника.", _nav_kb("staff:back:link"))


@router.message_callback(StaffAdd.settlement, F.callback.payload.startswith("staff:settpage:"))
async def staff_add_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    page = int(event.callback.payload.split(":")[-1])
    await _render_guard_settlements(event, context, page=page, mode="add")


@router.message_callback(StaffAdd.settlement, F.callback.payload.startswith("staff:tgl:"))
async def staff_add_toggle_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    parts = event.callback.payload.split(":")
    if len(parts) < 4:
        return
    sett_id = int(parts[2])
    page = int(parts[3])
    data = await context.get_data()
    selected = set(_selected_ids(data))
    if sett_id in selected:
        selected.remove(sett_id)
    else:
        selected.add(sett_id)
    await context.update_data(settlement_ids=sorted(selected))
    await _render_guard_settlements(event, context, page=page, mode="add")


@router.message_callback(StaffAdd.settlement, F.callback.payload == "staff:settok")
async def staff_add_settlements_ok(event: MessageCallback, context: MemoryContext):
    await ack(event)
    data = await context.get_data()
    ids = _selected_ids(data)
    if not ids:
        await _render_guard_settlements(
            event,
            context,
            page=0,
            mode="add",
            notice="Выберите хотя бы один поселок.",
        )
        return
    with session_scope() as session:
        repo = Repo(session)
        staff = repo.add_staff(
            user_id=int(data["user_id"]),
            role="guard",
            name=data["name"],
            max_link=data.get("max_link") or "",
            settlement_ids=ids,
        )
        staff = repo.get_staff_by_id(staff.id)
        text = "✅ Сохранено\n\n" + staff_card_text(staff)
        sid = staff.id
    await clear_ctx(context)
    await edit_or_answer(event, text, staff_card_keyboard(sid, "guard"))


@router.message_created(StaffAdd.settlement)
async def staff_add_settlement_text(event: MessageCreated, context: MemoryContext):
    await event.message.answer("Выберите поселки кнопками и нажмите Ок.")


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
    # staff:edit:name:12 / staff:edit:link:12
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

    if field == "settlements" and role == "guard":
        with session_scope() as session:
            current = Repo(session).get_staff_by_id(staff_id)
            ids = [item.id for item in current.settlements] if current else []
        await context.set_state(StaffEdit.settlements)
        await context.update_data(staff_id=staff_id, settlement_ids=ids, role=role)
        await _render_guard_settlements(event, context, page=0, mode="edit", staff_id=staff_id)
        return

    if field not in {"name", "link"}:
        await edit_or_answer(event, "Это поле больше не редактируется.", _nav_kb(f"staff:view:{staff_id}"))
        return

    await context.set_state(StaffEdit.value)
    await context.update_data(staff_id=staff_id, field=field, role=role)
    prompt = _REF_PROMPT if field == "link" else "Новое имя:"
    await edit_or_answer(event, prompt, _nav_kb(f"staff:view:{staff_id}"))


@router.message_callback(StaffEdit.settlements, F.callback.payload.startswith("staff:etgl:"))
async def staff_edit_toggle_settlement(event: MessageCallback, context: MemoryContext):
    await ack(event)
    parts = event.callback.payload.split(":")
    if len(parts) < 5:
        return
    staff_id = int(parts[2])
    sett_id = int(parts[3])
    page = int(parts[4])
    data = await context.get_data()
    selected = set(_selected_ids(data))
    if sett_id in selected:
        selected.remove(sett_id)
    else:
        selected.add(sett_id)
    await context.update_data(staff_id=staff_id, settlement_ids=sorted(selected))
    await _render_guard_settlements(event, context, page=page, mode="edit", staff_id=staff_id)


@router.message_callback(StaffEdit.settlements, F.callback.payload.startswith("staff:epage:"))
async def staff_edit_sett_page(event: MessageCallback, context: MemoryContext):
    await ack(event)
    parts = event.callback.payload.split(":")
    if len(parts) < 4:
        return
    staff_id = int(parts[2])
    page = int(parts[3])
    await _render_guard_settlements(event, context, page=page, mode="edit", staff_id=staff_id)


@router.message_callback(StaffEdit.settlements, F.callback.payload.startswith("staff:eok:"))
async def staff_edit_settlements_ok(event: MessageCallback, context: MemoryContext):
    await ack(event)
    parts = event.callback.payload.split(":")
    if len(parts) < 3:
        return
    staff_id = int(parts[2])
    ids = _selected_ids(await context.get_data())
    if not ids:
        await _render_guard_settlements(
            event,
            context,
            page=0,
            mode="edit",
            staff_id=staff_id,
            notice="Выберите хотя бы один поселок.",
        )
        return
    with session_scope() as session:
        repo = Repo(session)
        staff = repo.set_guard_settlements(staff_id, ids)
        if not staff:
            await edit_or_answer(event, "Сотрудник не найден.", _nav_kb("menu:main"))
            await clear_ctx(context)
            return
        text = staff_card_text(staff)
        role = staff.role
    await clear_ctx(context)
    await edit_or_answer(event, "Поселки обновлены.\n\n" + text, staff_card_keyboard(staff_id, role))


@router.message_created(StaffEdit.settlements)
async def staff_edit_settlements_text(event: MessageCreated, context: MemoryContext):
    await event.message.answer("Выберите поселки кнопками и нажмите Ок.")


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
        else:
            await event.message.answer("Это поле больше не редактируется.")
            await clear_ctx(context)
            return
        staff = repo.get_staff_by_id(staff_id)
        body = staff_card_text(staff)
        role = staff.role
    await clear_ctx(context)
    await event.message.answer(body, attachments=[staff_card_keyboard(staff_id, role).as_markup()])
