from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _goal_status_values(enum_class: type[GoalStatus]) -> list[str]:
    return [item.value for item in enum_class]


class WeightGoal(Base):
    __tablename__ = "weight_goals"
    __table_args__ = (
        CheckConstraint(
            "target_weight_kg >= 20 AND target_weight_kg <= 500",
            name="ck_weight_goals_target_weight_range",
        ),
        CheckConstraint(
            "start_weight_kg IS NULL OR "
            "(start_weight_kg >= 20 AND start_weight_kg <= 500)",
            name="ck_weight_goals_start_weight_range",
        ),
        Index("ix_weight_goals_user_id_status", "user_id", "status"),
        Index(
            "uq_weight_goals_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
    )
    target_date: Mapped[date | None] = mapped_column(Date)
    start_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    status: Mapped[GoalStatus] = mapped_column(
        Enum(
            GoalStatus,
            name="goal_status",
            values_callable=_goal_status_values,
        ),
        nullable=False,
        default=GoalStatus.ACTIVE,
        server_default=GoalStatus.ACTIVE.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
