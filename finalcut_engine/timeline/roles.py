"""Editing roles: how clips are categorised for organisation, mixing, and export.

Roles let the audio mixer, the export panel ("export just the dialogue stem")
and the timeline's visual grouping all agree on one taxonomy, with optional
sub-roles (``"Dialogue.Interview"``) as in Final Cut Pro.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VideoRole(str, Enum):
    VIDEO = "Video"
    TITLES = "Titles"
    GENERATORS = "Generators"


class AudioRole(str, Enum):
    DIALOGUE = "Dialogue"
    MUSIC = "Music"
    EFFECTS = "Effects"
    AMBIENCE = "Ambience"


@dataclass(frozen=True)
class Role:
    """A role, optionally qualified with a sub-role, e.g. ``Dialogue.Interview``."""

    name: str
    subrole: str | None = None

    def __str__(self) -> str:
        return f"{self.name}.{self.subrole}" if self.subrole else self.name

    @classmethod
    def parse(cls, text: str) -> "Role":
        if "." in text:
            name, sub = text.split(".", 1)
            return cls(name, sub)
        return cls(text)

    def matches(self, other: "Role") -> bool:
        """A bare role (no sub-role) matches all of its sub-roles."""
        if self.subrole is None:
            return self.name == other.name
        return self.name == other.name and self.subrole == other.subrole


DEFAULT_VIDEO_ROLE = Role(VideoRole.VIDEO.value)
DEFAULT_DIALOGUE_ROLE = Role(AudioRole.DIALOGUE.value)
DEFAULT_MUSIC_ROLE = Role(AudioRole.MUSIC.value)
DEFAULT_EFFECTS_ROLE = Role(AudioRole.EFFECTS.value)
