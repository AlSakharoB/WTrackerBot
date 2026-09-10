from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FoodFolder(Base):
    __tablename__ = "food_folders"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_food_folders_user_id_normalized_name",
        ),
        UniqueConstraint(
            "user_id",
            "id",
            name="uq_food_folders_user_id_id",
        ),
        UniqueConstraint(
            "user_id",
            "sort_order",
            name="uq_food_folders_user_id_sort_order",
        ),
        CheckConstraint("sort_order >= 0", name="food_folders_sort_order_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FoodFolderItem(Base):
    __tablename__ = "food_folder_items"
    __table_args__ = (
        CheckConstraint(
            "(ingredient_id IS NOT NULL) <> (dish_id IS NOT NULL)",
            name="food_folder_items_exactly_one_food",
        ),
        ForeignKeyConstraint(
            ["user_id", "folder_id"],
            ["food_folders.user_id", "food_folders.id"],
            name="fk_food_folder_items_user_folder",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "ingredient_id"],
            ["ingredients.user_id", "ingredients.id"],
            name="fk_food_folder_items_user_ingredient",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "dish_id"],
            ["dishes.user_id", "dishes.id"],
            name="fk_food_folder_items_user_dish",
            ondelete="CASCADE",
        ),
        Index(
            "uq_food_folder_items_ingredient_id",
            "ingredient_id",
            unique=True,
            postgresql_where=text("ingredient_id IS NOT NULL"),
        ),
        Index(
            "uq_food_folder_items_dish_id",
            "dish_id",
            unique=True,
            postgresql_where=text("dish_id IS NOT NULL"),
        ),
        Index("ix_food_folder_items_user_folder", "user_id", "folder_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    folder_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ingredient_id: Mapped[int | None] = mapped_column(BigInteger)
    dish_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
