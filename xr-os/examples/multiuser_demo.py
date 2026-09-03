"""
Shared-world multi-user demo: starts the WebSocket server in-process and
connects two clients that sync head pose to each other.

    python examples/multiuser_demo.py
"""

import asyncio
import threading

import uvicorn

from xr_os.multiuser.client import SharedWorldClient
from xr_os.multiuser.protocol import Envelope, UserState
from xr_os.multiuser.server import create_app

HOST, PORT = "127.0.0.1", 8756


def _run_server() -> None:
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")


async def _run_clients() -> None:
    alice = SharedWorldClient(f"ws://{HOST}:{PORT}", room_id="demo-room", user_id="alice")
    bob = SharedWorldClient(f"ws://{HOST}:{PORT}", room_id="demo-room", user_id="bob")
    await alice.connect()
    await bob.connect()

    async def print_bob_updates() -> None:
        async for envelope in bob.messages():
            if envelope.type.value == "user_state":
                print(f"[bob] saw {envelope.user_id} at {envelope.payload['head_position']}")
                return

    listener = asyncio.create_task(print_bob_updates())
    await alice.send_user_state(UserState(user_id="alice", head_position=(1.0, 1.6, -2.0)))
    await listener

    await alice.close()
    await bob.close()


def main() -> None:
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    import time

    time.sleep(1.0)  # let the server bind before clients connect
    asyncio.run(_run_clients())


if __name__ == "__main__":
    main()
