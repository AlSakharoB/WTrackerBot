from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)


@dataclass(frozen=True, slots=True)
class OwnedSharePackageRecord:
    package: SharePackage
    completed_imports: int


class ShareTokenHashCollisionError(Exception):
    """A generated token hash already exists in storage."""


class ShareRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_package(
        self,
        *,
        owner_user_id: int,
        token_hash: str,
        package_type: SharePackageType,
        payload_version: int,
        payload: dict[str, object],
        item_count: int,
        expires_at: datetime,
    ) -> SharePackage:
        statement = (
            insert(SharePackage)
            .values(
                owner_user_id=owner_user_id,
                token_hash=token_hash,
                package_type=package_type,
                payload_version=payload_version,
                payload=payload,
                item_count=item_count,
                status=SharePackageStatus.ACTIVE,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=[SharePackage.token_hash])
            .returning(SharePackage)
        )
        package = await self._session.scalar(statement)
        if package is None:
            raise ShareTokenHashCollisionError
        return package

    async def get_owned_by_id(
        self,
        package_id: int,
        owner_user_id: int,
    ) -> SharePackage | None:
        statement = select(SharePackage).where(
            SharePackage.id == package_id,
            SharePackage.owner_user_id == owner_user_id,
        )
        return await self._session.scalar(statement)

    async def get_owned_record(
        self,
        package_id: int,
        owner_user_id: int,
    ) -> OwnedSharePackageRecord | None:
        completed_imports = (
            select(func.count(ShareImport.id))
            .where(
                ShareImport.package_id == SharePackage.id,
                ShareImport.status == ShareImportStatus.COMPLETED,
            )
            .correlate(SharePackage)
            .scalar_subquery()
        )
        statement = select(SharePackage, completed_imports).where(
            SharePackage.id == package_id,
            SharePackage.owner_user_id == owner_user_id,
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return OwnedSharePackageRecord(row[0], int(row[1]))

    async def list_owned(
        self,
        owner_user_id: int,
        package_type: SharePackageType,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[OwnedSharePackageRecord], int]:
        completed_imports = (
            select(func.count(ShareImport.id))
            .where(
                ShareImport.package_id == SharePackage.id,
                ShareImport.status == ShareImportStatus.COMPLETED,
            )
            .correlate(SharePackage)
            .scalar_subquery()
        )
        filters = (
            SharePackage.owner_user_id == owner_user_id,
            SharePackage.package_type == package_type,
        )
        total = int(
            await self._session.scalar(
                select(func.count(SharePackage.id)).where(*filters)
            )
            or 0
        )
        statement = (
            select(SharePackage, completed_imports)
            .where(*filters)
            .order_by(SharePackage.created_at.desc(), SharePackage.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [OwnedSharePackageRecord(row[0], int(row[1])) for row in rows], total

    async def get_by_token_hash(self, token_hash: str) -> SharePackage | None:
        statement = select(SharePackage).where(SharePackage.token_hash == token_hash)
        return await self._session.scalar(statement)

    async def get_by_id(
        self,
        package_id: int,
        *,
        for_update: bool = False,
    ) -> SharePackage | None:
        statement = select(SharePackage).where(SharePackage.id == package_id)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def revoke_owned(
        self,
        package_id: int,
        owner_user_id: int,
        revoked_at: datetime,
    ) -> SharePackage | None:
        statement = (
            update(SharePackage)
            .where(
                SharePackage.id == package_id,
                SharePackage.owner_user_id == owner_user_id,
                SharePackage.status == SharePackageStatus.ACTIVE,
            )
            .values(
                status=SharePackageStatus.REVOKED,
                revoked_at=revoked_at,
                updated_at=revoked_at,
            )
            .returning(SharePackage)
            .execution_options(populate_existing=True)
        )
        package = await self._session.scalar(statement)
        if package is not None:
            return package
        return await self.get_owned_by_id(package_id, owner_user_id)

    async def rotate_owned(
        self,
        package_id: int,
        owner_user_id: int,
        *,
        token_hash: str,
        expires_at: datetime,
        rotated_at: datetime,
    ) -> SharePackage | None:
        statement = (
            update(SharePackage)
            .where(
                SharePackage.id == package_id,
                SharePackage.owner_user_id == owner_user_id,
            )
            .values(
                token_hash=token_hash,
                status=SharePackageStatus.ACTIVE,
                expires_at=expires_at,
                revoked_at=None,
                updated_at=rotated_at,
            )
            .returning(SharePackage)
            .execution_options(populate_existing=True)
        )
        try:
            async with self._session.begin_nested():
                return await self._session.scalar(statement)
        except IntegrityError as error:
            raise ShareTokenHashCollisionError from error

    async def delete_stale_packages(
        self,
        *,
        cutoff: datetime,
        batch_size: int,
    ) -> int:
        stale_ids = (
            select(SharePackage.id)
            .where(
                or_(
                    (
                        (SharePackage.status == SharePackageStatus.ACTIVE)
                        & (SharePackage.expires_at <= cutoff)
                    ),
                    (
                        (SharePackage.status == SharePackageStatus.REVOKED)
                        & (SharePackage.revoked_at <= cutoff)
                    ),
                )
            )
            .order_by(SharePackage.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        statement = (
            delete(SharePackage)
            .where(SharePackage.id.in_(stale_ids))
            .returning(SharePackage.id)
        )
        deleted_ids = (await self._session.scalars(statement)).all()
        return len(deleted_ids)

    async def get_import(
        self,
        package_id: int,
        recipient_user_id: int,
    ) -> ShareImport | None:
        statement = select(ShareImport).where(
            ShareImport.package_id == package_id,
            ShareImport.recipient_user_id == recipient_user_id,
        )
        return await self._session.scalar(statement)

    async def claim_import(
        self,
        package_id: int,
        recipient_user_id: int,
    ) -> tuple[ShareImport, bool]:
        statement = (
            insert(ShareImport)
            .values(
                package_id=package_id,
                recipient_user_id=recipient_user_id,
                status=ShareImportStatus.PROCESSING,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ShareImport.package_id,
                    ShareImport.recipient_user_id,
                ]
            )
            .returning(ShareImport)
        )
        claimed = await self._session.scalar(statement)
        if claimed is not None:
            return claimed, True
        existing = await self.get_import(package_id, recipient_user_id)
        if existing is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("Share import conflict row was not found")
        return existing, False

    async def complete_ingredient_import(
        self,
        import_id: int,
        *,
        created_count: int,
        reused_count: int,
        skipped_count: int,
        completed_at: datetime,
    ) -> ShareImport:
        statement = (
            update(ShareImport)
            .where(
                ShareImport.id == import_id,
                ShareImport.status == ShareImportStatus.PROCESSING,
            )
            .values(
                status=ShareImportStatus.COMPLETED,
                created_ingredients_count=created_count,
                reused_ingredients_count=reused_count,
                skipped_ingredients_count=skipped_count,
                completed_at=completed_at,
            )
            .returning(ShareImport)
            .execution_options(populate_existing=True)
        )
        completed = await self._session.scalar(statement)
        if completed is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("Share import could not be completed")
        return completed

    async def complete_dish_import(
        self,
        import_id: int,
        *,
        created_ingredients_count: int,
        reused_ingredients_count: int,
        skipped_ingredients_count: int,
        created_dishes_count: int,
        skipped_dishes_count: int,
        completed_at: datetime,
    ) -> ShareImport:
        statement = (
            update(ShareImport)
            .where(
                ShareImport.id == import_id,
                ShareImport.status == ShareImportStatus.PROCESSING,
            )
            .values(
                status=ShareImportStatus.COMPLETED,
                created_ingredients_count=created_ingredients_count,
                reused_ingredients_count=reused_ingredients_count,
                skipped_ingredients_count=skipped_ingredients_count,
                created_dishes_count=created_dishes_count,
                skipped_dishes_count=skipped_dishes_count,
                completed_at=completed_at,
            )
            .returning(ShareImport)
            .execution_options(populate_existing=True)
        )
        completed = await self._session.scalar(statement)
        if completed is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("Share import could not be completed")
        return completed
