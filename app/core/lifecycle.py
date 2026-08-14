import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

ShutdownCallback = Callable[[], Awaitable[None]]


class LifecycleManager:
    def __init__(self, *, drain_timeout_seconds: int) -> None:
        self._drain_timeout_seconds = drain_timeout_seconds
        self._accepting_updates = True
        self._active_update_tasks: set[asyncio.Task[Any]] = set()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_callbacks: list[tuple[str, ShutdownCallback]] = []
        self._idle = asyncio.Event()
        self._idle.set()
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_complete = False

    @property
    def accepting_updates(self) -> bool:
        return self._accepting_updates

    @property
    def active_update_count(self) -> int:
        return len(self._active_update_tasks)

    @property
    def background_task_count(self) -> int:
        return len(self._background_tasks)

    def begin_update(self) -> bool:
        if not self._accepting_updates:
            return False
        task = asyncio.current_task()
        if task is None:
            return False
        self._active_update_tasks.add(task)
        self._idle.clear()
        return True

    def finish_update(self) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._active_update_tasks.discard(task)
        if not self._active_update_tasks:
            self._idle.set()

    def register_background_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_task_done)

    def register_shutdown_callback(
        self,
        name: str,
        callback: ShutdownCallback,
    ) -> None:
        self._shutdown_callbacks.append((name, callback))

    async def shutdown(self, **_: Any) -> None:
        async with self._shutdown_lock:
            if self._shutdown_complete:
                return

            self._accepting_updates = False
            logger.info(
                "Stopped accepting Telegram updates",
                extra={"operation": "lifecycle.stop_updates"},
            )
            await self._drain_active_updates()
            await self._stop_registered_components()
            await self._cancel_background_tasks()
            self._shutdown_complete = True

    async def _drain_active_updates(self) -> None:
        if not self._active_update_tasks:
            return
        logger.info(
            "Waiting for active update handlers",
            extra={"operation": "lifecycle.drain_updates"},
        )
        try:
            await asyncio.wait_for(
                self._idle.wait(),
                timeout=self._drain_timeout_seconds,
            )
            logger.info(
                "Active update handlers completed",
                extra={"operation": "lifecycle.drain_updates"},
            )
        except TimeoutError:
            tasks = tuple(self._active_update_tasks)
            logger.warning(
                "Update drain timeout; cancelling %d handler tasks",
                len(tasks),
                extra={"operation": "lifecycle.drain_updates"},
            )
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _stop_registered_components(self) -> None:
        for name, callback in reversed(self._shutdown_callbacks):
            try:
                await callback()
            except Exception as error:
                logger.error(
                    "Failed to stop lifecycle component %s",
                    name,
                    extra={
                        "operation": "lifecycle.stop_component",
                        "exception_type": type(error).__name__,
                    },
                )

    async def _cancel_background_tasks(self) -> None:
        tasks = tuple(task for task in self._background_tasks if not task.done())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        logger.info(
            "Background tasks stopped",
            extra={"operation": "lifecycle.stop_background_tasks"},
        )

    def _background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            logger.error(
                "Background task failed",
                extra={
                    "operation": "lifecycle.background_task",
                    "exception_type": type(error).__name__,
                },
            )
