from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.ui_preferences import DefaultSection, ThemeMode, WeightUnit


class UserUIPreference(Base):
    __tablename__ = "user_ui_preferences"
    __table_args__ = (
        CheckConstraint(
            "theme_mode IN ('system', 'light', 'dark')",
            name="theme_mode",
        ),
        CheckConstraint(
            "default_section IN ('ration', 'food', 'weight', 'profile')",
            name="default_section",
        ),
        CheckConstraint("default_weight_unit IN ('kg')", name="weight_unit"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    theme_mode: Mapped[ThemeMode] = mapped_column(
        String(16),
        nullable=False,
        default=ThemeMode.SYSTEM,
        server_default=ThemeMode.SYSTEM.value,
    )
    default_section: Mapped[DefaultSection] = mapped_column(
        String(16),
        nullable=False,
        default=DefaultSection.RATION,
        server_default=DefaultSection.RATION.value,
    )
    default_weight_unit: Mapped[WeightUnit] = mapped_column(
        String(8),
        nullable=False,
        default=WeightUnit.KG,
        server_default=WeightUnit.KG.value,
    )
    compact_lists: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
