from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Identity, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
