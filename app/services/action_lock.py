import hmac
import secrets
from dataclasses import dataclass
from time import monotonic
from typing import Protocol


class Clock(Protocol):
    def __call__(self) -> float: ...


@dataclass(frozen=True, slots=True)
class ActionLease:
    key: str
    lease_id: str


@dataclass(frozen=True, slots=True)
class _ActionLock:
    lease_id: str
    expires_at: float


class ActionLockService:
    """Short-lived, in-memory idempotency guard for callback actions."""

    def __init__(self, ttl_seconds: int, *, clock: Clock = monotonic) -> None:
        if not 10 <= ttl_seconds <= 30:
            msg = "Action lock TTL must be between 10 and 30 seconds"
            raise ValueError(msg)
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._locks: dict[str, _ActionLock] = {}

    def acquire(self, key: str) -> ActionLease | None:
        now = self._clock()
        self._prune_expired(now)
        current = self._locks.get(key)
        if current is not None and current.expires_at > now:
            return None

        lease = ActionLease(key=key, lease_id=secrets.token_urlsafe(8))
        self._locks[key] = _ActionLock(
            lease_id=lease.lease_id,
            expires_at=now + self._ttl_seconds,
        )
        return lease

    def release(self, lease: ActionLease) -> None:
        current = self._locks.get(lease.key)
        if current is not None and current.lease_id == lease.lease_id:
            self._locks.pop(lease.key, None)

    def _prune_expired(self, now: float) -> None:
        expired = [key for key, lock in self._locks.items() if lock.expires_at <= now]
        for key in expired:
            self._locks.pop(key, None)


def generate_action_token() -> str:
    return secrets.token_urlsafe(8)


def action_token_matches(expected: object, received: str) -> bool:
    return isinstance(expected, str) and hmac.compare_digest(expected, received)
