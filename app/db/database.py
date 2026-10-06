from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _sqlite_url(path) -> str:
    return f"sqlite:///{path.as_posix()}"


engine = create_engine(
    _sqlite_url(settings.SQLITE_PATH),
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def _migrate_prices_to_settlements() -> None:
    """Старая матрица цен была по участкам. Переносим на поселок участка."""
    insp = inspect(engine)
    if "prices" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("prices")}
    if "plot_id" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE prices_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id INTEGER NOT NULL,
                    settlement_id INTEGER NOT NULL,
                    amount FLOAT NOT NULL DEFAULT 0.0,
                    CONSTRAINT uq_price_vehicle_settlement UNIQUE (vehicle_id, settlement_id),
                    CONSTRAINT fk_prices_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
                    CONSTRAINT fk_prices_settlement FOREIGN KEY (settlement_id) REFERENCES settlements(id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO prices_new (vehicle_id, settlement_id, amount)
                SELECT p.vehicle_id, pl.settlement_id, MAX(p.amount)
                FROM prices AS p
                JOIN plots AS pl ON pl.id = p.plot_id
                GROUP BY p.vehicle_id, pl.settlement_id
                """
            )
        )
        conn.execute(text("DROP TABLE prices"))
        conn.execute(text("ALTER TABLE prices_new RENAME TO prices"))


def _migrate_entries_plot_name() -> None:
    """Участок въезда — строка, не запись из справочника."""
    insp = inspect(engine)
    if "entries" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("entries")}
    if "plot_id" not in cols:
        return
    plots_exist = "plots" in insp.get_table_names()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE entries_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    settlement_id INTEGER,
                    plot_name TEXT NOT NULL DEFAULT '',
                    vehicle_id INTEGER NOT NULL,
                    price_amount FLOAT NOT NULL DEFAULT 0.0,
                    photo_path TEXT NOT NULL,
                    reporter_user_id INTEGER NOT NULL,
                    CONSTRAINT fk_entries_settlement FOREIGN KEY (settlement_id) REFERENCES settlements(id) ON DELETE SET NULL,
                    CONSTRAINT fk_entries_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT
                )
                """
            )
        )
        if plots_exist:
            conn.execute(
                text(
                    """
                    INSERT INTO entries_new (
                        created_at, settlement_id, plot_name, vehicle_id, price_amount, photo_path, reporter_user_id
                    )
                    SELECT e.created_at, pl.settlement_id, COALESCE(pl.name, ''), e.vehicle_id,
                           e.price_amount, e.photo_path, e.reporter_user_id
                    FROM entries AS e
                    LEFT JOIN plots AS pl ON pl.id = e.plot_id
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO entries_new (
                        created_at, settlement_id, plot_name, vehicle_id, price_amount, photo_path, reporter_user_id
                    )
                    SELECT created_at, NULL, '', vehicle_id, price_amount, photo_path, reporter_user_id
                    FROM entries
                    """
                )
            )
        conn.execute(text("DROP TABLE entries"))
        conn.execute(text("ALTER TABLE entries_new RENAME TO entries"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entries_created_at ON entries (created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entries_reporter ON entries (reporter_user_id)"))


def _drop_staff_plot_name() -> None:
    """Участок не хранится у охранника: его вводят строкой при въезде."""
    insp = inspect(engine)
    if "staff" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("staff")}
    if "plot_name" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE staff DROP COLUMN plot_name"))


def _drop_staff_settlement_binding() -> None:
    """Менеджер не закреплён за поселком. У охранника поселки остаются в staff_settlements."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "staff" not in tables or "settlements" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("staff")}
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS staff_settlements (
                    staff_id INTEGER NOT NULL,
                    settlement_id INTEGER NOT NULL,
                    PRIMARY KEY (staff_id, settlement_id),
                    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
                    FOREIGN KEY (settlement_id) REFERENCES settlements(id) ON DELETE CASCADE
                )
                """
            )
        )
        if "settlement_id" in cols:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO staff_settlements (staff_id, settlement_id)
                    SELECT s.id, s.settlement_id
                    FROM staff AS s
                    JOIN settlements AS st ON st.id = s.settlement_id
                    WHERE s.role = 'guard' AND s.settlement_id IS NOT NULL
                    """
                )
            )
    if "settlement_id" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE staff_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    max_link TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO staff_new (id, user_id, role, name, max_link)
                SELECT id, user_id, role, name, COALESCE(max_link, '')
                FROM staff
                """
            )
        )
        conn.execute(text("DROP TABLE staff"))
        conn.execute(text("ALTER TABLE staff_new RENAME TO staff"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_staff_user_id ON staff (user_id)"))


def init_db() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    settings.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    from app.db import models  # noqa: F401

    _migrate_prices_to_settlements()
    _migrate_entries_plot_name()
    _drop_staff_plot_name()
    _drop_staff_settlement_binding()
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
