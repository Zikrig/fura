from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    plots: Mapped[list[Plot]] = relationship(back_populates="settlement", cascade="all, delete-orphan")
    staff: Mapped[list[Staff]] = relationship(back_populates="settlement")


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (UniqueConstraint("settlement_id", "name", name="uq_plot_settlement_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlements.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    settlement: Mapped[Settlement] = relationship(back_populates="plots")
    staff: Mapped[list[Staff]] = relationship(back_populates="plot")
    prices: Mapped[list[Price]] = relationship(back_populates="plot", cascade="all, delete-orphan")
    entries: Mapped[list[Entry]] = relationship(back_populates="plot")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    prices: Mapped[list[Price]] = relationship(back_populates="vehicle", cascade="all, delete-orphan")
    entries: Mapped[list[Entry]] = relationship(back_populates="vehicle")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("vehicle_id", "plot_id", name="uq_price_vehicle_plot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    plot_id: Mapped[int] = mapped_column(ForeignKey("plots.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    vehicle: Mapped[Vehicle] = relationship(back_populates="prices")
    plot: Mapped[Plot] = relationship(back_populates="prices")


class Staff(Base):
    """Менеджеры и охранники. Админы задаются только через .env."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # manager | guard
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    max_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id", ondelete="SET NULL"))
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id", ondelete="SET NULL"))

    settlement: Mapped[Settlement | None] = relationship(back_populates="staff")
    plot: Mapped[Plot | None] = relationship(back_populates="staff")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    plot_id: Mapped[int] = mapped_column(ForeignKey("plots.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False)
    price_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    photo_path: Mapped[str] = mapped_column(Text, nullable=False)
    reporter_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    plot: Mapped[Plot] = relationship(back_populates="entries")
    vehicle: Mapped[Vehicle] = relationship(back_populates="entries")
