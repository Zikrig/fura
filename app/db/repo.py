from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Entry, Price, Settlement, Staff, Vehicle


class Repo:
    def __init__(self, session: Session):
        self.session = session

    # ----- staff -----
    def get_staff(self, user_id: int) -> Staff | None:
        return self.session.scalar(select(Staff).where(Staff.user_id == user_id))

    def get_staff_by_id(self, staff_id: int) -> Staff | None:
        return self.session.scalar(
            select(Staff)
            .options(joinedload(Staff.settlement))
            .where(Staff.id == staff_id)
        )

    def list_staff(self, role: str) -> list[Staff]:
        return list(
            self.session.scalars(
                select(Staff)
                .options(joinedload(Staff.settlement))
                .where(Staff.role == role)
                .order_by(Staff.name.asc())
            ).unique()
        )

    def add_staff(
        self,
        *,
        user_id: int,
        role: str,
        name: str,
        max_link: str,
        settlement_id: int,
    ) -> Staff:
        existing = self.get_staff(user_id)
        if existing:
            existing.role = role
            existing.name = name
            existing.max_link = max_link
            existing.settlement_id = settlement_id
            self.session.flush()
            return existing
        row = Staff(
            user_id=user_id,
            role=role,
            name=name,
            max_link=max_link,
            settlement_id=settlement_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def delete_staff(self, staff_id: int) -> bool:
        row = self.get_staff_by_id(staff_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def update_staff_field(self, staff_id: int, **fields) -> Staff | None:
        row = self.get_staff_by_id(staff_id)
        if not row:
            return None
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        self.session.flush()
        return row

    # ----- settlements -----
    def list_settlements(self) -> list[Settlement]:
        return list(self.session.scalars(select(Settlement).order_by(Settlement.name.asc())))

    def get_settlement(self, settlement_id: int) -> Settlement | None:
        return self.session.get(Settlement, settlement_id)

    def get_settlement_by_name(self, name: str) -> Settlement | None:
        return self.session.scalar(select(Settlement).where(Settlement.name == name))

    def add_settlement(self, name: str) -> Settlement:
        row = Settlement(name=name.strip())
        self.session.add(row)
        self.session.flush()
        return row

    def ensure_settlement(self, name: str) -> Settlement:
        row = self.get_settlement_by_name(name)
        if row:
            return row
        return self.add_settlement(name)

    def rename_settlement(self, settlement_id: int, name: str) -> Settlement | None:
        row = self.get_settlement(settlement_id)
        if not row:
            return None
        row.name = name.strip()
        self.session.flush()
        return row

    def delete_settlement(self, settlement_id: int) -> bool:
        row = self.get_settlement(settlement_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    # ----- vehicles -----
    def list_vehicles(self) -> list[Vehicle]:
        return list(self.session.scalars(select(Vehicle).order_by(Vehicle.name.asc())))

    def get_vehicle(self, vehicle_id: int) -> Vehicle | None:
        return self.session.get(Vehicle, vehicle_id)

    def get_vehicle_by_name(self, name: str) -> Vehicle | None:
        return self.session.scalar(select(Vehicle).where(Vehicle.name == name))

    def add_vehicle(self, name: str) -> Vehicle:
        row = Vehicle(name=name.strip())
        self.session.add(row)
        self.session.flush()
        return row

    def rename_vehicle(self, vehicle_id: int, name: str) -> Vehicle | None:
        row = self.get_vehicle(vehicle_id)
        if not row:
            return None
        row.name = name.strip()
        self.session.flush()
        return row

    def delete_vehicle(self, vehicle_id: int) -> bool:
        row = self.get_vehicle(vehicle_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def ensure_vehicle(self, name: str) -> Vehicle:
        row = self.get_vehicle_by_name(name)
        if row:
            return row
        return self.add_vehicle(name)

    # ----- prices -----
    def get_price(self, vehicle_id: int, settlement_id: int) -> Price | None:
        return self.session.scalar(
            select(Price).where(Price.vehicle_id == vehicle_id, Price.settlement_id == settlement_id)
        )

    def set_price(self, vehicle_id: int, settlement_id: int, amount: float) -> Price:
        row = self.get_price(vehicle_id, settlement_id)
        if row:
            row.amount = float(amount)
            self.session.flush()
            return row
        row = Price(vehicle_id=vehicle_id, settlement_id=settlement_id, amount=float(amount))
        self.session.add(row)
        self.session.flush()
        return row

    def list_prices(self) -> list[Price]:
        return list(
            self.session.scalars(
                select(Price).options(joinedload(Price.vehicle), joinedload(Price.settlement))
            ).unique()
        )

    # ----- entries -----
    def add_entry(
        self,
        *,
        created_at: datetime,
        settlement_id: int,
        plot_name: str,
        vehicle_id: int,
        price_amount: float,
        photo_path: str,
        reporter_user_id: int,
    ) -> Entry:
        row = Entry(
            created_at=created_at,
            settlement_id=settlement_id,
            plot_name=plot_name.strip(),
            vehicle_id=vehicle_id,
            price_amount=float(price_amount),
            photo_path=photo_path,
            reporter_user_id=reporter_user_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_entries(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        settlement_id: int | None = None,
    ) -> list[Entry]:
        stmt = (
            select(Entry)
            .options(
                joinedload(Entry.settlement),
                joinedload(Entry.vehicle),
            )
            .order_by(Entry.created_at.asc())
        )
        if date_from is not None:
            stmt = stmt.where(Entry.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Entry.created_at < date_to)
        if settlement_id is not None:
            stmt = stmt.where(Entry.settlement_id == settlement_id)
        return list(self.session.scalars(stmt).unique())
