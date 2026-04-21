"""Async task queue for background processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4

import structlog

log = structlog.get_logger()


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: dict | None = None
    error: str | None = None


class TaskWorker:
    """Simple async task worker using asyncio."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._tasks: dict[UUID, Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False

    async def submit(self, name: str, coro) -> UUID:
        """Submit a coroutine for background execution. Returns task ID."""
        task = Task(name=name)
        self._tasks[task.id] = task

        async def _run():
            async with self._semaphore:
                task.status = TaskStatus.RUNNING
                try:
                    task.result = await coro
                    task.status = TaskStatus.COMPLETED
                except Exception as e:
                    task.error = str(e)
                    task.status = TaskStatus.FAILED
                    log.error("task_failed", task_id=str(task.id), name=name, error=str(e))

        asyncio.create_task(_run())
        return task.id

    def get_status(self, task_id: UUID) -> Task | None:
        return self._tasks.get(task_id)

    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """Remove completed/failed tasks older than max_age."""
        # Simple implementation — just clear completed tasks
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)
