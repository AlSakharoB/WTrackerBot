from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NutritionGoal(Base):
    __tablename__ = "nutrition_goals"
    __table_args__ = (
        CheckConstraint(
            "kcal_target IS NOT NULL OR protein_target_g IS NOT NULL OR "
            "fat_target_g IS NOT NULL OR carbs_target_g IS NOT NULL",
            name="ck_nutrition_goals_at_least_one_target",
        ),
        CheckConstraint(
            "kcal_target IS NULL OR (kcal_target > 0 AND kcal_target <= 10000)",
            name="ck_nutrition_goals_kcal_range",
        ),
        CheckConstraint(
            "protein_target_g IS NULL OR "
            "(protein_target_g > 0 AND protein_target_g <= 1000)",
            name="ck_nutrition_goals_protein_range",
        ),
        CheckConstraint(
            "fat_target_g IS NULL OR (fat_target_g > 0 AND fat_target_g <= 1000)",
            name="ck_nutrition_goals_fat_range",
        ),
        CheckConstraint(
            "carbs_target_g IS NULL OR (carbs_target_g > 0 AND carbs_target_g <= 2000)",
            name="ck_nutrition_goals_carbs_range",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_nutrition_goals_period",
        ),
        Index(
            "ix_nutrition_goals_user_id_effective_from",
            "user_id",
            "effective_from",
        ),
        Index(
            "uq_nutrition_goals_one_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kcal_target: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    protein_target_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fat_target_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    carbs_target_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
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
