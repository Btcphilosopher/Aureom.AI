"""Async WebSocket client for connecting an XR-OS session to a shared-world server."""

from __future__ import annotations

from typing import AsyncIterator, Callable

import websockets

from xr_os.multiuser.protocol import AnchorSync, Envelope, MessageType, ObjectSync, UserState


class SharedWorldClient:
    """Thin async client: connect, send state/objects/input, and iterate incoming messages."""

    def __init__(self, url: str, room_id: str, user_id: str) -> None:
        self.base_url = url.rstrip("/")
        self.room_id = room_id
        self.user_id = user_id
        self._ws: websockets.WebSocketClientProtocol | None = None

    @property
    def uri(self) -> str:
        return f"{self.base_url}/ws/{self.room_id}/{self.user_id}"

    async def connect(self) -> None:
        self._ws = await websockets.connect(self.uri)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _send(self, envelope: Envelope) -> None:
        if self._ws is None:
            raise RuntimeError("not connected: call connect() first")
        await self._ws.send(envelope.model_dump_json())

    async def send_user_state(self, state: UserState) -> None:
        await self._send(Envelope.make(MessageType.USER_STATE, user_id=self.user_id, room_id=self.room_id, payload=state))

    async def send_object_sync(self, obj: ObjectSync) -> None:
        await self._send(Envelope.make(MessageType.OBJECT_SYNC, user_id=self.user_id, room_id=self.room_id, payload=obj))

    async def send_anchor_sync(self, anchor: AnchorSync) -> None:
        await self._send(Envelope.make(MessageType.ANCHOR_SYNC, user_id=self.user_id, room_id=self.room_id, payload=anchor))

    async def send_input_event(self, payload: dict) -> None:
        await self._send(Envelope.make(MessageType.INPUT_EVENT, user_id=self.user_id, room_id=self.room_id, payload=payload))

    async def send_chat(self, text: str) -> None:
        await self._send(Envelope.make(MessageType.CHAT, user_id=self.user_id, room_id=self.room_id, payload={"text": text}))

    async def messages(self) -> AsyncIterator[Envelope]:
        if self._ws is None:
            raise RuntimeError("not connected: call connect() first")
        async for raw in self._ws:
            yield Envelope.model_validate_json(raw)

    async def run(self, on_message: Callable[[Envelope], None]) -> None:
        """Convenience loop: dispatch every incoming envelope to a synchronous callback."""
        async for envelope in self.messages():
            on_message(envelope)
