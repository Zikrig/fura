from __future__ import annotations

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.filters.command import Command
from maxapi.types import BotStarted, MessageCallback, MessageCreated

from app.handlers.common import ack, role_for, show_main_menu
from app.services.access import can_use_bot

router = Router("menu")


def _user_id_from_message(event: MessageCreated) -> int | None:
    if event.message and event.message.sender:
        return event.message.sender.user_id
    return None


@router.bot_started()
async def on_bot_started(event: BotStarted, context: MemoryContext | None = None):
    user_id = event.user.user_id if event.user else None
    if not user_id:
        return
    await show_main_menu(event, user_id, context)


@router.message_created(Command("start"))
async def cmd_start(event: MessageCreated, context: MemoryContext):
    user_id = _user_id_from_message(event)
    if not user_id:
        return
    await show_main_menu(event, user_id, context)


@router.message_callback(F.callback.payload == "menu:main")
async def cb_main(event: MessageCallback, context: MemoryContext):
    await ack(event)
    user_id = event.callback.user.user_id
    await show_main_menu(event, user_id, context)


@router.message_created()
async def any_text_to_menu(event: MessageCreated, context: MemoryContext):
    """Любая строка вне сценария → меню (если есть роль)."""
    user_id = _user_id_from_message(event)
    if not user_id:
        return
    state = await context.get_state()
    if state is not None:
        return
    role = role_for(user_id)
    if not can_use_bot(role):
        await event.message.answer("Нет доступа. Обратитесь к администратору.")
        return
    await show_main_menu(event, user_id, context)
