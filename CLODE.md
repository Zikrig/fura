# CLODE — fura_ochrana

MAX-бот контроля проезда автомобилей (въезд на участки).

## Куда лезть

| Задача | Файлы |
|--------|--------|
| Точка входа / webhook | `bot.py` |
| ENV / пути | `app/config.py` |
| Роли и права | `app/services/access.py` |
| Модели БД | `app/db/models.py`, `app/db/repo.py` |
| Меню и пагинация | `app/keyboards/menus.py` |
| Сотрудники | `app/handlers/staff.py` |
| Поселки / участки / транспорт | `app/handlers/directory.py` |
| Таблица цен Excel | `app/handlers/prices.py`, `app/services/excel_prices.py` |
| +Въезд | `app/handlers/entry.py` |
| Выгрузка результатов | `app/handlers/results.py`, `app/services/excel_results.py` |
| Callback без отката клавиатуры | `app/callback_ack.py` |

## Роли

- **admin** — только `ADMIN_USER_IDS` в `.env`
- **manager** — в таблице `staff` (`role=manager`), меню без «Менеджеры»
- **guard** — `staff.role=guard`, в меню в основном `+Въезд`

Любой текст вне FSM / `/start` → главное меню по роли.

## Инварианты MAX

- После `message.edit` подтверждать callback через `send_callback_ack` (`message=None` + notification `" "`).
- Снимать клавиатуру через `attachments=[]`, не `None`.
- Специфичные роутеры подключать раньше catch-all `menu`.
- API base: `platform-api2.max.ru` (`apply_max_api_url`).
- Документации MAX из интернета не доверять — ориентир на рабочие боты SNZG / links.

## Данные

- SQLite: `SQLITE_PATH` (по умолчанию `data/bot.sqlite3`)
- Фото въездов: `data/photos/`
- Excel: `data/exports/`
- Матрица цен: строки = транспорт (A), столбцы = `Поселок / Участок`, ячейки = цена; первая строка и столбец подсвечены.

## Ловушки

- Пагинация списков по 10 (`PAGE_SIZE`).
- Сотрудника добавляют числовым `user_id` или пересланным сообщением (`message.link.sender`). Отправитель входящего сообщения — это админ, его id не брать.
- Охранник при `+Въезд` пишет на свой участок из карточки; админ/менеджер выбирают участок.
- В выгрузке результатов фото встраиваются в Excel (Pillow + openpyxl).
