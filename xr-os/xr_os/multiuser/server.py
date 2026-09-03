"""FastAPI + WebSocket shared-world server: the prototype networking layer for multi-user XR."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from xr_os.multiuser.protocol import Envelope, MessageType


class Room:
    """One shared-world session: connected sockets plus the latest known state of everyone/everything in it."""

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.connections: dict[str, WebSocket] = {}
        self.users: dict[str, dict] = {}
        self.objects: dict[str, dict] = {}
        self.anchors: dict[str, dict] = {}

    def snapshot(self) -> dict:
        return {"users": self.users, "objects": self.objects, "anchors": self.anchors}


class SharedWorldServer:
    """Owns all active rooms and routes messages between their connected clients."""

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def _room(self, room_id: str) -> Room:
        return self.rooms.setdefault(room_id, Room(room_id))

    async def connect(self, room_id: str, user_id: str, websocket: WebSocket) -> Room:
        await websocket.accept()
        room = self._room(room_id)
        room.connections[user_id] = websocket
        await websocket.send_text(Envelope.make(MessageType.WELCOME, user_id=user_id, room_id=room_id).model_dump_json())
        await websocket.send_text(Envelope.make(MessageType.ROSTER, room_id=room_id, payload=room.snapshot()).model_dump_json())
        await self.broadcast(room_id, Envelope.make(MessageType.JOIN, user_id=user_id, room_id=room_id), exclude_user_id=user_id)
        return room

    async def disconnect(self, room_id: str, user_id: str) -> None:
        room = self.rooms.get(room_id)
        if room is None:
            return
        room.connections.pop(user_id, None)
        room.users.pop(user_id, None)
        await self.broadcast(room_id, Envelope.make(MessageType.LEAVE, user_id=user_id, room_id=room_id))
        if not room.connections:
            self.rooms.pop(room_id, None)

    async def handle_message(self, room_id: str, user_id: str, envelope: Envelope) -> None:
        room = self._room(room_id)
        if envelope.type == MessageType.PING:
            websocket = room.connections.get(user_id)
            if websocket is not None:
                await websocket.send_text(Envelope.make(MessageType.PONG, user_id=user_id, room_id=room_id).model_dump_json())
            return
        if envelope.type == MessageType.USER_STATE:
            room.users[user_id] = envelope.payload
        elif envelope.type == MessageType.OBJECT_SYNC:
            object_id = envelope.payload.get("object_id")
            if object_id:
                room.objects[object_id] = envelope.payload
        elif envelope.type == MessageType.ANCHOR_SYNC:
            anchor_id = envelope.payload.get("anchor_id")
            if anchor_id:
                room.anchors[anchor_id] = envelope.payload
        await self.broadcast(room_id, envelope, exclude_user_id=user_id)

    async def broadcast(self, room_id: str, envelope: Envelope, exclude_user_id: str | None = None) -> None:
        room = self.rooms.get(room_id)
        if room is None:
            return
        message = envelope.model_dump_json()
        for uid, websocket in list(room.connections.items()):
            if uid == exclude_user_id:
                continue
            try:
                await websocket.send_text(message)
            except Exception:
                room.connections.pop(uid, None)


def create_app(server: SharedWorldServer | None = None) -> FastAPI:
    server = server or SharedWorldServer()
    app = FastAPI(title="XR-OS Shared World")
    app.state.shared_world_server = server

    @app.websocket("/ws/{room_id}/{user_id}")
    async def ws_endpoint(websocket: WebSocket, room_id: str, user_id: str) -> None:
        await server.connect(room_id, user_id, websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                envelope = Envelope.model_validate_json(raw)
                await server.handle_message(room_id, user_id, envelope)
        except WebSocketDisconnect:
            await server.disconnect(room_id, user_id)

    @app.get("/rooms")
    def list_rooms() -> dict:
        return {room_id: {"user_count": len(room.connections)} for room_id, room in server.rooms.items()}

    return app
