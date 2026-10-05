from maxapi import Dispatcher

from app.handlers import directory, entry, menu, prices, results, staff


def setup_routers(dp: Dispatcher) -> None:
    # Специфичные роутеры раньше catch-all меню.
    dp.include_routers(
        staff.router,
        directory.router,
        prices.router,
        entry.router,
        results.router,
        menu.router,
    )
