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
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiaryEntryType(StrEnum):
    INGREDIENT = "ingredient"
    DISH = "dish"


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    OTHER = "other"


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_class]


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = (
        CheckConstraint("grams > 0", name="ck_diary_entries_grams_positive"),
        CheckConstraint(
            "kcal_snapshot >= 0 AND protein_snapshot >= 0 "
            "AND fat_snapshot >= 0 AND carbs_snapshot >= 0",
            name="ck_diary_entries_snapshots_non_negative",
        ),
        CheckConstraint(
            "(entry_type = 'ingredient' AND dish_id IS NULL) OR "
            "(entry_type = 'dish' AND ingredient_id IS NULL)",
            name="ck_diary_entries_source_type",
        ),
        Index("ix_diary_entries_user_id_entry_date", "user_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[DiaryEntryType] = mapped_column(
        Enum(
            DiaryEntryType,
            name="diary_entry_type",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    ingredient_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ingredients.id", ondelete="SET NULL"),
    )
    dish_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dishes.id", ondelete="SET NULL"),
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    meal_type: Mapped[MealType] = mapped_column(
        Enum(MealType, name="meal_type", values_callable=_enum_values),
        nullable=False,
        default=MealType.OTHER,
        server_default=MealType.OTHER.value,
    )
    kcal_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    protein_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fat_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    carbs_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
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
