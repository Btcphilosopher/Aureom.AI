"""Background job processing with a strict interactive-first priority order:

```
USER INTERACTION
    ^
TIMELINE PREVIEW
    ^
BACKGROUND RENDER
    ^
AI ANALYSIS
```

Lower numeric priority runs first; interactive work always preempts queued
(not yet started) background jobs. Workers run in daemon threads so the
editing engine's main thread is never blocked by proxy generation, waveform
analysis, or AI passes.
"""
from __future__ import annotations

import itertools
import queue
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

from finalcut_engine.core.events import EventBus


class JobPriority(IntEnum):
    USER_INTERACTION = 0
    TIMELINE_PREVIEW = 1
    BACKGROUND_RENDER = 2
    AI_ANALYSIS = 3


@dataclass(order=True)
class _QueueEntry:
    priority: int
    sequence: int
    job: "Job" = field(compare=False)


@dataclass
class Job:
    name: str
    fn: Callable[[], None]
    priority: JobPriority = JobPriority.BACKGROUND_RENDER


class BackgroundRenderQueue:
    def __init__(self, num_workers: int = 2, events: Optional[EventBus] = None) -> None:
        self._queue: "queue.PriorityQueue[_QueueEntry]" = queue.PriorityQueue()
        self._counter = itertools.count()
        self._workers = [threading.Thread(target=self._worker_loop, daemon=True) for _ in range(num_workers)]
        self._stop_event = threading.Event()
        self.events = events or EventBus()
        for w in self._workers:
            w.start()

    def submit(self, job: Job) -> None:
        self._queue.put(_QueueEntry(priority=int(job.priority), sequence=next(self._counter), job=job))
        self.events.publish("job_queued", source=self, job_name=job.name, priority=job.priority.name)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                entry = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            job = entry.job
            self.events.publish("job_started", source=self, job_name=job.name)
            try:
                job.fn()
                self.events.publish("job_finished", source=self, job_name=job.name)
            except Exception as exc:  # noqa: BLE001 - a failed background job must not kill the worker
                self.events.publish("job_failed", source=self, job_name=job.name, error=str(exc))
            finally:
                self._queue.task_done()

    def wait_idle(self, timeout: Optional[float] = None) -> None:
        self._queue.join()

    def pending_count(self) -> int:
        return self._queue.qsize()

    def stop(self) -> None:
        self._stop_event.set()
        for w in self._workers:
            w.join(timeout=1.0)
