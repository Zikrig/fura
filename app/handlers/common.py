from __future__ import annotations

from maxapi.context.context import MemoryContext
from maxapi.types import MessageCallback
from maxapi.types.input_media import InputMedia
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.callback_ack import send_callback_ack
from app.config import settings
from app.db.database import session_scope
from app.db.repo import Repo
from app.keyboards.menus import main_menu_keyboard
from app.services.access import Role, can_use_bot, resolve_role


async def ack(event: MessageCallback, notification: str | None = None) -> None:
    bot = event._ensure_bot()
    await send_callback_ack(bot, event.callback.callback_id, notification=notification)


def role_for(user_id: int) -> Role:
    with session_scope() as session:
        return resolve_role(user_id, settings, Repo(session))


async def clear_ctx(context: MemoryContext | None) -> None:
    if context is not None:
        await context.clear()


async def edit_or_answer(event, text: str, kb: InlineKeyboardBuilder | None = None) -> None:
    attachments = [kb.as_markup()] if kb is not None else []
    message = getattr(event, "message", None)
    # Чужое сообщение (текст участка и т.п.) бот не редактирует: API отвечает
    # success=false без исключения, и пользователь не видит ответа.
    if (
        isinstance(event, MessageCallback)
        and message is not None
        and getattr(message, "body", None) is not None
    ):
        try:
            edited = await message.edit(text=text, attachments=attachments if attachments else [])
            if edited is not None and getattr(edited, "success", False):
                return
        except Exception:
            pass
    if message is not None:
        await message.answer(text=text, attachments=attachments if attachments else None)
        return
    bot = event._ensure_bot()
    user_id = event.callback.user.user_id
    await bot.send_message(user_id=user_id, text=text, attachments=attachments or None)


async def show_main_menu(event, user_id: int, context: MemoryContext | None = None) -> None:
    await clear_ctx(context)
    role = role_for(user_id)
    if not can_use_bot(role):
        text = "Нет доступа. Обратитесь к администратору."
        if isinstance(event, MessageCallback):
            await edit_or_answer(event, text)
        elif getattr(event, "message", None) is not None:
            await event.message.answer(text)
        else:
            bot = event._ensure_bot()
            await bot.send_message(user_id=user_id, text=text)
        return
    title = {
        Role.ADMIN: "Главное меню (админ)",
        Role.MANAGER: "Главное меню (менеджер)",
        Role.GUARD: "Главное меню (охранник)",
    }.get(role, "Главное меню")
    kb = main_menu_keyboard(role)
    if isinstance(event, MessageCallback):
        await edit_or_answer(event, title, kb)
    elif getattr(event, "message", None) is not None:
        await event.message.answer(text=title, attachments=[kb.as_markup()])
    else:
        bot = event._ensure_bot()
        chat_id = getattr(event, "chat_id", None)
        if chat_id is not None:
            await bot.send_message(chat_id=chat_id, text=title, attachments=[kb.as_markup()])
        else:
            await bot.send_message(user_id=user_id, text=title, attachments=[kb.as_markup()])


async def send_file_to_user(bot, user_id: int, path, caption: str = "") -> None:
    await bot.send_message(
        user_id=user_id,
        text=caption or "Файл",
        attachments=[InputMedia(str(path))],
    )


def staff_card_text(staff) -> str:
    role_label = "Менеджер" if staff.role == "manager" else "Охранник"
    lines = [
        f"{role_label}: {staff.name}",
        f"user_id: {staff.user_id}",
        f"Ссылка: {staff.max_link or '—'}",
    ]
    if staff.role == "guard":
        names = ", ".join(s.name for s in staff.settlements)
        lines.append(f"Поселки: {names or '—'}")
    return "\n".join(lines)
