from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic


class RateLimitScope(StrEnum):
    MESSAGES = "messages"
    CALLBACKS = "callbacks"
    SEARCH = "search"
    WEIGHT_CHART = "weight_chart"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    count: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: float = 0


class RateLimitService:
    def __init__(
        self,
        rules: Mapping[RateLimitScope, RateLimitRule],
        *,
        notice_cooldown_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._rules = dict(rules)
        self._notice_cooldown_seconds = notice_cooldown_seconds
        self._clock = clock
        self._buckets: dict[tuple[int, RateLimitScope], deque[float]] = {}
        self._last_notice_at: dict[int, float] = {}
        self._checks_since_cleanup = 0

    def check(self, user_id: int, scope: RateLimitScope) -> RateLimitDecision:
        now = self._clock()
        rule = self._rules[scope]
        key = (user_id, scope)
        events = self._buckets.setdefault(key, deque())
        window_start = now - rule.window_seconds
        while events and events[0] <= window_start:
            events.popleft()

        self._checks_since_cleanup += 1
        if self._checks_since_cleanup >= 1000:
            self._cleanup(now)

        if len(events) >= rule.count:
            retry_after = max(0, events[0] + rule.window_seconds - now)
            return RateLimitDecision(False, retry_after)

        events.append(now)
        return RateLimitDecision(True)

    def should_send_notice(self, user_id: int) -> bool:
        now = self._clock()
        last_notice_at = self._last_notice_at.get(user_id)
        if (
            last_notice_at is not None
            and now - last_notice_at < self._notice_cooldown_seconds
        ):
            return False
        self._last_notice_at[user_id] = now
        return True

    def _cleanup(self, now: float) -> None:
        longest_window = max(
            (rule.window_seconds for rule in self._rules.values()),
            default=60,
        )
        stale_before = now - longest_window * 2
        self._buckets = {
            key: events
            for key, events in self._buckets.items()
            if events and events[-1] > stale_before
        }
        self._last_notice_at = {
            user_id: notice_at
            for user_id, notice_at in self._last_notice_at.items()
            if notice_at > stale_before
        }
        self._checks_since_cleanup = 0
