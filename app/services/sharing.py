from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.db.models.ingredient import Ingredient
from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import (
    ShareRepository,
    ShareTokenHashCollisionError,
)
from app.search import (
    DUPLICATE_NAME_SIMILARITY_THRESHOLD,
    names_have_different_numbers,
    normalize_search_text,
)
from app.services.ingredients import CreateIngredientData, IngredientService
from app.sharing.links import build_share_deep_link, build_telegram_share_url
from app.sharing.payloads import (
    DishSharePayload,
    IngredientSharePayload,
    SharedIngredient,
    SharePayload,
    SharePayloadLimitError,
    SharePayloadLimits,
    parse_share_payload,
    serialize_share_payload,
    validate_share_payload_limits,
)
from app.sharing.tokens import (
    generate_share_token,
    hash_share_token,
    is_valid_share_token,
)

TOKEN_GENERATION_ATTEMPTS = 3
DB_NUTRITION_QUANTUM = Decimal("0.01")


class InvalidShareLinkError(ValidationError):
    """Share token is malformed, unavailable, or revoked."""


class ExpiredShareLinkError(ValidationError):
    """Share package is past its expiry timestamp."""


class IngredientConflictType(StrEnum):
    NEW = "new"
    EXACT_SAME = "exact_same"
    NAME_CONFLICT = "name_conflict"
    SIMILAR_CONFLICT = "similar_conflict"


class IngredientImportResolution(StrEnum):
    ADD = "add"
    KEEP_MINE = "keep_mine"
    CREATE_COPY = "create_copy"


class BatchIngredientAction(StrEnum):
    CREATE = "create"
    REUSE = "reuse"
    COPY_WITH_GENERATED_NAME = "copy_with_generated_name"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CreatedSharePackage:
    package: SharePackage
    token: str
    deep_link: str
    telegram_share_url: str


@dataclass(frozen=True, slots=True)
class IngredientPackageAccess:
    package: SharePackage
    payload: IngredientSharePayload
    previous_import: ShareImport | None
    is_owner: bool


@dataclass(frozen=True, slots=True)
class IngredientPreflight:
    conflict_type: IngredientConflictType
    incoming: SharedIngredient
    existing: Ingredient | None = None


@dataclass(frozen=True, slots=True)
class IngredientImportResult:
    import_record: ShareImport | None
    preflight: IngredientPreflight
    ingredient: Ingredient | None
    already_completed: bool = False

    @property
    def requires_resolution(self) -> bool:
        return self.import_record is None and self.preflight.conflict_type in {
            IngredientConflictType.NAME_CONFLICT,
            IngredientConflictType.SIMILAR_CONFLICT,
        }


@dataclass(frozen=True, slots=True)
class BatchIngredientPreflight:
    items: tuple[IngredientPreflight, ...]

    @property
    def new_count(self) -> int:
        return sum(
            item.conflict_type is IngredientConflictType.NEW for item in self.items
        )

    @property
    def exact_count(self) -> int:
        return sum(
            item.conflict_type is IngredientConflictType.EXACT_SAME
            for item in self.items
        )

    @property
    def conflict_count(self) -> int:
        return len(self.items) - self.new_count - self.exact_count

    @property
    def conflicts(self) -> tuple[IngredientPreflight, ...]:
        return tuple(
            item
            for item in self.items
            if item.conflict_type
            in {
                IngredientConflictType.NAME_CONFLICT,
                IngredientConflictType.SIMILAR_CONFLICT,
            }
        )


@dataclass(frozen=True, slots=True)
class BatchIngredientPlanItem:
    preflight: IngredientPreflight
    action: BatchIngredientAction


@dataclass(frozen=True, slots=True)
class BatchIngredientImportPlan:
    items: tuple[BatchIngredientPlanItem, ...]


@dataclass(frozen=True, slots=True)
class BatchIngredientImportResult:
    import_record: ShareImport
    plan: BatchIngredientImportPlan
    created_ingredients: tuple[Ingredient, ...]
    already_completed: bool = False


