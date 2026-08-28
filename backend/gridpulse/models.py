"""Database schema for grid time-series data."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    region_name: Mapped[str] = mapped_column(String(64), nullable=False)


class GridLoad(Base):
    """One row per balancing authority per hour, as reported by EIA.

    Columns map to EIA region-data series types: D, DF, NG and TI. Values stay
    nullable because EIA publishes them on different lags, so a fresh hour often
    has demand but not yet a net-generation figure.
    """

    __tablename__ = "grid_load"

    # Ordered region-then-time so the primary key index also serves the
    # "latest N hours for one region" query that every endpoint runs.
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.region_id"), primary_key=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    actual_demand_mw: Mapped[float | None] = mapped_column(Float)
    forecast_demand_mw: Mapped[float | None] = mapped_column(Float)
    net_generation_mw: Mapped[float | None] = mapped_column(Float)
    interchange_mw: Mapped[float | None] = mapped_column(Float)
