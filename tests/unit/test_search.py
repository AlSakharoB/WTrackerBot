from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.exceptions import ValidationError
from app.search import SearchResult, normalize_search_text, tokenize_search_query
from app.services.search import SearchService


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" ЯИЧНЫЙ ", "яичный"),
        ("ёлка", "елка"),
        ("  ЯИЧНЫЙ   белок  ", "яичный белок"),
        ("Творог 5%", "творог 5"),
        ("Курица—гриль / филе", "курица гриль филе"),
        ("Продукт_2026", "продукт 2026"),
        ("---", ""),
    ],
)
def test_normalize_search_text(text: str, expected: str) -> None:
    assert normalize_search_text(text) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("кур   груд", ["кур", "груд"]),
        ("яиный бел", ["яиный", "бел"]),
        ("  Творог 5% ", ["творог", "5"]),
        ("---", []),
    ],
)
def test_tokenize_search_query(query: str, expected: list[str]) -> None:
    assert tokenize_search_query(query) == expected


async def test_search_service_normalizes_query_and_limits_results() -> None:
    expected = [SearchResult(1, "Творог 5%", Decimal("900"))]
    repository = Mock()
    repository.search_ingredients = AsyncMock(return_value=expected)
    service = SearchService(repository)

    result = await service.search_ingredients(
        user_id=10,
        query="  ТвОрОг   5% ",
        limit=1000,
    )

    assert result == expected
    repository.search_ingredients.assert_awaited_once_with(
        user_id=10,
        raw_query="ТвОрОг 5%",
        normalized_query="творог 5",
        tokens=["творог", "5"],
        similarity_threshold=Decimal("0.30"),
        limit=100,
    )


async def test_search_service_rejects_empty_normalized_query() -> None:
    repository = Mock()
    repository.search_dishes = AsyncMock()
    service = SearchService(repository)

    with pytest.raises(ValidationError):
        await service.search_dishes(user_id=10, query=" -- ")

    repository.search_dishes.assert_not_awaited()


@pytest.mark.parametrize("threshold", [Decimal("-0.01"), Decimal("1.01")])
def test_search_service_rejects_invalid_threshold(threshold: Decimal) -> None:
    with pytest.raises(ValueError):
        SearchService(Mock(), similarity_threshold=threshold)
