from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeightEntry(Base):
    __tablename__ = "weight_entries"
    __table_args__ = (
        CheckConstraint(
            "weight_kg >= 20 AND weight_kg <= 500",
            name="ck_weight_entries_weight_range",
        ),
        Index(
            "ix_weight_entries_user_id_measured_at",
            "user_id",
            desc("measured_at"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
