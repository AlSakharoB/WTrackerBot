from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SharePackageType(StrEnum):
    INGREDIENTS = "ingredients"
    DISHES = "dishes"


class SharePackageStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ShareImportStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"


class SharePackage(Base):
    __tablename__ = "share_packages"
    __table_args__ = (
        CheckConstraint(
            "package_type IN ('ingredients', 'dishes')",
            name="ck_share_packages_package_type",
        ),
        CheckConstraint(
            "payload_version >= 1",
            name="ck_share_packages_payload_version",
        ),
        CheckConstraint("item_count >= 1", name="ck_share_packages_item_count"),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_share_packages_status",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_share_packages_revoked_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    package_type: Mapped[SharePackageType] = mapped_column(String(16), nullable=False)
    payload_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    item_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[SharePackageStatus] = mapped_column(
        String(16),
        nullable=False,
        default=SharePackageStatus.ACTIVE,
        server_default=SharePackageStatus.ACTIVE.value,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


Index(
    "ix_share_packages_owner_created_at",
    SharePackage.owner_user_id,
    SharePackage.created_at.desc(),
)
Index(
    "ix_share_packages_status_expires_at",
    SharePackage.status,
    SharePackage.expires_at,
)


class ShareImport(Base):
    __tablename__ = "share_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_share_imports_status",
        ),
        CheckConstraint(
            "created_ingredients_count >= 0 AND "
            "reused_ingredients_count >= 0 AND "
            "skipped_ingredients_count >= 0 AND "
            "created_dishes_count >= 0 AND "
            "skipped_dishes_count >= 0",
            name="ck_share_imports_counts",
        ),
        CheckConstraint(
            "(status = 'processing' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_share_imports_completed_at",
        ),
        UniqueConstraint(
            "package_id",
            "recipient_user_id",
            name="uq_share_imports_package_id_recipient_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    package_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("share_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ShareImportStatus] = mapped_column(String(16), nullable=False)
    created_ingredients_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reused_ingredients_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    skipped_ingredients_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_dishes_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    skipped_dishes_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
