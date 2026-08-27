"""The FinalCut Engine facade: wires every subsystem together behind one entry point.

```
IMPORT MEDIA -> MEDIA ANALYSIS -> LIBRARY -> EVENT -> PROJECT -> MAGNETIC TIMELINE
   -> EDITING -> AUDIO -> COLOUR -> EFFECTS -> MOTION -> AI ASSISTANCE -> RENDER -> EXPORT
```

This class does not implement any of that logic itself — it owns one
instance of each subsystem and hands out references, so a UI layer (or a
script, or a test) has a single object to construct. Nothing here is
required: every subsystem remains independently usable and testable without
going through :class:`FinalCutEngine`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from finalcut_engine.core.clock import Clock
from finalcut_engine.core.events import EventBus
from finalcut_engine.core.project import Project
from finalcut_engine.core.state import UndoManager
from finalcut_engine.library.library import Library
from finalcut_engine.media.importer import MediaImporter
from finalcut_engine.optimisation.performance import PerformanceMonitor
from finalcut_engine.optimisation.render_scheduler import RenderScheduler
from finalcut_engine.render.render_engine import RenderEngine


@dataclass
class FinalCutEngine:
    library: Library
    #: (asset_id, Time) -> decoded frame. Left as a plain Callable (rather than
    #: importing Time here) to avoid a hard dependency on the render engine
    #: for callers that only need library/timeline/audio/colour features.
    frame_loader: Optional[Callable[..., np.ndarray]] = None

    events: EventBus = field(default_factory=EventBus)
    importer: MediaImporter = field(default_factory=MediaImporter)
    undo: UndoManager = field(default_factory=UndoManager)
    clock: Clock = field(default_factory=Clock)
    scheduler: RenderScheduler = field(default_factory=RenderScheduler)
    performance: PerformanceMonitor = field(default_factory=PerformanceMonitor)
    render_engine: Optional[RenderEngine] = None
    projects: dict[str, Project] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.undo = UndoManager(events=self.events)
        if self.render_engine is None and self.frame_loader is not None:
            self.render_engine = RenderEngine(frame_loader=self.frame_loader)

    @classmethod
    def new(cls, library_name: str, frame_loader: Callable) -> "FinalCutEngine":
        library = Library(name=library_name)
        return cls(library=library, frame_loader=frame_loader)

    def create_project(self, name: str) -> Project:
        project = Project(name=name)
        self.projects[project.id] = project
        self.events.publish("project_created", source=self, project_id=project.id)
        return project

    def shutdown(self) -> None:
        self.scheduler.shutdown()
