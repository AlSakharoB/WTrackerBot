from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)


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

    async def get_by_token_hash(self, token_hash: str) -> SharePackage | None:
        statement = select(SharePackage).where(SharePackage.token_hash == token_hash)
        return await self._session.scalar(statement)

    async def get_by_id(self, package_id: int) -> SharePackage | None:
        return await self._session.get(SharePackage, package_id)

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
        return await self._session.scalar(statement)

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
