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
| Поселки / транспорт | `app/handlers/directory.py` |
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
- Матрица цен: строки = транспорт (A), столбцы = поселок, ячейки = цена; первая строка и столбец подсвечены. Цена въезда — по выбранному поселку (`prices.settlement_id`). Участок въезда — строка `entries.plot_name`. У охранника она из `staff.plot_name` (ввод при регистрации). У админа и менеджера всегда `-1`. Справочника участков нет.

## Ловушки

- Пагинация списков по 10 (`PAGE_SIZE`).
- `session_scope` коммитит и закрывает сессию, а списки читают `item.name` уже снаружи. Поэтому `expire_on_commit=False`: иначе после сохранения поселка/транспорта `DetachedInstanceError`.
- Сотрудника добавляют числовым `user_id` или пересланным сообщением (`message.link.sender`). Отправитель входящего сообщения — это админ, его id не брать.
- Охранник при `+Въезд` берёт поселок и участок из карточки. Админ/менеджер выбирают поселок, участок пишется `-1`. Сумма — из цены поселка.
- В выгрузке результатов фото — PNG, после сохранения поправить связи `Target="/xl/..."` на относительные (`../drawings`, `../media`). С абсолютным Target часть программ открывает xlsx без картинки.
