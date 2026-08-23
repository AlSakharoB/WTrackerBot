from dataclasses import dataclass
from decimal import Decimal
from unicodedata import normalize

SEARCH_SIMILARITY_THRESHOLD = Decimal("0.30")
DUPLICATE_NAME_SIMILARITY_THRESHOLD = Decimal("0.69")
DUPLICATE_NAME_CANDIDATE_LIMIT = 10
SEARCH_DEFAULT_LIMIT = 10
SEARCH_MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class SearchResult:
    entity_id: int
    name: str
    score: Decimal


def normalize_search_text(text: str) -> str:
    normalized = normalize("NFKC", text).strip().lower().replace("ё", "е")
    words: list[str] = []
    current_word: list[str] = []

    for character in normalized:
        if character.isalnum():
            current_word.append(character)
        elif current_word:
            words.append("".join(current_word))
            current_word = []

    if current_word:
        words.append("".join(current_word))
    return " ".join(words)


def tokenize_search_query(query: str) -> list[str]:
    return normalize_search_text(query).split()


def names_have_different_numbers(first: str, second: str) -> bool:
    first_numbers = tuple(word for word in first.split() if word.isdecimal())
    second_numbers = tuple(word for word in second.split() if word.isdecimal())
    return first_numbers != second_numbers
