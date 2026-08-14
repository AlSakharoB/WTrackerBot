from collections.abc import Awaitable, Callable
from decimal import Decimal

from app.exceptions import ValidationError
from app.repositories.search import SearchRepository
from app.search import (
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
    SEARCH_SIMILARITY_THRESHOLD,
    SearchResult,
    normalize_search_text,
    tokenize_search_query,
)

SearchMethod = Callable[..., Awaitable[list[SearchResult]]]


class SearchService:
    def __init__(
        self,
        repository: SearchRepository,
        *,
        similarity_threshold: Decimal = SEARCH_SIMILARITY_THRESHOLD,
    ) -> None:
        if not Decimal("0") <= similarity_threshold <= Decimal("1"):
            raise ValueError("Similarity threshold must be between 0 and 1")
        self._repository = repository
        self._similarity_threshold = similarity_threshold

    async def search_ingredients(
        self,
        user_id: int,
        query: str,
        limit: int = SEARCH_DEFAULT_LIMIT,
    ) -> list[SearchResult]:
        return await self._search(
            self._repository.search_ingredients,
            user_id=user_id,
            query=query,
            limit=limit,
        )

    async def search_dishes(
        self,
        user_id: int,
        query: str,
        limit: int = SEARCH_DEFAULT_LIMIT,
    ) -> list[SearchResult]:
        return await self._search(
            self._repository.search_dishes,
            user_id=user_id,
            query=query,
            limit=limit,
        )

    async def _search(
        self,
        repository_method: SearchMethod,
        *,
        user_id: int,
        query: str,
        limit: int,
    ) -> list[SearchResult]:
        normalized_query = normalize_search_text(query)
        if not normalized_query:
            raise ValidationError("Введите название или часть названия.")
        safe_limit = min(max(limit, 1), SEARCH_MAX_LIMIT)
        return await repository_method(
            user_id=user_id,
            raw_query=" ".join(query.split()),
            normalized_query=normalized_query,
            tokens=tokenize_search_query(normalized_query),
            similarity_threshold=self._similarity_threshold,
            limit=safe_limit,
        )
