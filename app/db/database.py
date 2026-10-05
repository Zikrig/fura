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


def _migrate_staff_plot_name() -> None:
    insp = inspect(engine)
    if "staff" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("staff")}
    if "plot_name" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE staff ADD COLUMN plot_name TEXT NOT NULL DEFAULT ''"))


def init_db() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    settings.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    from app.db import models  # noqa: F401

    _migrate_prices_to_settlements()
    _migrate_entries_plot_name()
    _migrate_staff_plot_name()
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