class SharingService:
    def __init__(
        self,
        repository: ShareRepository,
        *,
        bot_username: str | None,
        link_ttl_days: int,
        limits: SharePayloadLimits,
        ingredient_repository: IngredientRepository | None = None,
        token_factory: Callable[[], str] = generate_share_token,
    ) -> None:
        self._repository = repository
        self._bot_username = bot_username
        self._link_ttl_days = link_ttl_days
        self._limits = limits
        self._ingredient_repository = ingredient_repository
        self._token_factory = token_factory

    async def create_ingredient_package(
        self,
        owner_user_id: int,
        ingredient_id: int,
    ) -> CreatedSharePackage:
        ingredient_repository = self._require_ingredient_repository()
        ingredient = await ingredient_repository.get_by_id(
            ingredient_id,
            owner_user_id,
        )
        if ingredient is None:
            raise NotFoundError("Ингредиент не найден.")
        payload = IngredientSharePayload(
            ingredients=[
                SharedIngredient(
                    key="i1",
                    name=ingredient.name,
                    kcal_per_100g=ingredient.kcal_per_100g,
                    protein_per_100g=ingredient.protein_per_100g,
                    fat_per_100g=ingredient.fat_per_100g,
                    carbs_per_100g=ingredient.carbs_per_100g,
                )
            ]
        )
        return await self.create_package(
            owner_user_id,
            payload,
            share_text=(
                f"Делюсь ингредиентом «{ingredient.name}». "
                "Откройте ссылку, чтобы добавить его в бот."
            ),
        )

    async def create_ingredient_batch_package(
        self,
        owner_user_id: int,
        ingredient_ids: list[int],
    ) -> CreatedSharePackage:
        if not ingredient_ids:
            raise ValidationError("Выберите хотя бы один ингредиент.")
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValidationError("Один ингредиент нельзя выбрать дважды.")
        if len(ingredient_ids) > self._limits.max_items:
            raise ValidationError(
                f"Можно выбрать не более {self._limits.max_items} ингредиентов."
            )
        ingredient_repository = self._require_ingredient_repository()
        ingredients = await ingredient_repository.get_by_ids(
            set(ingredient_ids),
            owner_user_id,
        )
        by_id = {ingredient.id: ingredient for ingredient in ingredients}
        if len(by_id) != len(ingredient_ids):
            raise NotFoundError("Один из выбранных ингредиентов удалён или недоступен.")
        ordered = [by_id[ingredient_id] for ingredient_id in ingredient_ids]
        payload = IngredientSharePayload(
            ingredients=[
                SharedIngredient(
                    key=f"i{index}",
                    name=ingredient.name,
                    kcal_per_100g=ingredient.kcal_per_100g,
                    protein_per_100g=ingredient.protein_per_100g,
                    fat_per_100g=ingredient.fat_per_100g,
                    carbs_per_100g=ingredient.carbs_per_100g,
                )
                for index, ingredient in enumerate(ordered, start=1)
            ]
        )
        return await self.create_package(
            owner_user_id,
            payload,
            share_text=(
                f"Делюсь набором ингредиентов ({len(ordered)}). "
                "Откройте ссылку, чтобы добавить их в бот."
            ),
        )

    async def create_package(
        self,
        owner_user_id: int,
        payload: SharePayload,
        *,
        share_text: str,
        now: datetime | None = None,
    ) -> CreatedSharePackage:
        if self._bot_username is None:
            raise ValidationError("Ссылки для обмена временно недоступны.")
        try:
            validate_share_payload_limits(payload, self._limits)
        except SharePayloadLimitError as error:
            raise ValidationError("Пакет слишком большой для отправки.") from error

        created_at = now or datetime.now(UTC)
        package_type = (
            SharePackageType.DISHES
            if isinstance(payload, DishSharePayload)
            else SharePackageType.INGREDIENTS
        )
        item_count = (
            len(payload.dishes)
            if isinstance(payload, DishSharePayload)
            else len(payload.ingredients)
        )
        serialized_payload = serialize_share_payload(payload)

        for _ in range(TOKEN_GENERATION_ATTEMPTS):
            token = self._token_factory()
            try:
                package = await self._repository.create_package(
                    owner_user_id=owner_user_id,
                    token_hash=hash_share_token(token),
                    package_type=package_type,
                    payload_version=payload.version,
                    payload=serialized_payload,
                    item_count=item_count,
                    expires_at=created_at + timedelta(days=self._link_ttl_days),
                )
            except ShareTokenHashCollisionError:
                continue
            deep_link = build_share_deep_link(self._bot_username, token)
            return CreatedSharePackage(
                package=package,
                token=token,
                deep_link=deep_link,
                telegram_share_url=build_telegram_share_url(deep_link, share_text),
            )
        raise RuntimeError("Could not allocate a unique share token")

    async def resolve_ingredient_token(
        self,
        token: str,
        recipient_user_id: int,
        *,
        now: datetime | None = None,
    ) -> IngredientPackageAccess:
        if not is_valid_share_token(token):
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        package = await self._repository.get_by_token_hash(hash_share_token(token))
        return await self._build_ingredient_access(
            package,
            recipient_user_id,
            now=now,
        )

    async def get_ingredient_package(
        self,
        package_id: int,
        recipient_user_id: int,
        *,
        now: datetime | None = None,
    ) -> IngredientPackageAccess:
        package = await self._repository.get_by_id(package_id)
        return await self._build_ingredient_access(
            package,
            recipient_user_id,
            now=now,
        )

    async def preflight_ingredient(
        self,
        recipient_user_id: int,
        incoming: SharedIngredient,
    ) -> IngredientPreflight:
        ingredient_repository = self._require_ingredient_repository()
        normalized_name = normalize_search_text(incoming.name)
        exact = await ingredient_repository.get_by_normalized_name(
            recipient_user_id,
            normalized_name,
        )
        if exact is not None:
            conflict_type = (
                IngredientConflictType.EXACT_SAME
                if _nutrition_matches(exact, incoming)
                else IngredientConflictType.NAME_CONFLICT
            )
            return IngredientPreflight(conflict_type, incoming, exact)

        candidates = await ingredient_repository.find_similar_names(
            recipient_user_id,
            normalized_name,
            DUPLICATE_NAME_SIMILARITY_THRESHOLD,
        )
        similar = next(
            (
                candidate
                for candidate in candidates
                if not names_have_different_numbers(
                    normalized_name,
                    candidate.name_normalized,
                )
            ),
            None,
        )
        if similar is not None:
            return IngredientPreflight(
                IngredientConflictType.SIMILAR_CONFLICT,
                incoming,
                similar,
            )
        return IngredientPreflight(IngredientConflictType.NEW, incoming)

    async def preflight_ingredient_batch(
        self,
        recipient_user_id: int,
        payload: IngredientSharePayload,
    ) -> BatchIngredientPreflight:
        items = [
            await self.preflight_ingredient(recipient_user_id, incoming)
            for incoming in payload.ingredients
        ]
        return BatchIngredientPreflight(tuple(items))

    async def build_ingredient_batch_plan(
        self,
        recipient_user_id: int,
        payload: IngredientSharePayload,
        conflict_decisions: dict[str, str],
    ) -> BatchIngredientImportPlan:
        preflight = await self.preflight_ingredient_batch(
            recipient_user_id,
            payload,
        )
        items: list[BatchIngredientPlanItem] = []
        for item in preflight.items:
            if item.conflict_type is IngredientConflictType.NEW:
                action = BatchIngredientAction.CREATE
            elif item.conflict_type is IngredientConflictType.EXACT_SAME:
                action = BatchIngredientAction.REUSE
            else:
                try:
                    selected = BatchIngredientAction(
                        conflict_decisions.get(
                            item.incoming.key,
                            BatchIngredientAction.SKIP,
                        )
                    )
                except ValueError:
                    selected = BatchIngredientAction.SKIP
                action = (
                    selected
                    if selected
                    in {
                        BatchIngredientAction.REUSE,
                        BatchIngredientAction.COPY_WITH_GENERATED_NAME,
                        BatchIngredientAction.SKIP,
                    }
                    else BatchIngredientAction.SKIP
                )
            items.append(BatchIngredientPlanItem(item, action))
        return BatchIngredientImportPlan(tuple(items))

    async def import_ingredient_batch(
        self,
        package_id: int,
        recipient_user_id: int,
        conflict_decisions: dict[str, str],
        *,
        now: datetime | None = None,
    ) -> BatchIngredientImportResult:
        completed_at = now or datetime.now(UTC)
        access = await self.get_ingredient_package(
            package_id,
            recipient_user_id,
            now=completed_at,
        )
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        plan = await self.build_ingredient_batch_plan(
            recipient_user_id,
            access.payload,
            conflict_decisions,
        )
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            return BatchIngredientImportResult(
                access.previous_import,
                plan,
                (),
                already_completed=True,
            )

        import_record, claimed = await self._repository.claim_import(
            package_id,
            recipient_user_id,
        )
        if not claimed:
            if import_record.status == ShareImportStatus.PROCESSING:
                raise ValidationError(
                    "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
                )
            return BatchIngredientImportResult(
                import_record,
                plan,
                (),
                already_completed=True,
            )

        created: list[Ingredient] = []
        created_count = 0
        reused_count = 0
        skipped_count = 0
        for item in plan.items:
            if item.action is BatchIngredientAction.CREATE:
                created.append(
                    await self._create_imported_ingredient(
                        recipient_user_id,
                        item.preflight.incoming,
                    )
                )
                created_count += 1
            elif item.action is BatchIngredientAction.REUSE:
                if item.preflight.existing is None:
                    raise ValidationError(
                        "План импорта устарел. Откройте ссылку заново."
                    )
                reused_count += 1
            elif item.action is BatchIngredientAction.COPY_WITH_GENERATED_NAME:
                created.append(
                    await self._create_unique_copy(
                        recipient_user_id,
                        item.preflight.incoming,
                    )
                )
                created_count += 1
            else:
                skipped_count += 1

        completed = await self._repository.complete_ingredient_import(
            import_record.id,
            created_count=created_count,
            reused_count=reused_count,
            skipped_count=skipped_count,
            completed_at=completed_at,
        )
        return BatchIngredientImportResult(completed, plan, tuple(created))

    async def import_ingredient(
        self,
        package_id: int,
        recipient_user_id: int,
        resolution: IngredientImportResolution,
        *,
        now: datetime | None = None,
    ) -> IngredientImportResult:
        completed_at = now or datetime.now(UTC)
        access = await self.get_ingredient_package(
            package_id,
            recipient_user_id,
            now=completed_at,
        )
        if len(access.payload.ingredients) != 1:
            raise InvalidShareLinkError("Ссылка предназначена для набора ингредиентов.")
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        incoming = access.payload.ingredients[0]
        preflight = await self.preflight_ingredient(recipient_user_id, incoming)
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            return IngredientImportResult(
                import_record=access.previous_import,
                preflight=preflight,
                ingredient=preflight.existing,
                already_completed=True,
            )
        if (
            preflight.conflict_type
            in {
                IngredientConflictType.NAME_CONFLICT,
                IngredientConflictType.SIMILAR_CONFLICT,
            }
            and resolution is IngredientImportResolution.ADD
        ):
            return IngredientImportResult(None, preflight, None)

        import_record, claimed = await self._repository.claim_import(
            package_id,
            recipient_user_id,
        )
        if not claimed:
            if import_record.status == ShareImportStatus.PROCESSING:
                raise ValidationError(
                    "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
                )
            return IngredientImportResult(
                import_record=import_record,
                preflight=preflight,
                ingredient=preflight.existing,
                already_completed=True,
            )

        ingredient: Ingredient | None
        created_count = 0
        reused_count = 0
        skipped_count = 0
        if (
            preflight.conflict_type is IngredientConflictType.NEW
            and resolution is IngredientImportResolution.KEEP_MINE
        ):
            ingredient = None
            skipped_count = 1
        elif (
            preflight.conflict_type is IngredientConflictType.NEW
            and resolution is IngredientImportResolution.CREATE_COPY
        ):
            ingredient = await self._create_unique_copy(
                recipient_user_id,
                incoming,
            )
            created_count = 1
        elif preflight.conflict_type is IngredientConflictType.NEW:
            ingredient = await self._create_imported_ingredient(
                recipient_user_id,
                incoming,
            )
            created_count = 1
        elif preflight.conflict_type is IngredientConflictType.EXACT_SAME:
            ingredient = preflight.existing
            reused_count = 1
        elif resolution is IngredientImportResolution.KEEP_MINE:
            ingredient = preflight.existing
            reused_count = 1
        elif resolution is IngredientImportResolution.CREATE_COPY:
            ingredient = await self._create_unique_copy(
                recipient_user_id,
                incoming,
            )
            created_count = 1
        else:  # pragma: no cover - guarded by conflict response above
            skipped_count = 1
            ingredient = None

        completed = await self._repository.complete_ingredient_import(
            import_record.id,
            created_count=created_count,
            reused_count=reused_count,
            skipped_count=skipped_count,
            completed_at=completed_at,
        )
        return IngredientImportResult(completed, preflight, ingredient)

    async def revoke_package(
        self,
        package_id: int,
        owner_user_id: int,
        *,
        now: datetime | None = None,
    ) -> SharePackage:
        package = await self._repository.revoke_owned(
            package_id,
            owner_user_id,
            now or datetime.now(UTC),
        )
        if package is None:
            raise NotFoundError("Ссылка не найдена или уже отозвана.")
        return package

    async def _build_ingredient_access(
        self,
        package: SharePackage | None,
        recipient_user_id: int,
        *,
        now: datetime | None,
    ) -> IngredientPackageAccess:
        if package is None or package.status != SharePackageStatus.ACTIVE:
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        current_time = now or datetime.now(UTC)
        if package.expires_at <= current_time:
            raise ExpiredShareLinkError(
                "Срок действия ссылки истёк. Попросите отправителя создать новую."
            )
        try:
            payload = parse_share_payload(package.payload)
        except ValueError as error:
            raise InvalidShareLinkError(
                "Ссылка недействительна или была отозвана."
            ) from error
        if (
            not isinstance(payload, IngredientSharePayload)
            or package.package_type != SharePackageType.INGREDIENTS
            or package.payload_version != payload.version
            or package.item_count != len(payload.ingredients)
        ):
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        try:
            validate_share_payload_limits(payload, self._limits)
        except SharePayloadLimitError as error:
            raise InvalidShareLinkError(
                "Ссылка недействительна или была отозвана."
            ) from error
        previous_import = await self._repository.get_import(
            package.id,
            recipient_user_id,
        )
        return IngredientPackageAccess(
            package=package,
            payload=payload,
            previous_import=previous_import,
            is_owner=package.owner_user_id == recipient_user_id,
        )

    async def _create_imported_ingredient(
        self,
        user_id: int,
        incoming: SharedIngredient,
    ) -> Ingredient:
        return await IngredientService(self._require_ingredient_repository()).create(
            user_id, _ingredient_data(incoming)
        )

    async def _create_unique_copy(
        self,
        user_id: int,
        incoming: SharedIngredient,
    ) -> Ingredient:
        service = IngredientService(self._require_ingredient_repository())
        for copy_number in range(1, 10_000):
            suffix = " (копия)" if copy_number == 1 else f" (копия {copy_number})"
            name = f"{incoming.name[: 255 - len(suffix)].rstrip()}{suffix}"
            try:
                return await service.create_import_copy(
                    user_id,
                    CreateIngredientData(name=name, **_nutrition_values(incoming)),
                )
            except DuplicateError:
                continue
        raise RuntimeError("Could not allocate a unique ingredient copy name")

    def _require_ingredient_repository(self) -> IngredientRepository:
        if self._ingredient_repository is None:
            raise RuntimeError("Ingredient repository is required for this operation")
        return self._ingredient_repository


def _nutrition_values(incoming: SharedIngredient) -> dict[str, Decimal]:
    return {
        "kcal_per_100g": incoming.kcal_per_100g,
        "protein_per_100g": incoming.protein_per_100g,
        "fat_per_100g": incoming.fat_per_100g,
        "carbs_per_100g": incoming.carbs_per_100g,
    }


def _ingredient_data(incoming: SharedIngredient) -> CreateIngredientData:
    return CreateIngredientData(name=incoming.name, **_nutrition_values(incoming))


def _nutrition_matches(
    existing: Ingredient,
    incoming: SharedIngredient,
) -> bool:
    return all(
        Decimal(str(getattr(existing, field))).quantize(
            DB_NUTRITION_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        == getattr(incoming, field).quantize(
            DB_NUTRITION_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        for field in (
            "kcal_per_100g",
            "protein_per_100g",
            "fat_per_100g",
            "carbs_per_100g",
        )
    )
