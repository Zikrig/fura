from __future__ import annotations

from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.services.access import Role

PAGE_SIZE = 10


def back_row(payload: str) -> list[CallbackButton]:
    return [CallbackButton(text="⬅ Назад", payload=payload)]


def main_menu_keyboard(role: Role) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if role == Role.ADMIN:
        kb.row(CallbackButton(text="Менеджеры", payload="staff:list:manager:0"))
        kb.row(CallbackButton(text="Охранники", payload="staff:list:guard:0"))
    elif role == Role.MANAGER:
        kb.row(CallbackButton(text="Охранники", payload="staff:list:guard:0"))

    if role in {Role.ADMIN, Role.MANAGER}:
        kb.row(CallbackButton(text="Поселки", payload="settl:list:0"))
        kb.row(CallbackButton(text="Транспорт", payload="veh:list:0"))
        kb.row(CallbackButton(text="Таблица Цены", payload="price:menu"))
        kb.row(CallbackButton(text="Таблица результаты", payload="res:period"))

    kb.row(CallbackButton(text="+Въезд", payload="entry:start"))
    return kb


def staff_list_keyboard(items: list, role: str, page: int, back_payload: str = "menu:main") -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        label = item.name
        if getattr(item, "role", None) == "guard" and item.settlements:
            names = ", ".join(s.name for s in item.settlements)
            label = f"{item.name} ({names})"
        kb.row(CallbackButton(text=label[:60], payload=f"staff:view:{item.id}"))
    _add_pager(kb, page, total, f"staff:list:{role}")
    kb.row(CallbackButton(text="➕ Добавить", payload=f"staff:add:{role}"))
    kb.row(*back_row(back_payload))
    return kb


def staff_card_keyboard(staff_id: int, role: str, page: int = 0) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Изменить ссылку", payload=f"staff:edit:link:{staff_id}"))
    kb.row(CallbackButton(text="Изменить имя", payload=f"staff:edit:name:{staff_id}"))
    if role == "guard":
        kb.row(CallbackButton(text="Изменить поселки", payload=f"staff:edit:settlements:{staff_id}"))
    kb.row(CallbackButton(text="🗑 Удалить", payload=f"staff:del:{staff_id}"))
    kb.row(*back_row(f"staff:list:{role}:{page}"))
    return kb


def paginated_named_keyboard(
    items: list,
    *,
    page: int,
    view_prefix: str,
    list_prefix: str,
    add_payload: str,
    back_payload: str,
    label_fn=None,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        label = label_fn(item) if label_fn else item.name
        kb.row(CallbackButton(text=str(label)[:60], payload=f"{view_prefix}:{item.id}"))
    _add_pager(kb, page, total, list_prefix)
    kb.row(CallbackButton(text="➕ Добавить", payload=add_payload))
    kb.row(*back_row(back_payload))
    return kb


def settlements_pick_keyboard(
    items: list,
    *,
    page: int,
    pick_prefix: str,
    page_prefix: str,
    back_payload: str,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        kb.row(CallbackButton(text=item.name[:60], payload=f"{pick_prefix}:{item.id}"))
    _add_pager(kb, page, total, page_prefix)
    kb.row(*back_row(back_payload))
    return kb


def settlements_multi_keyboard(
    items: list,
    *,
    page: int,
    selected_ids: set[int],
    toggle_prefix: str,
    page_prefix: str,
    ok_payload: str,
    back_payload: str,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        mark = "🟢" if item.id in selected_ids else "🔴"
        kb.row(
            CallbackButton(
                text=f"{mark} {item.name}"[:60],
                payload=f"{toggle_prefix}:{item.id}:{page}",
            )
        )
    _add_pager(kb, page, total, page_prefix)
    kb.row(CallbackButton(text="Ок", payload=ok_payload))
    kb.row(*back_row(back_payload))
    return kb


def price_menu_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="📥 Выгрузить Excel", payload="price:export"))
    kb.row(CallbackButton(text="📤 Загрузить Excel", payload="price:import"))
    kb.row(*back_row("menu:main"))
    return kb


def results_period_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Сегодня", payload="res:p:today"))
    kb.row(CallbackButton(text="Вчера", payload="res:p:yesterday"))
    kb.row(CallbackButton(text="За три дня", payload="res:p:3d"))
    kb.row(CallbackButton(text="За неделю", payload="res:p:week"))
    kb.row(CallbackButton(text="За все время", payload="res:p:all"))
    kb.row(CallbackButton(text="За дату", payload="res:p:date"))
    kb.row(CallbackButton(text="За диапазон", payload="res:p:range"))
    kb.row(*back_row("menu:main"))
    return kb


def results_settlement_keyboard(items: list, page: int = 0) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Все поселки", payload="res:sett:all"))
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        kb.row(CallbackButton(text=item.name[:60], payload=f"res:sett:{item.id}"))
    _add_pager(kb, page, total, "res:settpage")
    kb.row(*back_row("res:period"))
    return kb


def entry_vehicle_keyboard(items: list, page: int = 0) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(items)
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for item in chunk:
        kb.row(CallbackButton(text=item.name[:60], payload=f"entry:veh:{item.id}"))
    _add_pager(kb, page, total, "entry:vehpage")
    kb.row(*back_row("entry:back_photo"))
    return kb


def _add_pager(kb: InlineKeyboardBuilder, page: int, total: int, list_prefix: str) -> None:
    nav: list[CallbackButton] = []
    if page > 0:
        nav.append(CallbackButton(text=f"◀ {page}", payload=f"{list_prefix}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(CallbackButton(text=f"{page + 2} ▶", payload=f"{list_prefix}:{page + 1}"))
    if nav:
        kb.row(*nav)
