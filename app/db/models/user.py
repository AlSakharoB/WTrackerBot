from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.user_settings import AfterFoodAddAction, NumberFormat


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "number_format IN ('automatic', 'one_decimal', 'two_decimals')",
            name="ck_users_number_format",
        ),
        CheckConstraint(
            "after_food_add_action IN ('open_today', 'stay')",
            name="ck_users_after_food_add_action",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(35))
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Europe/Moscow",
        server_default="Europe/Moscow",
    )
    number_format: Mapped[NumberFormat] = mapped_column(
        String(16),
        nullable=False,
        default=NumberFormat.AUTOMATIC,
        server_default=NumberFormat.AUTOMATIC.value,
    )
    after_food_add_action: Mapped[AfterFoodAddAction] = mapped_column(
        String(16),
        nullable=False,
        default=AfterFoodAddAction.OPEN_TODAY,
        server_default=AfterFoodAddAction.OPEN_TODAY.value,
    )
    confirm_deletions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
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
