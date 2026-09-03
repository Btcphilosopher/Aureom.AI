"""Wire protocol for the shared-world WebSocket prototype network layer."""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    JOIN = "join"
    LEAVE = "leave"
    WELCOME = "welcome"  # server -> new client: assigns them their id
    ROSTER = "roster"  # server -> new client: catch-up snapshot of current room state
    USER_STATE = "user_state"  # head + hand pose sync
    OBJECT_SYNC = "object_sync"  # shared virtual object transform + ownership
    INPUT_EVENT = "input_event"  # forwarded gesture/voice/UI input event
    ANCHOR_SYNC = "anchor_sync"  # shared spatial anchor
    CHAT = "chat"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


class UserState(BaseModel):
    user_id: str
    head_position: tuple[float, float, float]
    head_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    left_hand_position: tuple[float, float, float] | None = None
    right_hand_position: tuple[float, float, float] | None = None
    timestamp: float = Field(default_factory=time.time)


class ObjectSync(BaseModel):
    object_id: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    owner_id: str | None = None
    timestamp: float = Field(default_factory=time.time)


class AnchorSync(BaseModel):
    anchor_id: str
    anchor_type: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    timestamp: float = Field(default_factory=time.time)


class Envelope(BaseModel):
    """Every message on the wire, regardless of payload kind."""

    type: MessageType
    user_id: str | None = None
    room_id: str | None = None
    payload: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    @classmethod
    def make(cls, type: MessageType, user_id: str | None = None, room_id: str | None = None, payload: BaseModel | dict | None = None) -> "Envelope":
        if isinstance(payload, BaseModel):
            payload = payload.model_dump()
        return cls(type=type, user_id=user_id, room_id=room_id, payload=payload or {})
