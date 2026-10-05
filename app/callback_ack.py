"""Подтверждение callback без отката attachments (паттерн из snzg_check_subscribe)."""

SILENT_NOTIFICATION = " "


async def send_callback_ack(bot, callback_id: str, *, notification: str | None = None) -> None:
    await bot.send_callback(
        callback_id=callback_id,
        message=None,
        notification=notification if notification is not None else SILENT_NOTIFICATION,
    )
