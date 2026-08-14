from decimal import Decimal

from sqlalchemy import Numeric, and_, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.dish import Dish
from app.db.models.ingredient import Ingredient
from app.search import SearchResult

SearchModel = type[Ingredient] | type[Dish]


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_ingredients(
        self,
        *,
        user_id: int,
        raw_query: str,
        normalized_query: str,
        tokens: list[str],
        similarity_threshold: Decimal,
        limit: int,
    ) -> list[SearchResult]:
        return await self._search(
            Ingredient,
            user_id=user_id,
            raw_query=raw_query,
            normalized_query=normalized_query,
            tokens=tokens,
            similarity_threshold=similarity_threshold,
            limit=limit,
        )

    async def search_dishes(
        self,
        *,
        user_id: int,
        raw_query: str,
        normalized_query: str,
        tokens: list[str],
        similarity_threshold: Decimal,
        limit: int,
    ) -> list[SearchResult]:
        return await self._search(
            Dish,
            user_id=user_id,
            raw_query=raw_query,
            normalized_query=normalized_query,
            tokens=tokens,
            similarity_threshold=similarity_threshold,
            limit=limit,
        )

    async def _search(
        self,
        model: SearchModel,
        *,
        user_id: int,
        raw_query: str,
        normalized_query: str,
        tokens: list[str],
        similarity_threshold: Decimal,
        limit: int,
    ) -> list[SearchResult]:
        name = model.name
        name_normalized = model.name_normalized
        threshold = float(similarity_threshold)
        await self._session.execute(
            select(
                func.set_config(
                    "pg_trgm.similarity_threshold",
                    str(similarity_threshold),
                    True,
                )
            )
        )
        full_similarity = func.similarity(name_normalized, normalized_query)
        trigram_match = name_normalized.op("%")(normalized_query)
        token_matches = [
            _token_matches(name_normalized, token, threshold) for token in tokens
        ]
        candidate_filter = or_(
            name_normalized == normalized_query,
            name_normalized.startswith(normalized_query),
            trigram_match,
            and_(*token_matches),
        )

        base_score = case(
            (name == raw_query, 1000.0),
            (name_normalized == normalized_query, 900.0),
            (name_normalized.startswith(normalized_query), 800.0),
            else_=0.0,
        )
        fuzzy_score = case(
            (full_similarity >= threshold, full_similarity * 30.0),
            else_=0.0,
        )
        token_score = sum(
            (_token_score(name_normalized, token, threshold) for token in tokens),
            literal(0.0),
        )
        score = cast(base_score + fuzzy_score + token_score, Numeric(12, 4)).label(
            "score"
        )
        statement = (
            select(
                model.id.label("entity_id"),
                name.label("name"),
                score,
            )
            .where(model.user_id == user_id, candidate_filter)
            .order_by(score.desc(), name_normalized, model.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            SearchResult(
                entity_id=row.entity_id,
                name=row.name,
                score=Decimal(row.score),
            )
            for row in rows
        ]


def _token_matches(
    name_normalized: ColumnElement[str],
    token: str,
    threshold: float,
) -> ColumnElement[bool]:
    exact_match = (
        func.strpos(
            func.concat(" ", name_normalized, " "),
            f" {token} ",
        )
        > 0
    )
    prefix_match = name_normalized.op("~")(f"(^| ){token}")
    if len(token) == 1:
        return or_(exact_match, prefix_match)
    return or_(
        exact_match,
        prefix_match,
        func.strict_word_similarity(token, name_normalized) >= threshold,
    )


def _token_score(
    name_normalized: ColumnElement[str],
    token: str,
    threshold: float,
) -> ColumnElement[float]:
    exact_match = (
        func.strpos(
            func.concat(" ", name_normalized, " "),
            f" {token} ",
        )
        > 0
    )
    prefix_match = name_normalized.op("~")(f"(^| ){token}")
    if len(token) == 1:
        return case(
            (exact_match, 10.0),
            (prefix_match, 5.0),
            else_=0.0,
        )

    similarity = func.strict_word_similarity(token, name_normalized)
    return case(
        (exact_match, 60.0),
        (prefix_match, 45.0),
        (similarity >= threshold, similarity * 30.0),
        else_=0.0,
    )
