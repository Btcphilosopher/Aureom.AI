"""
A fuller demo: run the deterministic simulator (virtual headset + hands +
room), watch the spatial map / tracking / physics come alive, place a
grabbable virtual object, and print the diagnostic dashboard.

    python examples/simulated_room_demo.py
"""

from xr_os.core.math3d import Vector3
from xr_os.dashboard.cli_dashboard import print_dashboard
from xr_os.physics.engine import RigidBody
from xr_os.runtime.app import XRWorld
from xr_os.simulation.sim_env import SimulatedXREnvironment
from xr_os.tracking.types import TrackedTarget
from xr_os.ui.elements import SpatialPanel


def main() -> None:
    world = XRWorld()
    env = SimulatedXREnvironment(services=world.services)

    # a virtual ball sitting on the (simulated) floor, ready to be grabbed
    ball = world.services.physics.add_body(RigidBody(position=Vector3(0.3, 1.0, -0.3), radius=0.08))

    panel = SpatialPanel(position=(0, 1.2, -1.5), size=(1.0, 0.4), name="hud")
    world.add(panel)

    for step in range(1, 271):  # ~3 seconds at 90Hz
        env.step(1 / 90)
        world.tick(1 / 90)
        if step % 90 == 0:
            head = world.services.tracking.get_pose(TrackedTarget.HEAD)
            print(f"t={env.time:.2f}s head={tuple(round(c, 2) for c in head.position)} ball_y={ball.position.y:.2f}")

    print()
    print_dashboard(world)


if __name__ == "__main__":
    main()
