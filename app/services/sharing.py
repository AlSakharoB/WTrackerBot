import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.db.models.dish import Dish
from app.db.models.ingredient import Ingredient
from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.dishes import DishRecord, DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import (
    OwnedSharePackageRecord,
    ShareRepository,
    ShareTokenHashCollisionError,
)
from app.search import (
    DUPLICATE_NAME_SIMILARITY_THRESHOLD,
    names_have_different_numbers,
    normalize_search_text,
)
from app.services.dishes import DishComponentData, DishDetails, DishService
from app.services.ingredients import CreateIngredientData, IngredientService
from app.services.nutrition import (
    DishNutritionValues,
    NutritionComponent,
    NutritionService,
    NutritionValues,
)
from app.sharing.links import build_share_deep_link, build_telegram_share_url
from app.sharing.payloads import (
    PAYLOAD_VERSION,
    DishSharePayload,
    IngredientSharePayload,
    SharedDish,
    SharedDishComponent,
    SharedIngredient,
    SharePayload,
    SharePayloadLimitError,
    SharePayloadLimits,
    parse_share_payload,
    raw_share_payload_size,
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
SHARE_MANAGEMENT_PAGE_SIZE = 5

logger = logging.getLogger(__name__)


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


class DishConflictType(StrEnum):
    NEW = "new"
    NAME_CONFLICT = "name_conflict"
    SIMILAR_CONFLICT = "similar_conflict"


class DishImportAction(StrEnum):
    CREATE = "create"
    CREATE_COPY = "create_copy"
    SKIP = "skip"
    UNRESOLVED = "unresolved"


class ShareRuntimeStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CreatedSharePackage:
    package: SharePackage
    token: str
    deep_link: str
    telegram_share_url: str


@dataclass(frozen=True, slots=True)
class OwnedSharePackage:
    package: SharePackage
    title: str
    runtime_status: ShareRuntimeStatus
    completed_imports: int


@dataclass(frozen=True, slots=True)
class OwnedSharePackagePage:
    items: tuple[OwnedSharePackage, ...]
    page: int
    pages: int
    total: int


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


@dataclass(frozen=True, slots=True)
class DishPackageAccess:
    package: SharePackage
    payload: DishSharePayload
    previous_import: ShareImport | None
    is_owner: bool


@dataclass(frozen=True, slots=True)
class DishPreflight:
    dish: SharedDish
    conflict_type: DishConflictType
    existing: Dish | None
    ingredients: BatchIngredientPreflight


@dataclass(frozen=True, slots=True)
class DishNamePreflight:
    dish: SharedDish
    conflict_type: DishConflictType
    existing: Dish | None


@dataclass(frozen=True, slots=True)
class BatchDishPreflight:
    dishes: tuple[DishNamePreflight, ...]
    ingredients: BatchIngredientPreflight

    @property
    def dish_conflict_count(self) -> int:
        return sum(
            item.conflict_type is not DishConflictType.NEW for item in self.dishes
        )


@dataclass(frozen=True, slots=True)
class DishIngredientPlanItem:
    preflight: IngredientPreflight
    action: BatchIngredientAction


@dataclass(frozen=True, slots=True)
class DishImportPlan:
    dish: SharedDish
    dish_conflict_type: DishConflictType
    dish_action: DishImportAction
    existing_dish: Dish | None
    ingredients: tuple[DishIngredientPlanItem, ...]

    @property
    def unresolved_ingredients(self) -> tuple[DishIngredientPlanItem, ...]:
        return tuple(
            item
            for item in self.ingredients
            if item.action is BatchIngredientAction.SKIP
        )

    @property
    def uses_changed_existing_ingredients(self) -> bool:
        return any(
            item.action is BatchIngredientAction.REUSE
            and item.preflight.conflict_type
            in {
                IngredientConflictType.NAME_CONFLICT,
                IngredientConflictType.SIMILAR_CONFLICT,
            }
            for item in self.ingredients
        )

    @property
    def can_import(self) -> bool:
        if self.dish_action is DishImportAction.SKIP:
            return True
        return (
            self.dish_action in {DishImportAction.CREATE, DishImportAction.CREATE_COPY}
            and not self.unresolved_ingredients
        )


@dataclass(frozen=True, slots=True)
class DishImportResult:
    import_record: ShareImport
    plan: DishImportPlan
    dish: DishDetails | None
    already_completed: bool = False


@dataclass(frozen=True, slots=True)
class BatchDishIngredientPlanItem:
    preflight: IngredientPreflight
    action: BatchIngredientAction
    required: bool


@dataclass(frozen=True, slots=True)
class BatchDishPlanItem:
    preflight: DishNamePreflight
    action: DishImportAction


@dataclass(frozen=True, slots=True)
class BatchDishImportPlan:
    ingredients: tuple[BatchDishIngredientPlanItem, ...]
    dishes: tuple[BatchDishPlanItem, ...]

    @property
    def unresolved_ingredients(self) -> tuple[BatchDishIngredientPlanItem, ...]:
        return tuple(
            item
            for item in self.ingredients
            if item.required and item.action is BatchIngredientAction.SKIP
        )

    @property
    def unresolved_dishes(self) -> tuple[BatchDishPlanItem, ...]:
        return tuple(
            item for item in self.dishes if item.action is DishImportAction.UNRESOLVED
        )

    @property
    def can_import(self) -> bool:
        return not self.unresolved_ingredients and not self.unresolved_dishes

    @property
    def uses_changed_existing_ingredients(self) -> bool:
        return any(
            item.required
            and item.action is BatchIngredientAction.REUSE
            and item.preflight.conflict_type
            in {
                IngredientConflictType.NAME_CONFLICT,
                IngredientConflictType.SIMILAR_CONFLICT,
            }
            for item in self.ingredients
        )


@dataclass(frozen=True, slots=True)
class BatchDishImportResult:
    import_record: ShareImport
    plan: BatchDishImportPlan
    dishes: tuple[DishDetails, ...]
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
        dish_repository: DishRepository | None = None,
        token_factory: Callable[[], str] = generate_share_token,
    ) -> None:
        self._repository = repository
        self._bot_username = bot_username
        self._link_ttl_days = link_ttl_days
        self._limits = limits
        self._ingredient_repository = ingredient_repository
        self._dish_repository = dish_repository
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

    async def create_dish_package(
        self,
        owner_user_id: int,
        dish_id: int,
    ) -> CreatedSharePackage:
        record = await self._require_dish_repository().get_by_id(
            dish_id,
            owner_user_id,
        )
        if record is None:
            raise NotFoundError("Блюдо не найдено.")
        payload = self._build_dish_payload(owner_user_id, [record])
        return await self.create_package(
            owner_user_id,
            payload,
            share_text=(
                f"Делюсь блюдом «{record.dish.name}». "
                "Откройте ссылку, чтобы добавить рецепт в бот."
            ),
        )

    async def create_dish_batch_package(
        self,
        owner_user_id: int,
        dish_ids: list[int],
    ) -> CreatedSharePackage:
        if not dish_ids:
            raise ValidationError("Выберите хотя бы одно блюдо.")
        if len(dish_ids) != len(set(dish_ids)):
            raise ValidationError("Одно блюдо нельзя выбрать дважды.")
        if len(dish_ids) > self._limits.max_items:
            raise ValidationError(
                f"Можно выбрать не более {self._limits.max_items} блюд."
            )
        records = await self._require_dish_repository().get_by_ids(
            set(dish_ids),
            owner_user_id,
        )
        by_id = {record.dish.id: record for record in records}
        if len(by_id) != len(dish_ids):
            raise NotFoundError("Одно из выбранных блюд удалено или недоступно.")
        ordered = [by_id[dish_id] for dish_id in dish_ids]
        payload = self._build_dish_payload(owner_user_id, ordered)
        return await self.create_package(
            owner_user_id,
            payload,
            share_text=(
                f"Делюсь набором блюд ({len(ordered)}). "
                "Откройте ссылку, чтобы добавить рецепты в бот."
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
            _log_share_event(
                "share_package_created",
                "sharing.package_created",
                package,
                user_id=owner_user_id,
            )
            return CreatedSharePackage(
                package=package,
                token=token,
                deep_link=deep_link,
                telegram_share_url=build_telegram_share_url(deep_link, share_text),
            )
        raise RuntimeError("Could not allocate a unique share token")

    async def list_owned_packages(
        self,
        owner_user_id: int,
        package_type: SharePackageType,
        *,
        page: int = 1,
        now: datetime | None = None,
    ) -> OwnedSharePackagePage:
        requested_page = max(page, 1)
        records, total = await self._repository.list_owned(
            owner_user_id,
            package_type,
            offset=(requested_page - 1) * SHARE_MANAGEMENT_PAGE_SIZE,
            limit=SHARE_MANAGEMENT_PAGE_SIZE,
        )
        pages = max(
            1,
            (total + SHARE_MANAGEMENT_PAGE_SIZE - 1) // SHARE_MANAGEMENT_PAGE_SIZE,
        )
        if total and requested_page > pages:
            requested_page = pages
            records, total = await self._repository.list_owned(
                owner_user_id,
                package_type,
                offset=(requested_page - 1) * SHARE_MANAGEMENT_PAGE_SIZE,
                limit=SHARE_MANAGEMENT_PAGE_SIZE,
            )
        current_time = now or datetime.now(UTC)
        return OwnedSharePackagePage(
            items=tuple(
                self._owned_package(record, current_time) for record in records
            ),
            page=requested_page,
            pages=pages,
            total=total,
        )

    async def get_owned_package(
        self,
        package_id: int,
        owner_user_id: int,
        *,
        now: datetime | None = None,
    ) -> OwnedSharePackage:
        record = await self._repository.get_owned_record(package_id, owner_user_id)
        if record is None:
            raise NotFoundError("Ссылка не найдена.")
        return self._owned_package(record, now or datetime.now(UTC))

    async def rotate_package(
        self,
        package_id: int,
        owner_user_id: int,
        *,
        now: datetime | None = None,
    ) -> CreatedSharePackage:
        if self._bot_username is None:
            raise ValidationError("Ссылки для обмена временно недоступны.")
        existing = await self._repository.get_owned_by_id(package_id, owner_user_id)
        if existing is None:
            raise NotFoundError("Ссылка не найдена.")
        rotated_at = now or datetime.now(UTC)
        for _ in range(TOKEN_GENERATION_ATTEMPTS):
            token = self._token_factory()
            token_hash = hash_share_token(token)
            if token_hash == existing.token_hash:
                continue
            try:
                package = await self._repository.rotate_owned(
                    package_id,
                    owner_user_id,
                    token_hash=token_hash,
                    expires_at=rotated_at + timedelta(days=self._link_ttl_days),
                    rotated_at=rotated_at,
                )
            except ShareTokenHashCollisionError:
                continue
            if package is None:  # pragma: no cover - owner checked above
                raise NotFoundError("Ссылка не найдена.")
            deep_link = build_share_deep_link(self._bot_username, token)
            title = self._package_title(package)
            noun = (
                "блюдом"
                if package.package_type == SharePackageType.DISHES
                else "ингредиентом"
            )
            if package.item_count > 1:
                noun = (
                    "набором блюд"
                    if package.package_type == SharePackageType.DISHES
                    else "набором ингредиентов"
                )
            share_text = (
                f"Делюсь {noun} «{title}». Откройте ссылку, чтобы добавить в бот."
            )
            _log_share_event(
                "share_package_rotated",
                "sharing.package_rotated",
                package,
                user_id=owner_user_id,
            )
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

    async def resolve_dish_token(
        self,
        token: str,
        recipient_user_id: int,
        *,
        now: datetime | None = None,
    ) -> DishPackageAccess:
        if not is_valid_share_token(token):
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        package = await self._repository.get_by_token_hash(hash_share_token(token))
        return await self._build_dish_access(
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
        for_update: bool = False,
    ) -> IngredientPackageAccess:
        package = await self._repository.get_by_id(
            package_id,
            for_update=for_update,
        )
        return await self._build_ingredient_access(
            package,
            recipient_user_id,
            now=now,
        )

    async def get_dish_package(
        self,
        package_id: int,
        recipient_user_id: int,
        *,
        now: datetime | None = None,
        for_update: bool = False,
    ) -> DishPackageAccess:
        package = await self._repository.get_by_id(
            package_id,
            for_update=for_update,
        )
        return await self._build_dish_access(
            package,
            recipient_user_id,
            now=now,
        )

    async def preflight_ingredient(
        self,
        recipient_user_id: int,
        incoming: SharedIngredient,
    ) -> IngredientPreflight:
        normalized_name = normalize_search_text(incoming.name)
        matches = await self._require_ingredient_repository().find_matches_for_names(
            recipient_user_id,
            {normalized_name},
            DUPLICATE_NAME_SIMILARITY_THRESHOLD,
        )
        return self._ingredient_preflight_from_candidates(
            incoming,
            normalized_name,
            matches.get(normalized_name, []),
        )

    @staticmethod
    def _ingredient_preflight_from_candidates(
        incoming: SharedIngredient,
        normalized_name: str,
        candidates: list[Ingredient],
    ) -> IngredientPreflight:
        exact = next(
            (
                candidate
                for candidate in candidates
                if candidate.name_normalized == normalized_name
            ),
            None,
        )
        if exact is not None:
            conflict_type = (
                IngredientConflictType.EXACT_SAME
                if _nutrition_matches(exact, incoming)
                else IngredientConflictType.NAME_CONFLICT
            )
            return IngredientPreflight(conflict_type, incoming, exact)

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
        normalized_names = {
            normalize_search_text(incoming.name) for incoming in payload.ingredients
        }
        matches = await self._require_ingredient_repository().find_matches_for_names(
            recipient_user_id,
            normalized_names,
            DUPLICATE_NAME_SIMILARITY_THRESHOLD,
        )
        items = []
        for incoming in payload.ingredients:
            normalized_name = normalize_search_text(incoming.name)
            items.append(
                self._ingredient_preflight_from_candidates(
                    incoming,
                    normalized_name,
                    matches.get(normalized_name, []),
                )
            )
        return BatchIngredientPreflight(tuple(items))

    async def preflight_dish(
        self,
        recipient_user_id: int,
        payload: DishSharePayload,
    ) -> DishPreflight:
        if len(payload.dishes) != 1:
            raise InvalidShareLinkError("Ссылка не содержит одно блюдо.")
        dish = payload.dishes[0]
        dish_preflight = (await self._preflight_dish_names(recipient_user_id, [dish]))[
            0
        ]
        ingredient_preflight = await self.preflight_ingredient_batch(
            recipient_user_id,
            IngredientSharePayload(ingredients=payload.ingredients),
        )
        return DishPreflight(
            dish=dish,
            conflict_type=dish_preflight.conflict_type,
            existing=dish_preflight.existing,
            ingredients=ingredient_preflight,
        )

    async def preflight_dish_batch(
        self,
        recipient_user_id: int,
        payload: DishSharePayload,
    ) -> BatchDishPreflight:
        dishes = await self._preflight_dish_names(
            recipient_user_id,
            payload.dishes,
        )
        ingredients = await self.preflight_ingredient_batch(
            recipient_user_id,
            IngredientSharePayload(ingredients=payload.ingredients),
        )
        return BatchDishPreflight(dishes=dishes, ingredients=ingredients)

    async def _preflight_dish_names(
        self,
        recipient_user_id: int,
        dishes: list[SharedDish],
    ) -> tuple[DishNamePreflight, ...]:
        normalized_names = {normalize_search_text(dish.name) for dish in dishes}
        matches = await self._require_dish_repository().find_matches_for_names(
            recipient_user_id,
            normalized_names,
            DUPLICATE_NAME_SIMILARITY_THRESHOLD,
        )
        preflights: list[DishNamePreflight] = []
        for dish in dishes:
            normalized_name = normalize_search_text(dish.name)
            existing = next(
                (
                    candidate
                    for candidate in matches.get(normalized_name, [])
                    if not names_have_different_numbers(
                        normalized_name,
                        candidate.name_normalized,
                    )
                ),
                None,
            )
            if existing is None:
                conflict_type = DishConflictType.NEW
            elif existing.name_normalized == normalized_name:
                conflict_type = DishConflictType.NAME_CONFLICT
            else:
                conflict_type = DishConflictType.SIMILAR_CONFLICT
            preflights.append(
                DishNamePreflight(
                    dish=dish,
                    conflict_type=conflict_type,
                    existing=existing,
                )
            )
        return tuple(preflights)

    async def build_dish_batch_import_plan(
        self,
        recipient_user_id: int,
        payload: DishSharePayload,
        ingredient_decisions: dict[str, str],
        dish_decisions: dict[str, str],
    ) -> BatchDishImportPlan:
        preflight = await self.preflight_dish_batch(recipient_user_id, payload)
        dish_items: list[BatchDishPlanItem] = []
        for item in preflight.dishes:
            requested = dish_decisions.get(item.dish.key)
            if requested == DishImportAction.SKIP.value:
                action = DishImportAction.SKIP
            elif item.conflict_type is DishConflictType.NEW:
                action = DishImportAction.CREATE
            elif requested == DishImportAction.CREATE_COPY.value:
                action = DishImportAction.CREATE_COPY
            else:
                action = DishImportAction.UNRESOLVED
            dish_items.append(BatchDishPlanItem(item, action))

        required_keys = {
            component.ingredient_key
            for item in dish_items
            if item.action in {DishImportAction.CREATE, DishImportAction.CREATE_COPY}
            for component in item.preflight.dish.components
        }
        ingredient_items: list[BatchDishIngredientPlanItem] = []
        for item in preflight.ingredients.items:
            required = item.incoming.key in required_keys
            if not required:
                action = BatchIngredientAction.SKIP
            elif item.conflict_type is IngredientConflictType.NEW:
                action = BatchIngredientAction.CREATE
            elif item.conflict_type is IngredientConflictType.EXACT_SAME:
                action = BatchIngredientAction.REUSE
            else:
                requested = ingredient_decisions.get(item.incoming.key)
                action = (
                    BatchIngredientAction(requested)
                    if requested
                    in {
                        BatchIngredientAction.REUSE.value,
                        BatchIngredientAction.COPY_WITH_GENERATED_NAME.value,
                    }
                    else BatchIngredientAction.SKIP
                )
            ingredient_items.append(BatchDishIngredientPlanItem(item, action, required))
        return BatchDishImportPlan(
            ingredients=tuple(ingredient_items),
            dishes=tuple(dish_items),
        )

    async def import_dish_batch(
        self,
        package_id: int,
        recipient_user_id: int,
        ingredient_decisions: dict[str, str],
        dish_decisions: dict[str, str],
        *,
        now: datetime | None = None,
    ) -> BatchDishImportResult:
        completed_at = now or datetime.now(UTC)
        access = await self.get_dish_package(
            package_id,
            recipient_user_id,
            now=completed_at,
            for_update=True,
        )
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        plan = await self.build_dish_batch_import_plan(
            recipient_user_id,
            access.payload,
            ingredient_decisions,
            dish_decisions,
        )
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            return BatchDishImportResult(
                access.previous_import,
                plan,
                (),
                already_completed=True,
            )
        if not plan.can_import:
            raise ValidationError("Сначала разрешите все конфликты импорта.")

        import_record, claimed = await self._repository.claim_import(
            package_id,
            recipient_user_id,
        )
        if not claimed:
            if import_record.status == ShareImportStatus.PROCESSING:
                raise ValidationError(
                    "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
                )
            return BatchDishImportResult(
                import_record,
                plan,
                (),
                already_completed=True,
            )

        ingredient_mapping: dict[str, Ingredient] = {}
        created_ingredients = 0
        reused_ingredients = 0
        skipped_ingredients = 0
        for item in plan.ingredients:
            if not item.required:
                skipped_ingredients += 1
                continue
            if item.action is BatchIngredientAction.CREATE:
                ingredient = await self._create_imported_ingredient(
                    recipient_user_id,
                    item.preflight.incoming,
                )
                created_ingredients += 1
            elif item.action is BatchIngredientAction.REUSE:
                ingredient = item.preflight.existing
                if ingredient is None:
                    raise ValidationError(
                        "План импорта устарел. Откройте ссылку заново."
                    )
                reused_ingredients += 1
            elif item.action is BatchIngredientAction.COPY_WITH_GENERATED_NAME:
                ingredient = await self._create_unique_copy(
                    recipient_user_id,
                    item.preflight.incoming,
                )
                created_ingredients += 1
            else:  # pragma: no cover - guarded by plan.can_import
                raise ValidationError("Сначала разрешите все конфликты импорта.")
            ingredient_mapping[item.preflight.incoming.key] = ingredient

        created_dishes: list[DishDetails] = []
        skipped_dishes = 0
        dish_service = DishService(self._require_dish_repository())
        for item in plan.dishes:
            if item.action is DishImportAction.SKIP:
                skipped_dishes += 1
                continue
            component_data = [
                DishComponentData(
                    ingredient_id=ingredient_mapping[component.ingredient_key].id,
                    grams=component.grams,
                )
                for component in item.preflight.dish.components
            ]
            component_ids = [component.ingredient_id for component in component_data]
            if len(component_ids) != len(set(component_ids)):
                raise ValidationError(
                    "Несколько компонентов сопоставлены одному ингредиенту. "
                    "Выберите отдельные копии."
                )
            if item.action is DishImportAction.CREATE_COPY:
                details = await self._create_unique_dish_copy(
                    recipient_user_id,
                    item.preflight.dish.name,
                    component_data,
                )
            else:
                details = await dish_service.create(
                    recipient_user_id,
                    item.preflight.dish.name,
                    component_data,
                )
            created_dishes.append(details)

        completed = await self._repository.complete_dish_import(
            import_record.id,
            created_ingredients_count=created_ingredients,
            reused_ingredients_count=reused_ingredients,
            skipped_ingredients_count=skipped_ingredients,
            created_dishes_count=len(created_dishes),
            skipped_dishes_count=skipped_dishes,
            completed_at=completed_at,
        )
        _log_share_event(
            "share_import_completed",
            "sharing.import_completed",
            access.package,
            user_id=recipient_user_id,
        )
        return BatchDishImportResult(completed, plan, tuple(created_dishes))

    async def build_dish_import_plan(
        self,
        recipient_user_id: int,
        payload: DishSharePayload,
        ingredient_decisions: dict[str, str],
        dish_decision: str | None,
    ) -> DishImportPlan:
        preflight = await self.preflight_dish(recipient_user_id, payload)
        ingredient_items: list[DishIngredientPlanItem] = []
        for item in preflight.ingredients.items:
            if item.conflict_type is IngredientConflictType.NEW:
                action = BatchIngredientAction.CREATE
            elif item.conflict_type is IngredientConflictType.EXACT_SAME:
                action = BatchIngredientAction.REUSE
            else:
                requested = ingredient_decisions.get(item.incoming.key)
                action = (
                    BatchIngredientAction(requested)
                    if requested
                    in {
                        BatchIngredientAction.REUSE.value,
                        BatchIngredientAction.COPY_WITH_GENERATED_NAME.value,
                    }
                    else BatchIngredientAction.SKIP
                )
            ingredient_items.append(DishIngredientPlanItem(item, action))

        if dish_decision == DishImportAction.SKIP.value:
            dish_action = DishImportAction.SKIP
        elif preflight.conflict_type is DishConflictType.NEW:
            dish_action = DishImportAction.CREATE
        elif dish_decision == DishImportAction.CREATE_COPY.value:
            dish_action = DishImportAction(dish_decision)
        else:
            dish_action = DishImportAction.UNRESOLVED
        return DishImportPlan(
            dish=preflight.dish,
            dish_conflict_type=preflight.conflict_type,
            dish_action=dish_action,
            existing_dish=preflight.existing,
            ingredients=tuple(ingredient_items),
        )

    async def import_dish(
        self,
        package_id: int,
        recipient_user_id: int,
        ingredient_decisions: dict[str, str],
        dish_decision: str | None,
        *,
        now: datetime | None = None,
    ) -> DishImportResult:
        completed_at = now or datetime.now(UTC)
        access = await self.get_dish_package(
            package_id,
            recipient_user_id,
            now=completed_at,
            for_update=True,
        )
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        plan = await self.build_dish_import_plan(
            recipient_user_id,
            access.payload,
            ingredient_decisions,
            dish_decision,
        )
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            return DishImportResult(
                access.previous_import,
                plan,
                None,
                already_completed=True,
            )
        if not plan.can_import:
            raise ValidationError("Сначала разрешите все конфликты импорта.")

        import_record, claimed = await self._repository.claim_import(
            package_id,
            recipient_user_id,
        )
        if not claimed:
            if import_record.status == ShareImportStatus.PROCESSING:
                raise ValidationError(
                    "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
                )
            return DishImportResult(
                import_record,
                plan,
                None,
                already_completed=True,
            )

        if plan.dish_action is DishImportAction.SKIP:
            completed = await self._repository.complete_dish_import(
                import_record.id,
                created_ingredients_count=0,
                reused_ingredients_count=0,
                skipped_ingredients_count=len(plan.ingredients),
                created_dishes_count=0,
                skipped_dishes_count=1,
                completed_at=completed_at,
            )
            return DishImportResult(completed, plan, None)

        ingredient_mapping: dict[str, Ingredient] = {}
        created_count = 0
        reused_count = 0
        for item in plan.ingredients:
            if item.action is BatchIngredientAction.CREATE:
                ingredient = await self._create_imported_ingredient(
                    recipient_user_id,
                    item.preflight.incoming,
                )
                created_count += 1
            elif item.action is BatchIngredientAction.REUSE:
                ingredient = item.preflight.existing
                if ingredient is None:
                    raise ValidationError(
                        "План импорта устарел. Откройте ссылку заново."
                    )
                reused_count += 1
            elif item.action is BatchIngredientAction.COPY_WITH_GENERATED_NAME:
                ingredient = await self._create_unique_copy(
                    recipient_user_id,
                    item.preflight.incoming,
                )
                created_count += 1
            else:  # pragma: no cover - guarded by plan.can_import
                raise ValidationError("Сначала разрешите все конфликты импорта.")
            ingredient_mapping[item.preflight.incoming.key] = ingredient

        component_data = [
            DishComponentData(
                ingredient_id=ingredient_mapping[item.ingredient_key].id,
                grams=item.grams,
            )
            for item in plan.dish.components
        ]
        component_ids = [item.ingredient_id for item in component_data]
        if len(component_ids) != len(set(component_ids)):
            raise ValidationError(
                "Несколько компонентов сопоставлены одному ингредиенту. "
                "Выберите отдельные копии."
            )
        dish_service = DishService(self._require_dish_repository())
        if plan.dish_action is DishImportAction.CREATE_COPY:
            details = await self._create_unique_dish_copy(
                recipient_user_id,
                plan.dish.name,
                component_data,
            )
        else:
            details = await dish_service.create(
                recipient_user_id,
                plan.dish.name,
                component_data,
            )
        completed = await self._repository.complete_dish_import(
            import_record.id,
            created_ingredients_count=created_count,
            reused_ingredients_count=reused_count,
            skipped_ingredients_count=0,
            created_dishes_count=1,
            skipped_dishes_count=0,
            completed_at=completed_at,
        )
        _log_share_event(
            "share_import_completed",
            "sharing.import_completed",
            access.package,
            user_id=recipient_user_id,
        )
        return DishImportResult(completed, plan, details)

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
            for_update=True,
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
        _log_share_event(
            "share_import_completed",
            "sharing.import_completed",
            access.package,
            user_id=recipient_user_id,
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
            for_update=True,
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
        _log_share_event(
            "share_import_completed",
            "sharing.import_completed",
            access.package,
            user_id=recipient_user_id,
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
            raise NotFoundError("Ссылка не найдена.")
        _log_share_event(
            "share_package_revoked",
            "sharing.package_revoked",
            package,
            user_id=owner_user_id,
        )
        return package

    @staticmethod
    def _owned_package(
        record: OwnedSharePackageRecord,
        now: datetime,
    ) -> OwnedSharePackage:
        package = record.package
        if package.status == SharePackageStatus.REVOKED:
            status = ShareRuntimeStatus.REVOKED
        elif now >= package.expires_at:
            status = ShareRuntimeStatus.EXPIRED
        else:
            status = ShareRuntimeStatus.ACTIVE
        return OwnedSharePackage(
            package=package,
            title=SharingService._package_title(package),
            runtime_status=status,
            completed_imports=record.completed_imports,
        )

    @staticmethod
    def _package_title(package: SharePackage) -> str:
        try:
            payload = parse_share_payload(package.payload)
        except ValueError:
            return "Недоступное содержимое"
        if isinstance(payload, DishSharePayload):
            return payload.dishes[0].name if payload.dishes else "Пустой пакет"
        return payload.ingredients[0].name if payload.ingredients else "Пустой пакет"

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
        payload = self._validated_package_payload(package)
        if (
            not isinstance(payload, IngredientSharePayload)
            or package.package_type != SharePackageType.INGREDIENTS
            or package.item_count != len(payload.ingredients)
        ):
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
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

    async def _build_dish_access(
        self,
        package: SharePackage | None,
        recipient_user_id: int,
        *,
        now: datetime | None,
    ) -> DishPackageAccess:
        if package is None or package.status != SharePackageStatus.ACTIVE:
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        current_time = now or datetime.now(UTC)
        if package.expires_at <= current_time:
            raise ExpiredShareLinkError(
                "Срок действия ссылки истёк. Попросите отправителя создать новую."
            )
        payload = self._validated_package_payload(package)
        if (
            not isinstance(payload, DishSharePayload)
            or package.package_type != SharePackageType.DISHES
            or package.item_count != len(payload.dishes)
        ):
            raise InvalidShareLinkError("Ссылка недействительна или была отозвана.")
        self._recalculate_dish_nutrition(payload)
        previous_import = await self._repository.get_import(
            package.id,
            recipient_user_id,
        )
        return DishPackageAccess(
            package=package,
            payload=payload,
            previous_import=previous_import,
            is_owner=package.owner_user_id == recipient_user_id,
        )

    def _validated_package_payload(self, package: SharePackage) -> SharePayload:
        try:
            if raw_share_payload_size(package.payload) > self._limits.max_payload_bytes:
                raise SharePayloadLimitError("Share payload is too large")
            if package.payload_version != PAYLOAD_VERSION:
                raise ValueError("Unsupported share payload version")
            payload = parse_share_payload(package.payload)
            if package.payload_version != payload.version:
                raise ValueError("Share payload version mismatch")
            validate_share_payload_limits(payload, self._limits)
            return payload
        except ValueError as error:
            raise InvalidShareLinkError(
                "Ссылка недействительна или была отозвана."
            ) from error

    @staticmethod
    def _recalculate_dish_nutrition(payload: DishSharePayload) -> None:
        ingredients = {item.key: item for item in payload.ingredients}
        for dish in payload.dishes:
            NutritionService.calculate_dish_nutrition(
                NutritionComponent(
                    nutrition_per_100g=NutritionValues(
                        kcal=ingredients[component.ingredient_key].kcal_per_100g,
                        protein=ingredients[component.ingredient_key].protein_per_100g,
                        fat=ingredients[component.ingredient_key].fat_per_100g,
                        carbs=ingredients[component.ingredient_key].carbs_per_100g,
                    ),
                    grams=component.grams,
                )
                for component in dish.components
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

    async def _create_unique_dish_copy(
        self,
        user_id: int,
        source_name: str,
        components: list[DishComponentData],
    ) -> DishDetails:
        service = DishService(self._require_dish_repository())
        for copy_number in range(1, 10_000):
            suffix = " (копия)" if copy_number == 1 else f" (копия {copy_number})"
            name = f"{source_name[: 255 - len(suffix)].rstrip()}{suffix}"
            try:
                return await service.create_import_copy(user_id, name, components)
            except DuplicateError:
                continue
        raise RuntimeError("Could not allocate a unique dish copy name")

    @staticmethod
    def _build_dish_payload(
        owner_user_id: int,
        records: list[DishRecord],
    ) -> DishSharePayload:
        ingredient_keys: dict[int, str] = {}
        shared_ingredients: list[SharedIngredient] = []
        shared_dishes: list[SharedDish] = []
        for dish_index, record in enumerate(records, start=1):
            if not record.components:
                raise ValidationError("Нельзя отправить блюдо без ингредиентов.")
            component_ids = [item.ingredient.id for item in record.components]
            if len(component_ids) != len(set(component_ids)):
                raise ValidationError("Рецепт содержит повторяющийся ингредиент.")
            if any(
                item.ingredient.user_id != owner_user_id for item in record.components
            ):
                raise NotFoundError("Один из ингредиентов блюда недоступен.")
            for item in record.components:
                ingredient = item.ingredient
                if ingredient.id in ingredient_keys:
                    continue
                key = f"i{len(ingredient_keys) + 1}"
                ingredient_keys[ingredient.id] = key
                shared_ingredients.append(
                    SharedIngredient(
                        key=key,
                        name=ingredient.name,
                        kcal_per_100g=ingredient.kcal_per_100g,
                        protein_per_100g=ingredient.protein_per_100g,
                        fat_per_100g=ingredient.fat_per_100g,
                        carbs_per_100g=ingredient.carbs_per_100g,
                    )
                )
            shared_dishes.append(
                SharedDish(
                    key=f"d{dish_index}",
                    name=record.dish.name,
                    components=[
                        SharedDishComponent(
                            ingredient_key=ingredient_keys[item.ingredient.id],
                            grams=item.grams,
                        )
                        for item in record.components
                    ],
                )
            )
        return DishSharePayload(
            ingredients=shared_ingredients,
            dishes=shared_dishes,
        )

    def _require_ingredient_repository(self) -> IngredientRepository:
        if self._ingredient_repository is None:
            raise RuntimeError("Ingredient repository is required for this operation")
        return self._ingredient_repository

    def _require_dish_repository(self) -> DishRepository:
        if self._dish_repository is None:
            raise RuntimeError("Dish repository is required for this operation")
        return self._dish_repository


class ShareCleanupService:
    def __init__(self, repository: ShareRepository) -> None:
        self._repository = repository

    async def cleanup_batch(
        self,
        *,
        retention_days: int,
        batch_size: int,
        now: datetime | None = None,
    ) -> int:
        current_time = now or datetime.now(UTC)
        return await self._repository.delete_stale_packages(
            cutoff=current_time - timedelta(days=retention_days),
            batch_size=batch_size,
        )


def _log_share_event(
    message: str,
    operation: str,
    package: SharePackage,
    *,
    user_id: int,
) -> None:
    logger.info(
        message,
        extra={
            "operation": operation,
            "user_id": user_id,
            "package_id": package.id,
            "package_type": str(package.package_type),
            "item_count": package.item_count,
        },
    )


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


def calculate_shared_dish_nutrition(
    payload: DishSharePayload,
) -> DishNutritionValues:
    if len(payload.dishes) != 1:
        raise ValidationError("Пакет должен содержать одно блюдо.")
    ingredients = {item.key: item for item in payload.ingredients}
    return NutritionService.calculate_dish_nutrition(
        NutritionComponent(
            nutrition_per_100g=NutritionValues(
                kcal=ingredients[item.ingredient_key].kcal_per_100g,
                protein=ingredients[item.ingredient_key].protein_per_100g,
                fat=ingredients[item.ingredient_key].fat_per_100g,
                carbs=ingredients[item.ingredient_key].carbs_per_100g,
            ),
            grams=item.grams,
        )
        for item in payload.dishes[0].components
    )
