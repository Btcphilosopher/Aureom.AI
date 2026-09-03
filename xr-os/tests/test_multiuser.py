"""Networking tests for the shared-world WebSocket protocol/server (via FastAPI's synchronous TestClient)."""

import pytest
from fastapi.testclient import TestClient

from xr_os.multiuser.protocol import Envelope, MessageType, ObjectSync, UserState
from xr_os.multiuser.server import SharedWorldServer, create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SharedWorldServer()))


def test_join_sends_welcome_and_roster(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as ws:
        welcome = ws.receive_json()
        roster = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["user_id"] == "alice"
        assert roster["type"] == "roster"
        assert roster["payload"] == {"users": {}, "objects": {}, "anchors": {}}


def test_second_user_join_is_broadcast_to_first(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice:
        alice.receive_json()  # welcome
        alice.receive_json()  # roster
        with client.websocket_connect("/ws/room1/bob") as bob:
            bob.receive_json()
            bob.receive_json()
            joined = alice.receive_json()
            assert joined["type"] == "join"
            assert joined["user_id"] == "bob"


def test_user_state_is_broadcast_and_stored_for_roster(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice, client.websocket_connect("/ws/room1/bob") as bob:
        alice.receive_json()
        alice.receive_json()
        bob.receive_json()
        bob.receive_json()
        alice.receive_json()  # bob's JOIN broadcast to alice

        state = UserState(user_id="bob", head_position=(1.0, 1.6, -2.0))
        bob.send_text(Envelope.make(MessageType.USER_STATE, user_id="bob", room_id="room1", payload=state).model_dump_json())

        received = alice.receive_json()
        assert received["type"] == "user_state"
        assert received["payload"]["head_position"] == [1.0, 1.6, -2.0]

        # a third user joining now (while bob is still connected) sees his state in their roster catch-up
        with client.websocket_connect("/ws/room1/carol") as carol:
            carol.receive_json()  # welcome
            roster = carol.receive_json()
            assert "bob" in roster["payload"]["users"]


def test_object_sync_updates_room_state(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice:
        alice.receive_json()
        alice.receive_json()
        obj = ObjectSync(object_id="cube1", position=(0, 1, -1), owner_id="alice")
        alice.send_text(Envelope.make(MessageType.OBJECT_SYNC, user_id="alice", room_id="room1", payload=obj).model_dump_json())

        with client.websocket_connect("/ws/room1/bob") as bob:
            bob.receive_json()
            roster = bob.receive_json()
            assert "cube1" in roster["payload"]["objects"]


def test_ping_receives_pong(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice:
        alice.receive_json()
        alice.receive_json()
        alice.send_text(Envelope.make(MessageType.PING, user_id="alice", room_id="room1").model_dump_json())
        pong = alice.receive_json()
        assert pong["type"] == "pong"


def test_leave_broadcasts_to_remaining_users(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice:
        alice.receive_json()
        alice.receive_json()
        with client.websocket_connect("/ws/room1/bob") as bob:
            bob.receive_json()
            bob.receive_json()
            alice.receive_json()  # bob's join
        left = alice.receive_json()
        assert left["type"] == "leave"
        assert left["user_id"] == "bob"


def test_rooms_endpoint_reports_user_count(client: TestClient):
    with client.websocket_connect("/ws/room1/alice") as alice:
        alice.receive_json()
        alice.receive_json()
        response = client.get("/rooms")
        assert response.json()["room1"]["user_count"] == 1
