from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReminderType(StrEnum):
    WEIGH_IN = "weigh_in"
    NUTRITION = "nutrition"


def _reminder_type_values(enum_class: type[ReminderType]) -> list[str]:
    return [item.value for item in enum_class]


class ReminderSetting(Base):
    __tablename__ = "reminder_settings"
    __table_args__ = (
        CheckConstraint(
            "weekdays_mask >= 1 AND weekdays_mask <= 127",
            name="ck_reminder_settings_weekdays_mask",
        ),
        UniqueConstraint(
            "user_id",
            "reminder_type",
            name="uq_reminder_settings_user_id_reminder_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type: Mapped[ReminderType] = mapped_column(
        Enum(
            ReminderType,
            name="reminder_type",
            values_callable=_reminder_type_values,
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    time_local: Mapped[time] = mapped_column(Time, nullable=False)
    weekdays_mask: Mapped[int] = mapped_column(Integer, nullable=False)
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
