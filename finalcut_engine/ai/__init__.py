"""The AI subsystem: optional, non-destructive analysis and suggestions.

Every analyzer here returns :class:`Suggestion` objects rather than mutating
the project (spec section 13: "AI suggestions must remain non-destructive
recommendations unless explicitly accepted by the editor"). Callers (the API
layer, a UI) decide whether to accept or reject each one.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class Suggestion:
    kind: str  # e.g. "replace_clip", "scene_cut", "highlight", "colour_match"
    summary: str
    reason: str
    confidence: float  # in [0, 1]
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: SuggestionStatus = SuggestionStatus.PENDING

    def accept(self) -> None:
        self.status = SuggestionStatus.ACCEPTED

    def reject(self) -> None:
        self.status = SuggestionStatus.REJECTED
