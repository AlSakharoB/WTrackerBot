from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalProductCache(Base):
    __tablename__ = "external_product_cache"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    barcode: Mapped[str] = mapped_column(String(14), primary_key=True)
    response_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    http_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_external_product_cache_expires_at", ExternalProductCache.expires_at)


class IngredientExternalSource(Base):
    __tablename__ = "ingredient_external_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "ingredient_id"],
            ["ingredients.user_id", "ingredients.id"],
            name="fk_ingredient_external_sources_user_ingredient",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            "external_code",
            name="uq_ingredient_external_sources_user_provider_code",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ingredient_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
