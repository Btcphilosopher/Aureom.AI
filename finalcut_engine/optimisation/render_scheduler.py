"""App-level scheduling policy on top of ``render.background_render``.

Maps the kinds of work the engine needs to do — timeline preview, proxy
generation, waveform/thumbnail analysis, AI passes, export — onto the
priority tiers from spec section 18, so callers don't need to know the
priority enum, just what *kind* of work they're submitting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from finalcut_engine.render.background_render import BackgroundRenderQueue, Job, JobPriority


@dataclass
class RenderScheduler:
    queue: BackgroundRenderQueue = field(default_factory=BackgroundRenderQueue)

    def schedule_interactive(self, name: str, fn: Callable[[], None]) -> None:
        self.queue.submit(Job(name, fn, JobPriority.USER_INTERACTION))

    def schedule_preview(self, name: str, fn: Callable[[], None]) -> None:
        self.queue.submit(Job(name, fn, JobPriority.TIMELINE_PREVIEW))

    def schedule_background_render(self, name: str, fn: Callable[[], None]) -> None:
        self.queue.submit(Job(name, fn, JobPriority.BACKGROUND_RENDER))

    def schedule_proxy_generation(self, name: str, fn: Callable[[], None]) -> None:
        self.schedule_background_render(f"proxy:{name}", fn)

    def schedule_waveform_generation(self, name: str, fn: Callable[[], None]) -> None:
        self.schedule_background_render(f"waveform:{name}", fn)

    def schedule_thumbnail_generation(self, name: str, fn: Callable[[], None]) -> None:
        self.schedule_background_render(f"thumbnail:{name}", fn)

    def schedule_ai_analysis(self, name: str, fn: Callable[[], None]) -> None:
        self.queue.submit(Job(f"ai:{name}", fn, JobPriority.AI_ANALYSIS))

    def schedule_export(self, name: str, fn: Callable[[], None]) -> None:
        # Export is background work but should not be starved indefinitely by
        # a constant stream of preview jobs; still below interactive editing.
        self.schedule_background_render(f"export:{name}", fn)

    def pending_count(self) -> int:
        return self.queue.pending_count()

    def wait_idle(self) -> None:
        self.queue.wait_idle()

    def shutdown(self) -> None:
        self.queue.stop()
